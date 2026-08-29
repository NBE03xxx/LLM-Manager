from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_reconciliation import (
    CopyPresence,
    DualCopyDeletionReconciler,
    DualCopyState,
    LocalBackupCopyObserver,
    RemoteBackupCopyObserver,
)


class DualCopyDeletionReconcilerTests(unittest.TestCase):
    def test_maps_all_observed_copy_combinations_to_display_states(self) -> None:
        expected = {
            (CopyPresence.PRESENT, CopyPresence.PRESENT): (DualCopyState.BOTH_AVAILABLE, False),
            (CopyPresence.PRESENT, CopyPresence.ABSENT): (DualCopyState.LOCAL_ONLY, True),
            (CopyPresence.ABSENT, CopyPresence.PRESENT): (DualCopyState.REMOTE_ONLY, True),
            (CopyPresence.ABSENT, CopyPresence.ABSENT): (DualCopyState.BOTH_DELETED, False),
            (CopyPresence.UNKNOWN, CopyPresence.PRESENT): (DualCopyState.UNKNOWN, True),
            (CopyPresence.ABSENT, CopyPresence.UNKNOWN): (DualCopyState.UNKNOWN, True),
        }
        factory = _ManifestFactory()
        manifest = factory.manifest
        for (local, remote), (state, attention) in expected.items():
            with self.subTest(local=local, remote=remote):
                result = DualCopyDeletionReconciler(_Observer(local), _Observer(remote)).reconcile(
                    manifest, CancellationToken()
                )
                self.assertEqual((result.local, result.remote), (local, remote))
                self.assertEqual((result.state, result.requires_attention), (state, attention))
        factory.close()

    def test_observer_failures_and_tamper_are_unknown_not_absent(self) -> None:
        factory = _ManifestFactory()
        local = LocalBackupCopyObserver(factory.local)
        self.assertEqual(local.observe(factory.manifest, CancellationToken()), CopyPresence.PRESENT)
        Path(factory.manifest.storage_location, "manifest.json").write_text("tampered")
        self.assertEqual(local.observe(factory.manifest, CancellationToken()), CopyPresence.UNKNOWN)
        self.assertEqual(RemoteBackupCopyObserver(_Remote("missing")).observe(factory.manifest, CancellationToken()), CopyPresence.ABSENT)
        self.assertEqual(RemoteBackupCopyObserver(_Remote("invalid")).observe(factory.manifest, CancellationToken()), CopyPresence.UNKNOWN)
        factory.close()

    def test_partial_deletion_is_reported_without_automatic_second_mutation(self) -> None:
        factory = _ManifestFactory()
        local = _Observer(CopyPresence.ABSENT)
        remote = _Observer(CopyPresence.PRESENT)
        result = DualCopyDeletionReconciler(local, remote).reconcile(factory.manifest, CancellationToken())
        self.assertEqual(result.state, DualCopyState.REMOTE_ONLY)
        self.assertEqual(local.calls, 1)
        self.assertEqual(remote.calls, 1)
        self.assertFalse(hasattr(local, "delete"))
        factory.close()

    def test_cancellation_stops_before_remote_observation(self) -> None:
        factory = _ManifestFactory()
        token = CancellationToken()
        local = _Observer(CopyPresence.PRESENT, cancel=token)
        remote = _Observer(CopyPresence.PRESENT)
        with self.assertRaises(OperationCancelled):
            DualCopyDeletionReconciler(local, remote).reconcile(factory.manifest, token)
        self.assertEqual(remote.calls, 0)
        factory.close()


class _Observer:
    def __init__(self, presence, cancel=None):
        self.presence = presence
        self.cancel = cancel
        self.calls = 0

    def observe(self, manifest, cancellation):
        self.calls += 1
        if self.cancel is not None:
            self.cancel.cancel()
        return self.presence


class _Remote:
    def __init__(self, outcome):
        self.outcome = outcome

    def load(self, manifest, cancellation):
        if self.outcome == "missing":
            raise AdapterError("remote_backup_not_found", "missing")
        raise AdapterError("invalid_remote_backup", "tampered")


class _ManifestFactory:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        target = root / "target"
        target.write_bytes(b"before")
        change = Change("change", str(target), ChangeOperation.REPLACE_FILE, "before", "after", None, "diff")
        changes = ChangeSet("changes", "ssh:box", (change,), "c" * 64)
        self.local = LocalBackupStore(root / "backups", (root,))
        self.manifest = self.local.create(
            BackupRequest("backup", "plan", "ssh:box", "SHA256:" + "a" * 43, changes, EncryptionInfo(enabled=False)),
            CancellationToken(),
        )

    def close(self):
        self.temp.cleanup()


if __name__ == "__main__":
    unittest.main()
