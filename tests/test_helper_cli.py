import hashlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.infrastructure.helper_cli import run_helper
from llm_manager.infrastructure.helper_protocol import HelperOperation, HelperOperationKind, HelperRequest, encode_request
from llm_manager.planning.ollama import DROP_IN_PATH


class _Backend:
    def __init__(self):
        self.content = None
        self.calls = []

    def read_file(self, target):
        return self.content

    def atomic_write(self, target, content, mode, uid, gid):
        self.calls.append((target, mode, uid, gid))
        self.content = content

    def remove_file(self, target):
        self.content = None

    def daemon_reload(self):
        self.calls.append("reload")

    def restart_unit(self, unit):
        self.calls.append(("restart", unit))


def _stage(runtime_base: Path, uid: int, operation_id: str = "operation-1"):
    content = b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\n'
    now = datetime.now(UTC)
    operation = HelperOperation(
        "write-1", HelperOperationKind.ATOMIC_REPLACE, target=DROP_IN_PATH,
        staged_content_hash=hashlib.sha256(content).hexdigest(), expected_mode=0o644,
        expected_uid=0, expected_gid=0,
    )
    request = HelperRequest(
        1, operation_id, "host-1", "plan-1", "a" * 64, (operation,),
        now, now + timedelta(minutes=5),
    ).with_hash()
    directory = runtime_base / str(uid) / "llm-manager/helper" / operation_id
    directory.mkdir(parents=True, mode=0o700)
    staging_root = runtime_base / str(uid) / "llm-manager/helper"
    staging_root.chmod(0o700)
    directory.chmod(0o700)
    request_path = directory / "request.json"
    request_path.write_bytes(encode_request(request))
    request_path.chmod(0o600)
    staged = directory / "write-1.content"
    staged.write_bytes(content)
    staged.chmod(0o600)
    return request, request_path


class HelperCliTests(unittest.TestCase):
    def test_derives_request_path_and_executes_as_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            uid = path_owner = runtime.stat().st_uid
            request, request_path = _stage(runtime, uid)
            self.assertEqual(path_owner, request_path.stat().st_uid)
            backend = _Backend()
            results = run_helper(
                request.operation_id, request.request_hash, environ={"PKEXEC_UID": str(uid)},
                runtime_base=runtime, backend=backend, effective_uid=0,
            )
            self.assertTrue(results[0].completed)
            self.assertEqual(backend.content, (request_path.parent / "write-1.content").read_bytes())

    def test_rejects_non_root_ambiguous_uid_wrong_mode_and_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            uid = runtime.stat().st_uid
            request, path = _stage(runtime, uid)
            with self.assertRaises(AdapterError):
                run_helper(request.operation_id, request.request_hash, environ={"PKEXEC_UID": str(uid)}, runtime_base=runtime, backend=_Backend(), effective_uid=uid)
            with self.assertRaises(AdapterError):
                run_helper(request.operation_id, request.request_hash, environ={"PKEXEC_UID": str(uid), "SUDO_UID": str(uid)}, runtime_base=runtime, backend=_Backend(), effective_uid=0)
            path.chmod(0o644)
            with self.assertRaises(AdapterError):
                run_helper(request.operation_id, request.request_hash, environ={"PKEXEC_UID": str(uid)}, runtime_base=runtime, backend=_Backend(), effective_uid=0)
            path.chmod(0o600)
            with self.assertRaises(AdapterError):
                run_helper("other-operation", request.request_hash, environ={"PKEXEC_UID": str(uid)}, runtime_base=runtime, backend=_Backend(), effective_uid=0)
            outside = runtime / "outside-request"
            outside.write_bytes(encode_request(request))
            outside.chmod(0o600)
            path.unlink()
            path.symlink_to(outside)
            with self.assertRaises(AdapterError):
                run_helper(request.operation_id, request.request_hash, environ={"PKEXEC_UID": str(uid)}, runtime_base=runtime, backend=_Backend(), effective_uid=0)

    def test_policy_requires_active_admin_and_fixed_executable(self) -> None:
        policy = Path("packaging/polkit/io.github.nbe03xxx.llm-manager.policy")
        root = ET.parse(policy).getroot()
        action = root.find("action")
        self.assertEqual(action.attrib["id"], "io.github.nbe03xxx.llm-manager.apply-system-settings")
        self.assertEqual(action.findtext("defaults/allow_any"), "no")
        self.assertEqual(action.findtext("defaults/allow_inactive"), "no")
        self.assertEqual(action.findtext("defaults/allow_active"), "auth_admin")
        annotations = {item.attrib["key"]: item.text for item in action.findall("annotate")}
        self.assertEqual(annotations["org.freedesktop.policykit.exec.path"], "/usr/bin/llm-manager-helper")


if __name__ == "__main__":
    unittest.main()
