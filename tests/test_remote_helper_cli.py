from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.remote_backup import SandboxRemoteRecoveryStore
from llm_manager.infrastructure.remote_helper import (
    REMOTE_HELPER_OPERATION, REMOTE_HELPER_PROTOCOL_VERSION,
    RemoteRecoveryRequest, encode_remote_request,
)
from llm_manager.infrastructure.remote_helper_cli import run_remote_helper


NOW = datetime.now(UTC)


class RemoteHelperCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.uid = os.getuid()
        if self.uid == 0:
            self.uid = 1000
        self.backup = SandboxRemoteRecoveryStore(
            Path(self.temp.name) / "remote", AesGcmBackupCipher(_Keys()),
            "remote-master-v1", sandbox=True,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_user_prepare_root_invoke_and_user_cleanup_fixed_flow(self):
        request = _request()
        relative = f".local/state/llm-manager/remote-helper/{request.request_id}/{request.request_hash}"
        code, _ = run_remote_helper(
            ("user-stage-prepare", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 0)
        directory = self.home / relative
        self._write(directory / "request.json", encode_remote_request(request))
        self._write(directory / "items" / f"0000-{request.item_hashes[0][1]}.bin", b"before")
        code, result = run_remote_helper(
            ("invoke-recovery", request.request_id, request.request_hash),
            environ={"SUDO_UID": str(self.uid)}, effective_uid=0, current_uid=0,
            home_for_uid=lambda _: self.home, backend=self.backup,
        )
        self.assertEqual(code, 0)
        self.assertIn(b'"success":true', result)
        self.assertTrue((directory / "result.json").is_file())
        code, _ = run_remote_helper(
            ("user-stage-remove", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 0)
        self.assertFalse(directory.exists())

    def test_rejects_privilege_path_uid_unknown_command_and_unsafe_cleanup(self):
        request = _request()
        relative = f".local/state/llm-manager/remote-helper/{request.request_id}/{request.request_hash}"
        cases = (
            (("user-stage-prepare", relative), {"effective_uid": 0, "current_uid": 0}),
            (("user-stage-prepare", "../escape"), {"effective_uid": self.uid, "current_uid": self.uid}),
            (("invoke-recovery", request.request_id, request.request_hash), {"effective_uid": self.uid, "current_uid": self.uid}),
            (("invoke-recovery", request.request_id, request.request_hash), {"effective_uid": 0, "current_uid": 0, "environ": {}}),
            (("shell", "id"), {"effective_uid": self.uid, "current_uid": self.uid}),
        )
        for argv, kwargs in cases:
            with self.subTest(argv=argv):
                code, result = run_remote_helper(argv, home_for_uid=lambda _: self.home, backend=self.backup, **kwargs)
                self.assertEqual(code, 1)
                self.assertIn(b'"success":false', result)
        run_remote_helper(
            ("user-stage-prepare", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        directory = self.home / relative
        (directory / "unexpected").write_text("unsafe")
        code, _ = run_remote_helper(
            ("user-stage-remove", relative), effective_uid=self.uid, current_uid=self.uid,
            home_for_uid=lambda _: self.home,
        )
        self.assertEqual(code, 1)
        self.assertTrue(directory.exists())

    @staticmethod
    def _write(path, content):
        path.write_bytes(content)
        os.chmod(path, 0o600)


def _request():
    digest = hashlib.sha256(b"before").hexdigest()
    base = RemoteRecoveryRequest(
        REMOTE_HELPER_PROTOCOL_VERSION, REMOTE_HELPER_OPERATION, "backup-1", "backup-1",
        "plan-1", "c" * 64, "ssh:gpu-box", "SHA256:" + "a" * 43, "d" * 64,
        "/var/lib/llm-manager/backups/87fe234ee99a458ab8e75e14/backup-1",
        "remote-master-v1", "remote_root", (("/etc/example", digest),),
        NOW, NOW + timedelta(days=30), False, NOW, NOW + timedelta(minutes=5),
    )
    return base.with_hash()


class _Keys:
    def get_key(self, key_reference, key_scope):
        if (key_reference, key_scope) != ("remote-master-v1", "remote_root"):
            raise AdapterError("invalid_key", "unexpected key")
        return b"r" * 32


if __name__ == "__main__":
    unittest.main()
