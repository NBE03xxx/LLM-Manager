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

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive

from .backup import _atomic_write
from .backup_deletion import BackupDeletionResultStore
from .backup_manifest_evidence import BackupManifestEvidenceStore
from .backup_reconciliation import BackupReconciliationResultStore, DualCopyState


MAX_EVIDENCE_RETENTION_EXECUTION_BYTES = 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}")
_FINGERPRINT = re.compile(r"SHA256:[A-Za-z0-9+/]{43}")


class EvidenceRetentionDisposition(StrEnum):
    KEEP = "keep"
    CANDIDATE = "candidate"
    ORPHAN = "orphan"
    MISSING_MANIFEST = "missing_manifest"


@dataclass(frozen=True, slots=True)
class BackupEvidenceRetentionRecord:
    request_hash: str
    backup_id: str
    host_id: str
    protected: bool | None
    deletion_request_id: str | None
    completed_at: datetime | None
    disposition: EvidenceRetentionDisposition
    reason: str


class BackupEvidenceRetentionPlanner:
    """Build a read-only plan; orphan or recovery evidence is never auto-selected."""

    def __init__(
        self,
        manifests: BackupManifestEvidenceStore,
        deletions: BackupDeletionResultStore,
    ) -> None:
        self.manifests = manifests
        self.deletions = deletions

    def plan_for_host(
        self, host_id: str, host_fingerprint: str, now: datetime,
        *, keep_generations: int = 10,
    ) -> tuple[BackupEvidenceRetentionRecord, ...]:
        if now.tzinfo is None or keep_generations != 10:
            raise AdapterError("invalid_evidence_retention_policy", "policy is fixed")
        deletion_results = self.deletions.list_for_host(host_id, host_fingerprint)
        by_request_hash = {}
        for result in deletion_results:
            if result.request_hash in by_request_hash:
                raise AdapterError(
                    "evidence_retention_binding_mismatch", "request hash is not unique"
                )
            by_request_hash[result.request_hash] = result
        linked = []
        matched_hashes = set()
        records = []
        for entry in self.manifests.list_entries():
            manifest = entry.manifest
            if manifest.host_id != host_id:
                continue
            if manifest.host_fingerprint != host_fingerprint:
                raise AdapterError(
                    "evidence_retention_binding_mismatch", "host fingerprint changed"
                )
            result = by_request_hash.get(entry.request_hash)
            if result is None:
                records.append(BackupEvidenceRetentionRecord(
                    entry.request_hash, manifest.backup_id, manifest.host_id,
                    manifest.protected, None, None,
                    EvidenceRetentionDisposition.ORPHAN, "missing_deletion_result",
                ))
                continue
            self.manifests.load(result)
            linked.append((entry, result))
            matched_hashes.add(entry.request_hash)
        for result in deletion_results:
            if result.request_hash not in matched_hashes:
                records.append(BackupEvidenceRetentionRecord(
                    result.request_hash, result.backup_id, result.host_id, None,
                    result.request_id, result.completed_at,
                    EvidenceRetentionDisposition.MISSING_MANIFEST,
                    "missing_manifest_evidence",
                ))
        linked.sort(key=lambda item: item[1].completed_at, reverse=True)
        cutoff = now - timedelta(days=30)
        for index, (entry, result) in enumerate(linked):
            manifest = entry.manifest
            if manifest.protected:
                disposition, reason = EvidenceRetentionDisposition.KEEP, "protected"
            elif result.requires_attention or result.state is not DualCopyState.BOTH_DELETED:
                disposition, reason = EvidenceRetentionDisposition.KEEP, "recovery_required"
            elif result.completed_at <= cutoff:
                disposition, reason = EvidenceRetentionDisposition.CANDIDATE, "older_than_30_days"
            elif index >= keep_generations:
                disposition, reason = EvidenceRetentionDisposition.CANDIDATE, "beyond_10_generations"
            else:
                disposition, reason = EvidenceRetentionDisposition.KEEP, "within_policy"
            records.append(BackupEvidenceRetentionRecord(
                entry.request_hash, manifest.backup_id, manifest.host_id,
                manifest.protected, result.request_id, result.completed_at,
                disposition, reason,
            ))
        return tuple(sorted(
            records,
            key=lambda item: (
                item.completed_at is not None,
                item.completed_at or datetime.min.replace(tzinfo=now.tzinfo),
                item.request_hash,
            ),
            reverse=True,
        ))


class EvidenceRetentionExecutionState(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BackupEvidenceRetentionExecution:
    schema_version: str
    request_hash: str
    backup_id: str
    host_id: str
    host_fingerprint: str
    deletion_result_hash: str
    reconciliation_result_hashes: tuple[str, ...]
    state: EvidenceRetentionExecutionState
    removed_kinds: tuple[str, ...]
    remaining_kinds: tuple[str, ...]
    error_code: str | None
    completed_at: datetime
    execution_hash: str = ""

    def with_hash(self) -> "BackupEvidenceRetentionExecution":
        value = replace(self, execution_hash="")
        return replace(value, execution_hash=hashlib.sha256(_execution_bytes(value)).hexdigest())


class BackupEvidenceRetentionExecutionStore:
    """Persist immutable canonical execution evidence for restart inspection."""

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe evidence retention execution root")

    def save(
        self, execution: BackupEvidenceRetentionExecution,
    ) -> BackupEvidenceRetentionExecution:
        _validate_execution(execution)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._root_metadata()
        path = self._path(execution.execution_hash)
        if path.exists() or path.is_symlink():
            raise AdapterError(
                "evidence_retention_execution_exists", "execution is immutable"
            )
        _atomic_write(path, _execution_bytes(execution), 0o600)
        return self.load(execution.execution_hash)

    def load(self, execution_hash: str) -> BackupEvidenceRetentionExecution:
        self._root_metadata()
        path = self._path(execution_hash)
        if path.is_symlink() or not path.is_file():
            raise AdapterError(
                "evidence_retention_execution_not_found", "execution is missing"
            )
        metadata = path.stat(follow_symlinks=False)
        if (stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.getuid()
                or metadata.st_size > MAX_EVIDENCE_RETENTION_EXECUTION_BYTES):
            raise AdapterError(
                "unsafe_evidence_retention_execution", "execution metadata is unsafe"
            )
        content = path.read_bytes()
        execution = _decode_execution(content)
        if content != _execution_bytes(execution):
            raise AdapterError(
                "invalid_evidence_retention_execution", "execution is not canonical"
            )
        _validate_execution(execution)
        if execution.execution_hash != execution_hash:
            raise AdapterError(
                "evidence_retention_execution_binding_mismatch",
                "execution filename changed identity",
            )
        return execution

    def _path(self, execution_hash: str) -> Path:
        if not isinstance(execution_hash, str) or not _DIGEST.fullmatch(execution_hash):
            raise AdapterError(
                "invalid_evidence_retention_execution", "execution hash is invalid"
            )
        return self.root / f"{execution_hash}.json"

    def _root_metadata(self) -> None:
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError(
                "unsafe_evidence_retention_execution", "execution root is unsafe"
            )
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError(
                "unsafe_evidence_retention_execution", "root metadata is unsafe"
            )


class BackupEvidenceRetentionExecutionPersistenceError(AdapterError):
    """Expose the terminal execution when its immutable evidence could not be saved."""

    def __init__(
        self,
        execution: BackupEvidenceRetentionExecution,
        cause_code: str,
    ) -> None:
        super().__init__(
            "evidence_retention_execution_persistence_failed",
            "evidence retention finished but execution evidence could not be persisted",
        )
        self.execution = execution
        self.cause_code = cause_code


class BackupEvidenceRetentionExecutor:
    """Delete only a freshly revalidated candidate, stopping after the first failure."""

    def __init__(
        self,
        planner: BackupEvidenceRetentionPlanner,
        manifests: BackupManifestEvidenceStore,
        deletions: BackupDeletionResultStore,
        reconciliations: BackupReconciliationResultStore,
        executions: BackupEvidenceRetentionExecutionStore,
    ) -> None:
        self.planner = planner
        self.manifests = manifests
        self.deletions = deletions
        self.reconciliations = reconciliations
        self.executions = executions

    def execute(
        self, request_hash: str, host_id: str, host_fingerprint: str,
        now: datetime, cancellation: CancellationToken,
    ) -> BackupEvidenceRetentionExecution:
        if cancellation.cancelled:
            raise OperationCancelled("evidence retention cancelled")
        plan = self.planner.plan_for_host(host_id, host_fingerprint, now)
        record = next((item for item in plan if item.request_hash == request_hash), None)
        if record is None or record.disposition is not EvidenceRetentionDisposition.CANDIDATE:
            raise AdapterError("evidence_retention_not_candidate", "evidence is not removable")
        if record.deletion_request_id is None:
            raise AdapterError("evidence_retention_binding_mismatch", "deletion result is missing")
        deletion = self.deletions.load(record.deletion_request_id)
        manifest = self.manifests.load(deletion)
        if (manifest.backup_id, manifest.host_id, manifest.host_fingerprint) != (
            record.backup_id, host_id, host_fingerprint,
        ):
            raise AdapterError("evidence_retention_binding_mismatch", "manifest changed identity")
        reconciliation_results = self.reconciliations.list_for_deletion_result(
            deletion.result_hash, host_id, host_fingerprint
        )
        if any(
            (result.backup_id, result.manifest_hash) != (
                deletion.backup_id, deletion.manifest_hash
            )
            for result in reconciliation_results
        ):
            raise AdapterError(
                "evidence_retention_binding_mismatch", "reconciliation changed identity"
            )
        operations = [
            *(("reconciliation", result, self.reconciliations.delete)
              for result in reconciliation_results),
            ("manifest", deletion, self.manifests.delete),
            ("deletion", deletion, self.deletions.delete),
        ]
        removed = []
        for index, (kind, value, delete) in enumerate(operations):
            try:
                if cancellation.cancelled:
                    raise OperationCancelled("evidence retention cancelled")
                delete(value)
                removed.append(kind)
            except (AdapterError, OperationCancelled, OSError, ValueError) as error:
                remaining = tuple(item[0] for item in operations[index:])
                execution = BackupEvidenceRetentionExecution(
                    "1.0", request_hash, record.backup_id, host_id, host_fingerprint,
                    deletion.result_hash,
                    tuple(item.result_hash for item in reconciliation_results),
                    EvidenceRetentionExecutionState.PARTIAL if removed
                    else EvidenceRetentionExecutionState.FAILED,
                    tuple(removed), remaining,
                    getattr(error, "code", "evidence_retention_failed"),
                    now,
                ).with_hash()
                return self._persist(execution)
        execution = BackupEvidenceRetentionExecution(
            "1.0", request_hash, record.backup_id, host_id, host_fingerprint,
            deletion.result_hash,
            tuple(item.result_hash for item in reconciliation_results),
            EvidenceRetentionExecutionState.COMPLETED, tuple(removed), (), None, now,
        ).with_hash()
        return self._persist(execution)

    def _persist(
        self, execution: BackupEvidenceRetentionExecution,
    ) -> BackupEvidenceRetentionExecution:
        try:
            return self.executions.save(execution)
        except (AdapterError, OSError, ValueError) as error:
            raise BackupEvidenceRetentionExecutionPersistenceError(
                execution,
                getattr(error, "code", "evidence_retention_execution_store_failed"),
            ) from error


def _execution_bytes(execution: BackupEvidenceRetentionExecution) -> bytes:
    return json.dumps(
        to_primitive(execution), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _validate_execution(execution: BackupEvidenceRetentionExecution) -> None:
    text_fields = (
        execution.schema_version, execution.request_hash, execution.backup_id,
        execution.host_id, execution.host_fingerprint,
        execution.deletion_result_hash, execution.execution_hash,
    )
    if (any(not isinstance(value, str) for value in text_fields)
            or not isinstance(execution.completed_at, datetime)
            or not isinstance(execution.reconciliation_result_hashes, tuple)
            or not isinstance(execution.removed_kinds, tuple)
            or not isinstance(execution.remaining_kinds, tuple)
            or any(not isinstance(value, str) for value in (
                execution.reconciliation_result_hashes
                + execution.removed_kinds + execution.remaining_kinds
            ))
            or (execution.error_code is not None
                and not isinstance(execution.error_code, str))
            or execution.schema_version != "1.0"
            or not _DIGEST.fullmatch(execution.request_hash)
            or not _DIGEST.fullmatch(execution.deletion_result_hash)
            or not _DIGEST.fullmatch(execution.execution_hash)
            or not execution.backup_id or not execution.host_id
            or not _FINGERPRINT.fullmatch(execution.host_fingerprint)
            or execution.completed_at.tzinfo is None
            or any(not _DIGEST.fullmatch(value)
                   for value in execution.reconciliation_result_hashes)
            or len(set(execution.reconciliation_result_hashes))
            != len(execution.reconciliation_result_hashes)
            or any(kind not in {"reconciliation", "manifest", "deletion"}
                   for kind in execution.removed_kinds + execution.remaining_kinds)):
        raise AdapterError(
            "invalid_evidence_retention_execution", "execution fields are invalid"
        )
    expected = hashlib.sha256(
        _execution_bytes(replace(execution, execution_hash=""))
    ).hexdigest()
    if execution.execution_hash != expected:
        raise AdapterError(
            "evidence_retention_execution_binding_mismatch", "execution hash changed"
        )
    if execution.state is EvidenceRetentionExecutionState.COMPLETED:
        valid_state = not execution.remaining_kinds and execution.error_code is None
    elif execution.state is EvidenceRetentionExecutionState.PARTIAL:
        valid_state = bool(
            execution.removed_kinds and execution.remaining_kinds
            and execution.error_code
        )
    else:
        valid_state = bool(
            not execution.removed_kinds and execution.remaining_kinds
            and execution.error_code
        )
    if not valid_state:
        raise AdapterError(
            "invalid_evidence_retention_execution", "execution state is inconsistent"
        )


def _decode_execution(content: bytes) -> BackupEvidenceRetentionExecution:
    try:
        value = json.loads(content)
        required = {
            "backup_id", "completed_at", "deletion_result_hash", "error_code",
            "execution_hash", "host_fingerprint", "host_id", "reconciliation_result_hashes",
            "remaining_kinds", "removed_kinds", "request_hash", "schema_version", "state",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("unexpected fields")
        return BackupEvidenceRetentionExecution(
            value["schema_version"], value["request_hash"], value["backup_id"],
            value["host_id"], value["host_fingerprint"], value["deletion_result_hash"],
            tuple(value["reconciliation_result_hashes"]),
            EvidenceRetentionExecutionState(value["state"]),
            tuple(value["removed_kinds"]), tuple(value["remaining_kinds"]),
            value["error_code"], datetime.fromisoformat(value["completed_at"]),
            value["execution_hash"],
        )
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterError(
            "invalid_evidence_retention_execution", "execution cannot be decoded"
        ) from error
