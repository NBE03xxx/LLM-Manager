import tempfile
import unittest
import os
import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation, ValidationStatus
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import BackupRestoreItem, LocalBackupStore
from llm_manager.infrastructure.remote_backup import (
    DualCopyPrivilegedBackupStore,
    RemoteRecoveryReceipt,
    RemoteRootRecoveryStore,
    SandboxRemoteRecoveryStore,
    remote_storage_location,
)
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher


class DualCopyPrivilegedBackupStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = self.root / "target.conf"
        self.target.write_bytes(b"before")
        change = Change(
            "change", str(self.target), ChangeOperation.REPLACE_FILE,
            "before", "after", None, "diff",
        )
        self.changes = ChangeSet("changes", "ssh:gpu-box", (change,), "c" * 64)
        self.request = BackupRequest(
            "backup-1", "plan-1", "ssh:gpu-box", "SHA256:" + "a" * 43,
            self.changes, EncryptionInfo(enabled=False),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_creates_and_verifies_both_copies_with_independent_remote_key(self) -> None:
        remote = _RemoteCopy()
        store = self._store(remote)
        manifest = store.create(self.request, CancellationToken())
        results = store.verify(manifest, CancellationToken())
        self.assertTrue(all(item.status is ValidationStatus.PASSED for item in results))
        self.assertEqual(remote.items[0].content, b"before")
        self.assertEqual(remote.receipt.key_scope, "remote_root")

    def test_remote_failure_preserves_local_backup_but_blocks_apply(self) -> None:
        remote = _RemoteCopy(fail_create=True)
        store = self._store(remote)
        manifest = store.create(self.request, CancellationToken())
        self.assertTrue(Path(manifest.storage_location, "manifest.json").is_file())
        results = store.verify(manifest, CancellationToken())
        self.assertEqual(results[-1].status, ValidationStatus.FAILED)

    def test_rejects_tampered_binding_scope_location_and_item_hash(self) -> None:
        mutations = (
            lambda receipt: replace(receipt, host_fingerprint="SHA256:" + "b" * 43).with_hash(),
            lambda receipt: replace(receipt, key_scope="local_secret_service").with_hash(),
            lambda receipt: replace(receipt, storage_location="/tmp/escape").with_hash(),
            lambda receipt: replace(receipt, item_hashes=((str(self.target), "f" * 64),)).with_hash(),
            lambda receipt: replace(receipt, receipt_hash="f" * 64),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                remote = _RemoteCopy(mutate=mutate)
                store = self._store(remote)
                manifest = store.create(self.request, CancellationToken())
                self.assertEqual(
                    store.verify(manifest, CancellationToken())[-1].status,
                    ValidationStatus.FAILED,
                )

    def test_sandbox_remote_store_encrypts_reloads_and_detects_tamper(self) -> None:
        remote = SandboxRemoteRecoveryStore(
            self.root / "remote-root", AesGcmBackupCipher(_RemoteKeys()),
            "remote-master-v1", sandbox=True,
        )
        store = self._store(remote)
        manifest = store.create(self.request, CancellationToken())
        receipt = remote.load(manifest, CancellationToken())
        directory = self.root / "remote-root" / receipt.storage_location.split("/")[-2] / manifest.backup_id
        envelope = next((directory / "items").iterdir()).read_bytes()
        self.assertNotIn(b"before", envelope)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600 for path in (directory / "items").iterdir()))
        self.assertEqual((directory / "receipt.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((directory / "retention.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(store.verify(manifest, CancellationToken())[-1].status, ValidationStatus.PASSED)
        restarted = SandboxRemoteRecoveryStore(
            self.root / "remote-root", AesGcmBackupCipher(_RemoteKeys()),
            "remote-master-v1", sandbox=True,
        )
        self.assertEqual(restarted.load(manifest, CancellationToken()), receipt)
        item_path = next((directory / "items").iterdir())
        item_path.write_bytes(item_path.read_bytes()[:-1] + b"x")
        self.assertEqual(store.verify(manifest, CancellationToken())[-1].status, ValidationStatus.FAILED)

    def test_sandbox_remote_store_rejects_production_mode_and_symlink_root(self) -> None:
        with self.assertRaises(ValueError):
            SandboxRemoteRecoveryStore(
                self.root / "remote-root", AesGcmBackupCipher(_RemoteKeys()),
                "remote-master-v1",
            )
        with self.assertRaises(ValueError):
            RemoteRootRecoveryStore(
                Path("/var/lib/llm-manager/backups"), AesGcmBackupCipher(_RemoteKeys()),
                "remote-master-v1", effective_uid=1000,
            )
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "remote-link"
        os.symlink(outside, link)
        with self.assertRaises(ValueError):
            SandboxRemoteRecoveryStore(
                link, AesGcmBackupCipher(_RemoteKeys()), "remote-master-v1", sandbox=True,
            )

    def test_remote_retention_keeps_ten_generations_protected_and_last_copy(self) -> None:
        remote = SandboxRemoteRecoveryStore(
            self.root / "remote-retention", AesGcmBackupCipher(_RemoteKeys()),
            "remote-master-v1", sandbox=True,
        )
        manifest = self.local_manifest()
        restore = self._restore_item()
        start = datetime(2026, 8, 1, tzinfo=UTC)
        manifests = []
        for index in range(12):
            current = replace(
                manifest, backup_id=f"retention-{index}", created_at=start + timedelta(days=index),
                retention_expires_at=start + timedelta(days=index + 30), manifest_hash=f"{index + 1:064x}",
            )
            remote.create(current, (restore,), CancellationToken())
            manifests.append(current)
        remote.set_protected(manifests[0], True)
        with self.assertRaises(AdapterError):
            remote.prune(
                "ssh:gpu-box", now=start + timedelta(days=12),
                expected_fingerprint="SHA256:" + "b" * 43,
            )
        removed = remote.prune(
            "ssh:gpu-box", now=start + timedelta(days=12),
            expected_fingerprint=manifest.host_fingerprint,
        )
        self.assertEqual(removed, ("retention-1",))
        records = remote.list_retention("ssh:gpu-box")
        self.assertEqual(len(records), 11)
        self.assertTrue(next(item for item in records if item.backup_id == "retention-0").protected)

        for record in records:
            remote.set_protected(next(item for item in manifests if item.backup_id == record.backup_id), record.backup_id == "retention-0")
        removed = remote.prune("ssh:gpu-box", now=start + timedelta(days=100))
        self.assertEqual(len(removed), 10)
        self.assertEqual(tuple(item.backup_id for item in remote.list_retention("ssh:gpu-box")), ("retention-0",))

    def test_remote_retention_tamper_and_unknown_entry_prevent_prune(self) -> None:
        remote = SandboxRemoteRecoveryStore(
            self.root / "remote-retention", AesGcmBackupCipher(_RemoteKeys()),
            "remote-master-v1", sandbox=True,
        )
        manifest = self.local_manifest()
        remote.create(manifest, (self._restore_item(),), CancellationToken())
        directory = self.root / "remote-retention" / remote_storage_location(manifest).split("/")[-2] / manifest.backup_id
        retention = directory / "retention.json"
        original = retention.read_bytes()
        retention.write_bytes(original[:-1] + b" ")
        with self.assertRaises(AdapterError):
            remote.list_retention("ssh:gpu-box")
        retention.write_bytes(original)
        remote.create(replace(manifest, backup_id="backup-2", manifest_hash="e" * 64), (self._restore_item(),), CancellationToken())
        (directory.parent / "backup-2" / "unexpected").write_text("unsafe")
        with self.assertRaises(AdapterError):
            remote.prune("ssh:gpu-box", now=datetime(2027, 1, 1, tzinfo=UTC), keep_generations=1)

    def local_manifest(self):
        local = LocalBackupStore(self.root / "manifest-local", (self.root,))
        return local.create(self.request, CancellationToken())

    def _restore_item(self):
        stat_result = self.target.stat()
        return BackupRestoreItem(
            str(self.target), True, b"before", hashlib.sha256(b"before").hexdigest(),
            stat_result.st_mode & 0o777, stat_result.st_uid, stat_result.st_gid,
        )

    def _store(self, remote):
        local = LocalBackupStore(self.root / f"backups-{id(remote)}", (self.root,))
        return DualCopyPrivilegedBackupStore(local, remote)


class _RemoteCopy:
    def __init__(self, fail_create=False, mutate=None):
        self.fail_create = fail_create
        self.mutate = mutate
        self.receipt = None
        self.items = ()

    def create(self, manifest, items, cancellation):
        if self.fail_create:
            raise OSError("injected remote copy failure")
        self.items = items
        receipt = RemoteRecoveryReceipt(
            "1.0", manifest.backup_id, manifest.plan_id, manifest.change_set_hash,
            manifest.host_id, manifest.host_fingerprint, manifest.manifest_hash,
            remote_storage_location(manifest), "AES-256-GCM", 1,
            "remote-key-1", "remote_root",
            tuple((item.target, item.sha256) for item in manifest.items), True,
        ).with_hash()
        self.receipt = self.mutate(receipt) if self.mutate else receipt
        return self.receipt

    def load(self, manifest, cancellation):
        if self.receipt is None:
            raise AdapterError("remote_backup_not_found", "remote copy is missing")
        return self.receipt


class _RemoteKeys:
    def get_key(self, key_reference, key_scope):
        if (key_reference, key_scope) != ("remote-master-v1", "remote_root"):
            raise AdapterError("invalid_key", "unexpected remote key")
        return b"r" * 32


if __name__ == "__main__":
    unittest.main()
