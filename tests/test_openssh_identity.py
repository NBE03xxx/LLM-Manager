import unittest

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandResult
from llm_manager.infrastructure.openssh_identity import OpenSshHostIdentityResolver


FINGERPRINT = "SHA256:" + "A" * 43


class OpenSshHostIdentityResolverTests(unittest.TestCase):
    def test_resolves_effective_destination_and_negotiated_fingerprint(self) -> None:
        runner = _Runner()
        result = OpenSshHostIdentityResolver(runner).resolve("development", CancellationToken())
        self.assertEqual((result.hostname, result.port), ("192.0.2.10", 2222))
        self.assertEqual(result.host_key_alias, "gate-key")
        self.assertEqual((result.algorithm, result.fingerprint), ("ssh-ed25519", FINGERPRINT))
        self.assertEqual(runner.requests[0][:3], ("ssh", "-G", "--"))
        self.assertIn("StrictHostKeyChecking=yes", runner.requests[1])
        self.assertIn("UpdateHostKeys=no", runner.requests[1])
        self.assertEqual(runner.requests[1][-1], "true")

    def test_authentication_or_host_key_failure_never_returns_identity(self) -> None:
        runner = _Runner(probe_exit=255)
        with self.assertRaisesRegex(AdapterError, "did not confirm"):
            OpenSshHostIdentityResolver(runner).resolve("development", CancellationToken())

    def test_verified_known_host_can_request_interactive_authentication(self) -> None:
        runner = _Runner(
            probe_exit=255,
            stderr=(
                f"debug1: Server host key: ssh-ed25519 {FINGERPRINT}\n"
                "debug1: Host 'example' is known and matches the ED25519 host key.\n"
                "user@example: Permission denied (publickey,password).\n"
            ),
        )
        identity = OpenSshHostIdentityResolver(runner).resolve(
            "development", CancellationToken()
        )
        self.assertTrue(identity.authentication_required)
        self.assertEqual(identity.fingerprint, FINGERPRINT)

    def test_accepts_openssh_crlf_debug_output(self) -> None:
        runner = _Runner(
            stderr=f"debug1: Server host key: ssh-ed25519 {FINGERPRINT}\r\n"
        )
        identity = OpenSshHostIdentityResolver(runner).resolve(
            "development", CancellationToken()
        )
        self.assertEqual(identity.fingerprint, FINGERPRINT)

    def test_rejects_missing_ambiguous_and_malformed_fingerprint(self) -> None:
        for stderr in (
            "Permission denied\n",
            f"debug1: Server host key: ssh-ed25519 {FINGERPRINT}\n"
            f"debug1: Server host key: ecdsa-sha2-nistp256 SHA256:{'B' * 43}\n",
            "debug1: Server host key: ssh-ed25519 SHA256:short\n",
        ):
            with self.subTest(stderr=stderr):
                with self.assertRaisesRegex(AdapterError, "verified server host key"):
                    OpenSshHostIdentityResolver(_Runner(stderr=stderr)).resolve(
                        "development", CancellationToken()
                    )

    def test_rejects_alias_injection_before_process(self) -> None:
        runner = _Runner()
        with self.assertRaises(ValueError):
            OpenSshHostIdentityResolver(runner).resolve("-oProxyCommand=bad", CancellationToken())
        self.assertEqual(runner.requests, [])

    def test_config_failure_timeout_and_invalid_port_fail_closed(self) -> None:
        cases = (
            _Runner(config_exit=1),
            _Runner(config_timeout=True),
            _Runner(config_stdout="hostname example\nport invalid\n"),
        )
        for runner in cases:
            with self.subTest(runner=runner), self.assertRaises(AdapterError):
                OpenSshHostIdentityResolver(runner).resolve("development", CancellationToken())


class _Runner:
    def __init__(
        self,
        *,
        config_exit=0,
        config_timeout=False,
        config_stdout="hostname 192.0.2.10\nport 2222\nhostkeyalias gate-key\n",
        probe_exit=0,
        stderr=None,
    ):
        self.config_exit = config_exit
        self.config_timeout = config_timeout
        self.config_stdout = config_stdout
        self.probe_exit = probe_exit
        self.stderr = stderr if stderr is not None else f"debug1: Server host key: ssh-ed25519 {FINGERPRINT}\n"
        self.requests = []

    def run(self, request, cancellation):
        self.requests.append(request.argv)
        if request.correlation_id == "ssh.identity.config":
            return CommandResult(request.argv, self.config_exit, self.config_stdout, "", self.config_timeout, 1)
        return CommandResult(request.argv, self.probe_exit, "", self.stderr, False, 1)


if __name__ == "__main__":
    unittest.main()
