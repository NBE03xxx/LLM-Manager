from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_deletion import (
    BackupDeletionResult, BackupDeletionResultStore, CopyDeleteOutcome,
    new_backup_deletion_request,
)
from llm_manager.infrastructure.backup_manifest_evidence import BackupManifestEvidenceStore
from llm_manager.infrastructure.backup_inventory import BackupListAction
from llm_manager.infrastructure.backup_reconciliation import (
    BackupReconciliationResult, CopyPresence, DualCopyState,
)
from llm_manager.infrastructure.backup_reconciliation_action import (
    BackupReconciliationActionService,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
FINGERPRINT = "SHA256:" + "a" * 43


class BackupReconciliationActionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        target = root / "target"
        target.write_bytes(b"before")
        change = Change(
            "change", str(target), ChangeOperation.REPLACE_FILE,
            "before", "after", None, "diff",
        )
        self.manifests = LocalBackupStore(root / "backups", (root,))
        self.manifest = self.manifests.create(BackupRequest(
            "backup-1", "plan-1", "ssh:host", FINGERPRINT,
            ChangeSet("changes", "ssh:host", (change,), "c" * 64),
            EncryptionInfo(enabled=False),
        ), CancellationToken())
        self.deletions = BackupDeletionResultStore(root / "deletions")
        self.request = new_backup_deletion_request("delete-1", self.manifest, now=NOW)
        self.deletion = self.deletions.save(BackupDeletionResult(
            "1.0", "delete-1", self.request.request_hash, self.manifest.backup_id,
            self.manifest.host_id, FINGERPRINT, self.manifest.manifest_hash,
            CopyDeleteOutcome.FAILED, CopyDeleteOutcome.NOT_ATTEMPTED,
            "remote_failed", None, CopyPresence.PRESENT, CopyPresence.PRESENT,
            DualCopyState.BOTH_AVAILABLE, True, NOW,
        ).with_hash())
        self.evidence = BackupManifestEvidenceStore(root / "manifest-evidence")
        self.evidence.save(self.request, self.manifest)
        self.runner = _Runner()
        self.service = BackupReconciliationActionService(
            self.manifests, self.deletions, self.runner, self.evidence
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_dispatches_only_latest_bound_readonly_reconciliation(self):
        result = self.service.execute(
            BackupListAction.RECONCILE_COPIES, "reconcile-1", "backup-1",
            "ssh:host", FINGERPRINT, CancellationToken(),
        )
        self.assertEqual(result.reconciliation_id, "reconcile-1")
        self.assertEqual(
            self.runner.calls,
            [("reconcile-1", self.deletion, self.manifest)],
        )

    def test_rejects_mutation_action_binding_missing_manifest_and_cancel(self):
        with self.assertRaises(AdapterError):
            self.service.execute(
                BackupListAction.RETRY_REMOTE_DELETE, "reconcile-1", "backup-1",
                "ssh:host", FINGERPRINT, CancellationToken(),
            )
        with self.assertRaises(AdapterError):
            self.service.execute(
                BackupListAction.RECONCILE_COPIES, "reconcile-1", "missing",
                "ssh:host", FINGERPRINT, CancellationToken(),
            )
        with self.assertRaises(AdapterError):
            self.service.execute(
                BackupListAction.RECONCILE_COPIES, "reconcile-1", "backup-1",
                "ssh:host", "SHA256:" + "z" * 43, CancellationToken(),
            )
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(OperationCancelled):
            self.service.execute(
                BackupListAction.RECONCILE_COPIES, "reconcile-1", "backup-1",
                "ssh:host", FINGERPRINT, token,
            )
        self.assertEqual(self.runner.calls, [])

    def test_uses_immutable_manifest_evidence_after_local_copy_is_deleted(self):
        self.manifests.delete(self.manifest, CancellationToken())
        result = self.service.execute(
            BackupListAction.RECONCILE_COPIES, "reconcile-after-delete", "backup-1",
            "ssh:host", FINGERPRINT, CancellationToken(),
        )
        self.assertEqual(result.reconciliation_id, "reconcile-after-delete")
        self.assertEqual(self.runner.calls[0][2], self.manifest)
        evidence_path = Path(self.temp.name) / (
            f"manifest-evidence/{self.request.request_hash}.json"
        )
        evidence_path.write_bytes(evidence_path.read_bytes()[:-1] + b" ")
        with self.assertRaises(AdapterError):
            self.service.execute(
                BackupListAction.RECONCILE_COPIES, "reconcile-tampered", "backup-1",
                "ssh:host", FINGERPRINT, CancellationToken(),
            )


class _Runner:
    def __init__(self):
        self.calls = []

    def reconcile(self, reconciliation_id, deletion, manifest, cancellation):
        self.calls.append((reconciliation_id, deletion, manifest))
        return BackupReconciliationResult(
            "1.0", reconciliation_id, deletion.result_hash, manifest.backup_id,
            manifest.host_id, manifest.host_fingerprint, manifest.manifest_hash,
            NOW, CopyPresence.PRESENT, CopyPresence.ABSENT,
            DualCopyState.LOCAL_ONLY, True,
        ).with_hash()
