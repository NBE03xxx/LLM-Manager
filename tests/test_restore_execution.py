from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.application.restore_preflight import PrepareLocalRestore
from llm_manager.application.restore_preview import CreateRestoreApproval, CreateRestorePreview
from llm_manager.infrastructure.audit import LocalAuditLog
from llm_manager.infrastructure.local_restore import SingleTargetLocalRestoreExecutor
from llm_manager.infrastructure.restore_execution import (
    LocalRestoreCoordinator,
    RestoreExecutionPersistenceError,
    RestoreExecutionState,
    RestoreExecutionStore,
)
from tests.test_restore_preflight import _fixture


class RestoreExecutionTests(unittest.TestCase):
    def _coordinator(self, root: Path):
        store, manifest, preview, approval = _fixture(root)
        authorization = PrepareLocalRestore(store).execute(
            manifest.host_id, manifest.backup_id, preview, approval, CancellationToken()
        )
        evidence = RestoreExecutionStore(root / "restore-executions")
        audit = LocalAuditLog(root / "audit")
        return LocalRestoreCoordinator(
            SingleTargetLocalRestoreExecutor(store), evidence, audit
        ), authorization, manifest, evidence, audit

    def test_persists_attempt_audit_and_committed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, authorization, manifest, _store, audit = self._coordinator(Path(directory))
            Path(manifest.items[0].target).write_text("new", encoding="utf-8")
            preview = CreateRestorePreview().execute(manifest)
            approval = CreateRestoreApproval().execute(
                preview, "approval-new", "tester", True
            )
            authorization = PrepareLocalRestore(coordinator.executor.backups).execute(
                manifest.host_id, manifest.backup_id, preview, approval, CancellationToken()
            )
            result = coordinator.execute(authorization, CancellationToken())
            self.assertEqual(result.state, RestoreExecutionState.COMMITTED)
            self.assertEqual(Path(manifest.items[0].target).read_text(encoding="utf-8"), "old")
            self.assertEqual(tuple(item.event_type for item in audit.read_all()), (
                "restore.started", "restore.committed",
            ))
            self.assertEqual(
                coordinator.store.load_evidence(authorization.authorization_hash), result
            )
            with self.assertRaisesRegex(AdapterError, "already consumed"):
                coordinator.execute(authorization, CancellationToken())

    def test_attempt_persistence_failure_prevents_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, authorization, manifest, _store, _audit = self._coordinator(Path(directory))
            target = Path(manifest.items[0].target)
            coordinator.store = _AttemptFailStore()
            with self.assertRaises(OSError):
                coordinator.execute(authorization, CancellationToken())
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_restart_load_rejects_tamper_and_unsafe_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator, authorization, manifest, store, _audit = self._coordinator(root)
            result = coordinator.execute(authorization, CancellationToken())
            restarted = RestoreExecutionStore(root / "restore-executions")
            self.assertEqual(restarted.load_evidence(authorization.authorization_hash), result)
            path = root / "restore-executions" / f"{authorization.authorization_hash}.result.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(AdapterError) as caught:
                restarted.load_evidence(authorization.authorization_hash)
            self.assertEqual(caught.exception.code, "invalid_restore_evidence")
            attempt = root / "restore-executions" / f"{authorization.authorization_hash}.attempt.json"
            attempt.chmod(0o644)
            with self.assertRaises(AdapterError) as caught:
                restarted.load_attempt(authorization.authorization_hash)
            self.assertEqual(caught.exception.code, "unsafe_restore_execution_store")

    def test_strict_list_rejects_unknown_and_orphan_result_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            coordinator, authorization, _manifest, store, _audit = self._coordinator(root)
            coordinator.execute(authorization, CancellationToken())
            unknown = root / "restore-executions" / "README"
            unknown.write_text("unknown", encoding="utf-8")
            with self.assertRaises(AdapterError) as caught:
                store.list_strict()
            self.assertEqual(caught.exception.code, "unsafe_restore_execution_store")
            unknown.unlink()
            attempt = root / "restore-executions" / f"{authorization.authorization_hash}.attempt.json"
            attempt.unlink()
            with self.assertRaises(AdapterError) as caught:
                store.list_strict()
            self.assertEqual(caught.exception.code, "invalid_restore_evidence")

    def test_result_persistence_failure_exposes_committed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, authorization, manifest, _store, _audit = self._coordinator(Path(directory))
            target = Path(manifest.items[0].target)
            target.write_text("new", encoding="utf-8")
            preview = CreateRestorePreview().execute(manifest)
            approval = CreateRestoreApproval().execute(preview, "approval-new", "tester", True)
            authorization = PrepareLocalRestore(coordinator.executor.backups).execute(
                manifest.host_id, manifest.backup_id, preview, approval, CancellationToken()
            )
            coordinator.store = _ResultFailStore()
            with self.assertRaises(RestoreExecutionPersistenceError) as caught:
                coordinator.execute(authorization, CancellationToken())
            self.assertEqual(caught.exception.evidence.state, RestoreExecutionState.COMMITTED)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_start_audit_failure_consumes_attempt_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, authorization, manifest, store, _audit = self._coordinator(Path(directory))
            coordinator.audit = _FailAudit(1)
            target = Path(manifest.items[0].target)
            with self.assertRaises(AdapterError):
                coordinator.execute(authorization, CancellationToken())
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(
                store.load_attempt(authorization.authorization_hash).authorization_hash,
                authorization.authorization_hash,
            )
            with self.assertRaises(AdapterError) as caught:
                coordinator.execute(authorization, CancellationToken())
            self.assertEqual(caught.exception.code, "restore_authorization_consumed")
            views = store.list_strict()
            self.assertEqual(len(views), 1)
            self.assertEqual(views[0].state, "attempt_only")
            self.assertTrue(views[0].requires_attention)

    def test_commit_audit_failure_persists_unknown_and_exposes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, authorization, manifest, store, _audit = self._coordinator(Path(directory))
            target = Path(manifest.items[0].target)
            target.write_text("new", encoding="utf-8")
            preview = CreateRestorePreview().execute(manifest)
            approval = CreateRestoreApproval().execute(preview, "approval-new", "tester", True)
            authorization = PrepareLocalRestore(coordinator.executor.backups).execute(
                manifest.host_id, manifest.backup_id, preview, approval, CancellationToken()
            )
            coordinator.audit = _FailAudit(2)
            with self.assertRaises(RestoreExecutionPersistenceError) as caught:
                coordinator.execute(authorization, CancellationToken())
            self.assertEqual(caught.exception.evidence.state, RestoreExecutionState.UNKNOWN)
            self.assertEqual(target.read_text(encoding="utf-8"), "old")
            self.assertEqual(
                store.load_evidence(authorization.authorization_hash).state,
                RestoreExecutionState.UNKNOWN,
            )


class _AttemptFailStore:
    def save_attempt(self, _value):
        raise OSError("injected attempt failure")


class _ResultFailStore:
    def save_attempt(self, value):
        return value.with_hash()

    def save_evidence(self, _value):
        raise OSError("injected result failure")


class _FailAudit:
    def __init__(self, fail_at):
        self.calls = 0
        self.fail_at = fail_at

    def append(self, _event_type, _correlation_id, _fields):
        self.calls += 1
        if self.calls == self.fail_at:
            raise AdapterError("audit_failed", "injected audit failure")


if __name__ == "__main__":
    unittest.main()
