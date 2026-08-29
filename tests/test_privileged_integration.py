import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.domain.enums import ChangeOperation, PlanStatus, Severity, ValidationStatus
from llm_manager.domain.models import (
    ApprovalRecord,
    BackupItem,
    BackupManifest,
    Change,
    ChangeSet,
    LocalizedMessage,
    ValidationResult,
)
from llm_manager.infrastructure.backup import BackupRestoreItem
from llm_manager.infrastructure.helper_backend import LocalSystemHelperBackend
from llm_manager.infrastructure.helper_cli import run_helper
from llm_manager.infrastructure.helper_receipts import HelperReceiptStatus, HelperReceiptStore
from llm_manager.infrastructure.helper_staging import HelperStagingStore
from llm_manager.infrastructure.journal import JournalStatus, LocalOperationJournal
from llm_manager.infrastructure.policykit import LocalPolicyKitInvoker
from llm_manager.infrastructure.privileged_apply import (
    ApprovedHelperRequestFactory,
    PrivilegedRollbackRequestFactory,
    PrivilegedSafeApplyCoordinator,
)
from llm_manager.planning.ollama import DROP_IN_PATH
from tests.fixtures import plan


class PrivilegedBoundaryIntegrationTests(unittest.TestCase):
    def test_coordinator_crosses_staging_cli_receipt_and_backend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory), before=b"old", validation_passes=True)
            outcome = fixture.coordinator.execute(
                fixture.current_plan, fixture.approval, "operation-1", CancellationToken()
            )

            self.assertEqual(outcome.status, PlanStatus.COMMITTED)
            self.assertEqual(fixture.target.read_bytes(), fixture.after)
            journal = fixture.journal.load("operation-1")
            receipt = fixture.receipts.load("operation-1")
            self.assertEqual(journal.status, JournalStatus.COMMITTED)
            self.assertEqual(receipt.status, HelperReceiptStatus.COMPLETED)
            self.assertEqual(journal.request_hash, receipt.request_hash)
            self.assertEqual(
                fixture.service_calls,
                [
                    ("/usr/bin/systemctl", "daemon-reload"),
                    ("/usr/bin/systemctl", "restart", "ollama.service"),
                ],
            )

    def test_runtime_failure_uses_a_separately_receipted_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(Path(directory), before=b"old", validation_passes=False)
            outcome = fixture.coordinator.execute(
                fixture.current_plan, fixture.approval, "operation-1", CancellationToken()
            )

            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertEqual(fixture.target.read_bytes(), b"old")
            journal = fixture.journal.load("operation-1")
            apply_receipt = fixture.receipts.load("operation-1")
            rollback_receipt = fixture.receipts.load("operation-1-rollback")
            self.assertEqual(journal.status, JournalStatus.ROLLED_BACK)
            self.assertEqual(journal.request_hash, apply_receipt.request_hash)
            self.assertEqual(journal.rollback_request_hash, rollback_receipt.request_hash)
            self.assertEqual(rollback_receipt.status, HelperReceiptStatus.COMPLETED)

    def test_daemon_reload_failure_rolls_back_through_the_same_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = _Fixture(
                Path(directory), before=None, validation_passes=True,
                fail_service_call=1,
            )
            outcome = fixture.coordinator.execute(
                fixture.current_plan, fixture.approval, "operation-1", CancellationToken()
            )

            self.assertEqual(outcome.status, PlanStatus.ROLLED_BACK)
            self.assertFalse(fixture.target.exists())
            self.assertEqual(
                fixture.receipts.load("operation-1").status,
                HelperReceiptStatus.FAILED,
            )
            self.assertEqual(
                fixture.receipts.load("operation-1-rollback").status,
                HelperReceiptStatus.COMPLETED,
            )


class _Fixture:
    def __init__(
        self,
        root: Path,
        *,
        before: bytes | None,
        validation_passes: bool,
        fail_service_call: int | None = None,
    ) -> None:
        self.root = root
        self.runtime = root / "run-user"
        self.system_root = root / "system-root"
        self.target = self.system_root / DROP_IN_PATH.removeprefix("/")
        unit_root = self.target.parent.parent
        unit_root.mkdir(parents=True)
        unit_root.chmod(0o755)
        if before is not None:
            self.target.parent.mkdir()
            self.target.parent.chmod(0o755)
            self.target.write_bytes(before)
        self.after = b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n'
        self.service_calls: list[tuple[str, ...]] = []
        self._fail_service_call = fail_service_call
        self.backend = LocalSystemHelperBackend(
            root=self.system_root,
            service_runner=self._service,
            sandbox=True,
        )
        self.receipts = HelperReceiptStore(root / "receipts", sandbox=True)
        uid = os.getuid()
        if uid == 0:
            raise unittest.SkipTest("sandbox PolicyKit boundary requires a non-root invoking user")
        staging_root = self.runtime / str(uid) / "llm-manager" / "helper"
        invoker = LocalPolicyKitInvoker(
            HelperStagingStore(staging_root, owner_uid=uid),
            _CliRunner(self.runtime, self.backend, self.receipts, uid),
        )
        self.current_plan, self.approval = _approved_plan(before, self.after)
        backups = _SandboxBackupStore(root / "backups", before)
        self.journal = LocalOperationJournal(
            root / "journal", (Path("/etc/systemd/system"),)
        )
        self.coordinator = PrivilegedSafeApplyCoordinator(
            backups,
            ApprovedHelperRequestFactory(),
            PrivilegedRollbackRequestFactory(),
            invoker,
            _Validator(validation_passes),
            self.journal,
        )

    def _service(self, argv: tuple[str, ...]) -> int:
        self.service_calls.append(argv)
        if self._fail_service_call == len(self.service_calls):
            return 1
        return 0


class _CliRunner:
    def __init__(self, runtime, backend, receipts, uid):
        self.runtime = runtime
        self.backend = backend
        self.receipts = receipts
        self.uid = uid

    def run(self, command, cancellation):
        operation_id, request_hash = command.argv[-2:]
        results = run_helper(
            operation_id,
            request_hash,
            environ={"PKEXEC_UID": str(self.uid)},
            runtime_base=self.runtime,
            backend=self.backend,
            receipts=self.receipts,
            effective_uid=0,
        )
        completed = all(item.completed for item in results)
        value = {
            "operations": [
                {
                    "completed": item.completed,
                    "error_code": item.error_code,
                    "kind": item.kind.value,
                    "operation_id": item.operation_id,
                }
                for item in results
            ],
            "status": "completed" if completed else "failed",
        }
        stdout = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        return CommandResult(command.argv, 0 if completed else 1, stdout, "", False, 1)


class _SandboxBackupStore:
    def __init__(self, root: Path, before: bytes | None):
        self.root = root
        self.before = before

    def create(self, request, cancellation):
        digest = hashlib.sha256(self.before).hexdigest() if self.before is not None else None
        item = BackupItem(
            DROP_IN_PATH,
            self.before is not None,
            "item" if self.before is not None else None,
            digest,
            0o644 if self.before is not None else None,
            0 if self.before is not None else None,
            0 if self.before is not None else None,
        )
        return BackupManifest(
            request.backup_id,
            "1.0",
            request.plan_id,
            request.change_set.content_hash,
            request.host_id,
            request.host_fingerprint,
            (item,),
            "d" * 64,
            str(self.root),
            request.encryption,
            complete=True,
        )

    def verify(self, manifest, cancellation):
        return (_validation("backup", True),)

    def restore_items(self, manifest, cancellation):
        item = manifest.items[0]
        return (
            BackupRestoreItem(
                item.target, item.existed, self.before, item.sha256,
                item.mode, item.uid, item.gid,
            ),
        )


class _Validator:
    def __init__(self, passed: bool):
        self.passed = passed

    def validate(self, change_set, cancellation):
        return (_validation("runtime", self.passed),)


def _approved_plan(before: bytes | None, after: bytes):
    operation = ChangeOperation.CREATE_FILE if before is None else ChangeOperation.REPLACE_FILE
    rollback = ChangeOperation.REMOVE_CREATED_FILE if before is None else ChangeOperation.REPLACE_FILE
    change = Change(
        "ollama-change",
        DROP_IN_PATH,
        operation,
        "absent" if before is None else "present",
        (("OLLAMA_HOST", "127.0.0.1:11434"),),
        hashlib.sha256(before).hexdigest() if before is not None else None,
        "diff",
        requires_root=True,
        requires_restart=True,
        rollback_operation=rollback,
        validation_checks=("systemd.daemon_reload", "ollama.service.active"),
        replacement_text=after.decode(),
    )
    changes = ChangeSet(
        "ollama-changes", "host-1", (change,), "b" * 64,
        affected_services=("ollama.service",),
    )
    current = replace(plan(), change_set=changes)
    approval = ApprovalRecord(
        "approval", current.plan_id, current.report_hash, changes.content_hash,
        "tester", current.backup_policy.content_hash, True,
    )
    return current, approval


def _validation(check: str, passed: bool) -> ValidationResult:
    return ValidationResult(
        check,
        "integration",
        check,
        ValidationStatus.PASSED if passed else ValidationStatus.FAILED,
        "passed",
        "passed" if passed else "failed",
        Severity.INFO if passed else Severity.HIGH,
        LocalizedMessage("test.validation"),
    )


if __name__ == "__main__":
    unittest.main()
