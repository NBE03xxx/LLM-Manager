from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_deletion import (
    BackupDeletionResult, CopyDeleteOutcome,
)
from llm_manager.infrastructure.backup_reconciliation import (
    BackupReconciliationResultStore,
    BackupReconciliationRunner,
    CopyPresence,
    DualCopyDeletionReconciler,
    DualCopyState,
    LocalBackupCopyObserver,
    RemoteBackupCopyObserver,
)


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


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

    def test_runner_persists_result_bound_to_deletion_and_manifest(self) -> None:
        factory = _ManifestFactory()
        deletion = _deletion(factory.manifest)
        store = BackupReconciliationResultStore(Path(factory.temp.name) / "reconciliation")
        local = _Observer(CopyPresence.PRESENT)
        remote = _Observer(CopyPresence.ABSENT)
        result = BackupReconciliationRunner(
            DualCopyDeletionReconciler(local, remote), store, clock=lambda: NOW
        ).reconcile("reconcile-1", deletion, factory.manifest, CancellationToken())
        self.assertEqual(result.source_deletion_result_hash, deletion.result_hash)
        self.assertEqual(result.state, DualCopyState.LOCAL_ONLY)
        self.assertEqual(store.load("reconcile-1"), result)
        self.assertEqual(store.list_for_host(
            factory.manifest.host_id, factory.manifest.host_fingerprint
        ), (result,))
        self.assertEqual((local.calls, remote.calls), (1, 1))
        path = Path(factory.temp.name) / "reconciliation/reconcile-1.json"
        path.write_bytes(path.read_bytes()[:-1] + b" ")
        with self.assertRaises(AdapterError):
            store.load("reconcile-1")
        factory.close()

    def test_runner_rejects_changed_deletion_binding_before_observation(self) -> None:
        factory = _ManifestFactory()
        deletion = _deletion(factory.manifest)
        changed = BackupDeletionResult(
            deletion.schema_version, deletion.request_id, deletion.request_hash,
            deletion.backup_id, deletion.host_id, deletion.host_fingerprint,
            "d" * 64, deletion.remote_outcome, deletion.local_outcome,
            deletion.remote_error, deletion.local_error, deletion.local_presence,
            deletion.remote_presence, deletion.state, deletion.requires_attention,
            deletion.completed_at,
        ).with_hash()
        local = _Observer(CopyPresence.PRESENT)
        with self.assertRaises(AdapterError):
            BackupReconciliationRunner(
                DualCopyDeletionReconciler(local, _Observer(CopyPresence.PRESENT)),
                BackupReconciliationResultStore(Path(factory.temp.name) / "reconciliation"),
                clock=lambda: NOW,
            ).reconcile("reconcile-1", changed, factory.manifest, CancellationToken())
        self.assertEqual(local.calls, 0)
        with self.assertRaises(AdapterError):
            BackupReconciliationRunner(
                DualCopyDeletionReconciler(local, _Observer(CopyPresence.PRESENT)),
                BackupReconciliationResultStore(Path(factory.temp.name) / "reconciliation"),
                clock=lambda: NOW,
            ).reconcile("../unsafe", deletion, factory.manifest, CancellationToken())
        self.assertEqual(local.calls, 0)
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


def _deletion(manifest):
    return BackupDeletionResult(
        "1.0", "delete-1", "b" * 64, manifest.backup_id, manifest.host_id,
        manifest.host_fingerprint, manifest.manifest_hash,
        CopyDeleteOutcome.FAILED, CopyDeleteOutcome.NOT_ATTEMPTED,
        "remote_failed", None, CopyPresence.PRESENT, CopyPresence.PRESENT,
        DualCopyState.BOTH_AVAILABLE, True, NOW,
    ).with_hash()


if __name__ == "__main__":
    unittest.main()
