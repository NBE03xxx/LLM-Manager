from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import AuditPort, CancellationToken, RuntimeValidatorPort
from llm_manager.domain.enums import PlanStatus, ValidationStatus
from llm_manager.domain.models import ApprovalRecord, DiagnosticReport, OptimizationPlan

from .journal import JournalStatus, JournalTarget, LocalOperationJournal
from .safe_apply import ApplyOutcome
from .ssh_user_apply_preparation import (
    PrepareSshUserApply, PrepareSshUserRollback, PreparedSshUserApply,
)


class SshApplyTransport(Protocol):
    def apply(self, request_content: bytes, payload: bytes, cancellation: CancellationToken): ...
    def read_result(self, request_content: bytes, cancellation: CancellationToken): ...


class SshRollbackTransport(Protocol):
    def rollback(self, request_content: bytes, restore_content: bytes | None, cancellation: CancellationToken): ...
    def read_result(self, request_content: bytes, cancellation: CancellationToken): ...


@dataclass(slots=True)
class SshUserSafeApplyCoordinator:
    preparation: PrepareSshUserApply
    rollback_factory: PrepareSshUserRollback
    apply_transport: SshApplyTransport
    rollback_transport: SshRollbackTransport
    validator: RuntimeValidatorPort
    journal: LocalOperationJournal
    audit: AuditPort | None = None

    def execute(
        self,
        plan: OptimizationPlan,
        report: DiagnosticReport,
        approval: ApprovalRecord,
        operation_id: str,
        cancellation: CancellationToken,
    ) -> ApplyOutcome:
        manifest = None
        prepared = None
        try:
            self._audit("apply.approved", plan, (("approval_id", approval.approval_id),))
            prepared = self.preparation.execute(
                plan, report, approval, operation_id, cancellation
            )
            manifest = prepared.manifest
            self._audit("backup.verified", plan, (("backup_id", manifest.backup_id),))
            self.journal.create(
                operation_id, plan.plan_id, prepared.request.host_id,
                prepared.request.change_set_hash,
                (JournalTarget(
                    manifest.items[0].target,
                    prepared.request.before_hash,
                    prepared.request.after_hash,
                ),),
                approval_id=approval.approval_id,
                backup_id=manifest.backup_id,
                manifest_hash=manifest.manifest_hash,
                request_hash=prepared.request.request_hash,
            )
        except (AdapterError, OSError, OperationCancelled, ValueError) as error:
            return ApplyOutcome(PlanStatus.APPROVED, manifest, error=str(error))

        try:
            try:
                self.apply_transport.apply(
                    prepared.request_content, prepared.payload, cancellation
                )
            except (AdapterError, OSError, OperationCancelled):
                # A disconnect is ambiguous. Reconcile the exact immutable result;
                # never issue the Apply request a second time.
                self.apply_transport.read_result(
                    prepared.request_content, CancellationToken()
                )
            self.journal.update(operation_id, JournalStatus.VALIDATING)
            validations = self.validator.validate(plan.change_set, cancellation)  # type: ignore[arg-type]
            if _passed(validations):
                self._audit("apply.committed", plan, (("backup_id", manifest.backup_id),))
                self.journal.update(operation_id, JournalStatus.COMMITTED)
                return ApplyOutcome(PlanStatus.COMMITTED, manifest, validations)
            return self._rollback(
                plan, report, approval, prepared, operation_id, validations,
                "runtime validation failed", cancellation,
            )
        except (AdapterError, OSError, OperationCancelled, ValueError) as error:
            try:
                current = self.journal.load(operation_id)
            except (AdapterError, OSError):
                return ApplyOutcome(PlanStatus.RECOVERY_REQUIRED, manifest, error=str(error))
            if current.status is JournalStatus.APPLYING:
                # No verified Apply result means state is unknown. Do not guess or
                # launch rollback against an unproven after-hash.
                self.journal.update(operation_id, JournalStatus.ROLLING_BACK)
                self.journal.update(operation_id, JournalStatus.RECOVERY_REQUIRED)
                self._try_audit("apply.recovery_required", plan, (("backup_id", manifest.backup_id),))
                return ApplyOutcome(PlanStatus.RECOVERY_REQUIRED, manifest, error=str(error))
            return self._rollback(
                plan, report, approval, prepared, operation_id, (), str(error), cancellation
            )

    def _rollback(
        self, plan, report, approval, prepared: PreparedSshUserApply,
        operation_id, validations, error, cancellation,
    ) -> ApplyOutcome:
        recovery_token = CancellationToken()
        try:
            current = self.journal.load(operation_id)
            if current.status in {JournalStatus.APPLYING, JournalStatus.VALIDATING}:
                self.journal.update(operation_id, JournalStatus.ROLLING_BACK)
            rollback = self.rollback_factory.execute(
                plan, report, approval, prepared, f"{operation_id}-rollback", recovery_token
            )
            self.journal.bind_rollback(operation_id, rollback.request.request_hash)
            try:
                self.rollback_transport.rollback(
                    rollback.request_content, rollback.restore_content, recovery_token
                )
            except (AdapterError, OSError, OperationCancelled):
                self.rollback_transport.read_result(
                    rollback.request_content, CancellationToken()
                )
            self._audit("rollback.completed", plan, (("backup_id", prepared.manifest.backup_id),))
            self.journal.update(operation_id, JournalStatus.ROLLED_BACK)
            return ApplyOutcome(PlanStatus.ROLLED_BACK, prepared.manifest, validations, error)
        except (AdapterError, OSError, OperationCancelled, ValueError) as rollback_error:
            try:
                current = self.journal.load(operation_id)
                if current.status is not JournalStatus.RECOVERY_REQUIRED:
                    self.journal.update(operation_id, JournalStatus.RECOVERY_REQUIRED)
            except (AdapterError, OSError):
                pass
            self._try_audit(
                "rollback.recovery_required", plan,
                (("backup_id", prepared.manifest.backup_id),),
            )
            return ApplyOutcome(
                PlanStatus.RECOVERY_REQUIRED, prepared.manifest, validations,
                f"{error}; rollback: {rollback_error}",
            )

    def _audit(self, event: str, plan: OptimizationPlan, fields) -> None:
        if self.audit is not None:
            self.audit.append(event, plan.plan_id, fields)

    def _try_audit(self, event: str, plan: OptimizationPlan, fields) -> bool:
        try:
            self._audit(event, plan, fields)
            return True
        except (AdapterError, OSError):
            return False


def _passed(results) -> bool:
    return bool(results) and all(item.status is ValidationStatus.PASSED for item in results)
