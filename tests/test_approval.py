import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from llm_manager.application.approval import CreateApprovalRecord
from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import EncryptionInfo
from tests.fixtures import plan


def encrypted_policy() -> EncryptionInfo:
    return EncryptionInfo(True, "AES-256-GCM", 1, "local-master-v1", "local_secret_service")


class CreateApprovalRecordTests(unittest.TestCase):
    def test_binds_all_current_hashes_and_uses_shortest_expiry(self) -> None:
        now = datetime.now(UTC)
        current = replace(
            plan(), backup_policy=encrypted_policy(), expires_at=now + timedelta(minutes=2)
        )
        record = CreateApprovalRecord().execute(
            current, "approval-1", "tester", True, False, now
        )
        self.assertTrue(record.is_valid_for(current, now))
        self.assertEqual(record.change_set_hash, current.change_set.content_hash)
        self.assertEqual(record.backup_policy_hash, current.backup_policy.content_hash)
        self.assertEqual(record.expires_at, current.expires_at)

    def test_plaintext_requires_independent_acknowledgement(self) -> None:
        current = plan()
        with self.assertRaisesRegex(AdapterError, "risk must be acknowledged"):
            CreateApprovalRecord().execute(current, "approval-1", "tester", True, False)
        record = CreateApprovalRecord().execute(
            current, "approval-1", "tester", True, True
        )
        self.assertTrue(record.plaintext_backup_acknowledged)

    def test_rejects_missing_review_change_set_identity_and_stale_plan(self) -> None:
        service = CreateApprovalRecord()
        current = replace(plan(), backup_policy=encrypted_policy())
        with self.assertRaisesRegex(AdapterError, "review confirmation"):
            service.execute(current, "approval-1", "tester", False, False)
        with self.assertRaisesRegex(AdapterError, "change set"):
            service.execute(replace(current, change_set=None), "approval-1", "tester", True, False)
        with self.assertRaisesRegex(AdapterError, "identity"):
            service.execute(current, "", "tester", True, False)
        now = datetime.now(UTC)
        with self.assertRaisesRegex(AdapterError, "expired"):
            service.execute(
                replace(current, expires_at=now - timedelta(seconds=1)),
                "approval-1",
                "tester",
                True,
                False,
                now,
            )


if __name__ == "__main__":
    unittest.main()
