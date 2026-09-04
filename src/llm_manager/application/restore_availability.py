from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from llm_manager.domain.enums import HostKind


class RestoreRoute(StrEnum):
    LOCAL_USER = "local_user"
    LOCAL_ROOT = "local_root"
    SSH_USER = "ssh_user"
    SSH_ROOT = "ssh_root"


@dataclass(frozen=True, slots=True)
class RestoreAvailability:
    route: RestoreRoute
    available: bool
    reason_code: str


@dataclass(frozen=True, slots=True)
class AssessProductionRestoreAvailability:
    """Fail closed until inventory, preflight, execution, and evidence are complete."""

    available_routes: frozenset[RestoreRoute] = frozenset()

    def execute(self, host_kind: HostKind, requires_root: bool) -> RestoreAvailability:
        route = {
            (HostKind.LOCAL, False): RestoreRoute.LOCAL_USER,
            (HostKind.LOCAL, True): RestoreRoute.LOCAL_ROOT,
            (HostKind.SSH, False): RestoreRoute.SSH_USER,
            (HostKind.SSH, True): RestoreRoute.SSH_ROOT,
        }[(host_kind, requires_root)]
        reason = {
            RestoreRoute.LOCAL_USER: "local_user_restore_composition_missing",
            RestoreRoute.LOCAL_ROOT: "local_root_restore_protocol_missing",
            RestoreRoute.SSH_USER: "ssh_user_restore_protocol_missing",
            RestoreRoute.SSH_ROOT: "ssh_root_restore_protocol_missing",
        }[route]
        available = route in self.available_routes
        return RestoreAvailability(route, available, "available" if available else reason)
