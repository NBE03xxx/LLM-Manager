import unittest
from threading import Thread
from time import sleep

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


if __name__ == "__main__":
    unittest.main()
