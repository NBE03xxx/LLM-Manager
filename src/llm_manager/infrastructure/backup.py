from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import Severity, ValidationStatus
from llm_manager.domain.errors import InvariantViolation
from llm_manager.domain.models import (
    BackupItem,
    BackupManifest,
    EncryptionInfo,
    LocalizedMessage,
    ValidationResult,
    utc_now,
)
from llm_manager.domain.serialization import to_primitive
from llm_manager.domain.serialization import validate_schema_version
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher, MAX_ENVELOPE_BYTES

MAX_ITEM_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class BackupRestoreItem:
    target: str
    existed: bool
    content: bytes | None
    sha256: str | None
    mode: int | None
    uid: int | None
    gid: int | None


class LocalBackupStore:
    def __init__(self, root: Path, allowed_roots: tuple[Path, ...], cipher: AesGcmBackupCipher | None = None) -> None:
        self.root = root.resolve()
        self.allowed_roots = tuple(path.resolve() for path in allowed_roots)
        self._manifests: dict[tuple[str, str], BackupManifest] = {}
        self.cipher = cipher

    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest:
        _cancel(cancellation)
        if request.host_id != request.change_set.host_id:
            raise AdapterError("host_mismatch", "backup request and ChangeSet host differ")
        if not request.backup_id or Path(request.backup_id).name != request.backup_id:
            raise AdapterError("invalid_backup_id", "backup ID must be a single path component")
        backup_dir = self.root / _safe_component(request.host_id) / request.backup_id
        item_dir = backup_dir / "items"
        item_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        os.chmod(self.root, 0o700)
        os.chmod(backup_dir.parent, 0o700)
        os.chmod(backup_dir, 0o700)
        items: list[BackupItem] = []
        targets = tuple(dict.fromkeys(change.target for change in request.change_set.changes))
        try:
            for index, target_text in enumerate(targets):
                _cancel(cancellation)
                target = self._validated_target(target_text)
                if target.is_symlink():
                    raise AdapterError("symlink_rejected", f"backup target is a symlink: {target}")
                try:
                    stat = target.stat()
                except FileNotFoundError:
                    items.append(BackupItem(str(target), False, None, None, storage_location=str(backup_dir)))
                    continue
                if not target.is_file():
                    raise AdapterError("unsupported_target", f"backup target is not a regular file: {target}")
                if stat.st_size > MAX_ITEM_BYTES:
                    raise AdapterError("item_too_large", f"backup target exceeds 16 MiB: {target}")
                content = target.read_bytes()
                digest = hashlib.sha256(content).hexdigest()
                stored_content = self._encode_content(content, request.encryption, request.backup_id, request.host_fingerprint, str(target))
                content_name = f"{index:04d}-{digest}.{'enc' if request.encryption.enabled else 'bin'}"
                content_path = item_dir / content_name
                _atomic_write(content_path, stored_content, 0o600)
                items.append(
                    BackupItem(
                        target=str(target),
                        existed=True,
                        content_ref=f"items/{content_name}",
                        sha256=digest,
                        mode=stat.st_mode & 0o7777,
                        uid=stat.st_uid,
                        gid=stat.st_gid,
                        storage_location=str(backup_dir),
                    )
                )
            created = utc_now()
            manifest = BackupManifest(
                backup_id=request.backup_id,
                schema_version="1.0",
                plan_id=request.plan_id,
                change_set_hash=request.change_set.content_hash,
                host_id=request.host_id,
                host_fingerprint=request.host_fingerprint,
                items=tuple(items),
                manifest_hash="",
                storage_location=str(backup_dir),
                encryption=request.encryption,
                created_at=created,
                retention_expires_at=created + timedelta(days=30),
                complete=True,
            )
            manifest = replace(manifest, manifest_hash=_manifest_hash(manifest))
            _atomic_write(
                backup_dir / "manifest.json",
                json.dumps(to_primitive(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                ),
                0o600,
            )
            self._manifests[(manifest.host_id, manifest.backup_id)] = manifest
            return manifest
        except Exception:
            # Incomplete directories are deliberately left for forensic cleanup,
            # but never registered or returned as complete manifests.
            raise

    def verify(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[ValidationResult, ...]:
        _cancel(cancellation)
        results: list[ValidationResult] = []
        expected_manifest_hash = _manifest_hash(replace(manifest, manifest_hash=""))
        base = Path(manifest.storage_location).resolve()
        disk_manifest = base / "manifest.json"
        expected_bytes = _manifest_bytes(manifest)
        try:
            disk_bytes = disk_manifest.read_bytes()
        except OSError:
            disk_bytes = None
        manifest_ok = (
            manifest.complete
            and manifest.manifest_hash == expected_manifest_hash
            and disk_bytes == expected_bytes
            and disk_manifest.is_file()
            and not disk_manifest.is_symlink()
        )
        results.append(_result("backup.manifest", manifest_ok, expected_manifest_hash, manifest.manifest_hash))
        if not _within(base, self.root):
            results.append(_result("backup.location", False, str(self.root), str(base)))
            return tuple(results)
        for index, item in enumerate(manifest.items):
            _cancel(cancellation)
            if not item.existed:
                results.append(_result(f"backup.item.{index}", item.content_ref is None, None, item.content_ref))
                continue
            valid = False
            actual: str | None = None
            if item.content_ref and not Path(item.content_ref).is_absolute():
                content_path = (base / item.content_ref).resolve()
                if _within(content_path, base) and content_path.is_file() and not content_path.is_symlink():
                    try:
                        limit = MAX_ENVELOPE_BYTES if manifest.encryption.enabled else MAX_ITEM_BYTES
                        if content_path.stat().st_size > limit:
                            raise AdapterError("item_too_large", "stored backup item exceeds its format limit")
                        content = self._decode_content(content_path.read_bytes(), manifest.encryption, manifest.backup_id, manifest.host_fingerprint, item.target)
                        actual = hashlib.sha256(content).hexdigest()
                        valid = actual == item.sha256
                    except AdapterError:
                        valid = False
            results.append(_result(f"backup.item.{index}", valid, item.sha256, actual))
        return tuple(results)

    def restore(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[ValidationResult, ...]:
        verification = self.verify(manifest, cancellation)
        if any(result.status is not ValidationStatus.PASSED for result in verification):
            return verification
        results: list[ValidationResult] = []
        base = Path(manifest.storage_location).resolve()
        for index, item in reversed(tuple(enumerate(manifest.items))):
            _cancel(cancellation)
            try:
                target = self._validated_target(item.target)
                if target.is_symlink():
                    raise AdapterError("symlink_rejected", f"restore target is a symlink: {target}")
                if item.existed:
                    if item.content_ref is None:
                        raise AdapterError("invalid_manifest", "existing backup item has no content")
                    stored_content = (base / item.content_ref).read_bytes()
                    content = self._decode_content(stored_content, manifest.encryption, manifest.backup_id, manifest.host_fingerprint, item.target)
                    _atomic_write(target, content, item.mode or 0o600)
                    if item.uid is not None and item.gid is not None:
                        os.chown(target, item.uid, item.gid, follow_symlinks=False)
                elif target.exists():
                    target.unlink()
                    _fsync_directory(target.parent)
                results.append(_result(f"restore.item.{index}", True, item.sha256, item.sha256))
            except (OSError, AdapterError) as error:
                results.append(_result(f"restore.item.{index}", False, "restored", str(error)))
        return tuple(results)

    def restore_items(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[BackupRestoreItem, ...]:
        """Return verified plaintext needed by a declared privileged rollback."""
        verification = self.verify(manifest, cancellation)
        if not verification or any(result.status is not ValidationStatus.PASSED for result in verification):
            raise AdapterError("invalid_backup", "backup cannot be used for privileged rollback")
        base = Path(manifest.storage_location).resolve()
        restored: list[BackupRestoreItem] = []
        for item in reversed(manifest.items):
            _cancel(cancellation)
            content = None
            if item.existed:
                if item.content_ref is None:
                    raise AdapterError("invalid_manifest", "existing backup item has no content")
                stored = (base / item.content_ref).read_bytes()
                content = self._decode_content(
                    stored, manifest.encryption, manifest.backup_id, manifest.host_fingerprint, item.target
                )
                if hashlib.sha256(content).hexdigest() != item.sha256:
                    raise AdapterError("invalid_backup", "backup item hash changed after verification")
            restored.append(BackupRestoreItem(item.target, item.existed, content, item.sha256, item.mode, item.uid, item.gid))
        return tuple(restored)

    def list_manifests(self, host_id: str) -> tuple[BackupManifest, ...]:
        self._load_host_manifests(host_id)
        return tuple(
            sorted(
                (item for item in self._manifests.values() if item.host_id == host_id),
                key=lambda item: item.created_at,
                reverse=True,
            )
        )

    def set_protected(self, host_id: str, backup_id: str, protected: bool) -> BackupManifest:
        self._load_host_manifests(host_id)
        key = (host_id, backup_id)
        try:
            current = self._manifests[key]
        except KeyError as error:
            raise AdapterError("backup_not_found", "backup manifest was not found") from error
        updated = replace(current, protected=protected, manifest_hash="")
        updated = replace(updated, manifest_hash=_manifest_hash(updated))
        _atomic_write(Path(updated.storage_location) / "manifest.json", _manifest_bytes(updated), 0o600)
        self._manifests[key] = updated
        return updated

    def delete(self, manifest: BackupManifest, cancellation: CancellationToken) -> None:
        """Delete one explicitly selected, verified, unprotected local backup."""
        _cancel(cancellation)
        if manifest.protected:
            raise AdapterError("protected_backup", "protected backup cannot be deleted")
        if not Path(manifest.storage_location).exists():
            raise AdapterError("backup_not_found", "local backup was already absent")
        results = self.verify(manifest, cancellation)
        if not results or any(item.status is not ValidationStatus.PASSED for item in results):
            raise AdapterError("invalid_backup", "local backup must verify before deletion")
        directory = Path(manifest.storage_location).resolve()
        if not _within(directory, self.root):
            raise AdapterError("invalid_backup", "local backup is outside its store")
        _remove_backup_tree(directory)
        self._manifests.pop((manifest.host_id, manifest.backup_id), None)

    def prune(self, host_id: str, now: datetime | None = None, keep_generations: int = 10) -> tuple[str, ...]:
        """Remove expired/excess unprotected backups while retaining one recovery point."""
        current = now or utc_now()
        manifests = list(self.list_manifests(host_id))
        removable = [
            item for index, item in enumerate(manifests)
            if not item.protected
            and len(manifests) > 1
            and (index >= keep_generations or (item.retention_expires_at is not None and item.retention_expires_at <= current))
        ]
        removed: list[str] = []
        for item in reversed(removable):
            if len([value for value in manifests if value.backup_id not in removed]) <= 1:
                break
            directory = Path(item.storage_location).resolve()
            if not _within(directory, self.root):
                continue
            _remove_backup_tree(directory)
            self._manifests.pop((item.host_id, item.backup_id), None)
            removed.append(item.backup_id)
        return tuple(removed)

    def _validated_target(self, target_text: str) -> Path:
        target = Path(target_text)
        if not target.is_absolute():
            raise AdapterError("invalid_target", "backup target must be absolute")
        resolved_parent = target.parent.resolve()
        if not any(_within(resolved_parent, root) for root in self.allowed_roots):
            raise AdapterError("target_not_allowed", f"target is outside sandbox roots: {target}")
        return resolved_parent / target.name

    def _encode_content(self, content: bytes, encryption: EncryptionInfo, backup_id: str, host_fingerprint: str | None, target: str) -> bytes:
        if not encryption.enabled:
            return content
        if self.cipher is None:
            raise AdapterError("encryption_unavailable", "encrypted backup requires a key provider")
        return self.cipher.encrypt(
            content,
            backup_id=backup_id,
            host_fingerprint=host_fingerprint,
            target=target,
            key_reference=encryption.key_reference or "",
            key_scope=encryption.key_scope or "",
        )

    def _decode_content(self, content: bytes, encryption: EncryptionInfo, backup_id: str, host_fingerprint: str | None, target: str) -> bytes:
        if not encryption.enabled:
            return content
        if self.cipher is None:
            raise AdapterError("encryption_unavailable", "encrypted backup requires a key provider")
        return self.cipher.decrypt(
            content,
            backup_id=backup_id,
            host_fingerprint=host_fingerprint,
            target=target,
            expected_key_reference=encryption.key_reference or "",
            expected_key_scope=encryption.key_scope or "",
        )

    def _load_host_manifests(self, host_id: str) -> None:
        host_directory = self.root / _safe_component(host_id)
        if not host_directory.exists():
            return
        if host_directory.is_symlink() or not host_directory.is_dir():
            raise AdapterError("invalid_backup_store", "host backup location is unsafe")
        loaded: dict[tuple[str, str], BackupManifest] = {}
        for backup_directory in host_directory.iterdir():
            if backup_directory.is_symlink() or not backup_directory.is_dir():
                continue
            try:
                manifest = _read_manifest(backup_directory / "manifest.json", backup_directory, host_id)
            except AdapterError:
                continue
            loaded[(host_id, manifest.backup_id)] = manifest
        for key in tuple(self._manifests):
            if key[0] == host_id:
                self._manifests.pop(key)
        self._manifests.update(loaded)


def _manifest_hash(manifest: BackupManifest) -> str:
    primitive = to_primitive(replace(manifest, manifest_hash=""))
    encoded = json.dumps(primitive, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _manifest_bytes(manifest: BackupManifest) -> bytes:
    return json.dumps(to_primitive(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_manifest(path: Path, backup_directory: Path, expected_host_id: str) -> BackupManifest:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise AdapterError("invalid_manifest", "manifest file is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterError("invalid_manifest", "manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise AdapterError("invalid_manifest", "manifest root must be an object")
    try:
        schema_version = _text(value, "schema_version")
        validate_schema_version(schema_version)
        items_value = value["items"]
        encryption_value = value["encryption"]
        if not isinstance(items_value, list) or not isinstance(encryption_value, dict):
            raise ValueError("invalid nested manifest values")
        items = tuple(_backup_item(item) for item in items_value)
        encryption = EncryptionInfo(
            enabled=_boolean(encryption_value, "enabled"),
            scheme=_optional_text(encryption_value, "scheme"),
            envelope_version=_optional_integer(encryption_value, "envelope_version"),
            key_reference=_optional_text(encryption_value, "key_reference"),
            key_scope=_optional_text(encryption_value, "key_scope"),
        )
        manifest = BackupManifest(
            backup_id=_text(value, "backup_id"),
            schema_version=schema_version,
            plan_id=_text(value, "plan_id"),
            change_set_hash=_text(value, "change_set_hash"),
            host_id=_text(value, "host_id"),
            host_fingerprint=_optional_text(value, "host_fingerprint"),
            items=items,
            manifest_hash=_text(value, "manifest_hash"),
            storage_location=_text(value, "storage_location"),
            encryption=encryption,
            protected=_boolean(value, "protected"),
            created_at=_timestamp(value, "created_at"),
            retention_expires_at=_optional_timestamp(value, "retention_expires_at"),
            complete=_boolean(value, "complete"),
        )
    except (KeyError, TypeError, ValueError, InvariantViolation) as error:
        raise AdapterError("invalid_manifest", "manifest fields are invalid") from error
    if (
        manifest.host_id != expected_host_id
        or manifest.backup_id != backup_directory.name
        or Path(manifest.storage_location).resolve() != backup_directory.resolve()
        or not manifest.complete
        or _manifest_hash(replace(manifest, manifest_hash="")) != manifest.manifest_hash
        or _manifest_bytes(manifest) != path.read_bytes()
    ):
        raise AdapterError("invalid_manifest", "manifest identity or integrity check failed")
    return manifest


def _backup_item(value: object) -> BackupItem:
    if not isinstance(value, dict):
        raise ValueError("backup item must be an object")
    return BackupItem(
        target=_text(value, "target"),
        existed=_boolean(value, "existed"),
        content_ref=_optional_text(value, "content_ref"),
        sha256=_optional_text(value, "sha256"),
        mode=_optional_integer(value, "mode"),
        uid=_optional_integer(value, "uid"),
        gid=_optional_integer(value, "gid"),
        selinux_context=_optional_text(value, "selinux_context"),
        service_state=_optional_text(value, "service_state"),
        storage_location=_optional_text(value, "storage_location"),
    )


def _text(value: dict[str, object], key: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item:
        raise ValueError(f"{key} must be non-empty text")
    return item


def _optional_text(value: dict[str, object], key: str) -> str | None:
    item = value[key]
    if item is not None and not isinstance(item, str):
        raise ValueError(f"{key} must be text or null")
    return item


def _boolean(value: dict[str, object], key: str) -> bool:
    item = value[key]
    if type(item) is not bool:
        raise ValueError(f"{key} must be boolean")
    return item


def _optional_integer(value: dict[str, object], key: str) -> int | None:
    item = value[key]
    if item is not None and type(item) is not int:
        raise ValueError(f"{key} must be integer or null")
    return item


def _timestamp(value: dict[str, object], key: str) -> datetime:
    result = datetime.fromisoformat(_text(value, key))
    if result.tzinfo is None:
        raise ValueError(f"{key} must include a timezone")
    return result


def _optional_timestamp(value: dict[str, object], key: str) -> datetime | None:
    item = value[key]
    if item is None:
        return None
    if not isinstance(item, str):
        raise ValueError(f"{key} must be timestamp or null")
    result = datetime.fromisoformat(item)
    if result.tzinfo is None:
        raise ValueError(f"{key} must include a timezone")
    return result


def _safe_component(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_backup_tree(directory: Path) -> None:
    # The store creates a fixed two-level layout; reject links and unexpected directories.
    if directory.is_symlink() or not directory.is_dir():
        raise AdapterError("invalid_backup", f"unsafe backup directory: {directory}")
    allowed = {"items", "manifest.json"}
    if {item.name for item in directory.iterdir()} - allowed:
        raise AdapterError("invalid_backup", "unexpected backup entry prevents deletion")
    items = directory / "items"
    if items.exists():
        if items.is_symlink() or not items.is_dir():
            raise AdapterError("invalid_backup", f"unsafe item directory: {items}")
        for child in items.iterdir():
            if child.is_symlink() or not child.is_file():
                raise AdapterError("invalid_backup", f"unsafe backup item: {child}")
            child.unlink()
        items.rmdir()
    manifest = directory / "manifest.json"
    if manifest.exists():
        if manifest.is_symlink() or not manifest.is_file():
            raise AdapterError("invalid_backup", f"unsafe manifest: {manifest}")
        manifest.unlink()
    directory.rmdir()
    _fsync_directory(directory.parent)


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("backup operation cancelled")


def _result(check: str, passed: bool, expected: object, actual: object) -> ValidationResult:
    return ValidationResult(
        validation_id=check,
        scope="backup",
        check=check,
        status=ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
        expected=expected,  # type: ignore[arg-type]
        actual=actual,  # type: ignore[arg-type]
        severity=Severity.INFO if passed else Severity.HIGH,
        message=LocalizedMessage(f"validation.{check}.{'passed' if passed else 'failed'}"),
    )
