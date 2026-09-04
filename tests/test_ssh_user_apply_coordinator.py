from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import PlanStatus, ValidationStatus
from llm_manager.domain.models import ValidationResult
from llm_manager.infrastructure.journal import JournalStatus, LocalOperationJournal
from llm_manager.infrastructure.ssh_user_apply_coordinator import SshUserSafeApplyCoordinator
from llm_manager.infrastructure.ssh_user_apply_preparation import (
    PrepareSshUserApply, PrepareSshUserRollback,
)
from tests.test_ssh_user_apply_preparation import (
    ABSOLUTE, RELATIVE, NOW, _Backups, _bound_inputs,
)


class SshUserSafeApplyCoordinatorTests(unittest.TestCase):
    def test_commits_after_apply_result_and_runtime_validation(self) -> None:
        with _Case() as case:
            outcome = case.execute()
            self.assertEqual(outcome.status, PlanStatus.COMMITTED)
            self.assertEqual(case.apply.calls, ["apply"])
            self.assertEqual(case.rollback.calls, [])
            self.assertEqual(case.journal.load("operation-1").status, JournalStatus.COMMITTED)
            self.assertEqual(case.audit.events[-1], "apply.committed")

    def test_validation_failure_rolls_back_with_bound_request(self) -> None:
        with _Case(validation_passed=False) as case:
            outcome = case.execute()
            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertEqual(case.rollback.calls, ["rollback"])
            journal = case.journal.load("operation-1")
            self.assertEqual(journal.status, JournalStatus.ROLLED_BACK)
            self.assertIsNotNone(journal.rollback_request_hash)

    def test_ambiguous_apply_without_result_requires_recovery_and_never_rolls_back(self) -> None:
        with _Case(apply_fails=True, apply_read_fails=True) as case:
            outcome = case.execute()
            self.assertEqual(outcome.status, PlanStatus.RECOVERY_REQUIRED)
            self.assertEqual(case.apply.calls, ["apply", "read"])
            self.assertEqual(case.rollback.calls, [])
            self.assertEqual(case.journal.load("operation-1").status, JournalStatus.RECOVERY_REQUIRED)

    def test_disconnect_reconciles_apply_and_rollback_results_without_retry(self) -> None:
        with _Case(
            validation_passed=False, apply_fails=True, rollback_fails=True
        ) as case:
            outcome = case.execute()
            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertEqual(case.apply.calls, ["apply", "read"])
            self.assertEqual(case.rollback.calls, ["rollback", "read"])

    def test_user_cancellation_after_apply_does_not_cancel_safety_rollback(self) -> None:
        with _Case(validation_passed=False, cancel_during_validation=True) as case:
            outcome = case.execute()
            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertEqual(case.rollback.calls, ["rollback"])

    def test_unverified_backup_and_unrecoverable_rollback_fail_closed(self) -> None:
        with _Case(remote_passed=False) as case:
            outcome = case.execute()
            self.assertEqual(outcome.status, PlanStatus.APPROVED)
            self.assertEqual(case.apply.calls, [])
        with _Case(
            validation_passed=False, rollback_fails=True, rollback_read_fails=True
        ) as case:
            outcome = case.execute()
            self.assertEqual(outcome.status, PlanStatus.RECOVERY_REQUIRED)
            self.assertEqual(case.journal.load("operation-1").status, JournalStatus.RECOVERY_REQUIRED)


class _Case:
    def __init__(
        self, *, validation_passed=True, remote_passed=True,
        apply_fails=False, apply_read_fails=False,
        rollback_fails=False, rollback_read_fails=False, cancel_during_validation=False,
    ):
        self.temp = tempfile.TemporaryDirectory()
        self.report, self.plan, self.approval = _bound_inputs()
        self.backups = _Backups(remote_passed=remote_passed)
        self.apply = _ApplyTransport(apply_fails, apply_read_fails)
        self.rollback = _RollbackTransport(rollback_fails, rollback_read_fails)
        self.validator = _Validator(validation_passed, cancel_during_validation)
        self.journal = LocalOperationJournal(
            Path(self.temp.name) / "journal", (Path(ABSOLUTE).parent,)
        )
        self.audit = _Audit()
        self.coordinator = SshUserSafeApplyCoordinator(
            PrepareSshUserApply(self.backups, {ABSOLUTE: RELATIVE}, lambda: NOW),
            PrepareSshUserRollback(self.backups, lambda: NOW),
            self.apply, self.rollback, self.validator, self.journal, self.audit,
        )

    def __enter__(self): return self
    def __exit__(self, *_args): self.temp.cleanup()
    def execute(self):
        return self.coordinator.execute(
            self.plan, self.report, self.approval, "operation-1", CancellationToken()
        )


class _ApplyTransport:
    def __init__(self, fail, read_fail):
        self.fail, self.read_fail, self.calls = fail, read_fail, []
    def apply(self, request, payload, cancellation):
        self.calls.append("apply")
        if self.fail: raise AdapterError("disconnect", "ambiguous Apply")
        return object()
    def read_result(self, request, cancellation):
        self.calls.append("read")
        if self.read_fail: raise AdapterError("missing_result", "no Apply result")
        return object()


class _RollbackTransport:
    def __init__(self, fail, read_fail):
        self.fail, self.read_fail, self.calls = fail, read_fail, []
    def rollback(self, request, content, cancellation):
        self.calls.append("rollback")
        if self.fail: raise AdapterError("disconnect", "ambiguous rollback")
        return object()
    def read_result(self, request, cancellation):
        self.calls.append("read")
        if self.read_fail: raise AdapterError("missing_result", "no rollback result")
        return object()


class _Validator:
    def __init__(self, passed, cancel=False): self.passed, self.cancel = passed, cancel
    def validate(self, change_set, cancellation):
        if self.cancel:
            cancellation.cancel()
        return (ValidationResult(
            "runtime", "ssh", "runtime",
            ValidationStatus.PASSED if self.passed else ValidationStatus.FAILED,
        ),)


class _Audit:
    def __init__(self): self.events = []
    def append(self, event, correlation, fields): self.events.append(event)


if __name__ == "__main__":
    unittest.main()
