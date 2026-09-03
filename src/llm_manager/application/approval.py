from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import ApprovalRecord, OptimizationPlan, utc_now


@dataclass(frozen=True, slots=True)
class CreateApprovalRecord:
    lifetime: timedelta = timedelta(minutes=5)

    def execute(
        self,
        plan: OptimizationPlan,
        approval_id: str,
        actor: str,
        explicit_review: bool,
        plaintext_backup_acknowledged: bool,
        now: datetime | None = None,
    ) -> ApprovalRecord:
        current = now or utc_now()
        if not explicit_review:
            raise AdapterError("explicit_review_required", "review confirmation is required")
        if plan.change_set is None or not plan.change_set.changes:
            raise AdapterError("change_set_required", "an executable change set is required")
        if plan.expires_at is not None and current >= plan.expires_at:
            raise AdapterError("stale_plan", "optimization plan has expired")
        if not approval_id.strip() or not actor.strip():
            raise AdapterError("approval_identity_required", "approval identity is required")
        if not plan.backup_policy.enabled and not plaintext_backup_acknowledged:
            raise AdapterError(
                "plaintext_backup_acknowledgement_required",
                "unencrypted backup risk must be acknowledged",
            )
        expires_at = current + self.lifetime
        if plan.expires_at is not None:
            expires_at = min(expires_at, plan.expires_at)
        record = ApprovalRecord(
            approval_id=approval_id,
            plan_id=plan.plan_id,
            report_hash=plan.report_hash,
            change_set_hash=plan.change_set.content_hash,
            actor=actor,
            backup_policy_hash=plan.backup_policy.content_hash,
            plaintext_backup_acknowledged=plaintext_backup_acknowledged,
            approved_at=current,
            expires_at=expires_at,
        )
        if not record.is_valid_for(plan, current):
            raise AdapterError("invalid_approval", "approval is not valid for the current plan")
        return record
