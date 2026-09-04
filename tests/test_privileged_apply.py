import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import ChangeOperation, PlanStatus, Severity, ValidationStatus
from llm_manager.domain.models import ApprovalRecord, BackupItem, BackupManifest, Change, ChangeSet, EncryptionInfo, LocalizedMessage, ValidationResult
from llm_manager.infrastructure.backup import BackupRestoreItem
from llm_manager.infrastructure.helper_executor import HelperOperationResult
from llm_manager.infrastructure.helper_protocol import HelperOperationKind
from llm_manager.infrastructure.journal import JournalStatus, LocalOperationJournal
from llm_manager.infrastructure.privileged_apply import ApprovedHelperRequestFactory, LocalPrivilegedApplyService, PrivilegedRollbackRequestFactory, PrivilegedSafeApplyCoordinator
from llm_manager.planning.ollama import DROP_IN_PATH
from tests.fixtures import plan


def _approved():
    content = '[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n'
    change = Change(
        "ollama-change", DROP_IN_PATH, ChangeOperation.CREATE_FILE, "absent",
        (("OLLAMA_HOST", "127.0.0.1:11434"),), None, "diff",
        requires_root=True, requires_restart=True,
        rollback_operation=ChangeOperation.REMOVE_CREATED_FILE,
        validation_checks=("systemd.daemon_reload", "ollama.service.active"),
        replacement_text=content,
    )
    changes = ChangeSet("ollama-changes", "host-1", (change,), "b" * 64, affected_services=("ollama.service",))
    current = replace(plan(), change_set=changes)
    approval = ApprovalRecord("approval", current.plan_id, current.report_hash, changes.content_hash, "tester", current.backup_policy.content_hash, True)
    return current, approval, content


class ApprovedHelperRequestFactoryTests(unittest.TestCase):
    def test_binds_approved_plan_and_builds_fixed_operation_sequence(self) -> None:
        current, approval, content = _approved()
        prepared = ApprovedHelperRequestFactory().prepare(current, approval, "operation-1")
        request = prepared.request
        self.assertEqual(request.plan_id, current.plan_id)
        self.assertEqual(request.change_set_hash, current.change_set.content_hash)
        self.assertEqual([item.kind.value for item in request.operations], ["atomic_replace", "daemon_reload", "restart_unit"])
        self.assertEqual(request.operations[0].target, DROP_IN_PATH)
        self.assertEqual(request.operations[0].staged_content_hash, hashlib.sha256(content.encode()).hexdigest())
        self.assertEqual(prepared.staged_contents, (("operation-1:write", content.encode()),))

    def test_rejects_invalid_approval_and_non_allowlisted_plan(self) -> None:
        current, approval, _ = _approved()
        with self.assertRaises(AdapterError):
            ApprovedHelperRequestFactory().prepare(current, replace(approval, change_set_hash="c" * 64), "operation-1")
        unsafe_change = replace(current.change_set.changes[0], target="/etc/passwd")
        unsafe_set = replace(current.change_set, changes=(unsafe_change,))
        with self.assertRaises(AdapterError):
            ApprovedHelperRequestFactory().prepare(replace(current, change_set=unsafe_set), approval, "operation-1")

    def test_service_passes_only_prepared_request_to_invoker(self) -> None:
        current, approval, _ = _approved()
        invoker = _Invoker()
        readiness = _Readiness(True)
        results = LocalPrivilegedApplyService(ApprovedHelperRequestFactory(), invoker, readiness).execute(current, approval, "operation-1", CancellationToken())
        self.assertEqual(results, ())
        self.assertEqual(invoker.request.plan_id, current.plan_id)
        self.assertEqual(invoker.contents[0][0], "operation-1:write")
        self.assertEqual(readiness.calls, 1)

    def test_service_rechecks_helper_before_invocation(self) -> None:
        current, approval, _ = _approved()
        invoker = _Invoker()
        with self.assertRaises(AdapterError) as caught:
            LocalPrivilegedApplyService(
                ApprovedHelperRequestFactory(), invoker, _Readiness(False)
            ).execute(current, approval, "operation-1", CancellationToken())
        self.assertEqual(caught.exception.code, "privileged_helper_unavailable")
        self.assertFalse(hasattr(invoker, "request"))

    def test_manifest_binding_rejects_another_change_set(self) -> None:
        current, approval, _ = _approved()
        item = BackupItem(DROP_IN_PATH, False, None, None)
        manifest = BackupManifest(
            "operation-1", "1.0", current.plan_id, "c" * 64,
            current.change_set.host_id, None, (item,), "d" * 64, "/tmp/backup",
            current.backup_policy, complete=True,
        )
        with self.assertRaises(AdapterError) as caught:
            ApprovedHelperRequestFactory().prepare(
                current, approval, "operation-1", manifest=manifest
            )
        self.assertEqual(caught.exception.code, "workflow_binding_mismatch")


class PrivilegedSafeApplyCoordinatorTests(unittest.TestCase):
    def test_policykit_denial_does_not_invoke_rollback_helper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, backend, _, journal, current, approval = self._workflow(
                Path(directory), b"old"
            )

            def deny(*_args):
                raise AdapterError("privilege_denied", "dismissed")

            backend.invoke = deny
            outcome = coordinator.execute(
                current, approval, "operation-1", CancellationToken()
            )

            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertEqual(journal.load("operation-1").status, JournalStatus.ROLLED_BACK)
            self.assertEqual(backend.content, b"old")

    def test_helper_change_before_apply_stops_without_invoking_or_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            readiness = _Readiness(True, False)
            coordinator, backend, backups, journal, current, approval = self._workflow(
                Path(directory), b"old", readiness=readiness
            )
            outcome = coordinator.execute(current, approval, "operation-1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.APPROVED)
            self.assertIsNotNone(outcome.manifest)
            self.assertEqual(readiness.calls, 2)
            self.assertEqual(backups.create_calls, 1)
            self.assertEqual(backend.requests, [])
            with self.assertRaises(AdapterError):
                journal.load("operation-1")

    def test_unready_helper_stops_before_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, backend, backups, _, current, approval = self._workflow(
                Path(directory), b"old", readiness=_Readiness(False)
            )
            outcome = coordinator.execute(current, approval, "operation-1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.APPROVED)
            self.assertIsNone(outcome.manifest)
            self.assertEqual(backups.create_calls, 0)
            self.assertEqual(backend.requests, [])

    def test_success_binds_backup_approval_request_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, backend, backups, journal, current, approval = self._workflow(Path(directory), b"old")
            outcome = coordinator.execute(current, approval, "operation-1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.COMMITTED)
            self.assertEqual(backend.content, current.change_set.changes[0].replacement_text.encode())
            record = journal.load("operation-1")
            self.assertEqual(record.approval_id, approval.approval_id)
            self.assertEqual(record.backup_id, outcome.manifest.backup_id)
            self.assertEqual(record.manifest_hash, outcome.manifest.manifest_hash)
            self.assertEqual(record.request_hash, backend.requests[0].request_hash)
            self.assertEqual(backend.requests[0].manifest_hash, outcome.manifest.manifest_hash)
            self.assertEqual(outcome.manifest.change_set_hash, current.change_set.content_hash)

    def test_apply_stage_failures_and_runtime_failure_rollback(self) -> None:
        for failure in ("atomic_replace", "daemon_reload", "restart_unit", "validation"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                validator = _RuntimeValidator(failure != "validation")
                coordinator, backend, _, journal, current, approval = self._workflow(Path(directory), b"old", validator)
                backend.fail_apply = failure if failure != "validation" else None
                outcome = coordinator.execute(current, approval, "operation-1", CancellationToken())
                self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
                self.assertEqual(backend.content, b"old")
                self.assertEqual(journal.load("operation-1").status, JournalStatus.ROLLED_BACK)
                if failure == "atomic_replace":
                    self.assertEqual(len(backend.requests), 1)
                else:
                    self.assertEqual([item.kind for item in backend.requests[-1].operations], [HelperOperationKind.RESTORE_FILE, HelperOperationKind.DAEMON_RELOAD, HelperOperationKind.RESTART_UNIT])
                    self.assertEqual(journal.load("operation-1").rollback_request_hash, backend.requests[-1].request_hash)

    def test_created_file_rollback_removes_then_reloads_and_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            coordinator, backend, _, _, current, approval = self._workflow(Path(directory), None, _RuntimeValidator(False))
            outcome = coordinator.execute(current, approval, "operation-1", CancellationToken())
            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertIsNone(backend.content)
            self.assertEqual([item.kind for item in backend.requests[-1].operations], [HelperOperationKind.REMOVE_CREATED_FILE, HelperOperationKind.DAEMON_RELOAD, HelperOperationKind.RESTART_UNIT])

    def test_rollback_failures_require_recovery(self) -> None:
        for failure in ("restore_file", "daemon_reload", "restart_unit"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                coordinator, backend, _, journal, current, approval = self._workflow(Path(directory), b"old", _RuntimeValidator(False))
                backend.fail_rollback = failure
                outcome = coordinator.execute(current, approval, "operation-1", CancellationToken())
                self.assertEqual(outcome.status, PlanStatus.RECOVERY_REQUIRED)
                self.assertEqual(journal.load("operation-1").status, JournalStatus.RECOVERY_REQUIRED)

    @staticmethod
    def _workflow(root: Path, before: bytes | None, validator=None, readiness=None):
        current, approval, _ = _approved()
        change = current.change_set.changes[0]
        operation = ChangeOperation.CREATE_FILE if before is None else ChangeOperation.REPLACE_FILE
        rollback = ChangeOperation.REMOVE_CREATED_FILE if before is None else ChangeOperation.REPLACE_FILE
        change = replace(change, operation=operation, rollback_operation=rollback, before_hash=hashlib.sha256(before).hexdigest() if before is not None else None)
        changes = replace(current.change_set, changes=(change,))
        current = replace(current, change_set=changes)
        approval = replace(approval, change_set_hash=changes.content_hash)
        backend = _WorkflowInvoker(before)
        backups = _BackupStore(backend, root)
        journal = LocalOperationJournal(root / "journal", (Path("/etc/systemd/system"),))
        coordinator = PrivilegedSafeApplyCoordinator(
            backups, ApprovedHelperRequestFactory(), PrivilegedRollbackRequestFactory(),
            backend, validator or _RuntimeValidator(True), journal,
            readiness or _Readiness(True),
        )
        return coordinator, backend, backups, journal, current, approval


class _Invoker:
    def invoke(self, request, staged_contents, cancellation):
        self.request = request
        self.contents = staged_contents
        return ()


class _BackupStore:
    def __init__(self, backend, root):
        self.backend = backend
        self.root = root
        self.create_calls = 0

    def create(self, request, cancellation):
        self.create_calls += 1
        before = self.backend.content
        item = BackupItem(DROP_IN_PATH, before is not None, "item" if before is not None else None, hashlib.sha256(before).hexdigest() if before is not None else None, 0o644 if before is not None else None, 0 if before is not None else None, 0 if before is not None else None)
        return BackupManifest(request.backup_id, "1.0", request.plan_id, request.change_set.content_hash, request.host_id, request.host_fingerprint, (item,), "d" * 64, str(self.root), request.encryption, complete=True)

    def verify(self, manifest, cancellation):
        return (_validation("backup", True),)

    def restore_items(self, manifest, cancellation):
        item = manifest.items[0]
        return (BackupRestoreItem(item.target, item.existed, self.backend.original, item.sha256, item.mode, item.uid, item.gid),)


class _WorkflowInvoker:
    def __init__(self, content):
        self.content = content
        self.original = content
        self.fail_apply = None
        self.fail_rollback = None
        self.requests = []

    def invoke(self, request, staged_contents, cancellation):
        self.requests.append(request)
        staged = dict(staged_contents)
        rollback = request.operation_id.endswith("-rollback")
        failure = self.fail_rollback if rollback else self.fail_apply
        results = []
        stopped = False
        for operation in request.operations:
            if stopped:
                results.append(HelperOperationResult(operation.operation_id, operation.kind, False, "not_executed"))
                continue
            if failure == operation.kind.value:
                results.append(HelperOperationResult(operation.operation_id, operation.kind, False, "injected_failure"))
                stopped = True
                continue
            if operation.kind in {HelperOperationKind.ATOMIC_REPLACE, HelperOperationKind.RESTORE_FILE}:
                self.content = staged[operation.operation_id]
            elif operation.kind is HelperOperationKind.REMOVE_CREATED_FILE:
                self.content = None
            results.append(HelperOperationResult(operation.operation_id, operation.kind, True))
        return tuple(results)


class _RuntimeValidator:
    def __init__(self, passed):
        self.passed = passed

    def validate(self, change_set, cancellation):
        return (_validation("runtime", self.passed),)


class _Readiness:
    def __init__(self, *states):
        self.states = states
        self.calls = 0

    def assert_ready(self, cancellation):
        state = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        if not state:
            raise AdapterError("privileged_helper_unavailable", "helper is not ready")


def _validation(check, passed):
    return ValidationResult(check, "test", check, ValidationStatus.PASSED if passed else ValidationStatus.FAILED, "passed", "passed" if passed else "failed", Severity.INFO if passed else Severity.HIGH, LocalizedMessage("test.validation"))


if __name__ == "__main__":
    unittest.main()
