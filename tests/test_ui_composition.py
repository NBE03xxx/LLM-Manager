import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_manager.application.host_discovery import HostCandidate
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
