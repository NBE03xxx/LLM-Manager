from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation, ValidationStatus
from llm_manager.domain.models import BackupItem, BackupManifest, Change, ChangeSet, EncryptionInfo
from llm_manager.infrastructure.backup import LocalBackupStore
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.remote_backup import (
    DualCopyPrivilegedBackupStore,
    SandboxRemoteRecoveryStore,
    encode_remote_receipt,
)
from llm_manager.infrastructure.remote_helper import (
    RemoteHelperRecoveryCopyStore,
    decode_remote_request,
)


class RemoteHelperRecoveryCopyStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.target = self.root / "target.conf"
        self.target.write_bytes(b"before")
        changes = ChangeSet(
            "changes", "ssh:gpu-box",
            (Change("change", str(self.target), ChangeOperation.REPLACE_FILE, "before", "after", None, "diff"),),
            "c" * 64,
        )
        self.request = BackupRequest(
            "backup-1", "plan-1", "ssh:gpu-box", "SHA256:" + "a" * 43,
            changes, EncryptionInfo(enabled=False),
        )
        self.local = LocalBackupStore(self.root / "local", (self.root,))
        self.backend = SandboxRemoteRecoveryStore(
            self.root / "remote", AesGcmBackupCipher(_Keys()), "remote-master-v1", sandbox=True,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_canonical_request_crosses_user_staging_and_root_backend_boundary(self) -> None:
        transport = _Transport(self.backend)
        remote = RemoteHelperRecoveryCopyStore(transport, "remote-master-v1")
        store = DualCopyPrivilegedBackupStore(self.local, remote)
        manifest = store.create(self.request, CancellationToken())
        results = store.verify(manifest, CancellationToken())
        self.assertTrue(all(item.status is ValidationStatus.PASSED for item in results))
        self.assertEqual(transport.create_request.local_manifest_hash, manifest.manifest_hash)
        self.assertEqual(transport.create_request.host_fingerprint, manifest.host_fingerprint)
        self.assertEqual(transport.create_request.key_reference, "remote-master-v1")
        self.assertEqual(transport.receipt.receipt_hash, results[-1].actual)

    def test_transfer_disconnect_encryption_failure_and_receipt_failure_block_apply(self) -> None:
        for failure in ("transfer", "encrypt", "receipt"):
            with self.subTest(failure=failure):
                local = LocalBackupStore(self.root / f"local-{failure}", (self.root,))
                transport = _Transport(self.backend, failure=failure)
                remote = RemoteHelperRecoveryCopyStore(transport, "remote-master-v1")
                store = DualCopyPrivilegedBackupStore(local, remote)
                manifest = store.create(replace(self.request, backup_id=f"backup-{failure}"), CancellationToken())
                self.assertTrue(Path(manifest.storage_location, "manifest.json").is_file())
                self.assertEqual(store.verify(manifest, CancellationToken())[-1].status, ValidationStatus.FAILED)

    def test_rejects_noncanonical_tampered_request_and_reconnected_receipt(self) -> None:
        transport = _Transport(self.backend)
        remote = RemoteHelperRecoveryCopyStore(transport, "remote-master-v1")
        manifest = self.local.create(self.request, CancellationToken())
        items = self.local.restore_items(manifest, CancellationToken())
        receipt = remote.create(manifest, items, CancellationToken())
        content = transport.create_content
        with self.assertRaises(AdapterError):
            decode_remote_request(content + b"\n", expected_hash=transport.create_request.request_hash, now=datetime.now(UTC))
        value = json.loads(content)
        value["host_fingerprint"] = "SHA256:" + "b" * 43
        tampered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(AdapterError):
            decode_remote_request(tampered, expected_hash=transport.create_request.request_hash, now=datetime.now(UTC))
        transport.receipt = replace(receipt, host_fingerprint="SHA256:" + "b" * 43).with_hash()
        with self.assertRaises(AdapterError):
            remote.load(manifest, CancellationToken())


class _Transport:
    def __init__(self, backend, *, failure=None):
        self.backend = backend
        self.failure = failure
        self.receipt = None
        self.create_request = None
        self.create_content = b""
        self.manifest = None

    def create_recovery_copy(self, request_content, staged_items, cancellation):
        if self.failure == "transfer":
            raise OSError("injected transfer disconnect")
        request = decode_remote_request(
            request_content,
            expected_hash=json.loads(request_content)["request_hash"],
            now=datetime.now(UTC),
        )
        self.create_request = request
        self.create_content = request_content
        manifest = BackupManifest(
            request.backup_id, "1.0", request.plan_id, request.change_set_hash,
            request.host_id, request.host_fingerprint,
            tuple(
                BackupItem(item.target, item.existed, None, item.sha256, item.mode, item.uid, item.gid)
                for item in staged_items
            ),
            request.local_manifest_hash, "/fake-local-not-used", EncryptionInfo(enabled=False),
            complete=True,
        )
        if self.failure == "encrypt":
            raise AdapterError("remote_encryption_failed", "injected encryption failure")
        self.receipt = self.backend.create(manifest, staged_items, cancellation)
        return encode_remote_receipt(self.receipt)

    def read_recovery_receipt(self, request_content, cancellation):
        if self.failure == "receipt" or self.receipt is None:
            raise AdapterError("remote_receipt_unavailable", "injected receipt retrieval failure")
        return encode_remote_receipt(self.receipt)


class _Keys:
    def get_key(self, key_reference, key_scope):
        if (key_reference, key_scope) != ("remote-master-v1", "remote_root"):
            raise AdapterError("invalid_key", "unexpected key")
        return b"r" * 32


if __name__ == "__main__":
    unittest.main()
