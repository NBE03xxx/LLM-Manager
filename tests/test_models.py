import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

from llm_manager.domain.enums import ChangeOperation, HostKind, ProbeStatus, ValidationStatus
from llm_manager.domain.errors import InvariantViolation
from llm_manager.domain.models import (
    ApprovalRecord,
    Change,
    ChangeSet,
    DiskInfo,
    GPUInfo,
    HardwareInfo,
    HostCapabilities,
    HostInfo,
    ProbeResult,
    ValidationResult,
)

from tests.fixtures import plan


class ModelInvariantTests(unittest.TestCase):
    def test_models_are_frozen(self) -> None:
        host = HostInfo("local", HostKind.LOCAL, "Local", HostCapabilities())
        with self.assertRaises(FrozenInstanceError):
            host.display_name = "Changed"  # type: ignore[misc]

    def test_ssh_host_requires_alias(self) -> None:
        with self.assertRaises(InvariantViolation):
            HostInfo("ssh", HostKind.SSH, "Remote", HostCapabilities())

    def test_probe_success_requires_value(self) -> None:
        with self.assertRaises(InvariantViolation):
            ProbeResult[object](ProbeStatus.OK)

    def test_probe_failure_rejects_value(self) -> None:
        with self.assertRaises(InvariantViolation):
            ProbeResult(ProbeStatus.TIMEOUT, value="stale")

    def test_disk_rejects_free_space_above_total(self) -> None:
        with self.assertRaises(InvariantViolation):
            DiskInfo("/", 10, 11)

    def test_gpu_rejects_invalid_utilization(self) -> None:
        with self.assertRaises(InvariantViolation):
            GPUInfo("0", "NVIDIA", "GPU", utilization_pct=101)

    def test_hardware_rejects_invalid_memory(self) -> None:
        with self.assertRaises(InvariantViolation):
            HardwareInfo("CPU", 8, 100, 101, 0, 0)

    def test_change_ids_must_be_unique(self) -> None:
        change = Change(
            "same", "/x", ChangeOperation.REPLACE_FILE, "a", "b", "hash", "diff"
        )
        with self.assertRaises(InvariantViolation):
            ChangeSet("set", "host", (change, change), "hash")

    def test_change_rejects_untyped_operation(self) -> None:
        with self.assertRaises(InvariantViolation):
            Change("id", "/x", "replace_file", "a", "b", "hash", "diff")  # type: ignore[arg-type]

    def test_validation_duration_must_be_non_negative(self) -> None:
        with self.assertRaises(InvariantViolation):
            ValidationResult("id", "host", "api", ValidationStatus.PASSED, duration_ms=-1)


class ApprovalTests(unittest.TestCase):
    def test_approval_is_bound_to_plan_and_hashes(self) -> None:
        item = plan()
        approval = ApprovalRecord(
            approval_id="approval-1",
            plan_id=item.plan_id,
            report_hash=item.report_hash,
            change_set_hash=item.change_set.content_hash,  # type: ignore[union-attr]
            actor="tester",
            backup_policy_hash=item.backup_policy.content_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        self.assertTrue(approval.is_valid_for(item))

    def test_expired_approval_is_invalid(self) -> None:
        item = plan()
        approval = ApprovalRecord(
            approval_id="approval-1",
            plan_id=item.plan_id,
            report_hash=item.report_hash,
            change_set_hash="changes-hash",
            actor="tester",
            backup_policy_hash=item.backup_policy.content_hash,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        self.assertFalse(approval.is_valid_for(item))


if __name__ == "__main__":
    unittest.main()
