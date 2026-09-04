from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.infrastructure.remote_helper_cli import run_remote_helper
from llm_manager.infrastructure.remote_user_apply import (
    REMOTE_USER_APPLY_OPERATION,
    REMOTE_USER_APPLY_PROTOCOL_VERSION,
    RemoteUserApplyExecutor,
    RemoteUserApplyRequest,
    decode_remote_user_apply_request,
    encode_remote_user_apply_request,
)


class RemoteUserApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.target = self.home / ".config/opencode/opencode.jsonc"
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b'{"model":"old"}\n')
        self.before = hashlib.sha256(self.target.read_bytes()).hexdigest()
        self.after_content = b'{"model":"new"}\n'
        self.after = hashlib.sha256(self.after_content).hexdigest()
        self.now = utc_now()
        self.request = RemoteUserApplyRequest(
            REMOTE_USER_APPLY_PROTOCOL_VERSION,
            REMOTE_USER_APPLY_OPERATION,
            "apply-1",
            "plan-1",
            "1" * 64,
            "backup-1",
            "2" * 64,
            "ssh-host",
            "SHA256:verified",
            ".config/opencode/opencode.jsonc",
            self.before,
            self.after,
            self.now,
            self.now + timedelta(minutes=5),
        ).with_hash()
        self.staging = self.home / ".local/state/llm-manager/remote-helper"
        operation = self.staging / self.request.request_id / self.request.request_hash
        items = operation / "items"
        items.mkdir(mode=0o700, parents=True)
        for parent in (self.home / ".local", self.home / ".local/state", self.home / ".local/state/llm-manager", self.staging, operation.parent, operation):
            os.chmod(parent, 0o700)
        self._write_private(operation / "request.json", encode_remote_user_apply_request(self.request))
        self._write_private(items / f"0000-{self.after}.bin", self.after_content)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write_private(path: Path, content: bytes) -> None:
        path.write_bytes(content)
        os.chmod(path, 0o600)

    def test_executes_one_hash_bound_opencode_write_and_emits_bound_result(self) -> None:
        content = RemoteUserApplyExecutor(
            self.staging, self.home, os.getuid(), clock=lambda: self.now
        ).execute(self.request.request_id, self.request.request_hash, CancellationToken())

        self.assertEqual(self.target.read_bytes(), self.after_content)
        result = json.loads(content)
        self.assertEqual(result["request_hash"], self.request.request_hash)
        self.assertEqual(result["host_fingerprint"], "SHA256:verified")
        self.assertEqual(result["after_hash"], self.after)

    def test_rejects_stale_target_before_mutation(self) -> None:
        self.target.write_bytes(b"changed")
        with self.assertRaisesRegex(AdapterError, "remote target changed") as caught:
            RemoteUserApplyExecutor(
                self.staging, self.home, os.getuid(), clock=lambda: self.now
            ).execute(self.request.request_id, self.request.request_hash, CancellationToken())
        self.assertEqual(caught.exception.code, "stale_plan")
        self.assertEqual(self.target.read_bytes(), b"changed")

    def test_request_rejects_non_allowlisted_target_and_hash_tampering(self) -> None:
        unsafe = replace(self.request, target=".ssh/authorized_keys").with_hash()
        with self.assertRaises(AdapterError) as target_error:
            encode_remote_user_apply_request(unsafe)
        self.assertEqual(target_error.exception.code, "invalid_remote_user_apply_binding")

        content = encode_remote_user_apply_request(self.request).replace(b"plan-1", b"plan-2")
        with self.assertRaises(AdapterError) as hash_error:
            decode_remote_user_apply_request(
                content, expected_hash=self.request.request_hash, now=self.now
            )
        self.assertIn(
            hash_error.exception.code,
            {"invalid_remote_user_apply_request", "remote_user_apply_request_hash_mismatch"},
        )

    def test_cli_rejects_root_user_apply(self) -> None:
        code, content = run_remote_helper(
            ("user-apply", self.request.request_id, self.request.request_hash),
            effective_uid=0,
            current_uid=0,
            home_for_uid=lambda _uid: self.home,
        )
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(content)["code"], "invalid_remote_user")


if __name__ == "__main__":
    unittest.main()
