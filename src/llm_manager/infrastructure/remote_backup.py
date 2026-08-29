from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import Severity, ValidationStatus
from llm_manager.domain.models import BackupManifest, LocalizedMessage, ValidationResult

from .backup import BackupRestoreItem, _atomic_write, _safe_component, _within
from .backup_crypto import ALGORITHM, ENVELOPE_VERSION, AesGcmBackupCipher, MAX_ENVELOPE_BYTES


REMOTE_BACKUP_ROOT = "/var/lib/llm-manager/backups"


@dataclass(frozen=True, slots=True)
class RemoteRecoveryReceipt:
    schema_version: str
    backup_id: str
    plan_id: str
    change_set_hash: str
    host_id: str
    host_fingerprint: str
    local_manifest_hash: str
    storage_location: str
    scheme: str
    envelope_version: int
    key_reference: str
    key_scope: str
    item_hashes: tuple[tuple[str, str | None], ...]
    verified: bool
    receipt_hash: str = ""

    def with_hash(self) -> "RemoteRecoveryReceipt":
        return replace(self, receipt_hash=_receipt_hash(self))


@dataclass(frozen=True, slots=True)
class RemoteRetentionRecord:
    schema_version: str
    backup_id: str
    host_id: str
    receipt_hash: str
    created_at: datetime
    retention_expires_at: datetime
    protected: bool
    record_hash: str = ""

    def with_hash(self) -> "RemoteRetentionRecord":
        value = replace(self, record_hash="")
        return replace(value, record_hash=hashlib.sha256(_retention_bytes(value)).hexdigest())


class RemoteRecoveryCopyPort(Protocol):
    def create(
        self,
        manifest: BackupManifest,
        items: tuple[BackupRestoreItem, ...],
        cancellation: CancellationToken,
    ) -> RemoteRecoveryReceipt: ...

    def load(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> RemoteRecoveryReceipt: ...


class LocalBackupForRemoteCopy(Protocol):
    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest: ...
    def verify(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[ValidationResult, ...]: ...
    def restore_items(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[BackupRestoreItem, ...]: ...


class DualCopyPrivilegedBackupStore:
    """Keep the local backup authoritative and require a verified remote copy."""

    def __init__(self, local: LocalBackupForRemoteCopy, remote: RemoteRecoveryCopyPort) -> None:
        self.local = local
        self.remote = remote

    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest:
        manifest = self.local.create(request, cancellation)
        try:
            items = self.local.restore_items(manifest, cancellation)
            receipt = self.remote.create(manifest, items, cancellation)
            _validate_receipt(manifest, receipt)
        except (AdapterError, OSError, ValueError):
            # Preserve the local authoritative backup. verify() will fail closed
            # and prevent Apply when the remote copy is missing or invalid.
            return manifest
        return manifest

    def verify(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[ValidationResult, ...]:
        local_results = self.local.verify(manifest, cancellation)
        try:
            receipt = self.remote.load(manifest, cancellation)
            _validate_receipt(manifest, receipt)
            remote_result = _result(True, receipt.receipt_hash)
        except (AdapterError, OSError, ValueError) as error:
            remote_result = _result(False, getattr(error, "code", type(error).__name__))
        return local_results + (remote_result,)

    def restore_items(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[BackupRestoreItem, ...]:
        return self.local.restore_items(manifest, cancellation)


def _validate_receipt(manifest: BackupManifest, receipt: RemoteRecoveryReceipt) -> None:
    expected_items = tuple((item.target, item.sha256) for item in manifest.items)
    expected_location = remote_storage_location(manifest)
    if (
        receipt.schema_version != "1.0"
        or not receipt.verified
        or receipt.backup_id != manifest.backup_id
        or receipt.plan_id != manifest.plan_id
        or receipt.change_set_hash != manifest.change_set_hash
        or receipt.host_id != manifest.host_id
        or not manifest.host_fingerprint
        or receipt.host_fingerprint != manifest.host_fingerprint
        or receipt.local_manifest_hash != manifest.manifest_hash
        or receipt.storage_location != expected_location
        or receipt.scheme != ALGORITHM
        or receipt.envelope_version != ENVELOPE_VERSION
        or receipt.key_scope != "remote_root"
        or not receipt.key_reference
        or receipt.key_reference == manifest.encryption.key_reference
        or receipt.item_hashes != expected_items
        or receipt.receipt_hash != _receipt_hash(replace(receipt, receipt_hash=""))
    ):
        raise AdapterError(
            "invalid_remote_backup_receipt",
            "remote recovery copy is not bound to the local backup",
        )


def remote_storage_location(manifest: BackupManifest) -> str:
    if not manifest.backup_id or "/" in manifest.backup_id or manifest.backup_id in {".", ".."}:
        raise AdapterError("invalid_backup_id", "backup ID is not a safe path component")
    return f"{REMOTE_BACKUP_ROOT}/{_safe_component(manifest.host_id)}/{manifest.backup_id}"


def _receipt_hash(receipt: RemoteRecoveryReceipt) -> str:
    value = replace(receipt, receipt_hash="")
    encoded = json.dumps(
        {
            "backup_id": value.backup_id,
            "change_set_hash": value.change_set_hash,
            "host_fingerprint": value.host_fingerprint,
            "host_id": value.host_id,
            "item_hashes": value.item_hashes,
            "envelope_version": value.envelope_version,
            "key_reference": value.key_reference,
            "key_scope": value.key_scope,
            "local_manifest_hash": value.local_manifest_hash,
            "plan_id": value.plan_id,
            "receipt_hash": "",
            "schema_version": value.schema_version,
            "scheme": value.scheme,
            "storage_location": value.storage_location,
            "verified": value.verified,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RemoteRootRecoveryStore:
    """Root-side encrypted recovery store with an explicit sandbox override."""

    def __init__(
        self,
        root: Path,
        cipher: AesGcmBackupCipher,
        key_reference: str,
        *,
        sandbox: bool = False,
        effective_uid: int | None = None,
        owner_uid: int | None = None,
    ) -> None:
        if not key_reference:
            raise ValueError("remote recovery key reference is required")
        self.root = root.absolute()
        self.sandbox = sandbox
        self.effective_uid = os.geteuid() if effective_uid is None else effective_uid
        self.owner_uid = (os.getuid() if sandbox else 0) if owner_uid is None else owner_uid
        if not sandbox and self.root != Path(REMOTE_BACKUP_ROOT):
            raise ValueError("production remote recovery root is fixed")
        if not sandbox and self.effective_uid != 0:
            raise ValueError("production remote recovery store requires root")
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("sandbox remote recovery root is unsafe")
        if self.root.exists() and (
            not self.root.is_dir()
            or stat.S_IMODE(self.root.stat(follow_symlinks=False).st_mode) != 0o700
            or self.root.stat(follow_symlinks=False).st_uid != self.owner_uid
        ):
            raise ValueError("existing remote recovery root must be a private owned directory")
        self.cipher = cipher
        self.key_reference = key_reference

    def create(
        self,
        manifest: BackupManifest,
        items: tuple[BackupRestoreItem, ...],
        cancellation: CancellationToken,
    ) -> RemoteRecoveryReceipt:
        _cancel(cancellation)
        if not manifest.complete or not manifest.host_fingerprint:
            raise AdapterError("invalid_remote_backup", "complete fingerprint-bound manifest required")
        by_target = {item.target: item for item in items}
        if len(by_target) != len(items) or set(by_target) != {item.target for item in manifest.items}:
            raise AdapterError("invalid_remote_backup", "restore items do not match manifest")
        directory = self._directory(manifest)
        item_directory = directory / "items"
        item_directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        for path in (self.root, directory.parent, directory, item_directory):
            os.chmod(path, 0o700)
            self._verify_directory_metadata(path)
        for index, recorded in enumerate(manifest.items):
            _cancel(cancellation)
            item = by_target[recorded.target]
            if (item.existed, item.sha256) != (recorded.existed, recorded.sha256):
                raise AdapterError("invalid_remote_backup", "restore item identity changed")
            if not item.existed:
                if item.content is not None:
                    raise AdapterError("invalid_remote_backup", "absent item unexpectedly has content")
                continue
            if item.content is None or hashlib.sha256(item.content).hexdigest() != item.sha256:
                raise AdapterError("invalid_remote_backup", "restore item content hash is invalid")
            envelope = self.cipher.encrypt(
                item.content,
                backup_id=manifest.backup_id,
                host_fingerprint=manifest.host_fingerprint,
                target=item.target,
                key_reference=self.key_reference,
                key_scope="remote_root",
            )
            _atomic_write(item_directory / _item_name(index, item.sha256), envelope, 0o600)
        receipt = RemoteRecoveryReceipt(
            "1.0", manifest.backup_id, manifest.plan_id, manifest.change_set_hash,
            manifest.host_id, manifest.host_fingerprint, manifest.manifest_hash,
            remote_storage_location(manifest), ALGORITHM, ENVELOPE_VERSION,
            self.key_reference, "remote_root",
            tuple((item.target, item.sha256) for item in manifest.items), True,
        ).with_hash()
        self._verify_files(manifest, receipt, directory)
        _atomic_write(directory / "receipt.json", _receipt_bytes(receipt), 0o600)
        retention = RemoteRetentionRecord(
            "1.0", manifest.backup_id, manifest.host_id, receipt.receipt_hash,
            manifest.created_at,
            manifest.retention_expires_at or manifest.created_at + timedelta(days=30),
            manifest.protected,
        ).with_hash()
        _atomic_write(directory / "retention.json", _retention_bytes(retention), 0o600)
        self._verify_file_metadata(directory / "receipt.json", 1024 * 1024)
        self._verify_file_metadata(directory / "retention.json", 1024 * 1024)
        return receipt

    def load(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> RemoteRecoveryReceipt:
        _cancel(cancellation)
        directory = self._directory(manifest)
        path = directory / "receipt.json"
        if not self._safe_file(path, 1024 * 1024):
            raise AdapterError("remote_backup_not_found", "remote receipt is missing or unsafe")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            receipt = _decode_receipt(value)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_remote_backup_receipt", "remote receipt is malformed") from error
        if path.read_bytes() != _receipt_bytes(receipt):
            raise AdapterError("invalid_remote_backup_receipt", "remote receipt is not canonical")
        _validate_receipt(manifest, receipt)
        self._verify_files(manifest, receipt, directory)
        self._load_retention(directory, receipt)
        return receipt

    def set_protected(
        self, manifest: BackupManifest, protected: bool
    ) -> RemoteRetentionRecord:
        receipt = self.load(manifest, CancellationToken())
        directory = self._directory(manifest)
        current = self._load_retention(directory, receipt)
        updated = replace(current, protected=protected, record_hash="").with_hash()
        _atomic_write(directory / "retention.json", _retention_bytes(updated), 0o600)
        self._verify_file_metadata(directory / "retention.json", 1024 * 1024)
        return updated

    def delete(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> None:
        """Delete one explicitly selected, verified, unprotected remote copy."""
        _cancel(cancellation)
        receipt = self.load(manifest, cancellation)
        record = self._load_retention(self._directory(manifest), receipt)
        if manifest.protected or record.protected:
            raise AdapterError("protected_backup", "protected remote backup cannot be deleted")
        directory = self._directory(manifest)
        self._validate_backup_directory(directory)
        self._remove_backup_directory(directory)

    def list_retention(
        self,
        host_id: str,
        *,
        expected_fingerprint: str | None = None,
    ) -> tuple[RemoteRetentionRecord, ...]:
        host_root = self.root / _safe_component(host_id)
        if not host_root.exists():
            return ()
        if host_root.is_symlink() or not host_root.is_dir():
            raise AdapterError("invalid_remote_retention", "remote host backup root is unsafe")
        self._verify_directory_metadata(host_root)
        records: list[RemoteRetentionRecord] = []
        for directory in host_root.iterdir():
            if directory.is_symlink() or not directory.is_dir():
                raise AdapterError("invalid_remote_retention", "remote backup entry is unsafe")
            self._verify_directory_metadata(directory)
            receipt = self._load_receipt_unbound(directory)
            if (
                receipt.host_id != host_id
                or expected_fingerprint is not None
                and receipt.host_fingerprint != expected_fingerprint
            ):
                raise AdapterError(
                    "invalid_remote_retention", "remote receipt host identity is invalid"
                )
            record = self._load_retention(directory, receipt)
            if record.host_id != host_id or record.backup_id != directory.name:
                raise AdapterError("invalid_remote_retention", "remote retention identity is invalid")
            records.append(record)
        return tuple(sorted(records, key=lambda item: item.created_at, reverse=True))

    def prune(
        self,
        host_id: str,
        *,
        now: datetime,
        keep_generations: int = 10,
        expected_fingerprint: str | None = None,
    ) -> tuple[str, ...]:
        if now.tzinfo is None or keep_generations < 1:
            raise ValueError("remote retention requires timezone and at least one generation")
        records = self.list_retention(host_id, expected_fingerprint=expected_fingerprint)
        candidates = [
            item for index, item in enumerate(records)
            if not item.protected
            and (index >= keep_generations or item.retention_expires_at <= now)
        ]
        removable = candidates[: max(0, len(records) - 1)]
        directories = [self.root / _safe_component(host_id) / item.backup_id for item in removable]
        for directory in directories:
            self._validate_backup_directory(directory)
        removed: list[str] = []
        for item in sorted(removable, key=lambda value: value.created_at):
            self._remove_backup_directory(self.root / _safe_component(host_id) / item.backup_id)
            removed.append(item.backup_id)
        return tuple(removed)

    def _load_receipt_unbound(self, directory: Path) -> RemoteRecoveryReceipt:
        path = directory / "receipt.json"
        if not self._safe_file(path, 1024 * 1024):
            raise AdapterError("invalid_remote_retention", "remote receipt is missing or unsafe")
        return decode_remote_receipt(path.read_bytes())

    def _load_retention(
        self, directory: Path, receipt: RemoteRecoveryReceipt
    ) -> RemoteRetentionRecord:
        path = directory / "retention.json"
        if not self._safe_file(path, 1024 * 1024):
            raise AdapterError("invalid_remote_retention", "remote retention record is missing or unsafe")
        try:
            record = _decode_retention(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_remote_retention", "remote retention record is malformed") from error
        if path.read_bytes() != _retention_bytes(record):
            raise AdapterError("invalid_remote_retention", "remote retention record is not canonical")
        expected = hashlib.sha256(_retention_bytes(replace(record, record_hash=""))).hexdigest()
        if (
            record.record_hash != expected
            or record.backup_id != receipt.backup_id
            or record.host_id != receipt.host_id
            or record.receipt_hash != receipt.receipt_hash
            or record.created_at.tzinfo is None
            or record.retention_expires_at.tzinfo is None
            or record.retention_expires_at < record.created_at
        ):
            raise AdapterError("invalid_remote_retention", "remote retention binding is invalid")
        return record

    def _remove_backup_directory(self, directory: Path) -> None:
        self._validate_backup_directory(directory)
        items = directory / "items"
        for path in items.iterdir():
            path.unlink()
        items.rmdir()
        for name in ("receipt.json", "retention.json"):
            (directory / name).unlink()
        directory.rmdir()

    def _validate_backup_directory(self, directory: Path) -> None:
        try:
            self._verify_directory_metadata(directory)
        except AdapterError as error:
            raise AdapterError("unsafe_remote_prune", "remote backup directory is unsafe") from error
        allowed = {"items", "receipt.json", "retention.json"}
        if {entry.name for entry in directory.iterdir()} - allowed:
            raise AdapterError("unsafe_remote_prune", "unexpected remote backup entry prevents pruning")
        items = directory / "items"
        try:
            self._verify_directory_metadata(items)
        except AdapterError as error:
            raise AdapterError("unsafe_remote_prune", "remote item directory is unsafe") from error
        for path in items.iterdir():
            if not self._safe_file(path, MAX_ENVELOPE_BYTES):
                raise AdapterError("unsafe_remote_prune", "remote item entry is unsafe")
        for name in ("receipt.json", "retention.json"):
            path = directory / name
            if not self._safe_file(path, 1024 * 1024):
                raise AdapterError("unsafe_remote_prune", "remote metadata entry is unsafe")

    def _directory(self, manifest: BackupManifest) -> Path:
        remote_storage_location(manifest)
        if self.root.is_symlink():
            raise AdapterError("invalid_remote_backup", "remote backup root is a symlink")
        if self.root.exists():
            self._verify_directory_metadata(self.root)
        path = self.root / _safe_component(manifest.host_id) / manifest.backup_id
        if not _within(path.resolve(strict=False), self.root.resolve()):
            raise AdapterError("invalid_remote_backup", "remote backup path escaped root")
        current = self.root
        for part in path.relative_to(self.root).parts:
            current /= part
            if current.is_symlink():
                raise AdapterError("invalid_remote_backup", "remote backup path contains a symlink")
            if not current.exists():
                break
        return path

    def _verify_files(
        self, manifest: BackupManifest, receipt: RemoteRecoveryReceipt, directory: Path
    ) -> None:
        item_directory = directory / "items"
        for index, item in enumerate(manifest.items):
            if not item.existed:
                continue
            path = item_directory / _item_name(index, item.sha256)
            if not self._safe_file(path, MAX_ENVELOPE_BYTES):
                raise AdapterError("invalid_remote_backup", "remote item is missing or unsafe")
            plaintext = self.cipher.decrypt(
                path.read_bytes(), backup_id=manifest.backup_id,
                host_fingerprint=manifest.host_fingerprint, target=item.target,
                expected_key_reference=receipt.key_reference,
                expected_key_scope=receipt.key_scope,
            )
            if hashlib.sha256(plaintext).hexdigest() != item.sha256:
                raise AdapterError("invalid_remote_backup", "remote item hash does not match")

    def _safe_file(self, path: Path, max_bytes: int) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        metadata = path.stat(follow_symlinks=False)
        return (
            stat.S_IMODE(metadata.st_mode) == 0o600
            and metadata.st_uid == self.owner_uid
            and metadata.st_size <= max_bytes
        )

    def _verify_file_metadata(self, path: Path, max_bytes: int) -> None:
        if not self._safe_file(path, max_bytes):
            raise AdapterError("invalid_remote_backup", "remote backup file metadata is unsafe")

    def _verify_directory_metadata(self, path: Path) -> None:
        if path.is_symlink() or not path.is_dir():
            raise AdapterError("invalid_remote_backup", "remote backup directory is unsafe")
        metadata = path.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != self.owner_uid:
            raise AdapterError("invalid_remote_backup", "remote backup directory metadata is unsafe")


# Backward-compatible name for callers that explicitly pass sandbox=True.
SandboxRemoteRecoveryStore = RemoteRootRecoveryStore


def _receipt_bytes(receipt: RemoteRecoveryReceipt) -> bytes:
    value = {
        "backup_id": receipt.backup_id, "change_set_hash": receipt.change_set_hash,
        "envelope_version": receipt.envelope_version,
        "host_fingerprint": receipt.host_fingerprint, "host_id": receipt.host_id,
        "item_hashes": receipt.item_hashes, "key_reference": receipt.key_reference,
        "key_scope": receipt.key_scope, "local_manifest_hash": receipt.local_manifest_hash,
        "plan_id": receipt.plan_id, "receipt_hash": receipt.receipt_hash,
        "schema_version": receipt.schema_version, "scheme": receipt.scheme,
        "storage_location": receipt.storage_location, "verified": receipt.verified,
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _retention_bytes(record: RemoteRetentionRecord) -> bytes:
    value = {
        "backup_id": record.backup_id,
        "created_at": record.created_at.isoformat(),
        "host_id": record.host_id,
        "protected": record.protected,
        "receipt_hash": record.receipt_hash,
        "record_hash": record.record_hash,
        "retention_expires_at": record.retention_expires_at.isoformat(),
        "schema_version": record.schema_version,
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode_retention(value: object) -> RemoteRetentionRecord:
    expected = {
        "backup_id", "created_at", "host_id", "protected", "receipt_hash",
        "record_hash", "retention_expires_at", "schema_version",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("invalid retention fields")
    if type(value["protected"]) is not bool:
        raise ValueError("invalid retention protection")
    strings = {key: value[key] for key in expected if key != "protected"}
    if any(not isinstance(item, str) or not item for item in strings.values()):
        raise ValueError("invalid retention values")
    if value["schema_version"] != "1.0":
        raise ValueError("unsupported retention schema")
    return RemoteRetentionRecord(
        value["schema_version"], value["backup_id"], value["host_id"],
        value["receipt_hash"], datetime.fromisoformat(value["created_at"]),
        datetime.fromisoformat(value["retention_expires_at"]), value["protected"],
        value["record_hash"],
    )


def encode_remote_receipt(receipt: RemoteRecoveryReceipt) -> bytes:
    """Encode a validated receipt for transfer across the untrusted SSH boundary."""
    _validate_receipt_hash(receipt)
    return _receipt_bytes(receipt)


def decode_remote_receipt(content: bytes) -> RemoteRecoveryReceipt:
    """Decode only the canonical, hash-bound remote helper receipt schema."""
    if len(content) > 1024 * 1024:
        raise AdapterError("invalid_remote_backup_receipt", "remote receipt exceeds 1 MiB")
    try:
        receipt = _decode_receipt(json.loads(content.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AdapterError("invalid_remote_backup_receipt", "remote receipt is malformed") from error
    if content != _receipt_bytes(receipt):
        raise AdapterError("invalid_remote_backup_receipt", "remote receipt is not canonical")
    _validate_receipt_hash(receipt)
    return receipt


def _validate_receipt_hash(receipt: RemoteRecoveryReceipt) -> None:
    if receipt.receipt_hash != _receipt_hash(replace(receipt, receipt_hash="")):
        raise AdapterError("invalid_remote_backup_receipt", "remote receipt integrity check failed")


def _decode_receipt(value: object) -> RemoteRecoveryReceipt:
    if not isinstance(value, dict) or set(value) != {
        "backup_id", "change_set_hash", "envelope_version", "host_fingerprint", "host_id",
        "item_hashes", "key_reference", "key_scope", "local_manifest_hash", "plan_id",
        "receipt_hash", "schema_version", "scheme", "storage_location", "verified",
    }:
        raise ValueError("invalid receipt fields")
    hashes = value["item_hashes"]
    if not isinstance(hashes, list):
        raise ValueError("invalid item hashes")
    item_hashes = tuple((str(item[0]), item[1]) for item in hashes if isinstance(item, list) and len(item) == 2)
    if len(item_hashes) != len(hashes) or type(value["verified"]) is not bool or type(value["envelope_version"]) is not int:
        raise ValueError("invalid receipt values")
    strings = {key: value[key] for key in value if key not in {"item_hashes", "verified", "envelope_version"}}
    if any(not isinstance(item, str) for item in strings.values()):
        raise ValueError("invalid receipt strings")
    return RemoteRecoveryReceipt(
        value["schema_version"], value["backup_id"], value["plan_id"],
        value["change_set_hash"], value["host_id"], value["host_fingerprint"],
        value["local_manifest_hash"], value["storage_location"], value["scheme"],
        value["envelope_version"], value["key_reference"], value["key_scope"],
        item_hashes, value["verified"], value["receipt_hash"],
    )


def _item_name(index: int, digest: str | None) -> str:
    if digest is None or len(digest) != 64:
        raise AdapterError("invalid_remote_backup", "existing item digest is invalid")
    return f"{index:04d}-{digest}.enc"


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        from llm_manager.application.errors import OperationCancelled
        raise OperationCancelled("remote backup operation cancelled")


def _result(passed: bool, actual: str) -> ValidationResult:
    return ValidationResult(
        "backup.remote-copy",
        "backup",
        "backup.remote-copy",
        ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
        "verified",
        actual,
        Severity.INFO if passed else Severity.CRITICAL,
        LocalizedMessage("validation.backup.remote-copy"),
    )
