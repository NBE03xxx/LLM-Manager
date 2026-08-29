from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.remote_backup import SandboxRemoteRecoveryStore, decode_remote_receipt
from llm_manager.infrastructure.remote_helper import (
    REMOTE_HELPER_OPERATION, REMOTE_HELPER_PROTOCOL_VERSION,
    RemoteRecoveryRequest, encode_remote_request,
)
from llm_manager.infrastructure.remote_helper_executor import RemoteRecoveryHelperExecutor


NOW = datetime(2026, 8, 30, 6, 0, tzinfo=UTC)


class RemoteRecoveryHelperExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stage = self.root / "stage"
        self.remote = SandboxRemoteRecoveryStore(
            self.root / "remote", AesGcmBackupCipher(_Keys()), "remote-master-v1", sandbox=True
        )
        self.request = _request()
        self.directory = self.stage / self.request.request_id / self.request.request_hash
        (self.directory / "items").mkdir(parents=True)
        for path in (self.stage, self.directory.parent, self.directory, self.directory / "items"):
            os.chmod(path, 0o700)
        self._write(self.directory / "request.json", encode_remote_request(self.request))
        self._write(
            self.directory / "items" / f"0000-{self.request.item_hashes[0][1]}.bin", b"before"
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_verifies_user_staging_encrypts_and_publishes_private_receipt(self):
        executor = RemoteRecoveryHelperExecutor(
            self.stage, self.remote, os.getuid(), clock=lambda: NOW
        )
        content = executor.execute(
            self.request.request_id, self.request.request_hash, CancellationToken()
        )
        receipt = decode_remote_receipt(content)
        self.assertEqual(receipt.local_manifest_hash, self.request.local_manifest_hash)
        self.assertEqual(receipt.key_reference, self.request.key_reference)
        result = self.directory / "result.json"
        self.assertEqual(result.read_bytes(), content)
        self.assertEqual(result.stat().st_mode & 0o777, 0o600)
        retention = self.remote.list_retention(self.request.host_id)[0]
        self.assertEqual(retention.created_at, self.request.backup_created_at)
        self.assertEqual(retention.retention_expires_at, self.request.retention_expires_at)

    def test_rejects_missing_extra_mutated_unsafe_and_wrong_key_staging(self):
        cases = ("missing", "extra", "mutated", "mode", "wrong-key")
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as directory:
                    stage = Path(directory) / "stage"
                    request = _request(key="other-key" if case == "wrong-key" else "remote-master-v1")
                    target = stage / request.request_id / request.request_hash
                    (target / "items").mkdir(parents=True)
                    for path in (stage, target.parent, target, target / "items"):
                        os.chmod(path, 0o700)
                    self._write(target / "request.json", encode_remote_request(request))
                    item = target / "items" / f"0000-{request.item_hashes[0][1]}.bin"
                    if case != "missing":
                        self._write(item, b"changed" if case == "mutated" else b"before")
                    if case == "extra":
                        self._write(target / "items" / "extra", b"x")
                    if case == "mode":
                        os.chmod(item, 0o644)
                    with self.assertRaises(AdapterError):
                        RemoteRecoveryHelperExecutor(
                            stage, self.remote, os.getuid(), clock=lambda: NOW
                        ).execute(request.request_id, request.request_hash, CancellationToken())

    def test_rejects_replay_result_and_pre_cancel(self):
        executor = RemoteRecoveryHelperExecutor(self.stage, self.remote, os.getuid(), clock=lambda: NOW)
        executor.execute(self.request.request_id, self.request.request_hash, CancellationToken())
        with self.assertRaises(AdapterError):
            executor.execute(self.request.request_id, self.request.request_hash, CancellationToken())
        other = _request(backup="cancelled")
        directory = self.stage / other.request_id / other.request_hash
        (directory / "items").mkdir(parents=True)
        for path in (directory.parent, directory, directory / "items"):
            os.chmod(path, 0o700)
        self._write(directory / "request.json", encode_remote_request(other))
        self._write(directory / "items" / f"0000-{other.item_hashes[0][1]}.bin", b"before")
        with self.assertRaises(Exception) as caught:
            executor.execute(other.request_id, other.request_hash, CancellationToken(cancelled=True))
        self.assertEqual(type(caught.exception).__name__, "OperationCancelled")

    @staticmethod
    def _write(path, content):
        path.write_bytes(content)
        os.chmod(path, 0o600)


def _request(backup="backup-1", key="remote-master-v1"):
    digest = hashlib.sha256(b"before").hexdigest()
    return RemoteRecoveryRequest(
        REMOTE_HELPER_PROTOCOL_VERSION, REMOTE_HELPER_OPERATION, backup, backup, "plan-1",
        "c" * 64, "ssh:gpu-box", "SHA256:" + "a" * 43, "d" * 64,
        f"/var/lib/llm-manager/backups/87fe234ee99a458ab8e75e14/{backup}",
        key, "remote_root", (("/etc/example", digest),), NOW, NOW + timedelta(days=30),
        False, NOW, NOW + timedelta(minutes=5),
    ).with_hash()


class _Keys:
    def get_key(self, key_reference, key_scope):
        if (key_reference, key_scope) != ("remote-master-v1", "remote_root"):
            raise AdapterError("invalid_key", "unexpected key")
        return b"r" * 32


if __name__ == "__main__":
    unittest.main()
