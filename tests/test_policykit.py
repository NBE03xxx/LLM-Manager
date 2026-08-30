import hashlib
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.infrastructure.helper_protocol import HelperOperation, HelperOperationKind, HelperRequest
from llm_manager.infrastructure.helper_staging import HelperStagingStore
from llm_manager.infrastructure.policykit import HELPER, PKEXEC, LocalPolicyKitInvoker
from llm_manager.planning.ollama import DROP_IN_PATH


class _Runner:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request)
        return self.result


def _request(content: bytes):
    now = datetime.now(UTC)
    operations = (
        HelperOperation(
            "write-1", HelperOperationKind.ATOMIC_REPLACE, target=DROP_IN_PATH,
            staged_content_hash=hashlib.sha256(content).hexdigest(), expected_mode=0o644,
            expected_uid=0, expected_gid=0,
        ),
        HelperOperation("reload-1", HelperOperationKind.DAEMON_RELOAD),
    )
    return HelperRequest(1, "operation-1", "host-1", "plan-1", "a" * 64, operations, now, now + timedelta(minutes=5)).with_hash()


def _stdout(request, completed=True):
    value = {
        "status": "completed" if completed else "failed",
        "operations": [
            {"operation_id": item.operation_id, "kind": item.kind.value, "completed": completed, "error_code": None if completed else "denied"}
            for item in request.operations
        ],
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


class LocalPolicyKitInvokerTests(unittest.TestCase):
    def test_stages_complete_request_and_uses_fixed_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = b"safe"
            request = _request(content)
            stdout = _stdout(request)
            runner = _Runner(CommandResult((PKEXEC,), 0, stdout, "", False, 1))
            staging = HelperStagingStore(Path(directory) / "stage")
            results = LocalPolicyKitInvoker(staging, runner).invoke(
                request, (("write-1", content),), CancellationToken()
            )
            self.assertTrue(all(item.completed for item in results))
            self.assertEqual(runner.requests[0].argv, (PKEXEC, HELPER, request.operation_id, request.request_hash))
            self.assertTrue((Path(directory) / "stage/operation-1/request.json").is_file())

    def test_rejects_missing_content_timeout_and_malformed_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = b"safe"
            request = _request(content)
            staging = HelperStagingStore(Path(directory) / "stage")
            runner = _Runner(CommandResult((PKEXEC,), 1, "{}\n", "", False, 1))
            invoker = LocalPolicyKitInvoker(staging, runner)
            with self.assertRaises(AdapterError):
                invoker.invoke(request, (), CancellationToken())

        with tempfile.TemporaryDirectory() as directory:
            staging = HelperStagingStore(Path(directory) / "stage")
            timed_out = _Runner(CommandResult((PKEXEC,), None, "", "", True, 1))
            with self.assertRaises(AdapterError):
                LocalPolicyKitInvoker(staging, timed_out).invoke(request, (("write-1", content),), CancellationToken())

        with tempfile.TemporaryDirectory() as directory:
            staging = HelperStagingStore(Path(directory) / "stage")
            malformed = _Runner(CommandResult((PKEXEC,), 0, "{}\n", "", False, 1))
            with self.assertRaises(AdapterError):
                LocalPolicyKitInvoker(staging, malformed).invoke(request, (("write-1", content),), CancellationToken())

    def test_returns_declared_helper_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = b"safe"
            request = _request(content)
            runner = _Runner(CommandResult((PKEXEC,), 1, _stdout(request, False), "", False, 1))
            results = LocalPolicyKitInvoker(HelperStagingStore(Path(directory) / "stage"), runner).invoke(
                request, (("write-1", content),), CancellationToken()
            )
            self.assertFalse(results[0].completed)

    def test_maps_policykit_denial_without_parsing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = b"safe"
            request = _request(content)
            runner = _Runner(CommandResult((PKEXEC,), 126, "", "", False, 1))
            with self.assertRaises(AdapterError) as raised:
                LocalPolicyKitInvoker(HelperStagingStore(Path(directory) / "stage"), runner).invoke(
                    request, (("write-1", content),), CancellationToken()
                )
            self.assertEqual(raised.exception.code, "privilege_denied")

    def test_maps_uninstalled_helper_or_action_to_launch_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            content = b"safe"
            request = _request(content)
            runner = _Runner(CommandResult((PKEXEC,), 127, "", "", False, 1))
            with self.assertRaises(AdapterError) as raised:
                LocalPolicyKitInvoker(
                    HelperStagingStore(Path(directory) / "stage"), runner
                ).invoke(
                    request, (("write-1", content),), CancellationToken()
                )
            self.assertEqual(raised.exception.code, "helper_launch_failed")


if __name__ == "__main__":
    unittest.main()
