from __future__ import annotations

import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.infrastructure.openssh_remote_retention import (
    OpenSshRemoteRetentionInvoker,
    OpenSshRemoteRetentionPort,
)
from llm_manager.infrastructure.remote_backup import RemoteRetentionRecord
from llm_manager.infrastructure.remote_retention import (
    REMOTE_RETENTION_OPERATION,
    REMOTE_RETENTION_PROTOCOL_VERSION,
    RemoteRetentionHelperExecutor,
    RemoteRetentionRequest,
    RemoteRetentionResult,
    RemoteRetentionState,
    decode_remote_retention_request,
    decode_remote_retention_result,
    encode_remote_retention_request,
    encode_remote_retention_result,
)


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
FINGERPRINT = "SHA256:" + "a" * 43


class RemoteRetentionProtocolTests(unittest.TestCase):
    def test_request_and_result_are_canonical_hash_bound_and_time_bound(self) -> None:
        request = _request()
        content = encode_remote_retention_request(request)
        self.assertEqual(
            decode_remote_retention_request(content, expected_hash=request.request_hash, now=NOW),
            request,
        )
        with self.assertRaises(AdapterError):
            decode_remote_retention_request(
                content + b"\n", expected_hash=request.request_hash, now=NOW
            )
        with self.assertRaises(AdapterError):
            decode_remote_retention_request(
                content,
                expected_hash=request.request_hash,
                now=NOW + timedelta(minutes=6),
            )
        result = RemoteRetentionResult(
            "1.0", request.request_id, request.request_hash, request.host_id,
            request.host_fingerprint, NOW, RemoteRetentionState.COMPLETED,
            ("backup-1",), ("backup-2",), None,
        ).with_hash()
        self.assertEqual(
            decode_remote_retention_result(encode_remote_retention_result(result)), result
        )


class RemoteRetentionHelperExecutorTests(unittest.TestCase):
    def test_executes_fixed_ten_generation_prune_and_persists_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = _request()
            operation = _stage(Path(directory), request)
            backend = _Backend(("backup-2", "backup-1"), removed=("backup-1",))
            result = decode_remote_retention_result(
                RemoteRetentionHelperExecutor(
                    Path(directory), backend, os.getuid(), clock=lambda: NOW
                ).execute(request.request_id, request.request_hash, CancellationToken())
            )
            self.assertEqual(result.state, RemoteRetentionState.COMPLETED)
            self.assertEqual(result.removed_backup_ids, ("backup-1",))
            self.assertEqual(result.remaining_backup_ids, ("backup-2",))
            self.assertEqual(backend.prune_calls[0][-1], 10)
            self.assertEqual((operation / "result.json").stat().st_mode & 0o777, 0o600)

    def test_partial_failure_is_reconciled_and_unknown_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = _request("retention-partial")
            _stage(Path(directory), request)
            backend = _Backend(
                ("backup-2", "backup-1"), fail=AdapterError("delete_failed", "fail"),
                after_failure=("backup-2",),
            )
            result = decode_remote_retention_result(
                RemoteRetentionHelperExecutor(
                    Path(directory), backend, os.getuid(), clock=lambda: NOW
                ).execute(request.request_id, request.request_hash, CancellationToken())
            )
            self.assertEqual(result.state, RemoteRetentionState.PARTIAL)
            self.assertEqual(result.removed_backup_ids, ("backup-1",))
            self.assertEqual(result.error_code, "delete_failed")

        with tempfile.TemporaryDirectory() as directory:
            request = _request("retention-unknown")
            _stage(Path(directory), request)
            backend = _Backend(
                ("backup-1",), fail=AdapterError("delete_failed", "fail"),
                reconcile_fail=True,
            )
            result = decode_remote_retention_result(
                RemoteRetentionHelperExecutor(
                    Path(directory), backend, os.getuid(), clock=lambda: NOW
                ).execute(request.request_id, request.request_hash, CancellationToken())
            )
            self.assertEqual(result.state, RemoteRetentionState.UNKNOWN)
            self.assertEqual(result.remaining_backup_ids, ())


class OpenSshRemoteRetentionTests(unittest.TestCase):
    def test_transport_stages_canonical_request_and_binds_result(self) -> None:
        staging = _Staging()
        invoker = _Invoker(staging)
        port = OpenSshRemoteRetentionPort(staging, invoker, clock=lambda: NOW)
        result = port.prune("retention-1", "ssh:host", FINGERPRINT, CancellationToken())
        self.assertEqual(result.state, RemoteRetentionState.COMPLETED)
        self.assertTrue(staging.uploads[0][0].endswith("/request.json"))
        request = decode_remote_retention_request(
            staging.uploads[0][1], expected_hash=invoker.calls[0][1], now=NOW
        )
        self.assertEqual((request.host_id, request.host_fingerprint), ("ssh:host", FINGERPRINT))

    def test_root_invoker_uses_fixed_passwordless_command_and_readiness_gate(self) -> None:
        runner = _Runner(CommandResult(("ssh",), 0, "", "", False, 1))
        gate = _Gate()
        invoker = OpenSshRemoteRetentionInvoker(
            "development", runner, gate, control_socket="/tmp/cm"
        )
        invoker.invoke("retention-1", "a" * 64, CancellationToken())
        self.assertEqual(gate.calls, 1)
        self.assertEqual(
            runner.requests[0].argv[-1],
            "sudo -n -- /usr/bin/llm-manager-remote-helper invoke-retention retention-1 "
            + "a" * 64,
        )

    def test_transport_recovers_persisted_result_after_ambiguous_invoke_failure(self) -> None:
        staging = _Staging()
        invoker = _Invoker(
            staging, error=AdapterError("remote_retention_timeout", "ambiguous")
        )
        result = OpenSshRemoteRetentionPort(
            staging, invoker, clock=lambda: NOW
        ).prune("retention-1", "ssh:host", FINGERPRINT, CancellationToken())
        self.assertEqual(result.state, RemoteRetentionState.COMPLETED)


def _request(request_id: str = "retention-1") -> RemoteRetentionRequest:
    return RemoteRetentionRequest(
        "1.0", REMOTE_RETENTION_PROTOCOL_VERSION, REMOTE_RETENTION_OPERATION,
        request_id, "ssh:host", FINGERPRINT, NOW, NOW,
        NOW + timedelta(minutes=5),
    ).with_hash()


def _stage(root: Path, request: RemoteRetentionRequest) -> Path:
    operation = root / request.request_id / request.request_hash
    (operation / "items").mkdir(parents=True)
    for path in (root, operation.parent, operation, operation / "items"):
        os.chmod(path, 0o700)
    request_path = operation / "request.json"
    request_path.write_bytes(encode_remote_retention_request(request))
    os.chmod(request_path, 0o600)
    return operation


class _Backend:
    def __init__(self, records, *, removed=(), fail=None, after_failure=(), reconcile_fail=False):
        self.ids = tuple(records)
        self.removed = tuple(removed)
        self.fail = fail
        self.after_failure = tuple(after_failure)
        self.reconcile_fail = reconcile_fail
        self.failed = False
        self.prune_calls = []

    def list_retention(self, host_id, *, expected_fingerprint=None):
        if self.failed and self.reconcile_fail:
            raise AdapterError("invalid_remote_retention", "cannot reconcile")
        ids = self.after_failure if self.failed else self.ids
        return tuple(
            RemoteRetentionRecord(
                "1.0", item, host_id, "b" * 64, NOW,
                NOW + timedelta(days=30), False, "c" * 64,
            )
            for item in ids
        )

    def prune(self, host_id, *, now, keep_generations=10, expected_fingerprint=None):
        self.prune_calls.append((host_id, now, expected_fingerprint, keep_generations))
        if self.fail:
            self.failed = True
            raise self.fail
        self.ids = tuple(item for item in self.ids if item not in self.removed)
        return self.removed


class _Staging:
    def __init__(self):
        self.uploads = []
        self.result = b""

    def prepare_private_directory(self, path):
        self.path = path

    def upload_private_file(self, path, content):
        self.uploads.append((path, content))

    def read_private_file(self, path, max_bytes):
        return self.result

    def remove_private_tree(self, path):
        pass

    def invoke_recovery_helper(self, request_id, request_hash, cancellation):
        raise AssertionError("recovery helper must not be used")


class _Invoker:
    def __init__(self, staging, error=None):
        self.staging = staging
        self.error = error
        self.calls = []

    def invoke(self, request_id, request_hash, cancellation):
        self.calls.append((request_id, request_hash))
        request = decode_remote_retention_request(
            self.staging.uploads[-1][1], expected_hash=request_hash, now=NOW
        )
        self.staging.result = encode_remote_retention_result(
            RemoteRetentionResult(
                "1.0", request_id, request_hash, request.host_id,
                request.host_fingerprint, NOW, RemoteRetentionState.COMPLETED,
                (), ("backup-1",), None,
            ).with_hash()
        )
        if self.error:
            raise self.error


class _Runner:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request)
        return self.result


class _Gate:
    def __init__(self):
        self.calls = 0

    def assert_ready(self, cancellation):
        self.calls += 1


if __name__ == "__main__":
    unittest.main()
