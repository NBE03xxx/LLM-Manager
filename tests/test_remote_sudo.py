from __future__ import annotations

import unittest
from unittest.mock import patch

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.infrastructure.remote_sudo import OpenSshRemoteSudoInvoker
from llm_manager.infrastructure.ssh_auth import TerminalSpec


class OpenSshRemoteSudoInvokerTests(unittest.TestCase):
    def test_passwordless_uses_fixed_noninteractive_helper_argv(self) -> None:
        runner = _Runner(CommandResult(("ssh",), 0, "", "", False, 1))
        completion = _Completion()
        invoker = OpenSshRemoteSudoInvoker(
            runner, TerminalSpec("/usr/bin/ptyxis", "ptyxis"), completion
        )
        invoker.invoke("development", "/tmp/cm", "backup-1", "a" * 64, CancellationToken())
        self.assertEqual(runner.requests[0].argv[-1], "sudo -n -v")
        argv = runner.requests[1].argv
        self.assertEqual(argv[:6], ("ssh", "-S", "/tmp/cm", "-o", "BatchMode=yes", "--"))
        self.assertIn("sudo -n -- /usr/bin/llm-manager-remote-helper invoke-recovery backup-1", argv[-1])
        self.assertEqual(completion.calls, 0)

    def test_authenticated_helper_failure_does_not_open_another_terminal(self) -> None:
        runner = _RunnerSequence((
            CommandResult(("ssh",), 0, "", "", False, 1),
            CommandResult(("ssh",), 1, "", "helper failed", False, 1),
        ))
        invoker = OpenSshRemoteSudoInvoker(
            runner, TerminalSpec("/usr/bin/ptyxis", "ptyxis"), _Completion()
        )
        with patch("llm_manager.infrastructure.remote_sudo.subprocess.Popen") as popen:
            with self.assertRaises(AdapterError) as caught:
                invoker.invoke("host", None, "backup", "a" * 64, CancellationToken())
        self.assertEqual(caught.exception.code, "remote_helper_failed")
        popen.assert_not_called()

    def test_authentication_fallback_uses_external_terminal_and_bounded_completion(self) -> None:
        runner = _Runner(CommandResult(("ssh",), 1, "", "sudo: a password is required", False, 1))
        completion = _Completion(results=[False, True])
        ticks = iter((0.0, 0.0, 0.1, 0.2))
        invoker = OpenSshRemoteSudoInvoker(
            runner, TerminalSpec("/usr/bin/ptyxis", "ptyxis"), completion,
            timeout_seconds=10, poll_seconds=0, clock=lambda: next(ticks), sleeper=lambda _: None,
        )
        with patch("llm_manager.infrastructure.remote_sudo.subprocess.Popen") as popen:
            invoker.invoke("development", None, "backup-1", "b" * 64, CancellationToken())
        argv = popen.call_args.args[0]
        self.assertEqual(argv[0], "/usr/bin/ptyxis")
        self.assertIn("-t", argv)
        self.assertTrue(any("sudo -- /usr/bin/llm-manager-remote-helper" in item for item in argv))
        self.assertFalse(any("password" in item.lower() for item in argv))
        self.assertEqual(completion.calls, 2)

    def test_cancel_timeout_launch_failure_and_injection_fail_closed(self) -> None:
        cancelled = CancellationToken(cancelled=True)
        with self.assertRaises(OperationCancelled):
            self._invoker().invoke("host", None, "backup", "a" * 64, cancelled)
        for alias, request_id, digest in (("-oBad", "backup", "a" * 64), ("host", "../bad", "a" * 64), ("host", "backup", "x" * 64)):
            with self.subTest(alias=alias, request_id=request_id), self.assertRaises(AdapterError):
                self._invoker().invoke(alias, None, request_id, digest, CancellationToken())
        runner = _Runner(CommandResult(("ssh",), 1, "", "", False, 1))
        timeout = OpenSshRemoteSudoInvoker(
            runner, TerminalSpec("/usr/bin/ptyxis", "ptyxis"), _Completion(),
            timeout_seconds=1, poll_seconds=0, clock=_Clock((0.0, 0.0, 2.0)), sleeper=lambda _: None,
        )
        with patch("llm_manager.infrastructure.remote_sudo.subprocess.Popen"):
            with self.assertRaises(AdapterError) as caught:
                timeout.invoke("host", None, "backup", "a" * 64, CancellationToken())
        self.assertEqual(caught.exception.code, "remote_authorization_timeout")
        with patch("llm_manager.infrastructure.remote_sudo.subprocess.Popen", side_effect=OSError("fail")):
            with self.assertRaises(AdapterError) as caught:
                OpenSshRemoteSudoInvoker(
                    runner, TerminalSpec("/usr/bin/ptyxis", "ptyxis"), _Completion()
                ).invoke("host", None, "backup", "a" * 64, CancellationToken())
        self.assertEqual(caught.exception.code, "terminal_launch_failed")

    def _invoker(self):
        return OpenSshRemoteSudoInvoker(
            _Runner(CommandResult(("ssh",), 0, "", "", False, 1)),
            TerminalSpec("/usr/bin/ptyxis", "ptyxis"), _Completion(),
        )


class _Runner:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request)
        return self.result


class _RunnerSequence:
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request)
        return self.results.pop(0)


class _Completion:
    def __init__(self, results=()):
        self.results = list(results)
        self.calls = 0

    def completed(self, request_id, request_hash, cancellation):
        self.calls += 1
        return self.results.pop(0) if self.results else False


class _Clock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(self.values)


if __name__ == "__main__":
    unittest.main()
