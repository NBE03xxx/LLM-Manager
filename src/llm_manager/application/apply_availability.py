from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from llm_manager.application.optimization import stable_hash
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import DiagnosticReport, OptimizationPlan


class ApplyRoute(StrEnum):
    LOCAL_USER = "local_user"
    LOCAL_ROOT = "local_root"
    SSH_USER = "ssh_user"
    SSH_ROOT = "ssh_root"


@dataclass(frozen=True, slots=True)
class ApplyAvailability:
    route: ApplyRoute
    available: bool
    reason_code: str


class AssessProductionApplyAvailability:
    """Fail-closed route audit until each production composition is complete."""

    def execute(
        self, plan: OptimizationPlan, report: DiagnosticReport
    ) -> ApplyAvailability:
        if (
            plan.report_id != report.report_id
            or plan.report_hash != stable_hash(report)
            or plan.change_set is None
            or plan.change_set.host_id != report.host.host_id
        ):
            raise ValueError("apply_plan_binding_invalid")
        root_flags = {change.requires_root for change in plan.change_set.changes}
        if not root_flags:
            raise ValueError("change_set_empty")
        if len(root_flags) != 1:
            raise ValueError("mixed_privilege_plan_unsupported")
        requires_root = root_flags.pop()
        route = {
            (HostKind.LOCAL, False): ApplyRoute.LOCAL_USER,
            (HostKind.LOCAL, True): ApplyRoute.LOCAL_ROOT,
            (HostKind.SSH, False): ApplyRoute.SSH_USER,
            (HostKind.SSH, True): ApplyRoute.SSH_ROOT,
        }[(report.host.kind, requires_root)]
        reason = {
            ApplyRoute.LOCAL_USER: "local_user_apply_composition_missing",
            ApplyRoute.LOCAL_ROOT: "local_root_apply_composition_missing",
            ApplyRoute.SSH_USER: "ssh_user_apply_transport_missing",
            ApplyRoute.SSH_ROOT: "ssh_root_apply_protocol_missing",
        }[route]
        return ApplyAvailability(route, False, reason)
