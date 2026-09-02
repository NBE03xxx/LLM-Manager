import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import HostKind
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.ui.composition import DiagnosticTaskFactory, _local_opencode_candidates


class DiagnosticTaskFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.local = HostCandidate("local:test", HostKind.LOCAL, "Local")
        self.remote = HostCandidate("ssh:development", HostKind.SSH, "development", "development")
        self.local_runner = SubprocessRunner(ProcessPolicy(frozenset()))
        self.ssh_runner = SubprocessRunner(ProcessPolicy(frozenset()))
        self.factory = DiagnosticTaskFactory(
            (self.local, self.remote), self.local_runner, self.ssh_runner, ("/tmp/opencode.jsonc",)
        )

    def test_composes_local_and_ssh_services_without_running_them(self) -> None:
        local_service = self.factory._service(self.local)
        remote_service = self.factory._service(self.remote)
        self.assertEqual(local_service.host.display_name, "Local")
        self.assertEqual(remote_service.host.alias, "development")
        self.assertIs(local_service.host.runner, self.local_runner)
        self.assertIs(remote_service.host.runner, self.ssh_runner)

    def test_verified_fingerprint_is_injected_only_for_ssh(self) -> None:
        fingerprint = "SHA256:" + "A" * 43
        remote_service = self.factory._service(self.remote, fingerprint)
        self.assertEqual(remote_service.host.verified_fingerprint, fingerprint)

    def test_authentication_fallback_reuses_socket_for_identity_and_diagnosis(self) -> None:
        broker = MagicMock()
        fingerprint = "SHA256:" + "A" * 43
        broker.authenticate_alias.return_value = SimpleNamespace(
            socket_path="/run/user/1000/cm-test", verified_fingerprint=fingerprint
        )
        self.factory.ssh_auth_broker = broker
        report = object()
        service = MagicMock()
        service.execute.return_value = report
        with patch(
            "llm_manager.ui.composition.OpenSshHostIdentityResolver.resolve",
            side_effect=AdapterError("host_identity_unverified", "authentication required"),
        ) as resolve, patch.object(DiagnosticTaskFactory, "_service", return_value=service) as compose:
            result = self.factory._execute_ssh(
                self.remote, "diagnosis-test", CancellationToken()
            )
        self.assertIs(result, report)
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(compose.call_args.args[1], fingerprint)
        self.assertEqual(compose.call_args.args[2], "/run/user/1000/cm-test")
        broker.close.assert_called_once()

    def test_timeout_does_not_launch_interactive_authentication(self) -> None:
        broker = MagicMock()
        self.factory.ssh_auth_broker = broker
        with patch(
            "llm_manager.ui.composition.OpenSshHostIdentityResolver.resolve",
            side_effect=AdapterError("timeout", "connection timed out"),
        ), self.assertRaisesRegex(AdapterError, "timed out"):
            self.factory._execute_ssh(self.remote, "diagnosis-test", CancellationToken())
        broker.authenticate_alias.assert_not_called()

    def test_control_session_is_closed_when_diagnosis_fails(self) -> None:
        broker = MagicMock()
        session = SimpleNamespace(
            socket_path="/run/user/1000/cm-test", verified_fingerprint="SHA256:" + "A" * 43
        )
        broker.authenticate_alias.return_value = session
        self.factory.ssh_auth_broker = broker
        service = MagicMock()
        service.execute.side_effect = RuntimeError("diagnosis failed")
        with patch(
            "llm_manager.ui.composition.OpenSshHostIdentityResolver.resolve",
            side_effect=AdapterError("host_identity_unverified", "authentication required"),
        ), patch.object(DiagnosticTaskFactory, "_service", return_value=service), self.assertRaisesRegex(
            RuntimeError, "diagnosis failed"
        ):
            self.factory._execute_ssh(self.remote, "diagnosis-test", CancellationToken())
        broker.close.assert_called_once_with(session, ANY)

    def test_rejects_unknown_candidate_before_any_process(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown_host_candidate"):
            self.factory("ssh:unknown")

    def test_production_runner_allowlists_local_commands_and_system_ssh(self) -> None:
        factory = DiagnosticTaskFactory.production((self.local, self.remote))
        self.assertIn("lscpu", factory.local_runner.policy.allowed_executables)
        self.assertIn("curl", factory.local_runner.policy.allowed_executables)
        self.assertEqual(factory.ssh_runner.policy.allowed_executables, frozenset({"ssh"}))

    def test_production_factory_maps_discovered_ids_to_tasks(self) -> None:
        factory = DiagnosticTaskFactory.production((self.local, self.remote))
        self.assertTrue(callable(factory(self.local.host_id)))
        self.assertTrue(callable(factory(self.remote.host_id)))

    def test_local_config_uses_absolute_xdg_or_home_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": directory}):
                self.assertTrue(all(path.startswith(directory) for path in _local_opencode_candidates()))
            with patch.dict("os.environ", {"XDG_CONFIG_HOME": "relative"}), patch(
                "pathlib.Path.home", return_value=Path(directory)
            ):
                self.assertTrue(all(path.startswith(directory) for path in _local_opencode_candidates()))


if __name__ == "__main__":
    unittest.main()
