import hashlib
import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation, HostKind
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.journal import JournalStatus, JournalTarget, LocalOperationJournal
from llm_manager.infrastructure.local_apply_inventory import LocalApplyInventoryService
from llm_manager.ui.composition import LocalBackupInventoryTaskFactory


class LocalApplyInventoryTests(unittest.TestCase):
    def _stores(self, root: Path):
        target_root = root / "config" / "opencode"
        target_root.mkdir(parents=True)
        target = target_root / "opencode.json"
        target.write_text("old", encoding="utf-8")
        before = hashlib.sha256(b"old").hexdigest()
        after = hashlib.sha256(b"new").hexdigest()
        change = Change("change", str(target), ChangeOperation.REPLACE_FILE,
                        "old", "new", before, "masked", source_span=(0, 3),
                        replacement_text="new")
        changes = ChangeSet("changes", "local:test", (change,), "c" * 64)
        state = root / "state" / "llm-manager"
        state.mkdir(parents=True, mode=0o700)
        state.chmod(0o700)
        backups = LocalBackupStore(state / "backups", (target_root,))
        backups.create(BackupRequest(
            "operation-1", "plan-1", "local:test", None, changes,
            EncryptionInfo(enabled=False)), CancellationToken())
        journals = LocalOperationJournal(state / "journal", (target_root,))
        journals.create("operation-1", "plan-1", "local:test", changes.content_hash,
                        (JournalTarget(str(target), before, after),))
        journals.update("operation-1", JournalStatus.VALIDATING)
        journals.update("operation-1", JournalStatus.COMMITTED)
        return backups, journals, state

    def test_strict_restart_inventory_binds_manifest_and_terminal_journal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backups, journals, state = self._stores(root)
            restarted = LocalApplyInventoryService(
                LocalBackupStore(state / "backups", (root / "config" / "opencode",)),
                LocalOperationJournal(state / "journal", (root / "config" / "opencode",)))
            values = restarted.list_for_host("local:test", CancellationToken())
            self.assertEqual(len(values), 1)
            self.assertEqual(values[0].state, JournalStatus.COMMITTED)
            self.assertFalse(values[0].requires_attention)
            self.assertEqual(backups.list_manifests("local:test")[0].backup_id, "operation-1")
            self.assertEqual(journals.load("operation-1").status, JournalStatus.COMMITTED)

    def test_strict_inventory_rejects_tamper_and_unknown_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backups, journals, state = self._stores(root)
            manifest = backups.list_manifests("local:test")[0]
            Path(manifest.storage_location, "manifest.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(AdapterError, "manifest"):
                backups.list_manifests_strict("local:test")
            Path(state / "journal" / "README").write_text("unknown", encoding="utf-8")
            with self.assertRaisesRegex(AdapterError, "unknown journal"):
                journals.list_for_host_strict("local:test")

    def test_production_factory_empty_read_does_not_create_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = HostCandidate("local:test", HostKind.LOCAL, "Local")
            remote = HostCandidate("ssh:test", HostKind.SSH, "SSH", "test")
            factory = LocalBackupInventoryTaskFactory(
                (local, remote), root / "config", root / "state")
            self.assertEqual(factory(local.host_id)(CancellationToken()), ())
            self.assertFalse((root / "state" / "llm-manager").exists())
            with self.assertRaisesRegex(ValueError, "requires_local"):
                factory(remote.host_id)


if __name__ == "__main__":
    unittest.main()
