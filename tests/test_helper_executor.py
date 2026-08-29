import hashlib
import tempfile
import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.helper_executor import DeclaredHelperExecutor
from llm_manager.infrastructure.helper_protocol import HelperOperation, HelperOperationKind, HelperRequest
from llm_manager.infrastructure.helper_staging import HelperStagingStore
from llm_manager.planning.ollama import DROP_IN_PATH


def _request(before: bytes | None, after: bytes) -> HelperRequest:
    now = datetime.now(UTC)
    operations = (
        HelperOperation(
            "write-1",
            HelperOperationKind.ATOMIC_REPLACE,
            target=DROP_IN_PATH,
            before_hash=hashlib.sha256(before).hexdigest() if before is not None else None,
            staged_content_hash=hashlib.sha256(after).hexdigest(),
            expected_mode=0o644,
            expected_uid=0,
            expected_gid=0,
        ),
        HelperOperation("reload-1", HelperOperationKind.DAEMON_RELOAD),
        HelperOperation("restart-1", HelperOperationKind.RESTART_UNIT, unit="ollama.service"),
    )
    return HelperRequest(
        1, "operation-1", "host-1", "plan-1", "a" * 64, operations,
        now, now + timedelta(minutes=5),
    ).with_hash()


@dataclass
class _Backend:
    content: bytes | None
    fail_on: str | None = None
    calls: list[str] = field(default_factory=list)

    def read_file(self, target):
        self.calls.append("read_file")
        return self.content

    def atomic_write(self, target, content, mode, uid, gid):
        self.calls.append("atomic_write")
        if self.fail_on == "atomic_write":
            raise OSError("injected")
        self.content = content
        self.metadata = (mode, uid, gid)

    def remove_file(self, target):
        self.calls.append("remove_file")
        self.content = None

    def daemon_reload(self):
        self.calls.append("daemon_reload")
        if self.fail_on == "daemon_reload":
            raise OSError("injected")

    def restart_unit(self, unit):
        self.calls.append("restart_unit")


class DeclaredHelperExecutorTests(unittest.TestCase):
    def test_executes_verified_write_reload_restart_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            before = b"old"
            after = b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n'
            request = _request(before, after)
            staging = HelperStagingStore(Path(directory) / "stage")
            staging.stage(request, "write-1", after)
            backend = _Backend(before)
            results = DeclaredHelperExecutor(staging, backend).execute(request, request.request_hash)
            self.assertTrue(all(item.completed for item in results))
            self.assertEqual(backend.calls, ["read_file", "atomic_write", "daemon_reload", "restart_unit"])
            self.assertEqual(backend.content, after)
            self.assertEqual(backend.metadata, (0o644, 0, 0))

    def test_stale_target_stops_before_any_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = _request(b"old", b"new")
            staging = HelperStagingStore(Path(directory) / "stage")
            staging.stage(request, "write-1", b"new")
            backend = _Backend(b"changed")
            results = DeclaredHelperExecutor(staging, backend).execute(request, request.request_hash)
            self.assertEqual(results[0].error_code, "stale_helper_target")
            self.assertEqual(backend.calls, ["read_file"])

    def test_backend_failure_stops_later_operations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = _request(b"old", b"new")
            staging = HelperStagingStore(Path(directory) / "stage")
            staging.stage(request, "write-1", b"new")
            backend = _Backend(b"old", fail_on="daemon_reload")
            results = DeclaredHelperExecutor(staging, backend).execute(request, request.request_hash)
            self.assertEqual([item.completed for item in results], [True, False, False])
            self.assertEqual(results[2].error_code, "not_executed")
            self.assertEqual(backend.calls, ["read_file", "atomic_write", "daemon_reload"])

    def test_rejects_request_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = _request(None, b"new")
            executor = DeclaredHelperExecutor(HelperStagingStore(Path(directory) / "stage"), _Backend(None))
            with self.assertRaises(AdapterError):
                executor.execute(request, "b" * 64)


if __name__ == "__main__":
    unittest.main()
