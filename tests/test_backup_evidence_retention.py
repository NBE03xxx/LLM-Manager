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
    BackupEvidenceRetentionPlanner, EvidenceRetentionDisposition,
)
from llm_manager.infrastructure.backup_manifest_evidence import BackupManifestEvidenceStore
from llm_manager.infrastructure.backup_reconciliation import CopyPresence, DualCopyState


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
