from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.backup_evidence_retention import (
    BackupEvidenceRetentionExecution,
    BackupEvidenceRetentionExecutionStore,
    EvidenceRetentionExecutionState,
)
from llm_manager.infrastructure.backup_evidence_retention_cleanup import (
    BackupEvidenceRetentionCleanupService,
    new_backup_evidence_retention_cleanup_request,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)
FINGERPRINT = "SHA256:" + "a" * 43


class BackupEvidenceRetentionCleanupServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = BackupEvidenceRetentionExecutionStore(
            Path(self.temp.name) / "executions"
        )
        self.execution = self.store.save(BackupEvidenceRetentionExecution(
            "1.0", "a" * 64, "backup-1", "ssh:host", FINGERPRINT,
            "b" * 64, ("c" * 64,), EvidenceRetentionExecutionState.PARTIAL,
            ("reconciliation",), ("manifest", "deletion"),
            "manifest_delete_failed", NOW,
        ).with_hash())
        self.cleanup = _Cleanup()
        self.service = BackupEvidenceRetentionCleanupService(
            BackupEvidenceRetentionExecutionStore(Path(self.temp.name) / "executions"),
            self.cleanup,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_dispatches_only_explicit_request_bound_after_restart(self):
        request = new_backup_evidence_retention_cleanup_request(
            "cleanup-1", self.execution, now=NOW
        )
        self.assertEqual(
            self.service.execute(request, NOW, CancellationToken()), "resumed"
        )
        self.assertEqual(self.cleanup.calls, [(self.execution, request)])

    def test_rejects_tamper_expiry_binding_complete_and_cancel(self):
        request = new_backup_evidence_retention_cleanup_request(
            "cleanup-1", self.execution, now=NOW
        )
        invalid = (
            replace(request, remaining_kinds=("deletion",)),
            replace(request, request_hash="f" * 64),
        )
        for value in invalid:
            with self.assertRaises(AdapterError):
                self.service.execute(value, NOW, CancellationToken())
        with self.assertRaises(AdapterError):
            self.service.execute(request, NOW + timedelta(minutes=6), CancellationToken())
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(OperationCancelled):
            self.service.execute(request, NOW, token)
        complete = replace(
            self.execution, state=EvidenceRetentionExecutionState.COMPLETED,
            removed_kinds=("reconciliation", "manifest", "deletion"),
            remaining_kinds=(), error_code=None, execution_hash="",
        ).with_hash()
        with self.assertRaisesRegex(AdapterError, "complete"):
            new_backup_evidence_retention_cleanup_request(
                "cleanup-complete", complete, now=NOW
            )
        self.assertEqual(self.cleanup.calls, [])


class _Cleanup:
    def __init__(self):
        self.calls = []

    def resume(self, execution, request, cancellation):
        self.calls.append((execution, request))
        return "resumed"
