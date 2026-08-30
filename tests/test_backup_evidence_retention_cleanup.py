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
    BackupEvidenceRetentionCleanupExecutor,
    BackupEvidenceRetentionCleanupRequestStore, BackupEvidenceRetentionCleanupService,
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
        self.requests = BackupEvidenceRetentionCleanupRequestStore(
            Path(self.temp.name) / "requests"
        )
        self.service = BackupEvidenceRetentionCleanupService(
            BackupEvidenceRetentionExecutionStore(Path(self.temp.name) / "executions"),
            self.requests, self.cleanup,
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
        self.assertEqual(self.requests.load("cleanup-1"), request)

    def test_request_store_is_immutable_and_rejects_tamper_and_collision(self):
        request = new_backup_evidence_retention_cleanup_request(
            "cleanup-store", self.execution, now=NOW
        )
        self.assertEqual(self.requests.save(request), request)
        self.assertEqual(self.requests.save(request), request)
        with self.assertRaisesRegex(AdapterError, "reused"):
            self.requests.save(replace(
                request, created_at=request.created_at + timedelta(seconds=1),
                expires_at=request.expires_at + timedelta(seconds=1),
                request_hash="",
            ).with_hash())
        path = Path(self.temp.name) / "requests/cleanup-store.json"
        content = path.read_bytes()
        path.write_bytes(content[:-1] + b" ")
        with self.assertRaises(AdapterError):
            self.requests.load("cleanup-store")

    def test_cleanup_executor_deletes_only_bound_suffix_and_persists_result(self):
        deletion = _Deletion("b" * 64)
        deletions = _Deletions(deletion)
        manifests = _Manifests()
        reconciliations = _Reconciliations(())
        executor = BackupEvidenceRetentionCleanupExecutor(
            manifests, deletions, reconciliations, self.store,
            completed_at=lambda: NOW + timedelta(seconds=1),
        )
        request = new_backup_evidence_retention_cleanup_request(
            "cleanup-execute", self.execution, now=NOW
        )
        result = executor.resume(self.execution, request, CancellationToken())
        self.assertEqual(result.state, EvidenceRetentionExecutionState.COMPLETED)
        self.assertEqual(result.request_hash, request.request_hash)
        self.assertEqual(result.removed_kinds, ("manifest", "deletion"))
        self.assertEqual(manifests.deleted, [deletion])
        self.assertEqual(deletions.deleted, [deletion])
        self.assertEqual(self.store.load(result.execution_hash), result)

    def test_cleanup_executor_persists_cancel_without_deleting(self):
        deletion = _Deletion("b" * 64)
        deletions = _Deletions(deletion)
        manifests = _Manifests()
        executor = BackupEvidenceRetentionCleanupExecutor(
            manifests, deletions, _Reconciliations(()), self.store,
            completed_at=lambda: NOW + timedelta(seconds=1),
        )
        request = new_backup_evidence_retention_cleanup_request(
            "cleanup-cancel", self.execution, now=NOW
        )
        token = CancellationToken()
        token.cancel()
        result = executor.resume(self.execution, request, token)
        self.assertEqual(result.state, EvidenceRetentionExecutionState.FAILED)
        self.assertEqual(result.error_code, "evidence_retention_cleanup_failed")
        self.assertEqual(manifests.deleted, [])
        self.assertEqual(deletions.deleted, [])

    def test_cleanup_executor_stops_and_persists_partial_failure(self):
        deletion = _Deletion("b" * 64)
        deletions = _Deletions(deletion, fail_delete=True)
        manifests = _Manifests()
        executor = BackupEvidenceRetentionCleanupExecutor(
            manifests, deletions, _Reconciliations(()), self.store,
            completed_at=lambda: NOW + timedelta(seconds=1),
        )
        request = new_backup_evidence_retention_cleanup_request(
            "cleanup-partial", self.execution, now=NOW
        )
        result = executor.resume(self.execution, request, CancellationToken())
        self.assertEqual(result.state, EvidenceRetentionExecutionState.PARTIAL)
        self.assertEqual(result.removed_kinds, ("manifest",))
        self.assertEqual(result.remaining_kinds, ("deletion",))
        self.assertEqual(result.error_code, "cleanup_delete_failed")
        self.assertEqual(manifests.deleted, [deletion])

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


class _Deletion:
    def __init__(self, result_hash):
        self.result_hash = result_hash


class _Deletions:
    def __init__(self, deletion, *, fail_delete=False):
        self.deletion = deletion
        self.deleted = []
        self.fail_delete = fail_delete

    def list_for_host(self, host_id, fingerprint):
        return (self.deletion,)

    def delete(self, deletion):
        if self.fail_delete:
            raise AdapterError("cleanup_delete_failed", "injected")
        self.deleted.append(deletion)


class _Manifests:
    def __init__(self):
        self.deleted = []

    def load(self, deletion):
        return object()

    def delete(self, deletion):
        self.deleted.append(deletion)


class _Reconciliations:
    def __init__(self, results):
        self.results = results

    def list_for_deletion_result(self, result_hash, host_id, fingerprint):
        return self.results

    def delete(self, result):
        raise AssertionError("unexpected reconciliation deletion")
