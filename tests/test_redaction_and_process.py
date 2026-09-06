import sys
import unittest
from threading import Thread
from time import monotonic, sleep

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.infrastructure.redaction import REDACTED, redact_argv, redact_environment, redact_text


class RedactionTests(unittest.TestCase):
    def test_redacts_common_secret_forms(self) -> None:
        value = redact_text("Authorization: Bearer abc123 token=qwerty http://user:pass@host")
        self.assertNotIn("abc123", value)
        self.assertNotIn("qwerty", value)
        self.assertNotIn("user:pass", value)

    def test_redacts_separate_argv_value(self) -> None:
        self.assertEqual(redact_argv(("tool", "--token", "secret")), ("tool", "--token", REDACTED))

    def test_redacts_environment_by_key(self) -> None:
        self.assertEqual(redact_environment((("API_KEY", "secret"),)), (("API_KEY", REDACTED),))

    def test_redacts_quoted_assignments_without_leaking_value_tails(self) -> None:
        for value in (
            '{"api_key": "sentinel one, sentinel two"}',
            "password='sentinel one; sentinel two' status=failed",
            r'{"token": "sentinel\" tail"}',
            'secret="sentinel\nsecond line"',
            'password="sentinel unterminated tail',
        ):
            with self.subTest(value=value):
                result = redact_text(value)
                self.assertNotIn("sentinel", result)
                self.assertNotIn("tail", result)
                self.assertNotIn("second line", result)
                self.assertIn(REDACTED, result)


class ProcessRunnerTests(unittest.TestCase):
    def test_rejects_command_outside_allowlist(self) -> None:
        runner = SubprocessRunner(ProcessPolicy(frozenset()))
        with self.assertRaises(AdapterError):
            runner.run(CommandRequest(("uname",), 100, "test"), CancellationToken())

    def test_honours_pre_cancelled_token(self) -> None:
        runner = SubprocessRunner(ProcessPolicy({"uname"}))
        with self.assertRaises(OperationCancelled):
            runner.run(CommandRequest(("uname",), 100, "test"), CancellationToken(True))

    def test_token_can_be_cancelled_after_creation(self) -> None:
        token = CancellationToken()
        self.assertFalse(token.cancelled)
        token.cancel()
        self.assertTrue(token.cancelled)

    def test_cancels_running_process(self) -> None:
        runner = SubprocessRunner(ProcessPolicy({"sleep"}))
        token = CancellationToken()
        thread = Thread(target=lambda: (sleep(0.02), token.cancel()))
        thread.start()
        with self.assertRaises(OperationCancelled):
            runner.run(CommandRequest(("sleep", "2"), 1000, "test"), token)
        thread.join()

    def test_collects_both_streams_and_redacts_stderr(self) -> None:
        runner = SubprocessRunner(ProcessPolicy({sys.executable}, max_output_bytes=128))
        result = runner.run(
            CommandRequest(
                (sys.executable, "-c", "import os; os.write(1,b'normal'); os.write(2,b'token=sentinel')"),
                1000,
                "test",
            ),
            CancellationToken(),
        )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "normal")
        self.assertNotIn("sentinel", result.stderr_redacted)
        self.assertFalse(result.timed_out)

    def test_fails_closed_while_stdout_is_over_limit(self) -> None:
        self._assert_stream_over_limit(1)

    def test_fails_closed_while_stderr_is_over_limit(self) -> None:
        self._assert_stream_over_limit(2)

    def test_timeout_returns_only_already_bounded_output(self) -> None:
        runner = SubprocessRunner(ProcessPolicy({sys.executable}, max_output_bytes=128))
        result = runner.run(
            CommandRequest(
                (sys.executable, "-c", "import os,time; os.write(1,b'partial'); time.sleep(2)"),
                50,
                "test",
            ),
            CancellationToken(),
        )
        self.assertIsNone(result.exit_code)
        self.assertEqual(result.stdout, "partial")
        self.assertTrue(result.timed_out)

    def test_rejects_non_positive_output_limit(self) -> None:
        with self.assertRaises(ValueError):
            ProcessPolicy({"true"}, max_output_bytes=0)

    def test_timeout_remains_active_after_both_output_streams_close(self) -> None:
        runner = SubprocessRunner(ProcessPolicy({sys.executable}))
        started = monotonic()
        result = runner.run(
            CommandRequest(
                (sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(2)"),
                150, "test",
            ),
            CancellationToken(),
        )
        self.assertTrue(result.timed_out)
        self.assertLess(monotonic() - started, 1.0)

    def test_cancel_remains_active_after_both_output_streams_close(self) -> None:
        runner = SubprocessRunner(ProcessPolicy({sys.executable}))
        token = CancellationToken()
        thread = Thread(target=lambda: (sleep(0.15), token.cancel()))
        started = monotonic()
        thread.start()
        try:
            with self.assertRaises(OperationCancelled):
                runner.run(
                    CommandRequest(
                        (sys.executable, "-c", "import os,time; os.close(1); os.close(2); time.sleep(2)"),
                        5000, "test",
                    ),
                    token,
                )
        finally:
            thread.join()
        self.assertLess(monotonic() - started, 1.0)

    def _assert_stream_over_limit(self, descriptor: int) -> None:
        runner = SubprocessRunner(ProcessPolicy({sys.executable}, max_output_bytes=1024))
        with self.assertRaises(AdapterError) as raised:
            runner.run(
                CommandRequest(
                    (
                        sys.executable,
                        "-c",
                        f"import os,time; os.write({descriptor},b'x'*8192); time.sleep(2)",
                    ),
                    1000,
                    "test",
                ),
                CancellationToken(),
            )
        self.assertEqual(raised.exception.code, "command_output_too_large")


if __name__ == "__main__":
    unittest.main()
