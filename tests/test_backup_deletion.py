from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.backup_deletion import (
    BackupDeletionResultStore, CoordinatedBackupDeletion, CopyDeleteOutcome,
    new_backup_deletion_request,
)
from llm_manager.infrastructure.backup_manifest_evidence import BackupManifestEvidenceStore
from llm_manager.infrastructure.backup_reconciliation import (
    CopyPresence, DualCopyDeletionReconciler, DualCopyState,
    LocalBackupCopyObserver, RemoteBackupCopyObserver,
)
from llm_manager.infrastructure.remote_backup import SandboxRemoteRecoveryStore


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


class CoordinatedBackupDeletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        target = self.root / "target.conf"
        target.write_bytes(b"before")
        changes = ChangeSet(
            "changes", "ssh:box",
            (Change("change", str(target), ChangeOperation.REPLACE_FILE,
                    "before", "after", None, "diff"),), "c" * 64,
        )
        self.local = LocalBackupStore(self.root / "local", (self.root,))
        self.manifest = self.local.create(
            BackupRequest(
                "backup-1", "plan-1", "ssh:box", "SHA256:" + "a" * 43,
                changes, EncryptionInfo(enabled=False),
            ), CancellationToken(),
        )
        self.remote = SandboxRemoteRecoveryStore(
            self.root / "remote", AesGcmBackupCipher(_Keys()),
            "remote-master-v1", sandbox=True,
        )
        self.remote.create(
            self.manifest, self.local.restore_items(self.manifest, CancellationToken()),
            CancellationToken(),
        )
        self.results = BackupDeletionResultStore(self.root / "results")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_deletes_remote_then_local_and_persists_bound_result(self) -> None:
        result = self._coordinator(self.local, self.remote).delete(
            new_backup_deletion_request("delete-1", self.manifest, now=NOW),
            self.manifest, CancellationToken(),
        )
        self.assertEqual(result.remote_outcome, CopyDeleteOutcome.DELETED)
        self.assertEqual(result.local_outcome, CopyDeleteOutcome.DELETED)
        self.assertEqual(result.state, DualCopyState.BOTH_DELETED)
        self.assertFalse(result.requires_attention)
        self.assertFalse(Path(self.manifest.storage_location).exists())
        self.assertEqual(self.results.load("delete-1"), result)

    def test_remote_failure_preserves_local_and_records_not_attempted(self) -> None:
        remote, local = _DeletePort(error=AdapterError("remote_delete_failed", "x")), _DeletePort()
        result = self._coordinator(
            local, remote, local_presence=CopyPresence.PRESENT,
            remote_presence=CopyPresence.PRESENT,
        ).delete(new_backup_deletion_request("delete-2", self.manifest, now=NOW),
                 self.manifest, CancellationToken())
        self.assertEqual(result.remote_outcome, CopyDeleteOutcome.FAILED)
        self.assertEqual(result.local_outcome, CopyDeleteOutcome.NOT_ATTEMPTED)
        self.assertEqual(local.calls, 0)
        self.assertEqual(result.state, DualCopyState.BOTH_AVAILABLE)
        self.assertTrue(result.requires_attention)

    def test_local_failure_after_remote_success_is_local_only(self) -> None:
        remote, local = _DeletePort(), _DeletePort(error=AdapterError("local_delete_failed", "x"))
        result = self._coordinator(
            local, remote, local_presence=CopyPresence.PRESENT,
            remote_presence=CopyPresence.ABSENT,
        ).delete(new_backup_deletion_request("delete-3", self.manifest, now=NOW),
                 self.manifest, CancellationToken())
        self.assertEqual(result.remote_outcome, CopyDeleteOutcome.DELETED)
        self.assertEqual(result.local_outcome, CopyDeleteOutcome.FAILED)
        self.assertEqual(result.state, DualCopyState.LOCAL_ONLY)
        self.assertTrue(result.requires_attention)

    def test_cancel_after_remote_does_not_delete_local(self) -> None:
        token = CancellationToken()
        remote, local = _DeletePort(cancel=token), _DeletePort()
        result = self._coordinator(local, remote).delete(
            new_backup_deletion_request("delete-4", self.manifest, now=NOW),
            self.manifest, token,
        )
        self.assertEqual(result.remote_outcome, CopyDeleteOutcome.DELETED)
        self.assertEqual(result.local_outcome, CopyDeleteOutcome.NOT_ATTEMPTED)
        self.assertEqual(result.local_error, "cancelled")
        self.assertEqual(local.calls, 0)
        self.assertEqual(result.state, DualCopyState.UNKNOWN)

    def test_rejects_expired_tampered_and_protected_before_mutation(self) -> None:
        remote, local = _DeletePort(), _DeletePort()
        coordinator = self._coordinator(local, remote)
        valid = new_backup_deletion_request("delete-5", self.manifest, now=NOW)
        for request in (
            replace(valid, expires_at=NOW - timedelta(seconds=1)).with_hash(),
            replace(valid, host_fingerprint="SHA256:" + "b" * 43),
        ):
            with self.subTest(request=request), self.assertRaises(AdapterError):
                coordinator.delete(request, self.manifest, CancellationToken())
        with self.assertRaises(AdapterError):
            coordinator.delete(valid, replace(self.manifest, protected=True), CancellationToken())
        self.assertEqual((remote.calls, local.calls), (0, 0))

    def test_result_store_rejects_tamper_and_overwrite(self) -> None:
        result = self._coordinator(self.local, self.remote).delete(
            new_backup_deletion_request("delete-6", self.manifest, now=NOW),
            self.manifest, CancellationToken(),
        )
        with self.assertRaises(AdapterError):
            self.results.save(result)
        path = self.root / "results" / "delete-6.json"
        content = path.read_bytes()
        path.write_bytes(content[:-1] + b" ")
        with self.assertRaises(AdapterError):
            self.results.load("delete-6")

    def test_manifest_evidence_is_saved_before_remote_mutation(self) -> None:
        evidence = BackupManifestEvidenceStore(self.root / "manifest-evidence")
        request = new_backup_deletion_request("delete-evidence", self.manifest, now=NOW)
        result = CoordinatedBackupDeletion(
            self.local, self.remote,
            DualCopyDeletionReconciler(
                LocalBackupCopyObserver(self.local), RemoteBackupCopyObserver(self.remote)
            ),
            self.results, manifest_evidence=evidence, clock=lambda: NOW,
        ).delete(request, self.manifest, CancellationToken())
        self.assertEqual(evidence.load(result), self.manifest)
        self.assertFalse(Path(self.manifest.storage_location).exists())

    def test_manifest_evidence_failure_stops_before_remote_delete(self) -> None:
        remote, local = _DeletePort(), _DeletePort()
        coordinator = CoordinatedBackupDeletion(
            local, remote,
            DualCopyDeletionReconciler(
                _Observer(CopyPresence.PRESENT), _Observer(CopyPresence.PRESENT)
            ),
            self.results, manifest_evidence=_EvidenceFailure(), clock=lambda: NOW,
        )
        with self.assertRaises(AdapterError):
            coordinator.delete(
                new_backup_deletion_request("delete-evidence-fail", self.manifest, now=NOW),
                self.manifest, CancellationToken(),
            )
        self.assertEqual((remote.calls, local.calls), (0, 0))

    def _coordinator(self, local, remote, *, local_presence=None, remote_presence=None):
        local_observer = LocalBackupCopyObserver(self.local) if local_presence is None else _Observer(local_presence)
        remote_observer = RemoteBackupCopyObserver(self.remote) if remote_presence is None else _Observer(remote_presence)
        return CoordinatedBackupDeletion(
            local, remote, DualCopyDeletionReconciler(local_observer, remote_observer),
            self.results, clock=lambda: NOW,
        )


class _DeletePort:
    def __init__(self, *, error=None, cancel=None):
        self.error, self.cancel, self.calls = error, cancel, 0

    def delete(self, manifest, cancellation):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.cancel is not None:
            self.cancel.cancel()


class _Observer:
    def __init__(self, presence):
        self.presence = presence

    def observe(self, manifest, cancellation):
        return self.presence


class _Keys:
    def get_key(self, key_reference, key_scope):
        return b"r" * 32


class _EvidenceFailure:
    def save(self, request, manifest):
        raise AdapterError("manifest_evidence_failed", "injected")


if __name__ == "__main__":
    unittest.main()
