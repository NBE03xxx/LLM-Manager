from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken

from .backup_deletion import BackupDeletionResultStore
from .backup_manifest_evidence import BackupManifestEvidenceStore
from .backup_reconciliation import BackupReconciliationResultStore, DualCopyState


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
    request_hash: str
    backup_id: str
    state: EvidenceRetentionExecutionState
    removed_kinds: tuple[str, ...]
    remaining_kinds: tuple[str, ...]
    error_code: str | None


class BackupEvidenceRetentionExecutor:
    """Delete only a freshly revalidated candidate, stopping after the first failure."""

    def __init__(
        self,
        planner: BackupEvidenceRetentionPlanner,
        manifests: BackupManifestEvidenceStore,
        deletions: BackupDeletionResultStore,
        reconciliations: BackupReconciliationResultStore,
    ) -> None:
        self.planner = planner
        self.manifests = manifests
        self.deletions = deletions
        self.reconciliations = reconciliations

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
                return BackupEvidenceRetentionExecution(
                    request_hash, record.backup_id,
                    EvidenceRetentionExecutionState.PARTIAL if removed
                    else EvidenceRetentionExecutionState.FAILED,
                    tuple(removed), remaining,
                    getattr(error, "code", "evidence_retention_failed"),
                )
        return BackupEvidenceRetentionExecution(
            request_hash, record.backup_id, EvidenceRetentionExecutionState.COMPLETED,
            tuple(removed), (), None,
        )
