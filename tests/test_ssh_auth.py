import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.infrastructure.ssh_auth import (
    ExternalTerminalSshBroker,
    SshAuthRequest,
    SshAliasAuthRequest,
    SshControlSession,
    TerminalSpec,
    detect_terminal,
)


class FakeRunner:
    def __init__(self) -> None:
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request)
        return CommandResult(request.argv, 0, "", "", False, 1)


class SshAuthRequestTests(unittest.TestCase):
    def test_rejects_option_injection(self) -> None:
        with self.assertRaises(ValueError):
            SshAuthRequest("yoshimi", "-oProxyCommand=bad")

    def test_rejects_invalid_username_and_port(self) -> None:
        with self.assertRaises(ValueError):
            SshAuthRequest("bad user", "host")
        with self.assertRaises(ValueError):
            SshAuthRequest("user", "host", 70000)

    def test_alias_request_rejects_option_injection(self) -> None:
        with self.assertRaises(ValueError):
            SshAliasAuthRequest("-oProxyCommand=bad")


class TerminalTests(unittest.TestCase):
    def test_prefers_ptyxis(self) -> None:
        paths = {"ptyxis": "/usr/bin/ptyxis", "gnome-terminal": "/usr/bin/gnome-terminal"}
        self.assertEqual(detect_terminal(paths.get), TerminalSpec("/usr/bin/ptyxis", "ptyxis"))

    def test_ptyxis_keeps_command_as_separate_argv(self) -> None:
        spec = TerminalSpec("/usr/bin/ptyxis", "ptyxis")
        argv = spec.launch_argv("Title", ("ssh", "user@host"))
        self.assertEqual(argv, ("/usr/bin/ptyxis", "--title=Title", "--", "ssh", "user@host"))


class BrokerTests(unittest.TestCase):
    def test_authentication_launches_control_master_without_password_argument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = FakeRunner()
            broker = ExternalTerminalSshBroker(
                runner, Path(directory), TerminalSpec("/usr/bin/ptyxis", "ptyxis")
            )  # type: ignore[arg-type]
            with patch("llm_manager.infrastructure.ssh_auth.subprocess.Popen") as popen:
                with patch.object(ExternalTerminalSshBroker, "_is_ready", return_value=True):
                    session = broker.authenticate(
                        SshAuthRequest("yoshimi", "192.168.1.253"), CancellationToken()
                    )
            argv = popen.call_args.args[0]
            self.assertIn("ControlMaster=yes", argv)
            self.assertIn("BatchMode=no", argv)
            self.assertNotIn("secret-value", argv)
            self.assertFalse(hasattr(SshAuthRequest("user", "host"), "password"))
            self.assertEqual(session.target, "yoshimi@192.168.1.253")
            self.assertEqual((Path(directory) / "ssh").stat().st_mode & 0o777, 0o700)

    def test_close_uses_control_operation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = FakeRunner()
            broker = ExternalTerminalSshBroker(
                runner, Path(directory), TerminalSpec("/usr/bin/ptyxis", "ptyxis")
            )  # type: ignore[arg-type]
            broker.close(SshControlSession("user@host", 22, "/tmp/test-socket"), CancellationToken())
            self.assertIn("exit", runner.requests[0].argv)

    def test_alias_authentication_preserves_openssh_config_and_strict_host_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broker = ExternalTerminalSshBroker(
                FakeRunner(), Path(directory), TerminalSpec("/usr/bin/ptyxis", "ptyxis")
            )  # type: ignore[arg-type]
            with patch("llm_manager.infrastructure.ssh_auth.subprocess.Popen") as popen, patch.object(
                ExternalTerminalSshBroker, "_is_ready", return_value=True
            ):
                session = broker.authenticate_alias(
                    SshAliasAuthRequest("development"), CancellationToken()
                )
            argv = popen.call_args.args[0]
            self.assertEqual(session.target, "development")
            self.assertIsNone(session.port)
            self.assertNotIn("-p", argv)
            self.assertIn("StrictHostKeyChecking=yes", argv)
            self.assertIn("UpdateHostKeys=no", argv)
            self.assertEqual(argv[-1], "development")


if __name__ == "__main__":
    unittest.main()
