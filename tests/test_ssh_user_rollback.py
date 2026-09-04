from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive
from llm_manager.infrastructure.remote_user_rollback import (
    REMOTE_USER_ROLLBACK_OPERATION,
    REMOTE_USER_ROLLBACK_PROTOCOL_VERSION,
    RemoteUserRollbackRequest,
    RemoteUserRollbackResult,
    encode_remote_user_rollback_request,
)
from llm_manager.infrastructure.ssh_remote_staging import REMOTE_USER_STAGING_ROOT
from llm_manager.infrastructure.ssh_user_rollback import UserOnlySshRollbackTransport


NOW = datetime(2026, 9, 4, 14, 0, tzinfo=UTC)
BEFORE = b'{"model":"old"}\n'


class UserOnlySshRollbackTransportTests(unittest.TestCase):
    def test_stages_restore_then_request_invokes_fixed_rollback_and_reads_result(self) -> None:
        request = _request(True)
        runner = _Runner(_result(request))
        result = UserOnlySshRollbackTransport(runner, lambda: NOW).rollback(
            encode_remote_user_rollback_request(request), BEFORE, CancellationToken()
        )
        base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
        self.assertEqual(result.restored_hash, request.restore_hash)
        self.assertEqual(runner.calls[0], ("prepare", base))
        self.assertEqual(runner.calls[1][0:2], ("upload", f"{base}/items/0000-{request.restore_hash}.bin"))
        self.assertEqual(runner.calls[2][0:2], ("upload", f"{base}/request.json"))
        self.assertEqual(runner.calls[3], ("invoke", request.request_id, request.request_hash))

    def test_absent_restore_has_no_payload_and_reconciliation_does_not_invoke(self) -> None:
        request = _request(False)
        content = encode_remote_user_rollback_request(request)
        runner = _Runner(_result(request))
        UserOnlySshRollbackTransport(runner, lambda: NOW).rollback(
            content, None, CancellationToken()
        )
        self.assertEqual(sum(call[0] == "upload" for call in runner.calls), 1)
        runner.calls.clear()
        UserOnlySshRollbackTransport(runner, lambda: NOW).read_result(
            content, CancellationToken()
        )
        self.assertEqual([call[0] for call in runner.calls], ["read"])

    def test_rejects_payload_result_tamper_and_cancel_before_invoke(self) -> None:
        request = _request(True)
        with self.assertRaises(AdapterError) as payload:
            UserOnlySshRollbackTransport(_Runner(_result(request)), lambda: NOW).rollback(
                encode_remote_user_rollback_request(request), b"bad", CancellationToken()
            )
        self.assertEqual(payload.exception.code, "remote_user_rollback_payload_mismatch")

        wrong = replace(request, host_fingerprint="SHA256:other")
        with self.assertRaises(AdapterError) as result:
            UserOnlySshRollbackTransport(_Runner(_result(wrong)), lambda: NOW).rollback(
                encode_remote_user_rollback_request(request), BEFORE, CancellationToken()
            )
        self.assertEqual(result.exception.code, "remote_user_rollback_result_binding_mismatch")

        token = CancellationToken()
        runner = _Runner(_result(request), cancel_after_upload=2, token=token)
        with self.assertRaises(OperationCancelled):
            UserOnlySshRollbackTransport(runner, lambda: NOW).rollback(
                encode_remote_user_rollback_request(request), BEFORE, token
            )
        self.assertNotIn("invoke", [call[0] for call in runner.calls])


class _Runner:
    def __init__(self, result, *, cancel_after_upload=0, token=None):
        self.result = result
        self.cancel_after_upload = cancel_after_upload
        self.token = token
        self.uploads = 0
        self.calls = []

    def prepare_private_directory(self, path): self.calls.append(("prepare", path))
    def upload_private_file(self, path, content):
        self.calls.append(("upload", path, content))
        self.uploads += 1
        if self.uploads == self.cancel_after_upload and self.token is not None:
            self.token.cancel()
    def invoke_user_rollback(self, request_id, request_hash, cancellation):
        self.calls.append(("invoke", request_id, request_hash))
    def read_private_file(self, path, max_bytes):
        self.calls.append(("read", path, max_bytes))
        return self.result
    def remove_private_tree(self, path): self.calls.append(("remove", path))


def _request(existed: bool) -> RemoteUserRollbackRequest:
    return RemoteUserRollbackRequest(
        REMOTE_USER_ROLLBACK_PROTOCOL_VERSION, REMOTE_USER_ROLLBACK_OPERATION,
        "rollback-1", "a" * 64, "plan-1", "b" * 64, "backup-1", "c" * 64,
        "ssh-host", "SHA256:verified", ".config/opencode/opencode.jsonc",
        "d" * 64, existed, hashlib.sha256(BEFORE).hexdigest() if existed else None,
        0o600 if existed else None,
        NOW, NOW + timedelta(minutes=5),
    ).with_hash()


def _result(request: RemoteUserRollbackRequest) -> bytes:
    result = RemoteUserRollbackResult(
        request.request_id, request.request_hash, request.apply_request_hash,
        request.host_id, request.host_fingerprint, request.target, request.restore_hash,
    )
    return json.dumps(to_primitive(result), sort_keys=True, separators=(",", ":")).encode()


if __name__ == "__main__":
    unittest.main()
