import hashlib
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.helper_protocol import HelperOperation, HelperOperationKind, HelperRequest
from llm_manager.infrastructure.helper_staging import HelperStagingStore
from llm_manager.planning.ollama import DROP_IN_PATH


def _request(content: bytes) -> HelperRequest:
    now = datetime.now(UTC)
    operation = HelperOperation(
        "write-1",
        HelperOperationKind.ATOMIC_REPLACE,
        target=DROP_IN_PATH,
        staged_content_hash=hashlib.sha256(content).hexdigest(),
        expected_mode=0o644,
        expected_uid=0,
        expected_gid=0,
    )
    return HelperRequest(1, "operation-1", "host-1", "plan-1", "a" * 64, (operation,), now, now + timedelta(minutes=5)).with_hash()


class HelperStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "staging"
        self.store = HelperStagingStore(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_stage_verify_and_cleanup_use_fixed_private_paths(self) -> None:
        content = b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n'
        request = _request(content)
        path = self.store.stage(request, "write-1", content)
        self.assertEqual(path, self.root / "operation-1" / "write-1.content")
        self.assertEqual(self.store.verify(request, request.operations[0]), content)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        request_path = self.store.stage_request(request)
        self.assertEqual(request_path, path.parent / "request.json")
        self.assertEqual(request_path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(AdapterError):
            self.store.stage_request(request)
        self.store.cleanup("operation-1")
        self.assertFalse(path.parent.exists())

    def test_rejects_hash_mismatch_mutation_and_duplicate_stage(self) -> None:
        content = b"safe"
        request = _request(content)
        with self.assertRaises(AdapterError):
            self.store.stage(request, "write-1", b"different")
        path = self.store.stage(request, "write-1", content)
        with self.assertRaises(AdapterError):
            self.store.stage(request, "write-1", content)
        path.write_bytes(b"changed")
        with self.assertRaises(AdapterError):
            self.store.verify(request, request.operations[0])

    def test_rejects_world_readable_file_and_symlink(self) -> None:
        content = b"safe"
        request = _request(content)
        path = self.store.stage(request, "write-1", content)
        path.chmod(0o644)
        with self.assertRaises(AdapterError):
            self.store.verify(request, request.operations[0])
        path.unlink()
        target = Path(self.temp.name) / "outside"
        target.write_bytes(content)
        path.symlink_to(target)
        with self.assertRaises(AdapterError):
            self.store.verify(request, request.operations[0])

    def test_rejects_unsafe_root_and_unexpected_cleanup_entry(self) -> None:
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o777)
        content = b"safe"
        request = _request(content)
        with self.assertRaises(AdapterError):
            self.store.verify(request, request.operations[0])
        self.root.chmod(0o700)
        path = self.store.stage(request, "write-1", content)
        (path.parent / "unexpected").write_text("x", encoding="utf-8")
        with self.assertRaises(AdapterError):
            self.store.cleanup("operation-1")


if __name__ == "__main__":
    unittest.main()
