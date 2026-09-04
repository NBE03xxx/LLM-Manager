from __future__ import annotations

import hashlib
import json
import unittest
from datetime import UTC, datetime, timedelta

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.backup import BackupRestoreItem
from llm_manager.infrastructure.remote_helper import (
    REMOTE_HELPER_OPERATION,
    REMOTE_HELPER_PROTOCOL_VERSION,
    RemoteRecoveryRequest,
    encode_remote_request,
)
from llm_manager.infrastructure.ssh_remote_staging import (
    MAX_REMOTE_RECEIPT_BYTES,
    REMOTE_USER_STAGING_ROOT,
    RemoteRecoveryResultCompletionProbe,
    UserOnlySshRecoveryTransport,
)


NOW = datetime(2026, 8, 30, 3, 0, tzinfo=UTC)


class UserOnlySshRecoveryTransportTests(unittest.TestCase):
    def test_stages_private_items_then_request_invokes_fixed_identity_and_reads_result(self) -> None:
        runner = _Runner(result=b'{"receipt":"fake"}')
        transport = UserOnlySshRecoveryTransport(runner, clock=lambda: NOW)
        content = _request_content()
        item = BackupRestoreItem("/etc/example", True, b"before", hashlib.sha256(b"before").hexdigest(), 0o644, 0, 0)
        result = transport.create_recovery_copy(content, (item,), CancellationToken())
        request = json.loads(content)
        base = f"{REMOTE_USER_STAGING_ROOT}/backup-1/{request['request_hash']}"
        self.assertEqual(result, b'{"receipt":"fake"}')
        self.assertEqual(runner.calls[0], ("prepare", base))
        self.assertEqual(runner.calls[1][:2], ("upload", f"{base}/items/0000-{item.sha256}.bin"))
        self.assertEqual(runner.calls[2], ("upload", f"{base}/request.json", content))
        self.assertEqual(runner.calls[3], ("invoke", "backup-1", request["request_hash"]))
        self.assertEqual(runner.calls[4], ("read", f"{base}/result.json", MAX_REMOTE_RECEIPT_BYTES))

    def test_absent_items_are_declared_only_in_request_and_receipt_can_be_reloaded(self) -> None:
        runner = _Runner(result=b"receipt")
        transport = UserOnlySshRecoveryTransport(runner, clock=lambda: NOW)
        content = _request_content(item_hash=None)
        item = BackupRestoreItem("/etc/example", False, None, None, None, None, None)
        self.assertEqual(transport.create_recovery_copy(content, (item,), CancellationToken()), b"receipt")
        self.assertEqual(sum(call[0] == "upload" for call in runner.calls), 1)
        runner.calls.clear()
        self.assertEqual(transport.read_recovery_receipt(content, CancellationToken()), b"receipt")
        self.assertEqual(runner.calls[0][0], "read")

    def test_rejects_tamper_bad_content_and_cancellation_before_helper(self) -> None:
        content = _request_content()
        value = json.loads(content)
        value["storage_location"] = "/tmp/escape"
        tampered = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        with self.assertRaises(AdapterError):
            UserOnlySshRecoveryTransport(_Runner(), clock=lambda: NOW).create_recovery_copy(tampered, (), CancellationToken())
        bad = BackupRestoreItem("/etc/example", True, b"changed", hashlib.sha256(b"before").hexdigest(), 0o644, 0, 0)
        with self.assertRaises(AdapterError):
            UserOnlySshRecoveryTransport(_Runner(), clock=lambda: NOW).create_recovery_copy(content, (bad,), CancellationToken())
        valid = BackupRestoreItem("/etc/example", True, b"before", hashlib.sha256(b"before").hexdigest(), 0o644, 0, 0)
        runner = _Runner(cancel_after_upload=True)
        token = CancellationToken()
        runner.token = token
        with self.assertRaises(OperationCancelled):
            UserOnlySshRecoveryTransport(runner, clock=lambda: NOW).create_recovery_copy(content, (valid,), token)
        self.assertFalse(any(call[0] == "invoke" for call in runner.calls))

    def test_expired_request_and_oversized_result_fail_closed(self) -> None:
        content = _request_content()
        with self.assertRaises(AdapterError):
            UserOnlySshRecoveryTransport(_Runner(), clock=lambda: NOW + timedelta(minutes=6)).create_recovery_copy(content, (), CancellationToken())
        runner = _Runner(result=b"x" * (MAX_REMOTE_RECEIPT_BYTES + 1))
        with self.assertRaises(AdapterError):
            UserOnlySshRecoveryTransport(runner, clock=lambda: NOW).read_recovery_receipt(content, CancellationToken())


class RemoteRecoveryResultCompletionProbeTests(unittest.TestCase):
    def test_checks_only_the_bound_immutable_result_path(self) -> None:
        runner = _Runner(result=b"result")
        probe = RemoteRecoveryResultCompletionProbe(runner)
        self.assertTrue(probe.completed("backup-1", "a" * 64, CancellationToken()))
        self.assertEqual(
            runner.calls,
            [("read", f"{REMOTE_USER_STAGING_ROOT}/backup-1/{'a' * 64}/result.json",
              MAX_REMOTE_RECEIPT_BYTES)],
        )

    def test_missing_is_pending_but_other_failures_and_cancel_propagate(self) -> None:
        runner = _Runner(read_error="remote_staging_failed")
        probe = RemoteRecoveryResultCompletionProbe(runner)
        self.assertFalse(probe.completed("backup-1", "b" * 64, CancellationToken()))
        runner.read_error = "remote_result_too_large"
        with self.assertRaises(AdapterError) as caught:
            probe.completed("backup-1", "b" * 64, CancellationToken())
        self.assertEqual(caught.exception.code, "remote_result_too_large")
        with self.assertRaises(OperationCancelled):
            probe.completed("backup-1", "b" * 64, CancellationToken(True))
        with self.assertRaises(AdapterError):
            probe.completed("../backup", "b" * 64, CancellationToken())


class _Runner:
    def __init__(self, *, result=b"", cancel_after_upload=False, read_error=None):
        self.result = result
        self.cancel_after_upload = cancel_after_upload
        self.read_error = read_error
        self.calls = []
        self.token = None

    def prepare_private_directory(self, relative_path):
        self.calls.append(("prepare", relative_path))

    def upload_private_file(self, relative_path, content):
        self.calls.append(("upload", relative_path, content))
        if self.cancel_after_upload and self.token is not None:
            self.token.cancel()

    def invoke_recovery_helper(self, request_id, request_hash, cancellation):
        self.calls.append(("invoke", request_id, request_hash))

    def read_private_file(self, relative_path, max_bytes):
        self.calls.append(("read", relative_path, max_bytes))
        if self.read_error is not None:
            raise AdapterError(self.read_error, "fake read failure")
        if len(self.result) > max_bytes:
            raise AdapterError("remote_result_too_large", "fake bounded read rejected result")
        return self.result

    def remove_private_tree(self, relative_path):
        self.calls.append(("remove", relative_path))


def _request_content(item_hash=hashlib.sha256(b"before").hexdigest()):
    request = RemoteRecoveryRequest(
        REMOTE_HELPER_PROTOCOL_VERSION, REMOTE_HELPER_OPERATION, "backup-1", "backup-1",
        "plan-1", "c" * 64, "ssh:gpu-box", "SHA256:" + "a" * 43, "d" * 64,
        "/var/lib/llm-manager/backups/87fe234ee99a458ab8e75e14/backup-1",
        "remote-master-v1", "remote_root", (("/etc/example", item_hash),),
        NOW, NOW + timedelta(days=30), False, NOW,
        NOW + timedelta(minutes=5),
    ).with_hash()
    return encode_remote_request(request)


if __name__ == "__main__":
    unittest.main()
