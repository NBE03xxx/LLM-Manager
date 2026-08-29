from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import ChangeOperation
from llm_manager.domain.models import ApprovalRecord, OptimizationPlan, utc_now
from llm_manager.planning.ollama import DROP_IN_PATH

from .helper_executor import HelperOperationResult
from .helper_protocol import OLLAMA_UNIT, PROTOCOL_VERSION, HelperOperation, HelperOperationKind, HelperRequest, validate_request


@dataclass(frozen=True, slots=True)
class PreparedHelperApply:
    request: HelperRequest
    staged_contents: tuple[tuple[str, bytes], ...]


class HelperInvoker(Protocol):
    def invoke(self, request: HelperRequest, staged_contents: tuple[tuple[str, bytes], ...], cancellation: CancellationToken) -> tuple[HelperOperationResult, ...]: ...


class ApprovedHelperRequestFactory:
    def prepare(self, plan: OptimizationPlan, approval: ApprovalRecord, operation_id: str) -> PreparedHelperApply:
        now = utc_now()
        if plan.change_set is None or not approval.is_valid_for(plan, now):
            raise AdapterError("invalid_approval", "approval does not match the current privileged plan")
        changes = plan.change_set.changes
        if len(changes) != 1:
            raise AdapterError("unsupported_privileged_plan", "helper requires exactly one dedicated drop-in change")
        change = changes[0]
        if (
            not change.requires_root
            or change.target != DROP_IN_PATH
            or change.operation not in {ChangeOperation.CREATE_FILE, ChangeOperation.REPLACE_FILE}
            or change.replacement_text is None
            or "systemd.daemon_reload" not in change.validation_checks
            or not change.requires_restart
            or plan.change_set.affected_services != (OLLAMA_UNIT,)
        ):
            raise AdapterError("unsupported_privileged_plan", "plan is outside the privileged helper allowlist")
        content = change.replacement_text.encode("utf-8")
        write_id = f"{operation_id}:write"
        operations = (
            HelperOperation(write_id, HelperOperationKind.ATOMIC_REPLACE, target=DROP_IN_PATH, before_hash=change.before_hash, staged_content_hash=hashlib.sha256(content).hexdigest(), expected_mode=0o644, expected_uid=0, expected_gid=0),
            HelperOperation(f"{operation_id}:reload", HelperOperationKind.DAEMON_RELOAD),
            HelperOperation(f"{operation_id}:restart", HelperOperationKind.RESTART_UNIT, unit=OLLAMA_UNIT),
        )
        expiry_candidates = [now + timedelta(minutes=5)]
        if plan.expires_at is not None:
            expiry_candidates.append(plan.expires_at)
        if approval.expires_at is not None:
            expiry_candidates.append(approval.expires_at)
        request = HelperRequest(PROTOCOL_VERSION, operation_id, plan.change_set.host_id, plan.plan_id, plan.change_set.content_hash, operations, now, min(expiry_candidates)).with_hash()
        validate_request(request, request.request_hash, now=now)
        return PreparedHelperApply(request, ((write_id, content),))


@dataclass(slots=True)
class LocalPrivilegedApplyService:
    factory: ApprovedHelperRequestFactory
    invoker: HelperInvoker

    def execute(self, plan: OptimizationPlan, approval: ApprovalRecord, operation_id: str, cancellation: CancellationToken) -> tuple[HelperOperationResult, ...]:
        prepared = self.factory.prepare(plan, approval, operation_id)
        return self.invoker.invoke(prepared.request, prepared.staged_contents, cancellation)
