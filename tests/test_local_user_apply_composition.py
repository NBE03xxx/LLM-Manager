import hashlib
import os
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import ChangeOperation, HostKind, PlanStatus
from llm_manager.domain.models import ApprovalRecord, Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.ui.composition import LocalUserApplyTaskFactory
from tests.fixtures import plan


class _TestKeys:
    def get_key(self, _key_reference: str, _key_scope: str) -> bytes:
        return b"k" * 32


class LocalUserApplyTaskFactoryTests(unittest.TestCase):
    def test_encrypted_sandbox_apply_writes_backup_audit_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            target_root = config / "opencode"
            target_root.mkdir(parents=True)
            target = target_root / "opencode.json"
            original = '{"model":"old"}'
            replacement = '{"model":"new"}'
            target.write_text(original, encoding="utf-8")
            digest = hashlib.sha256(original.encode()).hexdigest()
            change_set = ChangeSet(
                "cs-local",
                "local:test",
                (Change("change-local", str(target), ChangeOperation.REPLACE_FILE,
                        "old", "new", digest, "masked", source_span=(0, len(original)),
                        replacement_text=replacement),),
                "c" * 64,
            )
            encryption = EncryptionInfo(
                True, "AES-256-GCM", 1, "local-master-v1", "local_secret_service"
            )
            current = replace(plan(), change_set=change_set, backup_policy=encryption)
            approval = ApprovalRecord(
                "approval-local", current.plan_id, current.report_hash,
                change_set.content_hash, "tester", encryption.content_hash,
            )
            factory = LocalUserApplyTaskFactory(
                (HostCandidate("local:test", HostKind.LOCAL, "Local"),),
                SubprocessRunner(ProcessPolicy(frozenset())), config, root / "state",
                lambda: _TestKeys(),
            )

            outcome = factory(current, approval)(CancellationToken())

            self.assertEqual(outcome.status, PlanStatus.COMMITTED)
            self.assertEqual(target.read_text(encoding="utf-8"), replacement)
            app_state = root / "state" / "llm-manager"
            self.assertTrue(any((app_state / "backups").rglob("*.enc")))
            self.assertTrue((app_state / "audit" / "HEAD").is_file())
            self.assertTrue(any((app_state / "journal").glob("*.json")))
            self.assertEqual(app_state.stat().st_mode & 0o777, 0o700)

    def test_rejects_remote_root_and_outside_targets_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            (config / "opencode").mkdir(parents=True)
            factory = LocalUserApplyTaskFactory(
                (HostCandidate("local:test", HostKind.LOCAL, "Local"),
                 HostCandidate("ssh:test", HostKind.SSH, "SSH", "test")),
                SubprocessRunner(ProcessPolicy(frozenset())), config, root / "state",
            )
            outside = replace(plan().change_set.changes[0],
                              target=str(root / "outside.json"), requires_root=False)
            cases = (
                ("local:test", outside, "target_not_allowed"),
                ("local:test", replace(outside, target=str(config / "opencode" / "x"),
                                       requires_root=True), "rejects_root"),
                ("ssh:test", replace(outside, target=str(config / "opencode" / "x")),
                 "requires_local"),
            )
            for host_id, change, error in cases:
                change_set = ChangeSet("cs", host_id, (change,), "c" * 64)
                with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                    factory(replace(plan(), change_set=change_set), MagicMock())

    def test_rejects_symlinked_application_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            config = root / "config"
            config.mkdir()
            (config / "opencode").symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink_rejected"):
                LocalUserApplyTaskFactory((), MagicMock(), config, root / "state")

    def test_rejects_preexisting_non_private_state_root_at_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            target_root = config / "opencode"
            target_root.mkdir(parents=True)
            target = target_root / "opencode.json"
            target.write_text("{}", encoding="utf-8")
            change = replace(
                plan().change_set.changes[0], target=str(target),
                before_hash=hashlib.sha256(b"{}").hexdigest(), requires_root=False,
                source_span=(0, 2), replacement_text="{}",
            )
            change_set = ChangeSet("cs", "local:test", (change,), "c" * 64)
            current = replace(plan(), change_set=change_set)
            approval = ApprovalRecord(
                "approval", current.plan_id, current.report_hash,
                change_set.content_hash, "tester", current.backup_policy.content_hash, True,
            )
            state = root / "state" / "llm-manager"
            state.mkdir(parents=True)
            os.chmod(state, 0o755)
            factory = LocalUserApplyTaskFactory(
                (HostCandidate("local:test", HostKind.LOCAL, "Local"),),
                SubprocessRunner(ProcessPolicy(frozenset())), config, root / "state",
            )
            with self.assertRaisesRegex(ValueError, "private_state_root_unsafe"):
                factory(current, approval)(CancellationToken())

    def test_invalid_approval_does_not_create_state_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            target_root = config / "opencode"
            target_root.mkdir(parents=True)
            target = target_root / "opencode.json"
            target.write_text("{}", encoding="utf-8")
            change = replace(
                plan().change_set.changes[0], target=str(target), requires_root=False
            )
            current = replace(
                plan(), change_set=ChangeSet("cs", "local:test", (change,), "c" * 64)
            )
            factory = LocalUserApplyTaskFactory(
                (HostCandidate("local:test", HostKind.LOCAL, "Local"),),
                SubprocessRunner(ProcessPolicy(frozenset())), config, root / "state",
            )
            with self.assertRaisesRegex(AdapterError, "approval"):
                factory(current, MagicMock(is_valid_for=lambda _plan: False))(
                    CancellationToken()
                )
            self.assertFalse((root / "state" / "llm-manager").exists())


@unittest.skipUnless(
    os.environ.get("LLM_MANAGER_SECRET_SERVICE_GATE") == "1",
    "explicit Secret Service desktop Gate is disabled",
)
class LocalUserApplySecretServiceGateTests(unittest.TestCase):
    def test_real_secret_service_encrypted_apply_and_key_cleanup(self) -> None:
        import secretstorage

        reference = f"phase5-local-user-gate-{uuid.uuid4().hex}"
        attributes = {
            "application": "llm-manager",
            "purpose": "backup-encryption",
            "key-reference": reference,
        }
        connection = secretstorage.dbus_init()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / "config"
                target_root = config / "opencode"
                target_root.mkdir(parents=True)
                target = target_root / "opencode.json"
                original = '{"model":"old"}'
                replacement = '{"model":"new"}'
                target.write_text(original, encoding="utf-8")
                change = Change(
                    "change-local", str(target), ChangeOperation.REPLACE_FILE,
                    "old", "new", hashlib.sha256(original.encode()).hexdigest(),
                    "masked", source_span=(0, len(original)),
                    replacement_text=replacement,
                )
                change_set = ChangeSet(
                    "cs-local", "local:test", (change,), "c" * 64
                )
                encryption = EncryptionInfo(
                    True, "AES-256-GCM", 1, reference, "local_secret_service"
                )
                current = replace(plan(), change_set=change_set, backup_policy=encryption)
                approval = ApprovalRecord(
                    "approval-local", current.plan_id, current.report_hash,
                    change_set.content_hash, "tester", encryption.content_hash,
                )
                factory = LocalUserApplyTaskFactory(
                    (HostCandidate("local:test", HostKind.LOCAL, "Local"),),
                    SubprocessRunner(ProcessPolicy(frozenset())), config, root / "state",
                )

                outcome = factory(current, approval)(CancellationToken())

                self.assertEqual(outcome.status, PlanStatus.COMMITTED)
                self.assertEqual(target.read_text(encoding="utf-8"), replacement)
                items = list(secretstorage.search_items(connection, attributes))
                self.assertEqual(len(items), 1)
                self.assertEqual(len(items[0].get_secret()), 32)
                envelope = next(
                    (root / "state" / "llm-manager" / "backups").rglob("*.enc")
                ).read_bytes()
                self.assertNotIn(original.encode(), envelope)
        finally:
            for item in secretstorage.search_items(connection, attributes):
                item.delete()
            self.assertEqual(list(secretstorage.search_items(connection, attributes)), [])


if __name__ == "__main__":
    unittest.main()
