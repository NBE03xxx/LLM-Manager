import unittest

from llm_manager.domain.enums import PlanStatus
from llm_manager.domain.errors import InvalidTransition
from llm_manager.domain.workflow import PlanStateMachine


class PlanStateMachineTests(unittest.TestCase):
    def test_success_path(self) -> None:
        machine = PlanStateMachine("plan")
        for state in (
            PlanStatus.REVIEWED,
            PlanStatus.APPROVED,
            PlanStatus.BACKED_UP,
            PlanStatus.APPLYING,
            PlanStatus.VALIDATING,
            PlanStatus.COMMITTED,
        ):
            machine = machine.transition_to(state)
        self.assertTrue(machine.terminal)

    def test_apply_failure_rolls_back(self) -> None:
        machine = PlanStateMachine("plan", PlanStatus.APPLYING)
        machine = machine.transition_to(PlanStatus.ROLLING_BACK)
        machine = machine.transition_to(PlanStatus.ROLLED_BACK)
        self.assertTrue(machine.terminal)

    def test_rollback_failure_requires_recovery(self) -> None:
        machine = PlanStateMachine("plan", PlanStatus.ROLLING_BACK)
        machine = machine.transition_to(PlanStatus.RECOVERY_REQUIRED)
        self.assertTrue(machine.terminal)

    def test_cannot_skip_backup(self) -> None:
        machine = PlanStateMachine("plan", PlanStatus.APPROVED)
        with self.assertRaises(InvalidTransition):
            machine.transition_to(PlanStatus.APPLYING)

    def test_terminal_state_rejects_transitions(self) -> None:
        machine = PlanStateMachine("plan", PlanStatus.COMMITTED)
        with self.assertRaises(InvalidTransition):
            machine.transition_to(PlanStatus.ROLLING_BACK)


if __name__ == "__main__":
    unittest.main()
