from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import BackupManifest, utc_now
from llm_manager.domain.serialization import to_primitive

from .backup import _atomic_write, _manifest_hash
from .backup_reconciliation import (
    BackupCopyReconciliation,
    CopyPresence,
    DualCopyDeletionReconciler,
    DualCopyState,
)


MAX_DELETION_RESULT_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")


class CopyDeleteOutcome(StrEnum):
    DELETED = "deleted"
    ALREADY_ABSENT = "already_absent"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BackupDeletionRequest:
    schema_version: str
    request_id: str
    backup_id: str
    host_id: str
    host_fingerprint: str
    manifest_hash: str
    created_at: datetime
    expires_at: datetime
    request_hash: str = ""

    def with_hash(self) -> "BackupDeletionRequest":
        value = replace(self, request_hash="")
        return replace(value, request_hash=hashlib.sha256(_bytes(value)).hexdigest())


@dataclass(frozen=True, slots=True)
class BackupDeletionResult:
    schema_version: str
    request_id: str
    request_hash: str
    backup_id: str
    host_id: str
    host_fingerprint: str
    manifest_hash: str
    remote_outcome: CopyDeleteOutcome
    local_outcome: CopyDeleteOutcome
    remote_error: str | None
    local_error: str | None
    local_presence: CopyPresence
    remote_presence: CopyPresence
    state: DualCopyState
    requires_attention: bool
    completed_at: datetime
    result_hash: str = ""

    def with_hash(self) -> "BackupDeletionResult":
        value = replace(self, result_hash="")
        return replace(value, result_hash=hashlib.sha256(_bytes(value)).hexdigest())


class BackupDeletePort(Protocol):
    def delete(self, manifest: BackupManifest, cancellation: CancellationToken) -> None: ...


class BackupDeletionCleanupPort(Protocol):
    def cleanup(self, request: BackupDeletionRequest, manifest: BackupManifest,
                cancellation: CancellationToken) -> None: ...

    def cleanup_pending(self, request: BackupDeletionRequest,
                        manifest: BackupManifest) -> bool: ...


class BackupManifestEvidencePort(Protocol):
    def save(
        self, request: BackupDeletionRequest, manifest: BackupManifest
    ) -> BackupManifest: ...


@dataclass(frozen=True, slots=True)
class BackupDeletionView:
    result: BackupDeletionResult
    staging_cleanup_pending: bool


class BackupDeletionResultStore:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe backup deletion result root")

    def save(self, result: BackupDeletionResult) -> BackupDeletionResult:
        _validate_result(result)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._root_metadata()
        path = self._path(result.request_id)
        if path.exists() or path.is_symlink():
            raise AdapterError("deletion_result_exists", "deletion result is immutable")
        _atomic_write(path, _bytes(result), 0o600)
        return self.load(result.request_id)

    def load(self, request_id: str) -> BackupDeletionResult:
        path = self._path(request_id)
        self._root_metadata()
        if path.is_symlink() or not path.is_file():
            raise AdapterError("deletion_result_not_found", "deletion result is missing")
        metadata = path.stat(follow_symlinks=False)
        if (
            stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_size > MAX_DELETION_RESULT_BYTES
        ):
            raise AdapterError("unsafe_deletion_result", "deletion result metadata is unsafe")
        content = path.read_bytes()
        result = _decode_result(content)
        if content != _bytes(result):
            raise AdapterError("invalid_deletion_result", "deletion result is not canonical")
        _validate_result(result)
        return result

    def list_for_host(
        self, host_id: str, host_fingerprint: str
    ) -> tuple[BackupDeletionResult, ...]:
        if not self.root.exists() and not self.root.is_symlink():
            return ()
        self._root_metadata()
        results = []
        for path in self.root.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise AdapterError("unsafe_deletion_result", "unexpected deletion result entry")
            result = self.load(path.stem)
            if result.host_id == host_id:
                if result.host_fingerprint != host_fingerprint:
                    raise AdapterError("deletion_result_binding_mismatch", "host fingerprint changed")
                results.append(result)
        return tuple(sorted(results, key=lambda item: item.completed_at, reverse=True))

    def _path(self, request_id: str) -> Path:
        if not _IDENTIFIER.fullmatch(request_id):
            raise AdapterError("invalid_deletion_identity", "deletion request ID is invalid")
        return self.root / f"{request_id}.json"

    def _root_metadata(self) -> None:
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_deletion_result", "deletion result root is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError("unsafe_deletion_result", "deletion result root metadata is unsafe")


class CoordinatedBackupDeletion:
    """Delete remote then local, recording every outcome without compensating mutation."""

    def __init__(
        self,
        local: BackupDeletePort,
        remote: BackupDeletePort,
        reconciler: DualCopyDeletionReconciler,
        results: BackupDeletionResultStore,
        cleanup: BackupDeletionCleanupPort | None = None,
        manifest_evidence: BackupManifestEvidencePort | None = None,
        *,
        clock=utc_now,
    ) -> None:
        self.local = local
        self.remote = remote
        self.reconciler = reconciler
        self.results = results
        self.cleanup = cleanup
        self.manifest_evidence = manifest_evidence
        self.clock = clock

    def delete(
        self,
        request: BackupDeletionRequest,
        manifest: BackupManifest,
        cancellation: CancellationToken,
    ) -> BackupDeletionResult:
        now = self.clock()
        _validate_request(request, manifest, now)
        if cancellation.cancelled:
            raise OperationCancelled("backup deletion cancelled")
        if self.manifest_evidence is not None:
            self.manifest_evidence.save(request, manifest)
        if cancellation.cancelled:
            raise OperationCancelled("backup deletion cancelled")
        remote_outcome, remote_error = self._delete_copy(
            self.remote, manifest, cancellation, remote=True
        )
        local_outcome = CopyDeleteOutcome.NOT_ATTEMPTED
        local_error = None
        if remote_outcome in {CopyDeleteOutcome.DELETED, CopyDeleteOutcome.ALREADY_ABSENT}:
            if cancellation.cancelled:
                local_error = "cancelled"
            else:
                local_outcome, local_error = self._delete_copy(
                    self.local, manifest, cancellation, remote=False
                )
        reconciliation = self._reconcile(manifest, cancellation)
        attention = (
            reconciliation.requires_attention
            or remote_outcome in {CopyDeleteOutcome.FAILED, CopyDeleteOutcome.UNKNOWN}
            or local_outcome in {
                CopyDeleteOutcome.FAILED,
                CopyDeleteOutcome.NOT_ATTEMPTED,
                CopyDeleteOutcome.UNKNOWN,
            }
        )
        result = BackupDeletionResult(
            "1.0", request.request_id, request.request_hash, request.backup_id,
            request.host_id, request.host_fingerprint, request.manifest_hash,
            remote_outcome, local_outcome, remote_error, local_error,
            reconciliation.local, reconciliation.remote, reconciliation.state,
            attention, self.clock(),
        ).with_hash()
        saved = self.results.save(result)
        if self.cleanup is not None and remote_outcome is not CopyDeleteOutcome.UNKNOWN:
            try:
                self.cleanup.cleanup(request, manifest, cancellation)
            except (AdapterError, OperationCancelled, OSError, ValueError):
                pass
        return saved

    @staticmethod
    def _delete_copy(port, manifest, cancellation, *, remote):
        try:
            port.delete(manifest, cancellation)
            return CopyDeleteOutcome.DELETED, None
        except OperationCancelled:
            return CopyDeleteOutcome.UNKNOWN, "cancelled"
        except AdapterError as error:
            absent = "remote_backup_not_found" if remote else "backup_not_found"
            if error.code == absent:
                return CopyDeleteOutcome.ALREADY_ABSENT, None
            return CopyDeleteOutcome.FAILED, error.code
        except (OSError, ValueError):
            return CopyDeleteOutcome.UNKNOWN, "delete_observation_failed"

    def _reconcile(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> BackupCopyReconciliation:
        if cancellation.cancelled:
            return BackupCopyReconciliation(
                manifest.backup_id, manifest.host_id, CopyPresence.UNKNOWN,
                CopyPresence.UNKNOWN, DualCopyState.UNKNOWN, True,
            )
        try:
            return self.reconciler.reconcile(manifest, cancellation)
        except (AdapterError, OSError, ValueError):
            return BackupCopyReconciliation(
                manifest.backup_id, manifest.host_id, CopyPresence.UNKNOWN,
                CopyPresence.UNKNOWN, DualCopyState.UNKNOWN, True,
            )


class BackupDeletionRecoveryService:
    """Reload immutable deletion state and retry only staging cleanup."""

    def __init__(self, results: BackupDeletionResultStore,
                 cleanup: BackupDeletionCleanupPort | None = None) -> None:
        self.results = results
        self.cleanup = cleanup

    def load(self, request: BackupDeletionRequest,
             manifest: BackupManifest) -> BackupDeletionView:
        _validate_request(request, manifest, request.created_at)
        result = self.results.load(request.request_id)
        if (
            result.request_hash, result.backup_id, result.host_id,
            result.host_fingerprint, result.manifest_hash,
        ) != (
            request.request_hash, request.backup_id, request.host_id,
            request.host_fingerprint, request.manifest_hash,
        ):
            raise AdapterError("deletion_result_binding_mismatch", "deletion result changed identity")
        pending = self.cleanup.cleanup_pending(request, manifest) if self.cleanup else False
        return BackupDeletionView(result, pending)

    def retry_cleanup(self, request: BackupDeletionRequest, manifest: BackupManifest,
                      cancellation: CancellationToken) -> BackupDeletionView:
        self.load(request, manifest)
        if self.cleanup is not None:
            self.cleanup.cleanup(request, manifest, cancellation)
        return self.load(request, manifest)


def new_backup_deletion_request(
    request_id: str, manifest: BackupManifest, *, now: datetime | None = None
) -> BackupDeletionRequest:
    current = now or utc_now()
    if manifest.host_fingerprint is None:
        raise AdapterError("invalid_deletion_identity", "host fingerprint is required")
    return BackupDeletionRequest(
        "1.0", request_id, manifest.backup_id, manifest.host_id,
        manifest.host_fingerprint, manifest.manifest_hash, current,
        current + timedelta(minutes=5),
    ).with_hash()


def validate_backup_deletion_result(result: BackupDeletionResult) -> None:
    """Validate immutable deletion evidence before presenting it outside its store."""
    _validate_result(result)


def _validate_request(
    request: BackupDeletionRequest, manifest: BackupManifest, now: datetime
) -> None:
    if (
        request.schema_version != "1.0"
        or not _IDENTIFIER.fullmatch(request.request_id)
        or not _IDENTIFIER.fullmatch(request.backup_id)
        or not _IDENTIFIER.fullmatch(request.host_id)
        or not _FINGERPRINT.fullmatch(request.host_fingerprint)
        or not _DIGEST.fullmatch(request.manifest_hash)
        or not _DIGEST.fullmatch(request.request_hash)
        or manifest.manifest_hash != _manifest_hash(replace(manifest, manifest_hash=""))
        or manifest.protected
        or (
            request.backup_id, request.host_id, request.host_fingerprint,
            request.manifest_hash,
        ) != (
            manifest.backup_id, manifest.host_id, manifest.host_fingerprint,
            manifest.manifest_hash,
        )
    ):
        raise AdapterError("invalid_deletion_identity", "deletion request binding is invalid")
    if any(item.tzinfo is None for item in (request.created_at, request.expires_at, now)):
        raise AdapterError("invalid_deletion_request", "deletion timestamps require timezone")
    if (
        request.created_at > now
        or now > request.expires_at
        or request.expires_at - request.created_at > timedelta(minutes=5)
        or request.request_hash
        != hashlib.sha256(_bytes(replace(request, request_hash=""))).hexdigest()
    ):
        raise AdapterError("expired_deletion_request", "deletion request is expired or modified")


def _validate_result(result: BackupDeletionResult) -> None:
    expected_state = _state(result.local_presence, result.remote_presence)
    if (
        result.schema_version != "1.0"
        or not _IDENTIFIER.fullmatch(result.request_id)
        or not _DIGEST.fullmatch(result.request_hash)
        or not _IDENTIFIER.fullmatch(result.backup_id)
        or not _IDENTIFIER.fullmatch(result.host_id)
        or not _FINGERPRINT.fullmatch(result.host_fingerprint)
        or not _DIGEST.fullmatch(result.manifest_hash)
        or result.completed_at.tzinfo is None
        or result.state is not expected_state
        or result.remote_outcome is CopyDeleteOutcome.NOT_ATTEMPTED
        or not _outcome_error_valid(result.remote_outcome, result.remote_error)
        or not _outcome_error_valid(result.local_outcome, result.local_error)
        or result.requires_attention
        != (
            result.state not in {DualCopyState.BOTH_AVAILABLE, DualCopyState.BOTH_DELETED}
            or result.remote_outcome in {CopyDeleteOutcome.FAILED, CopyDeleteOutcome.UNKNOWN}
            or result.local_outcome in {
                CopyDeleteOutcome.FAILED, CopyDeleteOutcome.NOT_ATTEMPTED,
                CopyDeleteOutcome.UNKNOWN,
            }
        )
    ):
        raise AdapterError("invalid_deletion_result", "deletion result is invalid")
    for error in (result.remote_error, result.local_error):
        if error is not None and not _IDENTIFIER.fullmatch(error):
            raise AdapterError("invalid_deletion_result", "deletion error code is invalid")
    expected = hashlib.sha256(_bytes(replace(result, result_hash=""))).hexdigest()
    if result.result_hash != expected:
        raise AdapterError("invalid_deletion_result", "deletion result integrity failed")


def _bytes(value: object) -> bytes:
    return json.dumps(
        to_primitive(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _decode_result(content: bytes) -> BackupDeletionResult:
    if len(content) > MAX_DELETION_RESULT_BYTES:
        raise AdapterError("invalid_deletion_result", "deletion result exceeds 1 MiB")
    try:
        value = json.loads(content.decode("utf-8"))
        expected = {
            "backup_id", "completed_at", "host_fingerprint", "host_id",
            "local_error", "local_outcome", "local_presence", "manifest_hash",
            "remote_error", "remote_outcome", "remote_presence", "request_hash",
            "request_id", "requires_attention", "result_hash", "schema_version", "state",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("fields")
        result = BackupDeletionResult(
            _text(value, "schema_version"), _text(value, "request_id"),
            _text(value, "request_hash"), _text(value, "backup_id"),
            _text(value, "host_id"), _text(value, "host_fingerprint"),
            _text(value, "manifest_hash"),
            CopyDeleteOutcome(_text(value, "remote_outcome")),
            CopyDeleteOutcome(_text(value, "local_outcome")),
            _optional(value, "remote_error"), _optional(value, "local_error"),
            CopyPresence(_text(value, "local_presence")),
            CopyPresence(_text(value, "remote_presence")),
            DualCopyState(_text(value, "state")),
            value["requires_attention"] if type(value["requires_attention"]) is bool else None,
            datetime.fromisoformat(_text(value, "completed_at")),
            _text(value, "result_hash"),
        )
        if type(result.requires_attention) is not bool:
            raise ValueError("requires_attention")
        return result
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise AdapterError("invalid_deletion_result", "deletion result is malformed") from error


def _text(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(key)
    return item


def _optional(value: dict[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise ValueError(key)
    return item


def _outcome_error_valid(outcome: CopyDeleteOutcome, error: str | None) -> bool:
    if outcome in {CopyDeleteOutcome.DELETED, CopyDeleteOutcome.ALREADY_ABSENT}:
        return error is None
    if outcome in {CopyDeleteOutcome.FAILED, CopyDeleteOutcome.UNKNOWN}:
        return error is not None
    return outcome is CopyDeleteOutcome.NOT_ATTEMPTED


def _state(local: CopyPresence, remote: CopyPresence) -> DualCopyState:
    if CopyPresence.UNKNOWN in {local, remote}:
        return DualCopyState.UNKNOWN
    if local is CopyPresence.PRESENT and remote is CopyPresence.PRESENT:
        return DualCopyState.BOTH_AVAILABLE
    if local is CopyPresence.PRESENT:
        return DualCopyState.LOCAL_ONLY
    if remote is CopyPresence.PRESENT:
        return DualCopyState.REMOTE_ONLY
    return DualCopyState.BOTH_DELETED
