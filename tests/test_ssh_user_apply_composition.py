from __future__ import annotations

import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.optimization import stable_hash
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import HostKind
from llm_manager.infrastructure.helper_compat import remote_helper_compatibility_probe
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.infrastructure.remote_backup import DualCopyPrivilegedBackupStore
from llm_manager.infrastructure.ssh_backup import SshSnapshotLocalBackupStore
from llm_manager.infrastructure.ssh_auth import TerminalSpec
from llm_manager.infrastructure.ssh_user_apply_coordinator import SshUserSafeApplyCoordinator
from llm_manager.infrastructure.ssh_user_home import RemoteUserHome
from llm_manager.ui.composition import (
    DiagnosticTaskFactory,
    ProductionApplyTaskFactory,
    SshUserApplyTaskFactory,
)
from tests.test_ssh_user_apply_preparation import ABSOLUTE, _bound_inputs


class SshUserApplyTaskFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report, self.plan, _approval = _bound_inputs()
        self.approval = MagicMock()
        self.approval.is_valid_for.return_value = True
        self.remote = HostCandidate("ssh:remote", HostKind.SSH, "Remote", "remote")
        runner = SubprocessRunner(ProcessPolicy(frozenset()))
        self.diagnostics = DiagnosticTaskFactory(
            (self.remote,), runner, runner, (), ssh_auth_broker=MagicMock()
        )

    def test_reidentifies_resolves_home_and_composes_exact_target_before_execute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = self._factory(Path(directory))
            coordinator = MagicMock()
            coordinator.execute.return_value = "committed"
            with patch(
                "llm_manager.ui.composition.OpenSshHostIdentityResolver.resolve",
                return_value=SimpleNamespace(
                    fingerprint=self.report.host.fingerprint,
                    authentication_required=False,
                ),
            ), patch(
                "llm_manager.ui.composition.ResolveSshUserHome.execute",
                return_value=RemoteUserHome(1000, "remote", "/home/remote"),
            ), patch.object(
                SshUserApplyTaskFactory, "_coordinator", return_value=coordinator
            ) as compose:
                result = factory(self.plan, self.report, self.approval)(CancellationToken())
            self.assertEqual(result, "committed")
            self.assertEqual(
                compose.call_args.args[3],
                {ABSOLUTE: ".config/opencode/opencode.jsonc"},
            )
            coordinator.execute.assert_called_once_with(
                self.plan, self.report, self.approval, ANY, ANY
            )

    def test_authenticated_session_is_reused_and_closed_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = self._factory(Path(directory))
            session = SimpleNamespace(socket_path="/run/user/1000/cm-test")
            self.diagnostics.ssh_auth_broker.authenticate_alias.return_value = session
            with patch(
                "llm_manager.ui.composition.OpenSshHostIdentityResolver.resolve",
                return_value=SimpleNamespace(
                    fingerprint=self.report.host.fingerprint,
                    authentication_required=True,
                ),
            ), patch(
                "llm_manager.ui.composition.ResolveSshUserHome.execute",
                return_value=RemoteUserHome(1000, "remote", "/home/remote"),
            ), patch.object(
                SshUserApplyTaskFactory, "_coordinator", side_effect=RuntimeError("stop")
            ):
                with self.assertRaisesRegex(RuntimeError, "stop"):
                    factory(self.plan, self.report, self.approval)(CancellationToken())
            self.diagnostics.ssh_auth_broker.close.assert_called_once_with(session, ANY)

    def test_rejects_changed_fingerprint_and_non_allowlisted_target_before_composition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = self._factory(Path(directory))
            with patch(
                "llm_manager.ui.composition.OpenSshHostIdentityResolver.resolve",
                return_value=SimpleNamespace(
                    fingerprint="SHA256:" + "b" * 43,
                    authentication_required=False,
                ),
            ):
                with self.assertRaisesRegex(Exception, "identity changed"):
                    factory(self.plan, self.report, self.approval)(CancellationToken())
            with patch(
                "llm_manager.ui.composition.OpenSshHostIdentityResolver.resolve",
                return_value=SimpleNamespace(
                    fingerprint=self.report.host.fingerprint,
                    authentication_required=False,
                ),
            ), patch(
                "llm_manager.ui.composition.ResolveSshUserHome.execute",
                return_value=RemoteUserHome(1000, "other", "/home/other"),
            ):
                with self.assertRaisesRegex(Exception, "allowlist"):
                    factory(self.plan, self.report, self.approval)(CancellationToken())

    def test_production_keeps_route_internal_and_uses_fixed_dependencies(self) -> None:
        factory = SshUserApplyTaskFactory.production(self.diagnostics)
        self.assertEqual(
            factory.transfer_runner.policy.allowed_executables,
            frozenset({"ssh", "scp"}),
        )
        self.assertEqual(factory.remote_key_reference, "remote-master-v1")
        self.assertEqual(factory.helper_probe.expected_package, "llm-manager-remote-helper")

    def test_composes_dual_backup_transports_and_private_evidence_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory = self._factory(root)
            coordinator = factory._coordinator(
                MagicMock(),
                "remote",
                "/run/user/1000/cm-test",
                {ABSOLUTE: ".config/opencode/opencode.jsonc"},
            )
            self.assertIsInstance(coordinator, SshUserSafeApplyCoordinator)
            self.assertIsInstance(
                coordinator.preparation.backups, DualCopyPrivilegedBackupStore
            )
            self.assertIsInstance(
                coordinator.preparation.backups.local, SshSnapshotLocalBackupStore
            )
            self.assertIs(
                coordinator.apply_transport.runner,
                coordinator.rollback_transport.runner,
            )
            self.assertEqual(
                coordinator.apply_transport.runner.control_socket,
                "/run/user/1000/cm-test",
            )
            self.assertTrue((root / "state" / "llm-manager").is_dir())
            self.assertEqual(
                stat.S_IMODE((root / "state" / "llm-manager" / "remote-recovery").stat().st_mode),
                0o700,
            )

    def test_runtime_validator_is_injectable_without_changing_production_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            factory = self._factory(Path(directory))
            validator = MagicMock()
            build_validator = MagicMock(return_value=validator)
            factory.runtime_validator_factory = build_validator
            coordinator = factory._coordinator(
                MagicMock(), "remote", None,
                {ABSOLUTE: ".config/opencode/opencode.jsonc"},
            )
            self.assertIs(coordinator.validator, validator)
            self.assertEqual(build_validator.call_args.args[1], (ABSOLUTE,))

    def test_missing_terminal_blocks_composition_before_backup_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            factory = self._factory(root)
            factory.terminal = None
            with self.assertRaisesRegex(Exception, "external terminal"):
                factory._coordinator(
                    MagicMock(), "remote", None,
                    {ABSOLUTE: ".config/opencode/opencode.jsonc"},
                )
            self.assertFalse((root / "state" / "llm-manager").exists())

    def _factory(self, root: Path) -> SshUserApplyTaskFactory:
        return SshUserApplyTaskFactory(
            self.diagnostics,
            SubprocessRunner(ProcessPolicy(frozenset())),
            root / "state",
            root / "runtime",
            remote_helper_compatibility_probe(frozenset({"0.1.0~dev0"})),
            TerminalSpec("/usr/bin/terminal", "ptyxis"),
            key_provider_factory=lambda: MagicMock(),
        )


class ProductionApplyTaskFactoryTests(unittest.TestCase):
    def test_routes_report_bound_local_and_ssh_user_plans(self) -> None:
        report, plan, approval = _bound_inputs()
        local = MagicMock(return_value="local-task")
        ssh_user = MagicMock(return_value="ssh-task")
        router = ProductionApplyTaskFactory(local, ssh_user)
        self.assertEqual(router(plan, report, approval), "ssh-task")
        ssh_user.assert_called_once_with(plan, report, approval)

        local_host = replace(report.host, host_id="local:test", kind=HostKind.LOCAL)
        local_report = replace(report, host=local_host)
        local_plan = replace(
            plan,
            report_hash=stable_hash(local_report),
            change_set=replace(plan.change_set, host_id=local_host.host_id),
        )
        self.assertEqual(router(local_plan, local_report, approval), "local-task")
        local.assert_called_once_with(local_plan, approval)

    def test_rejects_stale_report_and_ssh_root_without_dispatch(self) -> None:
        report, plan, approval = _bound_inputs()
        local = MagicMock()
        ssh_user = MagicMock()
        router = ProductionApplyTaskFactory(local, ssh_user)
        with self.assertRaisesRegex(ValueError, "binding"):
            router(plan, replace(report, report_id="changed"), approval)
        root_plan = replace(
            plan,
            change_set=replace(
                plan.change_set,
                changes=(replace(plan.change_set.changes[0], requires_root=True),),
            ),
        )
        with self.assertRaisesRegex(ValueError, "ssh_root"):
            router(root_plan, report, approval)
        local.assert_not_called()
        ssh_user.assert_not_called()


if __name__ == "__main__":
    unittest.main()
