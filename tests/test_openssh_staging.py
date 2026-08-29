from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.infrastructure.openssh_staging import OpenSshUserStagingRunner, REMOTE_HELPER


PATH = ".local/state/llm-manager/remote-helper/backup-1/" + "a" * 64


class OpenSshUserStagingRunnerTests(unittest.TestCase):
    def test_uses_fixed_ssh_scp_argv_control_socket_and_private_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            process = _Process(download=b"receipt")
            invoker = _Invoker()
            staging = OpenSshUserStagingRunner(
                "development", process, invoker, Path(directory) / "runtime",
                control_socket="/tmp/llm-manager-cm",
            )
            staging.prepare_private_directory(PATH)
            staging.upload_private_file(f"{PATH}/request.json", b"secret backup content")
            staging.invoke_recovery_helper("backup-1", "b" * 64, CancellationToken())
            self.assertEqual(staging.read_private_file(f"{PATH}/result.json", 1024), b"receipt")
            staging.remove_private_tree(PATH)
            prepare = process.requests[0].argv
            self.assertEqual(prepare[:6], ("ssh", "-S", "/tmp/llm-manager-cm", "-o", "BatchMode=yes", "--"))
            self.assertIn(REMOTE_HELPER, prepare[-1])
            upload = process.requests[1].argv
            self.assertEqual(upload[0], "scp")
            self.assertEqual(upload[-1], f"development:{PATH}/request.json")
            self.assertNotIn("secret backup content", " ".join(upload))
            self.assertEqual(invoker.calls, [("development", "/tmp/llm-manager-cm", "backup-1", "b" * 64)])
            self.assertEqual((Path(directory) / "runtime").stat().st_mode & 0o777, 0o700)

    def test_rejects_alias_path_and_invocation_injection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                OpenSshUserStagingRunner("-oProxyCommand=bad", _Process(), _Invoker(), Path(directory))
            staging = OpenSshUserStagingRunner("host", _Process(), _Invoker(), Path(directory))
            for path in ("/absolute", "../escape", ".local/state/llm-manager/other/file", PATH + "\ncommand"):
                with self.subTest(path=path), self.assertRaises(AdapterError):
                    staging.prepare_private_directory(path)
            with self.assertRaises(AdapterError):
                staging.invoke_recovery_helper("bad/id", "x" * 64, CancellationToken())

    def test_transfer_failure_timeout_missing_and_oversize_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            for result in (
                CommandResult(("scp",), 1, "", "failed", False, 1),
                CommandResult(("scp",), None, "", "", True, 1),
            ):
                with self.subTest(result=result):
                    staging = OpenSshUserStagingRunner("host", _Process(result=result), _Invoker(), Path(directory))
                    with self.assertRaises(AdapterError):
                        staging.upload_private_file(f"{PATH}/item", b"content")
            missing = OpenSshUserStagingRunner("host", _Process(), _Invoker(), Path(directory))
            with self.assertRaises(AdapterError):
                missing.read_private_file(f"{PATH}/result.json", 10)
            oversized = OpenSshUserStagingRunner("host", _Process(download=b"too large"), _Invoker(), Path(directory))
            with self.assertRaises(AdapterError):
                oversized.read_private_file(f"{PATH}/result.json", 3)


class _Process:
    def __init__(self, result=None, download=None):
        self.result = result
        self.download = download
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request)
        if request.correlation_id == "ssh.staging.download" and self.download is not None:
            Path(request.argv[-1]).write_bytes(self.download)
        return self.result or CommandResult(request.argv, 0, "", "", False, 1)


class _Invoker:
    def __init__(self):
        self.calls = []

    def invoke(self, alias, control_socket, request_id, request_hash, cancellation):
        self.calls.append((alias, control_socket, request_id, request_hash))


if __name__ == "__main__":
    unittest.main()
