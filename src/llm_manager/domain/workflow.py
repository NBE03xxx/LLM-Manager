from dataclasses import dataclass, replace

from .enums import PlanStatus
from .errors import InvalidTransition


_ALLOWED: dict[PlanStatus, frozenset[PlanStatus]] = {
    PlanStatus.DRAFT: frozenset({PlanStatus.REVIEWED}),
    PlanStatus.REVIEWED: frozenset({PlanStatus.APPROVED}),
    PlanStatus.APPROVED: frozenset({PlanStatus.BACKED_UP}),
    PlanStatus.BACKED_UP: frozenset({PlanStatus.APPLYING}),
    PlanStatus.APPLYING: frozenset({PlanStatus.VALIDATING, PlanStatus.ROLLING_BACK}),
    PlanStatus.VALIDATING: frozenset({PlanStatus.COMMITTED, PlanStatus.ROLLING_BACK}),
    PlanStatus.ROLLING_BACK: frozenset({PlanStatus.ROLLED_BACK, PlanStatus.RECOVERY_REQUIRED}),
    PlanStatus.COMMITTED: frozenset(),
    PlanStatus.ROLLED_BACK: frozenset(),
    PlanStatus.RECOVERY_REQUIRED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class PlanStateMachine:
    plan_id: str
    status: PlanStatus = PlanStatus.DRAFT

    @property
    def terminal(self) -> bool:
        return not _ALLOWED[self.status]

    def can_transition_to(self, target: PlanStatus) -> bool:
        return target in _ALLOWED[self.status]

    def transition_to(self, target: PlanStatus) -> "PlanStateMachine":
        if not self.can_transition_to(target):
            raise InvalidTransition(f"cannot transition {self.status.value} -> {target.value}")
        return replace(self, status=target)
