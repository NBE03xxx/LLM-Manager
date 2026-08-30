from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.backup_deletion import (
    BackupDeletionRecoveryService, BackupDeletionResultStore,
    CoordinatedBackupDeletion, CopyDeleteOutcome, new_backup_deletion_request,
)
from llm_manager.infrastructure.backup_reconciliation import (
    DualCopyDeletionReconciler, DualCopyState, LocalBackupCopyObserver,
    RemoteBackupCopyObserver,
)
from llm_manager.infrastructure.openssh_remote_deletion import (
    OpenSshRemoteDeletionPort, RemoteDeletionAttemptStore,
)
from llm_manager.infrastructure.remote_backup import SandboxRemoteRecoveryStore
from llm_manager.infrastructure.remote_deletion import RemoteDeletionHelperExecutor
from llm_manager.infrastructure.ssh_remote_staging import REMOTE_USER_STAGING_ROOT


NOW = datetime(2026, 8, 30, 12, tzinfo=UTC)


class BackupDeletionBoundaryIntegrationTests(unittest.TestCase):
    def test_disconnect_result_recovery_then_local_delete_and_safe_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.write_bytes(b"before")
            changes = ChangeSet(
                "changes", "ssh:host",
                (Change("change", str(target), ChangeOperation.REPLACE_FILE,
                        "before", "after", None, "diff"),), "c" * 64,
            )
            local = LocalBackupStore(root / "local", (root,))
            manifest = local.create(BackupRequest(
                "backup-1", "plan-1", "ssh:host", "SHA256:" + "a" * 43,
                changes, EncryptionInfo(enabled=False),
            ), CancellationToken())
            remote = SandboxRemoteRecoveryStore(
                root / "remote", AesGcmBackupCipher(_Keys()),
                "remote-master-v1", sandbox=True,
            )
            remote.create(
                manifest, local.restore_items(manifest, CancellationToken()),
                CancellationToken(),
            )
            staging = _FilesystemStaging(root / "remote-user", fail_reads=1)
            invoker = _RootInvoker(staging.root, remote)
            attempts = RemoteDeletionAttemptStore(root / "attempts")
            remote_port = OpenSshRemoteDeletionPort(
                staging, invoker, remote, attempts, lambda _: "remote-delete-1",
                clock=lambda: NOW,
            )
            results = BackupDeletionResultStore(root / "results")
            reconciler = DualCopyDeletionReconciler(
                LocalBackupCopyObserver(local), RemoteBackupCopyObserver(remote)
            )
            coordinator = CoordinatedBackupDeletion(
                local, remote_port, reconciler, results, cleanup=remote_port,
                clock=lambda: NOW,
            )

            first_request = new_backup_deletion_request("delete-1", manifest, now=NOW)
            first = coordinator.delete(first_request, manifest, CancellationToken())
            self.assertEqual(first.remote_outcome, CopyDeleteOutcome.UNKNOWN)
            self.assertEqual(first.local_outcome, CopyDeleteOutcome.NOT_ATTEMPTED)
            self.assertEqual(first.state, DualCopyState.LOCAL_ONLY)
            self.assertTrue(Path(manifest.storage_location).exists())
            self.assertEqual(invoker.calls, 1)
            self.assertFalse(staging.removed)

            recovered_invoker = _RootInvoker(staging.root, remote)
            recovered_port = OpenSshRemoteDeletionPort(
                staging, recovered_invoker, remote,
                RemoteDeletionAttemptStore(root / "attempts"),
                lambda _: "remote-delete-1", clock=lambda: NOW,
            )
            recovered_coordinator = CoordinatedBackupDeletion(
                local, recovered_port, reconciler, results, cleanup=recovered_port,
                clock=lambda: NOW,
            )
            second_request = new_backup_deletion_request("delete-2", manifest, now=NOW)
            second = recovered_coordinator.delete(
                second_request, manifest, CancellationToken()
            )
            self.assertEqual(second.remote_outcome, CopyDeleteOutcome.DELETED)
            self.assertEqual(second.local_outcome, CopyDeleteOutcome.DELETED)
            self.assertEqual(second.state, DualCopyState.BOTH_DELETED)
            self.assertEqual(recovered_invoker.calls, 0,
                             "persisted result must prevent remote replay after restart")
            self.assertTrue(staging.removed)

            view = BackupDeletionRecoveryService(results, recovered_port).load(
                second_request, manifest
            )
            self.assertFalse(view.staging_cleanup_pending)
            self.assertEqual(view.result, second)

    def test_cleanup_failure_is_pending_and_retry_does_not_repeat_deletion(self):
        cleanup = _Cleanup(fail=True)
        factory = _MinimalDeletion(cleanup)
        result = factory.coordinator.delete(
            factory.request, factory.manifest, CancellationToken()
        )
        service = BackupDeletionRecoveryService(factory.results, cleanup)
        self.assertTrue(service.load(factory.request, factory.manifest).staging_cleanup_pending)
        cleanup.fail = False
        view = service.retry_cleanup(factory.request, factory.manifest, CancellationToken())
        self.assertFalse(view.staging_cleanup_pending)
        self.assertEqual(view.result, result)
        self.assertEqual(cleanup.calls, 2)
        factory.close()


class _FilesystemStaging:
    def __init__(self, root, fail_reads=0):
        self.root, self.fail_reads, self.removed = root, fail_reads, False
        root.mkdir(mode=0o700)

    def _path(self, relative):
        parts = PurePosixPath(relative).parts
        prefix = PurePosixPath(REMOTE_USER_STAGING_ROOT).parts
        return self.root.joinpath(*parts[len(prefix):])

    def prepare_private_directory(self, relative):
        operation = self._path(relative)
        (operation / "items").mkdir(mode=0o700, parents=True, exist_ok=True)
        for path in (operation.parent, operation, operation / "items"):
            os.chmod(path, 0o700)

    def upload_private_file(self, relative, content):
        path = self._path(relative)
        path.write_bytes(content)
        os.chmod(path, 0o600)

    def read_private_file(self, relative, max_bytes):
        if self.fail_reads:
            self.fail_reads -= 1
            raise AdapterError("remote_staging_read_failed", "injected disconnect")
        return self._path(relative).read_bytes()

    def remove_private_tree(self, relative):
        operation = self._path(relative)
        for path in (operation / "items").iterdir():
            path.unlink()
        (operation / "items").rmdir()
        for name in ("request.json", "result.json"):
            (operation / name).unlink()
        operation.rmdir()
        self.removed = True


class _RootInvoker:
    def __init__(self, staging_root, remote):
        self.staging_root, self.remote, self.calls = staging_root, remote, 0

    def invoke(self, request_id, request_hash, cancellation):
        self.calls += 1
        RemoteDeletionHelperExecutor(
            self.staging_root, self.remote, os.getuid(), clock=lambda: NOW
        ).execute(request_id, request_hash, cancellation)


class _Cleanup:
    def __init__(self, fail=False):
        self.fail, self.cleaned, self.calls = fail, False, 0

    def cleanup(self, request, manifest, cancellation):
        self.calls += 1
        if self.fail:
            raise AdapterError("cleanup_failed", "injected")
        self.cleaned = True

    def cleanup_pending(self, request, manifest):
        return not self.cleaned


class _MinimalDeletion:
    def __init__(self, cleanup):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        target = root / "target"
        target.write_bytes(b"before")
        change = Change("change", str(target), ChangeOperation.REPLACE_FILE,
                        "before", "after", None, "diff")
        local = LocalBackupStore(root / "local", (root,))
        self.manifest = local.create(BackupRequest(
            "backup", "plan", "ssh:host", "SHA256:" + "a" * 43,
            ChangeSet("changes", "ssh:host", (change,), "c" * 64),
            EncryptionInfo(enabled=False),
        ), CancellationToken())
        remote = _DeletePort()
        self.results = BackupDeletionResultStore(root / "results")
        self.request = new_backup_deletion_request("delete", self.manifest, now=NOW)
        reconciler = DualCopyDeletionReconciler(
            _Observer(), _Observer()
        )
        self.coordinator = CoordinatedBackupDeletion(
            local, remote, reconciler, self.results, cleanup=cleanup, clock=lambda: NOW
        )

    def close(self):
        self.temp.cleanup()


class _DeletePort:
    def delete(self, manifest, cancellation):
        return None


class _Observer:
    def observe(self, manifest, cancellation):
        from llm_manager.infrastructure.backup_reconciliation import CopyPresence
        return CopyPresence.ABSENT


class _Keys:
    def get_key(self, key_reference, key_scope):
        return b"r" * 32


if __name__ == "__main__":
    unittest.main()
