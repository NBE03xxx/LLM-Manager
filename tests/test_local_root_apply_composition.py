import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import HostKind, PlanStatus
from llm_manager.infrastructure.process import ProcessPolicy, SubprocessRunner
from llm_manager.ui.composition import (
    LocalApplyTaskFactory,
    LocalRootApplyTaskFactory,
)
from tests.test_privileged_apply import (
    _BackupStore,
    _RuntimeValidator,
    _WorkflowInvoker,
    _approved,
)


class LocalRootApplyTaskFactoryTests(unittest.TestCase):
    def test_composes_privileged_coordinator_in_private_sandbox_state(self):
        current, approval, _ = _approved()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = _WorkflowInvoker(None)
            probe = MagicMock()
            probe.inspect.return_value.root_apply_allowed = True
            factory = LocalRootApplyTaskFactory(
                (HostCandidate("host-1", HostKind.LOCAL, "Local"),),
                SubprocessRunner(ProcessPolicy(frozenset())),
                SubprocessRunner(ProcessPolicy(frozenset())),
                root / "state",
                root / "runtime" / "helper",
                probe,
                backup_store_factory=lambda store_root, _allowed, _cipher: _BackupStore(
                    backend, store_root
                ),
                runtime_validator_factory=lambda _host: _RuntimeValidator(True),
                invoker_factory=lambda _staging, _runner: backend,
            )

            outcome = factory(current, approval)(CancellationToken())

            self.assertEqual(outcome.status, PlanStatus.COMMITTED)
            state = root / "state" / "llm-manager"
            self.assertTrue((state / "journal").is_dir())
            self.assertTrue((state / "audit" / "HEAD").is_file())
            self.assertEqual(probe.inspect.call_count, 2)

    def test_rejects_remote_user_and_mixed_plans_before_task_creation(self):
        current, approval, _ = _approved()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = LocalRootApplyTaskFactory(
                (HostCandidate("host-1", HostKind.SSH, "Remote", "remote"),),
                SubprocessRunner(ProcessPolicy(frozenset())),
                SubprocessRunner(ProcessPolicy(frozenset())),
                root / "state",
                root / "runtime" / "helper",
                MagicMock(),
            )
            with self.assertRaisesRegex(ValueError, "requires_local_host"):
                base(current, approval)
            local = replace(base, hosts=(HostCandidate("host-1", HostKind.LOCAL, "Local"),))
            user_change = replace(current.change_set.changes[0], requires_root=False)
            with self.assertRaisesRegex(ValueError, "requires_root_changes"):
                local(replace(current, change_set=replace(current.change_set, changes=(user_change,))), approval)

    def test_router_selects_one_privilege_route_and_rejects_mixing(self):
        current, approval, _ = _approved()
        user = MagicMock()
        root = MagicMock()
        router = LocalApplyTaskFactory(user, root)
        router(current, approval)
        root.assert_called_once_with(current, approval)
        user_change = replace(current.change_set.changes[0], requires_root=False)
        user_plan = replace(current, change_set=replace(current.change_set, changes=(user_change,)))
        router(user_plan, approval)
        user.assert_called_once_with(user_plan, approval)
        user_change = replace(user_change, change_id="user-change")
        mixed = replace(
            current,
            change_set=replace(current.change_set, changes=(current.change_set.changes[0], user_change)),
        )
        with self.assertRaisesRegex(ValueError, "mixed_privilege_plan_unsupported"):
            router(mixed, approval)


if __name__ == "__main__":
    unittest.main()
