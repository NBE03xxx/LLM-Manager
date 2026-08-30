from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive

from .backup_evidence_retention import (
    BackupEvidenceRetentionExecution,
    BackupEvidenceRetentionExecutionStore,
    EvidenceRetentionExecutionState,
)


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")


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


class BackupEvidenceRetentionCleanupService:
    """Authorize cleanup only from an explicit request bound to strict evidence."""

    def __init__(
        self,
        executions: BackupEvidenceRetentionExecutionStore,
        cleanup: BackupEvidenceRetentionCleanupPort,
    ) -> None:
        self.executions = executions
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
        return self.cleanup.resume(source, request, cancellation)


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
    request: BackupEvidenceRetentionCleanupRequest, now: datetime,
) -> None:
    if (
        not isinstance(request, BackupEvidenceRetentionCleanupRequest)
        or now.tzinfo is None
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
        or now < request.created_at
        or now > request.expires_at
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
