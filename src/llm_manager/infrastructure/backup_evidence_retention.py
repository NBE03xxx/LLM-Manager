from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from llm_manager.application.errors import AdapterError

from .backup_deletion import BackupDeletionResultStore
from .backup_manifest_evidence import BackupManifestEvidenceStore
from .backup_reconciliation import DualCopyState


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
