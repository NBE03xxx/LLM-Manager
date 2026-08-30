from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive

from .backup_evidence_retention import (
    BackupEvidenceRetentionExecution,
    BackupEvidenceRetentionExecutionStore,
    EvidenceRetentionExecutionState,
)
from .backup import _atomic_write


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")
MAX_EVIDENCE_RETENTION_CLEANUP_REQUEST_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class BackupEvidenceRetentionCleanupRequest:
    schema_version: str
    cleanup_id: str
    source_execution_hash: str
    source_request_hash: str
    backup_id: str
    host_id: str
    host_fingerprint: str
    remaining_kinds: tuple[str, ...]
    created_at: datetime
    expires_at: datetime
    request_hash: str = ""

    def with_hash(self) -> "BackupEvidenceRetentionCleanupRequest":
        value = replace(self, request_hash="")
        return replace(value, request_hash=hashlib.sha256(_bytes(value)).hexdigest())


class BackupEvidenceRetentionCleanupPort(Protocol):
    def resume(
        self,
        execution: BackupEvidenceRetentionExecution,
        request: BackupEvidenceRetentionCleanupRequest,
        cancellation: CancellationToken,
    ) -> object: ...


class BackupEvidenceRetentionCleanupRequestStore:
    """Persist an immutable cleanup request before any resumed deletion."""

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe evidence retention cleanup request root")

    def save(
        self, request: BackupEvidenceRetentionCleanupRequest,
    ) -> BackupEvidenceRetentionCleanupRequest:
        _validate_request(request, None)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._root_metadata()
        path = self._path(request.cleanup_id)
        if path.exists() or path.is_symlink():
            current = self.load(request.cleanup_id)
            if current != request:
                raise AdapterError(
                    "evidence_retention_cleanup_request_collision",
                    "cleanup identity was reused",
                )
            return current
        _atomic_write(path, _bytes(request), 0o600)
        return self.load(request.cleanup_id)

    def load(self, cleanup_id: str) -> BackupEvidenceRetentionCleanupRequest:
        self._root_metadata()
        path = self._path(cleanup_id)
        if path.is_symlink() or not path.is_file():
            raise AdapterError(
                "evidence_retention_cleanup_request_not_found",
                "cleanup request is missing",
            )
        metadata = path.stat(follow_symlinks=False)
        if (
            stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_size > MAX_EVIDENCE_RETENTION_CLEANUP_REQUEST_BYTES
        ):
            raise AdapterError(
                "unsafe_evidence_retention_cleanup_request",
                "cleanup request metadata is unsafe",
            )
        content = path.read_bytes()
        request = _decode_request(content)
        if content != _bytes(request):
            raise AdapterError(
                "invalid_evidence_retention_cleanup_request",
                "cleanup request is not canonical",
            )
        _validate_request(request, None)
        if request.cleanup_id != cleanup_id:
            raise AdapterError(
                "evidence_retention_cleanup_binding_mismatch",
                "cleanup filename changed identity",
            )
        return request

    def _path(self, cleanup_id: str) -> Path:
        if not isinstance(cleanup_id, str) or not _IDENTIFIER.fullmatch(cleanup_id):
            raise AdapterError(
                "invalid_evidence_retention_cleanup_request",
                "cleanup ID is invalid",
            )
        return self.root / f"{cleanup_id}.json"

    def _root_metadata(self) -> None:
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError(
                "unsafe_evidence_retention_cleanup_request",
                "cleanup request root is unsafe",
            )
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError(
                "unsafe_evidence_retention_cleanup_request",
                "cleanup request root metadata is unsafe",
            )


class BackupEvidenceRetentionCleanupService:
    """Authorize cleanup only from an explicit request bound to strict evidence."""

    def __init__(
        self,
        executions: BackupEvidenceRetentionExecutionStore,
        requests: BackupEvidenceRetentionCleanupRequestStore,
        cleanup: BackupEvidenceRetentionCleanupPort,
    ) -> None:
        self.executions = executions
        self.requests = requests
        self.cleanup = cleanup

    def execute(
        self,
        request: BackupEvidenceRetentionCleanupRequest,
        now: datetime,
        cancellation: CancellationToken,
    ) -> object:
        _validate_request(request, now)
        if cancellation.cancelled:
            raise OperationCancelled("evidence retention cleanup cancelled")
        executions = self.executions.list_for_host(
            request.host_id, request.host_fingerprint
        )
        source = next(
            (
                execution for execution in executions
                if execution.execution_hash == request.source_execution_hash
            ),
            None,
        )
        if source is None:
            raise AdapterError(
                "evidence_retention_cleanup_source_not_found",
                "source execution is missing",
            )
        if source.state is EvidenceRetentionExecutionState.COMPLETED:
            raise AdapterError(
                "evidence_retention_cleanup_not_required", "execution is complete"
            )
        if (
            source.request_hash != request.source_request_hash
            or source.backup_id != request.backup_id
            or source.host_id != request.host_id
            or source.host_fingerprint != request.host_fingerprint
            or source.remaining_kinds != request.remaining_kinds
        ):
            raise AdapterError(
                "evidence_retention_cleanup_binding_mismatch",
                "cleanup request changed execution identity",
            )
        if cancellation.cancelled:
            raise OperationCancelled("evidence retention cleanup cancelled")
        persisted = self.requests.save(request)
        if cancellation.cancelled:
            raise OperationCancelled("evidence retention cleanup cancelled")
        return self.cleanup.resume(source, persisted, cancellation)


def new_backup_evidence_retention_cleanup_request(
    cleanup_id: str,
    execution: BackupEvidenceRetentionExecution,
    *,
    now: datetime,
) -> BackupEvidenceRetentionCleanupRequest:
    if execution.state is EvidenceRetentionExecutionState.COMPLETED:
        raise AdapterError(
            "evidence_retention_cleanup_not_required", "execution is complete"
        )
    request = BackupEvidenceRetentionCleanupRequest(
        "1.0", cleanup_id, execution.execution_hash, execution.request_hash,
        execution.backup_id, execution.host_id, execution.host_fingerprint,
        execution.remaining_kinds, now, now + timedelta(minutes=5),
    ).with_hash()
    _validate_request(request, now)
    return request


def _bytes(request: BackupEvidenceRetentionCleanupRequest) -> bytes:
    return json.dumps(
        to_primitive(request), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _validate_request(
    request: BackupEvidenceRetentionCleanupRequest, now: datetime | None,
) -> None:
    if (
        not isinstance(request, BackupEvidenceRetentionCleanupRequest)
        or (now is not None and now.tzinfo is None)
        or request.schema_version != "1.0"
        or not _IDENTIFIER.fullmatch(request.cleanup_id)
        or not _DIGEST.fullmatch(request.source_execution_hash)
        or not _DIGEST.fullmatch(request.source_request_hash)
        or not _DIGEST.fullmatch(request.request_hash)
        or not request.backup_id
        or not request.host_id
        or not _FINGERPRINT.fullmatch(request.host_fingerprint)
        or request.created_at.tzinfo is None
        or request.expires_at.tzinfo is None
        or request.expires_at != request.created_at + timedelta(minutes=5)
        or (now is not None and now < request.created_at)
        or (now is not None and now > request.expires_at)
        or not request.remaining_kinds
        or any(
            kind not in {"reconciliation", "manifest", "deletion"}
            for kind in request.remaining_kinds
        )
        or hashlib.sha256(
            _bytes(replace(request, request_hash=""))
        ).hexdigest() != request.request_hash
    ):
        raise AdapterError(
            "invalid_evidence_retention_cleanup_request",
            "cleanup request is invalid",
        )


def _decode_request(content: bytes) -> BackupEvidenceRetentionCleanupRequest:
    try:
        value = json.loads(content)
        required = {
            "backup_id", "cleanup_id", "created_at", "expires_at",
            "host_fingerprint", "host_id", "remaining_kinds", "request_hash",
            "schema_version", "source_execution_hash", "source_request_hash",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("unexpected fields")
        return BackupEvidenceRetentionCleanupRequest(
            value["schema_version"], value["cleanup_id"],
            value["source_execution_hash"], value["source_request_hash"],
            value["backup_id"], value["host_id"], value["host_fingerprint"],
            tuple(value["remaining_kinds"]),
            datetime.fromisoformat(value["created_at"]),
            datetime.fromisoformat(value["expires_at"]), value["request_hash"],
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterError(
            "invalid_evidence_retention_cleanup_request",
            "cleanup request cannot be decoded",
        ) from error
