from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.backup_cleanup import BackupCleanupActionService
from llm_manager.infrastructure.backup_deletion import (
    BackupDeletionResult, BackupDeletionResultStore, CopyDeleteOutcome,
)
from llm_manager.infrastructure.backup_inventory import BackupListAction
from llm_manager.infrastructure.backup_reconciliation import CopyPresence, DualCopyState
from llm_manager.infrastructure.openssh_remote_retention import RemoteRetentionResultStore
from llm_manager.infrastructure.remote_retention import (
    RemoteRetentionResult, RemoteRetentionState,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
FINGERPRINT = "SHA256:" + "a" * 43


class BackupCleanupActionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.retention_results = RemoteRetentionResultStore(root / "retention")
        self.deletion_results = BackupDeletionResultStore(root / "deletion")
        self.retention_result = self.retention_results.save(RemoteRetentionResult(
            "1.0", "retention-1", "a" * 64, "ssh:host", FINGERPRINT,
            NOW, RemoteRetentionState.COMPLETED, (), ("backup-1",), None,
        ).with_hash())
        self.deletion_result = self.deletion_results.save(BackupDeletionResult(
            "1.0", "delete-1", "b" * 64, "backup-1", "ssh:host",
            FINGERPRINT, "c" * 64, CopyDeleteOutcome.DELETED,
            CopyDeleteOutcome.DELETED, None, None, CopyPresence.ABSENT,
            CopyPresence.ABSENT, DualCopyState.BOTH_DELETED, False, NOW,
        ).with_hash())
        self.retention = _RetentionCleanup()
        self.deletion = _DeletionCleanup()
        self.service = BackupCleanupActionService(
            self.retention_results, self.deletion_results,
            self.retention, self.deletion,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_executes_only_bound_retention_cleanup(self):
        self.assertTrue(self.service.execute(
            BackupListAction.RETRY_RETENTION_STAGING_CLEANUP,
            "ssh:host", FINGERPRINT, CancellationToken(),
        ))
        self.assertEqual(
            self.retention.calls,
            [("retention-1", "ssh:host", FINGERPRINT)],
        )

    def test_executes_only_latest_bound_deletion_cleanup(self):
        self.assertTrue(self.service.execute(
            BackupListAction.RETRY_STAGING_CLEANUP,
            "ssh:host", FINGERPRINT, CancellationToken(), backup_id="backup-1",
        ))
        self.assertEqual(self.deletion.calls, [self.deletion_result])

    def test_rejects_mutation_nonpending_binding_and_cancellation(self):
        with self.assertRaises(AdapterError):
            self.service.execute(
                BackupListAction.RETRY_REMOTE_DELETE, "ssh:host", FINGERPRINT,
                CancellationToken(), backup_id="backup-1",
            )
        self.deletion.pending = False
        with self.assertRaises(AdapterError):
            self.service.execute(
                BackupListAction.RETRY_STAGING_CLEANUP, "ssh:host", FINGERPRINT,
                CancellationToken(), backup_id="backup-1",
            )
        with self.assertRaises(AdapterError):
            self.service.execute(
                BackupListAction.RETRY_RETENTION_STAGING_CLEANUP,
                "ssh:host", "SHA256:" + "z" * 43, CancellationToken(),
            )
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(OperationCancelled):
            self.service.execute(
                BackupListAction.RETRY_RETENTION_STAGING_CLEANUP,
                "ssh:host", FINGERPRINT, token,
            )
        self.assertEqual(self.retention.calls, [])
        self.assertEqual(self.deletion.calls, [])


class _RetentionCleanup:
    def __init__(self):
        self.pending = True
        self.calls = []

    def cleanup_pending(self, request_id):
        return self.pending

    def retry_staging_cleanup(self, request_id, host_id, fingerprint, cancellation):
        self.calls.append((request_id, host_id, fingerprint))
        self.pending = False
        return True


class _DeletionCleanup:
    def __init__(self):
        self.pending = True
        self.calls = []

    def staging_cleanup_pending(self, result):
        return self.pending

    def retry_staging_cleanup(self, result, cancellation):
        self.calls.append(result)
        self.pending = False
        return True
