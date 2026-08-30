from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import ValidationStatus
from llm_manager.domain.models import BackupManifest
from llm_manager.domain.serialization import to_primitive

from .backup import _atomic_write, _fsync_directory


MAX_RECONCILIATION_RESULT_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")


class CopyPresence(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class DualCopyState(StrEnum):
    BOTH_AVAILABLE = "both_available"
    LOCAL_ONLY = "local_only"
    REMOTE_ONLY = "remote_only"
    BOTH_DELETED = "both_deleted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BackupCopyReconciliation:
    backup_id: str
    host_id: str
    local: CopyPresence
    remote: CopyPresence
    state: DualCopyState
    requires_attention: bool


@dataclass(frozen=True, slots=True)
class BackupReconciliationResult:
    schema_version: str
    reconciliation_id: str
    source_deletion_result_hash: str
    backup_id: str
    host_id: str
    host_fingerprint: str
    manifest_hash: str
    observed_at: datetime
    local: CopyPresence
    remote: CopyPresence
    state: DualCopyState
    requires_attention: bool
    result_hash: str = ""

    def with_hash(self) -> "BackupReconciliationResult":
        value = replace(self, result_hash="")
        return replace(value, result_hash=hashlib.sha256(_canonical(value)).hexdigest())


class BackupReconciliationResultStore:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe backup reconciliation result root")

    def save(self, result: BackupReconciliationResult) -> BackupReconciliationResult:
        _validate_result(result)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._root_metadata()
        path = self._path(result.reconciliation_id)
        if path.exists() or path.is_symlink():
            raise AdapterError("reconciliation_result_exists", "result is immutable")
        _atomic_write(path, _canonical(result), 0o600)
        return self.load(result.reconciliation_id)

    def load(self, reconciliation_id: str) -> BackupReconciliationResult:
        self._root_metadata()
        path = self._path(reconciliation_id)
        if path.is_symlink() or not path.is_file():
            raise AdapterError("reconciliation_result_not_found", "result is missing")
        metadata = path.stat(follow_symlinks=False)
        if (stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.getuid()
                or metadata.st_size > MAX_RECONCILIATION_RESULT_BYTES):
            raise AdapterError("unsafe_reconciliation_result", "result metadata is unsafe")
        content = path.read_bytes()
        result = _decode_result(content)
        if content != _canonical(result):
            raise AdapterError("invalid_reconciliation_result", "result is not canonical")
        _validate_result(result)
        return result

    def list_for_host(
        self, host_id: str, host_fingerprint: str
    ) -> tuple[BackupReconciliationResult, ...]:
        if not self.root.exists() and not self.root.is_symlink():
            return ()
        self._root_metadata()
        results = []
        for path in self.root.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise AdapterError("unsafe_reconciliation_result", "unexpected result entry")
            result = self.load(path.stem)
            if result.host_id == host_id:
                if result.host_fingerprint != host_fingerprint:
                    raise AdapterError("reconciliation_binding_mismatch", "fingerprint changed")
                results.append(result)
        return tuple(sorted(results, key=lambda item: item.observed_at, reverse=True))

    def list_for_deletion_result(
        self, source_result_hash: str, host_id: str, host_fingerprint: str,
    ) -> tuple[BackupReconciliationResult, ...]:
        if not _DIGEST.fullmatch(source_result_hash):
            raise AdapterError("invalid_reconciliation_result", "source hash is invalid")
        return tuple(
            result for result in self.list_for_host(host_id, host_fingerprint)
            if result.source_deletion_result_hash == source_result_hash
        )

    def delete(self, result: BackupReconciliationResult) -> None:
        current = self.load(result.reconciliation_id)
        if current != result:
            raise AdapterError("reconciliation_binding_mismatch", "result changed identity")
        self._path(result.reconciliation_id).unlink()
        _fsync_directory(self.root)

    def _path(self, reconciliation_id: str) -> Path:
        if not _IDENTIFIER.fullmatch(reconciliation_id):
            raise AdapterError("invalid_reconciliation_result", "result ID is invalid")
        return self.root / f"{reconciliation_id}.json"

    def _root_metadata(self) -> None:
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_reconciliation_result", "result root is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError("unsafe_reconciliation_result", "root metadata is unsafe")


class BackupCopyObserver(Protocol):
    def observe(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> CopyPresence: ...


class LocalBackupCopyObserver:
    def __init__(self, store) -> None:
        self.store = store

    def observe(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> CopyPresence:
        if cancellation.cancelled:
            raise OperationCancelled("backup copy reconciliation cancelled")
        location = Path(manifest.storage_location)
        if not location.exists():
            return CopyPresence.ABSENT
        try:
            results = self.store.verify(manifest, cancellation)
        except OperationCancelled:
            raise
        except (AdapterError, OSError, ValueError):
            return CopyPresence.UNKNOWN
        return (
            CopyPresence.PRESENT
            if results and all(item.status is ValidationStatus.PASSED for item in results)
            else CopyPresence.UNKNOWN
        )


class RemoteBackupCopyObserver:
    def __init__(self, store) -> None:
        self.store = store

    def observe(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> CopyPresence:
        if cancellation.cancelled:
            raise OperationCancelled("backup copy reconciliation cancelled")
        try:
            self.store.load(manifest, cancellation)
            return CopyPresence.PRESENT
        except OperationCancelled:
            raise
        except AdapterError as error:
            if error.code == "remote_backup_not_found":
                return CopyPresence.ABSENT
            return CopyPresence.UNKNOWN
        except (OSError, ValueError):
            return CopyPresence.UNKNOWN


class DualCopyDeletionReconciler:
    """Observe deletion outcomes without deleting, retrying, or repairing either copy."""

    def __init__(self, local: BackupCopyObserver, remote: BackupCopyObserver) -> None:
        self.local = local
        self.remote = remote

    def reconcile(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> BackupCopyReconciliation:
        if cancellation.cancelled:
            raise OperationCancelled("backup copy reconciliation cancelled")
        local = self.local.observe(manifest, cancellation)
        if cancellation.cancelled:
            raise OperationCancelled("backup copy reconciliation cancelled")
        remote = self.remote.observe(manifest, cancellation)
        state = _combined(local, remote)
        return BackupCopyReconciliation(
            manifest.backup_id,
            manifest.host_id,
            local,
            remote,
            state,
            state not in {DualCopyState.BOTH_AVAILABLE, DualCopyState.BOTH_DELETED},
        )


class BackupReconciliationRunner:
    """Persist a read-only observation bound to an immutable deletion result."""

    def __init__(self, reconciler: DualCopyDeletionReconciler,
                 results: BackupReconciliationResultStore, *, clock) -> None:
        self.reconciler = reconciler
        self.results = results
        self.clock = clock

    def reconcile(
        self, reconciliation_id: str, deletion_result,
        manifest: BackupManifest, cancellation: CancellationToken,
    ) -> BackupReconciliationResult:
        from .backup_deletion import validate_backup_deletion_result

        if not isinstance(reconciliation_id, str) or not _IDENTIFIER.fullmatch(
            reconciliation_id
        ):
            raise AdapterError("invalid_reconciliation_result", "result ID is invalid")
        validate_backup_deletion_result(deletion_result)
        if manifest.host_fingerprint is None or (
            deletion_result.backup_id, deletion_result.host_id,
            deletion_result.host_fingerprint, deletion_result.manifest_hash,
        ) != (
            manifest.backup_id, manifest.host_id,
            manifest.host_fingerprint, manifest.manifest_hash,
        ):
            raise AdapterError("reconciliation_binding_mismatch", "manifest changed identity")
        observed = self.reconciler.reconcile(manifest, cancellation)
        if (observed.backup_id, observed.host_id) != (
            manifest.backup_id, manifest.host_id,
        ):
            raise AdapterError("reconciliation_binding_mismatch", "observation changed identity")
        result = BackupReconciliationResult(
            "1.0", reconciliation_id, deletion_result.result_hash,
            manifest.backup_id, manifest.host_id, manifest.host_fingerprint,
            manifest.manifest_hash, self.clock(), observed.local, observed.remote,
            observed.state, observed.requires_attention,
        ).with_hash()
        return self.results.save(result)


def _combined(local: CopyPresence, remote: CopyPresence) -> DualCopyState:
    if CopyPresence.UNKNOWN in {local, remote}:
        return DualCopyState.UNKNOWN
    if local is CopyPresence.PRESENT and remote is CopyPresence.PRESENT:
        return DualCopyState.BOTH_AVAILABLE
    if local is CopyPresence.PRESENT:
        return DualCopyState.LOCAL_ONLY
    if remote is CopyPresence.PRESENT:
        return DualCopyState.REMOTE_ONLY
    return DualCopyState.BOTH_DELETED


def validate_backup_reconciliation_result(result: BackupReconciliationResult) -> None:
    _validate_result(result)


def _validate_result(result: BackupReconciliationResult) -> None:
    if (not isinstance(result.schema_version, str)
            or not isinstance(result.reconciliation_id, str)
            or not isinstance(result.source_deletion_result_hash, str)
            or not isinstance(result.backup_id, str)
            or not isinstance(result.host_id, str)
            or not isinstance(result.host_fingerprint, str)
            or not isinstance(result.manifest_hash, str)
            or not isinstance(result.observed_at, datetime)
            or not isinstance(result.local, CopyPresence)
            or not isinstance(result.remote, CopyPresence)
            or not isinstance(result.state, DualCopyState)
            or not isinstance(result.requires_attention, bool)
            or not isinstance(result.result_hash, str)
            or result.schema_version != "1.0"
            or not _IDENTIFIER.fullmatch(result.reconciliation_id)
            or not _IDENTIFIER.fullmatch(result.backup_id)
            or not _IDENTIFIER.fullmatch(result.host_id)
            or not _DIGEST.fullmatch(result.source_deletion_result_hash)
            or not _DIGEST.fullmatch(result.manifest_hash)
            or not _FINGERPRINT.fullmatch(result.host_fingerprint)
            or result.observed_at.tzinfo is None
            or result.state is not _combined(result.local, result.remote)
            or result.requires_attention != (
                result.state not in {DualCopyState.BOTH_AVAILABLE, DualCopyState.BOTH_DELETED}
            )):
        raise AdapterError("invalid_reconciliation_result", "result is invalid")
    expected = hashlib.sha256(_canonical(replace(result, result_hash=""))).hexdigest()
    if result.result_hash != expected:
        raise AdapterError("invalid_reconciliation_result", "result integrity failed")


def _canonical(value) -> bytes:
    return json.dumps(to_primitive(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _decode_result(content: bytes) -> BackupReconciliationResult:
    try:
        value = json.loads(content.decode("utf-8"))
        if set(value) != {
            "schema_version", "reconciliation_id", "source_deletion_result_hash",
            "backup_id", "host_id", "host_fingerprint", "manifest_hash",
            "observed_at", "local", "remote", "state", "requires_attention",
            "result_hash",
        }:
            raise ValueError("unexpected fields")
        return BackupReconciliationResult(
            value["schema_version"], value["reconciliation_id"],
            value["source_deletion_result_hash"], value["backup_id"],
            value["host_id"], value["host_fingerprint"], value["manifest_hash"],
            datetime.fromisoformat(value["observed_at"]), CopyPresence(value["local"]),
            CopyPresence(value["remote"]), DualCopyState(value["state"]),
            value["requires_attention"], value["result_hash"],
        )
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise AdapterError("invalid_reconciliation_result", "result is malformed") from error
