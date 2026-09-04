from __future__ import annotations

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.remote_user_apply import (
    REMOTE_USER_APPLY_OPERATION,
    REMOTE_USER_APPLY_PROTOCOL_VERSION,
    RemoteUserApplyRequest,
    RemoteUserApplyResult,
    encode_remote_user_apply_request,
)
from llm_manager.infrastructure.ssh_remote_staging import REMOTE_USER_STAGING_ROOT
from llm_manager.infrastructure.ssh_user_apply import UserOnlySshApplyTransport


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
PAYLOAD = b'{"model":"new"}\n'


class UserOnlySshApplyTransportTests(unittest.TestCase):
    def test_stages_payload_then_request_invokes_fixed_apply_and_reads_bound_result(self) -> None:
        request = _request()
        runner = _Runner(_result(request))
        result = UserOnlySshApplyTransport(runner, lambda: NOW).apply(
            encode_remote_user_apply_request(request), PAYLOAD, CancellationToken()
        )
        base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
        self.assertEqual(result.after_hash, request.after_hash)
        self.assertEqual(runner.calls[0], ("prepare", base))
        self.assertEqual(runner.calls[1], ("upload", f"{base}/items/0000-{request.after_hash}.bin", PAYLOAD))
        self.assertEqual(runner.calls[2][0:2], ("upload", f"{base}/request.json"))
        self.assertEqual(runner.calls[3], ("invoke-user-apply", request.request_id, request.request_hash))
        self.assertEqual(runner.calls[4][0], "read")

    def test_rejects_payload_and_result_binding_tamper(self) -> None:
        request = _request()
        transport = UserOnlySshApplyTransport(_Runner(_result(request)), lambda: NOW)
        with self.assertRaises(AdapterError) as payload_error:
            transport.apply(encode_remote_user_apply_request(request), b"changed", CancellationToken())
        self.assertEqual(payload_error.exception.code, "remote_user_apply_payload_mismatch")

        bad_result = _result(replace(request, host_fingerprint="SHA256:other"))
        with self.assertRaises(AdapterError) as result_error:
            UserOnlySshApplyTransport(_Runner(bad_result), lambda: NOW).apply(
                encode_remote_user_apply_request(request), PAYLOAD, CancellationToken()
            )
        self.assertEqual(result_error.exception.code, "remote_user_apply_result_binding_mismatch")

    def test_disconnect_reconciliation_reads_same_immutable_result_without_invoke(self) -> None:
        request = _request()
        runner = _Runner(_result(request))
        result = UserOnlySshApplyTransport(runner, lambda: NOW).read_result(
            encode_remote_user_apply_request(request), CancellationToken()
        )
        self.assertEqual(result.request_hash, request.request_hash)
        self.assertEqual([call[0] for call in runner.calls], ["read"])

    def test_cancel_after_request_publication_never_invokes_apply(self) -> None:
        request = _request()
        token = CancellationToken()
        runner = _Runner(_result(request), cancel_after_upload=2, token=token)
        with self.assertRaises(OperationCancelled):
            UserOnlySshApplyTransport(runner, lambda: NOW).apply(
                encode_remote_user_apply_request(request), PAYLOAD, token
            )
        self.assertNotIn("invoke-user-apply", [call[0] for call in runner.calls])


class _Runner:
    def __init__(self, result: bytes, *, cancel_after_upload: int = 0, token=None):
        self.result = result
        self.cancel_after_upload = cancel_after_upload
        self.token = token
        self.uploads = 0
        self.calls = []

    def prepare_private_directory(self, path):
        self.calls.append(("prepare", path))

    def upload_private_file(self, path, content):
        self.calls.append(("upload", path, content))
        self.uploads += 1
        if self.uploads == self.cancel_after_upload and self.token is not None:
            self.token.cancel()

    def invoke_user_apply(self, request_id, request_hash, cancellation):
        self.calls.append(("invoke-user-apply", request_id, request_hash))

    def read_private_file(self, path, max_bytes):
        self.calls.append(("read", path, max_bytes))
        if len(self.result) > max_bytes:
            raise AdapterError("remote_result_too_large", "bounded read rejected result")
        return self.result

    def remove_private_tree(self, path):
        self.calls.append(("remove", path))


def _request() -> RemoteUserApplyRequest:
    return RemoteUserApplyRequest(
        REMOTE_USER_APPLY_PROTOCOL_VERSION, REMOTE_USER_APPLY_OPERATION,
        "apply-1", "plan-1", "a" * 64, "backup-1", "b" * 64,
        "ssh-host", "SHA256:verified", ".config/opencode/opencode.jsonc",
        "c" * 64, hashlib.sha256(PAYLOAD).hexdigest(), NOW,
        NOW + timedelta(minutes=5),
    ).with_hash()


def _result(request: RemoteUserApplyRequest) -> bytes:
    value = RemoteUserApplyResult(
        request.request_id, request.request_hash, request.host_id,
        request.host_fingerprint, request.target, request.before_hash, request.after_hash,
    )
    from llm_manager.domain.serialization import to_primitive
    return json.dumps(to_primitive(value), sort_keys=True, separators=(",", ":")).encode()


if __name__ == "__main__":
    unittest.main()
