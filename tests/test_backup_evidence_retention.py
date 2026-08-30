from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_deletion import (
    BackupDeletionResult, BackupDeletionResultStore, CopyDeleteOutcome,
    new_backup_deletion_request,
)
from llm_manager.infrastructure.backup_evidence_retention import (
    BackupEvidenceRetentionExecutionStore, BackupEvidenceRetentionExecutor,
    BackupEvidenceRetentionPlanner,
    EvidenceRetentionDisposition, EvidenceRetentionExecutionState,
)
from llm_manager.infrastructure.backup_manifest_evidence import BackupManifestEvidenceStore
from llm_manager.infrastructure.backup_reconciliation import (
    BackupReconciliationResult, BackupReconciliationResultStore,
    CopyPresence, DualCopyState,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
FINGERPRINT = "SHA256:" + "a" * 43


class BackupEvidenceRetentionPlannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        target = self.root / "target"
        target.write_bytes(b"before")
        self.change = Change(
            "change", str(target), ChangeOperation.REPLACE_FILE,
            "before", "after", None, "diff",
        )
        self.backups = LocalBackupStore(self.root / "backups", (self.root,))
        self.evidence = BackupManifestEvidenceStore(self.root / "evidence")
        self.deletions = BackupDeletionResultStore(self.root / "deletions")
        self.reconciliations = BackupReconciliationResultStore(
            self.root / "reconciliations"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_plans_fixed_generation_retention_and_preserves_protected_orphan(self):
        created = []
        for index in range(12):
            manifest = self._manifest(index, protected=index == 11)
            request = new_backup_deletion_request(f"delete-{index}", manifest, now=NOW)
            self.evidence.save(request, manifest)
            result = self.deletions.save(_result(
                request, manifest, NOW - timedelta(days=index)
            ))
            created.append((request, manifest, result))
        orphan_manifest = self._manifest("orphan")
        orphan_request = new_backup_deletion_request(
            "delete-orphan", orphan_manifest, now=NOW
        )
        self.evidence.save(orphan_request, orphan_manifest)
        missing_manifest = self._manifest("missing-manifest")
        missing_request = new_backup_deletion_request(
            "delete-missing-manifest", missing_manifest, now=NOW
        )
        self.deletions.save(_result(missing_request, missing_manifest, NOW))

        records = BackupEvidenceRetentionPlanner(
            self.evidence, self.deletions
        ).plan_for_host("ssh:host", FINGERPRINT, NOW)
        by_backup = {record.backup_id: record for record in records}
        self.assertEqual(
            by_backup["backup-10"].disposition,
            EvidenceRetentionDisposition.CANDIDATE,
        )
        self.assertEqual(by_backup["backup-10"].reason, "beyond_10_generations")
        self.assertEqual(
            by_backup["backup-11"].disposition,
            EvidenceRetentionDisposition.KEEP,
        )
        self.assertEqual(by_backup["backup-11"].reason, "protected")
        self.assertEqual(
            by_backup["backup-orphan"].disposition,
            EvidenceRetentionDisposition.ORPHAN,
        )
        self.assertIsNone(by_backup["backup-orphan"].completed_at)
        self.assertEqual(
            by_backup["backup-missing-manifest"].disposition,
            EvidenceRetentionDisposition.MISSING_MANIFEST,
        )
        self.assertIsNone(by_backup["backup-missing-manifest"].protected)

    def test_marks_old_terminal_bundle_but_keeps_recovery_required(self):
        old = self._manifest("old")
        old_request = new_backup_deletion_request("delete-old", old, now=NOW)
        self.evidence.save(old_request, old)
        self.deletions.save(_result(old_request, old, NOW - timedelta(days=31)))
        recovery = self._manifest("recovery")
        recovery_request = new_backup_deletion_request(
            "delete-recovery", recovery, now=NOW
        )
        self.evidence.save(recovery_request, recovery)
        self.deletions.save(_result(
            recovery_request, recovery, NOW - timedelta(days=31), recovery=True
        ))
        records = BackupEvidenceRetentionPlanner(
            self.evidence, self.deletions
        ).plan_for_host("ssh:host", FINGERPRINT, NOW)
        by_backup = {record.backup_id: record for record in records}
        self.assertEqual(by_backup["backup-old"].reason, "older_than_30_days")
        self.assertEqual(
            by_backup["backup-old"].disposition,
            EvidenceRetentionDisposition.CANDIDATE,
        )
        self.assertEqual(by_backup["backup-recovery"].reason, "recovery_required")
        self.assertEqual(
            by_backup["backup-recovery"].disposition,
            EvidenceRetentionDisposition.KEEP,
        )

    def test_rejects_unknown_evidence_entry_and_policy_override(self):
        manifest = self._manifest("safe")
        request = new_backup_deletion_request("delete-safe", manifest, now=NOW)
        self.evidence.save(request, manifest)
        (self.root / "evidence/unexpected").write_text("unsafe")
        planner = BackupEvidenceRetentionPlanner(self.evidence, self.deletions)
        with self.assertRaises(AdapterError):
            planner.plan_for_host("ssh:host", FINGERPRINT, NOW)
        (self.root / "evidence/unexpected").unlink()
        with self.assertRaises(AdapterError):
            planner.plan_for_host("ssh:host", FINGERPRINT, NOW, keep_generations=9)

    def test_executor_removes_only_revalidated_candidate_in_reference_order(self):
        manifest = self._manifest("execute")
        request = new_backup_deletion_request("delete-execute", manifest, now=NOW)
        self.evidence.save(request, manifest)
        deletion = self.deletions.save(_result(
            request, manifest, NOW - timedelta(days=31)
        ))
        reconciliation = self.reconciliations.save(_reconciliation(
            "reconcile-execute", deletion, manifest
        ))
        execution = BackupEvidenceRetentionExecutor(
            BackupEvidenceRetentionPlanner(self.evidence, self.deletions),
            self.evidence, self.deletions, self.reconciliations,
        ).execute(request.request_hash, "ssh:host", FINGERPRINT, NOW,
                  CancellationToken())
        self.assertEqual(execution.state, EvidenceRetentionExecutionState.COMPLETED)
        self.assertEqual(execution.host_id, "ssh:host")
        self.assertEqual(execution.host_fingerprint, FINGERPRINT)
        self.assertEqual(execution.deletion_result_hash, deletion.result_hash)
        self.assertEqual(
            execution.reconciliation_result_hashes, (reconciliation.result_hash,)
        )
        self.assertEqual(
            execution.removed_kinds,
            ("reconciliation", "manifest", "deletion"),
        )
        for load in (
            lambda: self.reconciliations.load(reconciliation.reconciliation_id),
            lambda: self.evidence.load(deletion),
            lambda: self.deletions.load(deletion.request_id),
        ):
            with self.assertRaises(AdapterError):
                load()

        store = BackupEvidenceRetentionExecutionStore(self.root / "executions")
        self.assertEqual(store.save(execution), execution)
        self.assertEqual(store.load(execution.execution_hash), execution)
        with self.assertRaisesRegex(AdapterError, "immutable"):
            store.save(execution)

    def test_execution_store_rejects_tamper_filename_and_unsafe_metadata(self):
        execution = self._execution("stored")
        store = BackupEvidenceRetentionExecutionStore(self.root / "executions")
        store.save(execution)
        path = self.root / "executions" / f"{execution.execution_hash}.json"
        content = path.read_bytes()
        path.write_bytes(content.replace(b"backup-stored", b"backup-changed"))
        with self.assertRaises(AdapterError):
            store.load(execution.execution_hash)

        path.write_bytes(content)
        path.chmod(0o644)
        with self.assertRaisesRegex(AdapterError, "metadata"):
            store.load(execution.execution_hash)

        path.chmod(0o600)
        wrong_hash = "f" * 64
        path.rename(path.with_name(f"{wrong_hash}.json"))
        with self.assertRaisesRegex(AdapterError, "filename"):
            store.load(wrong_hash)

    def test_executor_stops_after_partial_failure_and_preserves_root_result(self):
        manifest = self._manifest("partial")
        request = new_backup_deletion_request("delete-partial", manifest, now=NOW)
        self.evidence.save(request, manifest)
        deletion = self.deletions.save(_result(
            request, manifest, NOW - timedelta(days=31)
        ))
        reconciliation = self.reconciliations.save(_reconciliation(
            "reconcile-partial", deletion, manifest
        ))
        execution = BackupEvidenceRetentionExecutor(
            BackupEvidenceRetentionPlanner(self.evidence, self.deletions),
            _FailingManifestDelete(self.evidence), self.deletions,
            self.reconciliations,
        ).execute(request.request_hash, "ssh:host", FINGERPRINT, NOW,
                  CancellationToken())
        self.assertEqual(execution.state, EvidenceRetentionExecutionState.PARTIAL)
        self.assertEqual(execution.removed_kinds, ("reconciliation",))
        self.assertEqual(execution.remaining_kinds, ("manifest", "deletion"))
        self.assertEqual(self.deletions.load(deletion.request_id), deletion)
        self.assertEqual(self.evidence.load(deletion), manifest)
        with self.assertRaises(AdapterError):
            self.reconciliations.load(reconciliation.reconciliation_id)

    def test_executor_reports_failed_when_first_reference_cannot_be_removed(self):
        manifest = self._manifest("failed")
        request = new_backup_deletion_request("delete-failed", manifest, now=NOW)
        self.evidence.save(request, manifest)
        deletion = self.deletions.save(_result(
            request, manifest, NOW - timedelta(days=31)
        ))
        reconciliation = self.reconciliations.save(_reconciliation(
            "reconcile-failed", deletion, manifest
        ))
        execution = BackupEvidenceRetentionExecutor(
            BackupEvidenceRetentionPlanner(self.evidence, self.deletions),
            self.evidence, self.deletions,
            _FailingReconciliationDelete(self.reconciliations),
        ).execute(request.request_hash, "ssh:host", FINGERPRINT, NOW,
                  CancellationToken())
        self.assertEqual(execution.state, EvidenceRetentionExecutionState.FAILED)
        self.assertEqual(execution.removed_kinds, ())
        self.assertEqual(
            execution.remaining_kinds,
            ("reconciliation", "manifest", "deletion"),
        )
        self.assertEqual(
            self.reconciliations.load(reconciliation.reconciliation_id), reconciliation
        )
        self.assertEqual(self.evidence.load(deletion), manifest)
        self.assertEqual(self.deletions.load(deletion.request_id), deletion)

    def test_executor_rejects_non_candidate_without_deleting(self):
        manifest = self._manifest("keep")
        request = new_backup_deletion_request("delete-keep", manifest, now=NOW)
        self.evidence.save(request, manifest)
        deletion = self.deletions.save(_result(request, manifest, NOW))
        with self.assertRaises(AdapterError):
            BackupEvidenceRetentionExecutor(
                BackupEvidenceRetentionPlanner(self.evidence, self.deletions),
                self.evidence, self.deletions, self.reconciliations,
            ).execute(request.request_hash, "ssh:host", FINGERPRINT, NOW,
                      CancellationToken())
        self.assertEqual(self.deletions.load(deletion.request_id), deletion)

    def _manifest(self, identity, *, protected=False):
        backup_id = f"backup-{identity}"
        manifest = self.backups.create(BackupRequest(
            backup_id, f"plan-{identity}", "ssh:host", FINGERPRINT,
            ChangeSet(f"changes-{identity}", "ssh:host", (self.change,), "c" * 64),
            EncryptionInfo(enabled=False),
        ), CancellationToken())
        return (
            self.backups.set_protected("ssh:host", backup_id, True)
            if protected else manifest
        )

    def _execution(self, identity):
        manifest = self._manifest(identity)
        request = new_backup_deletion_request(f"delete-{identity}", manifest, now=NOW)
        self.evidence.save(request, manifest)
        self.deletions.save(_result(request, manifest, NOW - timedelta(days=31)))
        return BackupEvidenceRetentionExecutor(
            BackupEvidenceRetentionPlanner(self.evidence, self.deletions),
            self.evidence, self.deletions, self.reconciliations,
        ).execute(request.request_hash, "ssh:host", FINGERPRINT, NOW,
                  CancellationToken())


def _result(request, manifest, completed_at, *, recovery=False):
    return BackupDeletionResult(
        "1.0", request.request_id, request.request_hash, manifest.backup_id,
        manifest.host_id, FINGERPRINT, manifest.manifest_hash,
        CopyDeleteOutcome.FAILED if recovery else CopyDeleteOutcome.DELETED,
        CopyDeleteOutcome.NOT_ATTEMPTED if recovery else CopyDeleteOutcome.DELETED,
        "remote_failed" if recovery else None, None,
        CopyPresence.PRESENT if recovery else CopyPresence.ABSENT,
        CopyPresence.PRESENT if recovery else CopyPresence.ABSENT,
        DualCopyState.BOTH_AVAILABLE if recovery else DualCopyState.BOTH_DELETED,
        recovery, completed_at,
    ).with_hash()


def _reconciliation(identity, deletion, manifest):
    return BackupReconciliationResult(
        "1.0", identity, deletion.result_hash, manifest.backup_id,
        manifest.host_id, FINGERPRINT, manifest.manifest_hash, NOW,
        CopyPresence.ABSENT, CopyPresence.ABSENT, DualCopyState.BOTH_DELETED,
        False,
    ).with_hash()


class _FailingManifestDelete:
    def __init__(self, delegate):
        self.delegate = delegate

    def load(self, result):
        return self.delegate.load(result)

    def delete(self, result):
        raise AdapterError("manifest_delete_failed", "injected")


class _FailingReconciliationDelete:
    def __init__(self, delegate):
        self.delegate = delegate

    def list_for_deletion_result(self, source_hash, host_id, fingerprint):
        return self.delegate.list_for_deletion_result(source_hash, host_id, fingerprint)

    def delete(self, result):
        raise AdapterError("reconciliation_delete_failed", "injected")
