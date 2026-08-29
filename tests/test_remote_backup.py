import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation, ValidationStatus
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.remote_backup import (
    DualCopyPrivilegedBackupStore,
    RemoteRecoveryReceipt,
    remote_storage_location,
)


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
            remote_storage_location(manifest),
            "remote-key-1", "remote_root",
            tuple((item.target, item.sha256) for item in manifest.items), True,
        ).with_hash()
        self.receipt = self.mutate(receipt) if self.mutate else receipt
        return self.receipt

    def load(self, backup_id, cancellation):
        if self.receipt is None:
            raise AdapterError("remote_backup_not_found", "remote copy is missing")
        return self.receipt


if __name__ == "__main__":
    unittest.main()
