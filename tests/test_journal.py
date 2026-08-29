import hashlib
import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.journal import JournalStatus, JournalTarget, LocalOperationJournal, ReconciliationState


class LocalOperationJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.targets = self.base / "targets"
        self.targets.mkdir()
        self.target = self.targets / "config"
        self.target.write_text("before", encoding="utf-8")
        self.before = hashlib.sha256(b"before").hexdigest()
        self.after = hashlib.sha256(b"after").hexdigest()
        self.store = LocalOperationJournal(self.base / "journal", (self.targets,))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_persists_updates_and_reloads_with_private_permissions(self) -> None:
        created = self.store.create("op-1", "plan-1", "host-1", "change-hash", (JournalTarget(str(self.target), self.before, self.after),))
        self.assertEqual(created.status, JournalStatus.APPLYING)
        updated = self.store.update("op-1", JournalStatus.VALIDATING)
        restarted = LocalOperationJournal(self.base / "journal", (self.targets,))
        self.assertEqual(restarted.load("op-1"), updated)
        self.assertEqual((self.base / "journal").stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.base / "journal" / "op-1.json").stat().st_mode & 0o777, 0o600)
        with self.assertRaises(AdapterError):
            self.store.update("op-1", JournalStatus.APPLYING)

    def test_reconciles_before_after_missing_and_unknown(self) -> None:
        missing = self.targets / "created"
        self.store.create("op-1", "plan-1", "host-1", "change-hash", (
            JournalTarget(str(self.target), self.before, self.after),
            JournalTarget(str(missing), None, self.after),
        ))
        initial = self.store.reconcile("op-1")
        self.assertEqual([item.state for item in initial], [ReconciliationState.UNAPPLIED, ReconciliationState.UNAPPLIED])
        self.target.write_text("after", encoding="utf-8")
        missing.write_text("after", encoding="utf-8")
        applied = self.store.reconcile("op-1")
        self.assertEqual([item.state for item in applied], [ReconciliationState.APPLIED, ReconciliationState.APPLIED])
        self.target.write_text("external", encoding="utf-8")
        self.assertEqual(self.store.reconcile("op-1")[0].state, ReconciliationState.UNKNOWN)

    def test_rejects_tamper_replay_and_outside_target(self) -> None:
        self.store.create("op-1", "plan-1", "host-1", "change-hash", (JournalTarget(str(self.target), self.before, self.after),))
        path = self.base / "journal" / "op-1.json"
        path.write_text(path.read_text(encoding="utf-8").replace('"status":"applying"', '"status":"committed"'), encoding="utf-8")
        with self.assertRaises(AdapterError):
            self.store.load("op-1")
        with self.assertRaises(AdapterError):
            self.store.create("op-1", "plan-1", "host-1", "change-hash", (JournalTarget(str(self.target), self.before, self.after),))
        outside = self.base / "outside"
        with self.assertRaises(AdapterError):
            self.store.create("op-2", "plan-1", "host-1", "change-hash", (JournalTarget(str(outside), None, self.after),))


if __name__ == "__main__":
    unittest.main()
