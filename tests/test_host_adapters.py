import unittest
from dataclasses import dataclass, field

from llm_manager.adapters.host.openssh import OpenSshHostAdapter
from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandRequest, CommandResult


@dataclass
class RecordingRunner:
    requests: list[CommandRequest] = field(default_factory=list)

    def run(self, request: CommandRequest, cancellation: CancellationToken) -> CommandResult:
        self.requests.append(request)
        return CommandResult(request.argv, 0, "remote-host\n", "", False, 1)


class OpenSshHostAdapterTests(unittest.TestCase):
    def test_rejects_option_injection_alias(self) -> None:
        with self.assertRaises(ValueError):
            OpenSshHostAdapter("-oProxyCommand=bad", RecordingRunner())  # type: ignore[arg-type]

    def test_uses_batch_mode_and_quoted_remote_command(self) -> None:
        runner = RecordingRunner()
        adapter = OpenSshHostAdapter("gpu-box", runner)  # type: ignore[arg-type]
        adapter.execute_readonly(
            CommandRequest(("cat", "--", "/tmp/a file"), 1000, "test"), CancellationToken()
        )
        self.assertEqual(
            runner.requests[0].argv,
            (
                "ssh",
                "-o",
                "BatchMode=yes",
                "--",
                "gpu-box",
                "env LC_ALL=C LANG=C cat -- '/tmp/a file'",
            ),
        )

    def test_rejects_remote_command_outside_allowlist(self) -> None:
        adapter = OpenSshHostAdapter("gpu-box", RecordingRunner())  # type: ignore[arg-type]
        with self.assertRaises(AdapterError):
            adapter.execute_readonly(CommandRequest(("rm", "/tmp/x"), 1000, "test"), CancellationToken())

    def test_allows_only_explicit_additional_absolute_executable(self) -> None:
        runner = RecordingRunner()
        adapter = OpenSshHostAdapter(
            "gpu-box", runner, allowed_remote_executables=frozenset({"/home/user/.opencode/bin/opencode"})
        )  # type: ignore[arg-type]
        adapter.execute_readonly(
            CommandRequest(("/home/user/.opencode/bin/opencode", "--version"), 1000, "test"),
            CancellationToken(),
        )
        self.assertIn("env LC_ALL=C LANG=C /home/user/.opencode/bin/opencode --version", runner.requests[0].argv[-1])

    def test_rejects_relative_additional_executable(self) -> None:
        with self.assertRaises(ValueError):
            OpenSshHostAdapter(
                "gpu-box", RecordingRunner(), allowed_remote_executables=frozenset({"custom/tool"})
            )  # type: ignore[arg-type]

    def test_identify_exposes_only_validated_fingerprint(self) -> None:
        fingerprint = "SHA256:" + "A" * 43
        adapter = OpenSshHostAdapter(
            "gpu-box", RecordingRunner(), verified_fingerprint=fingerprint
        )  # type: ignore[arg-type]
        self.assertEqual(adapter.identify(CancellationToken()).fingerprint, fingerprint)

    def test_rejects_malformed_fingerprint(self) -> None:
        with self.assertRaises(ValueError):
            OpenSshHostAdapter(
                "gpu-box", RecordingRunner(), verified_fingerprint="gpu-box"
            )  # type: ignore[arg-type]

    def test_uses_explicit_control_socket(self) -> None:
        runner = RecordingRunner()
        adapter = OpenSshHostAdapter(
            "gpu-box", runner, control_socket="/tmp/llm-manager/cm-test"
        )  # type: ignore[arg-type]
        adapter.execute_readonly(CommandRequest(("uname", "-n"), 1000, "test"), CancellationToken())
        self.assertEqual(runner.requests[0].argv[1:3], ("-S", "/tmp/llm-manager/cm-test"))

    def test_stat_reads_remote_metadata_and_hash_with_fixed_commands(self) -> None:
        runner = _StatRunner()
        adapter = OpenSshHostAdapter("gpu-box", runner)  # type: ignore[arg-type]
        result = adapter.stat("/usr/bin/llm-manager-remote-helper", CancellationToken())
        self.assertTrue(result.exists)
        self.assertEqual((result.mode, result.uid, result.gid), (0o755, 0, 0))
        self.assertFalse(result.is_symlink)
        self.assertIsNotNone(result.sha256)
        self.assertIn("stat '--printf=", runner.requests[0].argv[-1])
        self.assertIn("cat -- /usr/bin/llm-manager-remote-helper", runner.requests[1].argv[-1])

    def test_stat_reports_symlink_without_reading_target(self) -> None:
        runner = _StatRunner(stat_output="symbolic link|777|0|0|12")
        adapter = OpenSshHostAdapter("gpu-box", runner)  # type: ignore[arg-type]
        result = adapter.stat("/usr/bin/llm-manager-remote-helper", CancellationToken())
        self.assertTrue(result.is_symlink)
        self.assertIsNone(result.sha256)
        self.assertEqual(len(runner.requests), 1)


class _StatRunner(RecordingRunner):
    def __init__(self, stat_output="regular file|755|0|0|6"):
        super().__init__()
        self.stat_output = stat_output

    def run(self, request, cancellation):
        self.requests.append(request)
        output = self.stat_output if " stat " in request.argv[-1] else "helper"
        return CommandResult(request.argv, 0, output, "", False, 1)


if __name__ == "__main__":
    unittest.main()
