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
from llm_manager.infrastructure.remote_user_rollback import (
    REMOTE_USER_ROLLBACK_OPERATION,
    REMOTE_USER_ROLLBACK_PROTOCOL_VERSION,
    RemoteUserRollbackExecutor,
    RemoteUserRollbackRequest,
    decode_remote_user_rollback_result,
    encode_remote_user_rollback_request,
    validate_remote_user_rollback_result,
)


BEFORE = b'{"model":"old"}\n'
AFTER = b'{"model":"new"}\n'


class RemoteUserRollbackTests(unittest.TestCase):
    def test_atomically_restores_existing_file_and_emits_bound_result(self) -> None:
        with _Case(True) as case:
            content = case.execute()
            self.assertEqual(case.target.read_bytes(), BEFORE)
            self.assertEqual(case.target.stat().st_mode & 0o7777, 0o640)
            result = decode_remote_user_rollback_result(content)
            validate_remote_user_rollback_result(case.request, result)
            self.assertEqual(result.restored_hash, hashlib.sha256(BEFORE).hexdigest())

    def test_removes_file_created_by_apply(self) -> None:
        with _Case(False) as case:
            result = decode_remote_user_rollback_result(case.execute())
            self.assertFalse(case.target.exists())
            self.assertIsNone(result.restored_hash)

    def test_stale_target_and_unexpected_payload_fail_before_mutation(self) -> None:
        with _Case(True) as case:
            case.target.write_bytes(b"externally changed")
            with self.assertRaises(AdapterError) as stale:
                case.execute()
            self.assertEqual(stale.exception.code, "stale_rollback_target")
            self.assertEqual(case.target.read_bytes(), b"externally changed")
        with _Case(False) as case:
            extra = case.operation / "items/extra"
            extra.write_bytes(b"x")
            os.chmod(extra, 0o600)
            with self.assertRaises(AdapterError) as payload:
                case.execute()
            self.assertEqual(payload.exception.code, "remote_user_rollback_payload_mismatch")
            self.assertTrue(case.target.exists())

    def test_rejects_tamper_invalid_restore_binding_and_root_cli(self) -> None:
        with _Case(True) as case:
            invalid = replace(case.request, restore_existed=False).with_hash()
            with self.assertRaises(AdapterError) as binding:
                encode_remote_user_rollback_request(invalid)
            self.assertEqual(binding.exception.code, "invalid_remote_user_rollback_binding")

            request_path = case.operation / "request.json"
            request_path.write_bytes(request_path.read_bytes().replace(b"plan-1", b"plan-2"))
            with self.assertRaises(AdapterError):
                case.execute()

            code, content = run_remote_helper(
                ("user-rollback", case.request.request_id, case.request.request_hash),
                effective_uid=0, current_uid=0, home_for_uid=lambda _uid: case.home,
            )
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(content)["code"], "invalid_remote_user")


class _Case:
    def __init__(self, restore_existed: bool):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.target = self.home / ".config/opencode/opencode.jsonc"
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(AFTER)
        self.now = utc_now()
        restore_hash = hashlib.sha256(BEFORE).hexdigest() if restore_existed else None
        self.request = RemoteUserRollbackRequest(
            REMOTE_USER_ROLLBACK_PROTOCOL_VERSION, REMOTE_USER_ROLLBACK_OPERATION,
            "rollback-1", "a" * 64, "plan-1", "b" * 64, "backup-1", "c" * 64,
            "ssh-host", "SHA256:verified", ".config/opencode/opencode.jsonc",
            hashlib.sha256(AFTER).hexdigest(), restore_existed, restore_hash,
            0o640 if restore_existed else None, self.now, self.now + timedelta(minutes=5),
        ).with_hash()
        staging = self.home / ".local/state/llm-manager/remote-helper"
        self.operation = staging / self.request.request_id / self.request.request_hash
        items = self.operation / "items"
        items.mkdir(mode=0o700, parents=True)
        for path in (
            self.home / ".local", self.home / ".local/state",
            self.home / ".local/state/llm-manager", staging,
            self.operation.parent, self.operation, items,
        ):
            os.chmod(path, 0o700)
        self._write(self.operation / "request.json", encode_remote_user_rollback_request(self.request))
        if restore_existed:
            self._write(items / f"0000-{restore_hash}.bin", BEFORE)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        path.write_bytes(content)
        os.chmod(path, 0o600)

    def execute(self) -> bytes:
        return RemoteUserRollbackExecutor(
            self.home / ".local/state/llm-manager/remote-helper",
            self.home, os.getuid(), clock=lambda: self.now,
        ).execute(self.request.request_id, self.request.request_hash, CancellationToken())


if __name__ == "__main__":
    unittest.main()
