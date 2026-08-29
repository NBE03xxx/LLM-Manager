from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import AuditPort, BackupRequest, CancellationToken, RuntimeValidatorPort
from llm_manager.domain.enums import ChangeOperation, PlanStatus, Severity, ValidationStatus
from llm_manager.domain.models import ApprovalRecord, BackupManifest, LocalizedMessage, OptimizationPlan, ValidationResult, utc_now
from llm_manager.planning.ollama import DROP_IN_PATH

from .helper_executor import HelperOperationResult
from .helper_protocol import OLLAMA_UNIT, PROTOCOL_VERSION, HelperOperation, HelperOperationKind, HelperRequest, validate_request
from .journal import JournalStatus, JournalTarget, LocalOperationJournal
from .safe_apply import ApplyOutcome


@dataclass(frozen=True, slots=True)
class PreparedHelperApply:
    request: HelperRequest
    staged_contents: tuple[tuple[str, bytes], ...]


class HelperInvoker(Protocol):
    def invoke(self, request: HelperRequest, staged_contents: tuple[tuple[str, bytes], ...], cancellation: CancellationToken) -> tuple[HelperOperationResult, ...]: ...


class PrivilegedBackupStore(Protocol):
    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest: ...
    def verify(self, manifest: BackupManifest, cancellation: CancellationToken) -> tuple[ValidationResult, ...]: ...
    def restore_items(self, manifest: BackupManifest, cancellation: CancellationToken): ...


class ApprovedHelperRequestFactory:
    def prepare(
        self,
        plan: OptimizationPlan,
        approval: ApprovalRecord,
        operation_id: str,
        *,
        manifest: BackupManifest | None = None,
    ) -> PreparedHelperApply:
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
        if manifest is not None:
            _validate_manifest_binding(plan, approval, manifest, operation_id)
        request = HelperRequest(
            PROTOCOL_VERSION, operation_id, plan.change_set.host_id, plan.plan_id,
            plan.change_set.content_hash, operations, now, min(expiry_candidates),
            approval_id=approval.approval_id if manifest else None,
            backup_id=manifest.backup_id if manifest else None,
            manifest_hash=manifest.manifest_hash if manifest else None,
        ).with_hash()
        validate_request(request, request.request_hash, now=now)
        return PreparedHelperApply(request, ((write_id, content),))


@dataclass(slots=True)
class LocalPrivilegedApplyService:
    factory: ApprovedHelperRequestFactory
    invoker: HelperInvoker

    def execute(self, plan: OptimizationPlan, approval: ApprovalRecord, operation_id: str, cancellation: CancellationToken) -> tuple[HelperOperationResult, ...]:
        prepared = self.factory.prepare(plan, approval, operation_id)
        return self.invoker.invoke(prepared.request, prepared.staged_contents, cancellation)


class PrivilegedRollbackRequestFactory:
    def prepare(
        self,
        plan: OptimizationPlan,
        approval: ApprovalRecord,
        manifest: BackupManifest,
        operation_id: str,
        apply_request: HelperRequest,
        backups: PrivilegedBackupStore,
        cancellation: CancellationToken,
    ) -> PreparedHelperApply:
        _validate_manifest_binding(plan, approval, manifest, apply_request.operation_id)
        if (
            apply_request.approval_id != approval.approval_id
            or apply_request.backup_id != manifest.backup_id
            or apply_request.manifest_hash != manifest.manifest_hash
        ):
            raise AdapterError("workflow_binding_mismatch", "apply request is not bound to the approved backup")
        restore_items = backups.restore_items(manifest, cancellation)
        after_by_target = {
            item.target: item.staged_content_hash
            for item in apply_request.operations
            if item.kind is HelperOperationKind.ATOMIC_REPLACE
        }
        operations: list[HelperOperation] = []
        contents: list[tuple[str, bytes]] = []
        for index, item in enumerate(restore_items):
            after_hash = after_by_target.get(item.target)
            if after_hash is None:
                raise AdapterError("workflow_binding_mismatch", "backup target is absent from apply request")
            item_id = f"{operation_id}:restore:{index}"
            if item.existed:
                if item.content is None or item.sha256 is None:
                    raise AdapterError("invalid_backup", "restore content is incomplete")
                operations.append(HelperOperation(
                    item_id, HelperOperationKind.RESTORE_FILE, target=item.target,
                    before_hash=after_hash, staged_content_hash=item.sha256,
                    expected_mode=0o644, expected_uid=0, expected_gid=0,
                ))
                contents.append((item_id, item.content))
            else:
                operations.append(HelperOperation(
                    item_id, HelperOperationKind.REMOVE_CREATED_FILE,
                    target=item.target, before_hash=after_hash,
                ))
        operations.extend((
            HelperOperation(f"{operation_id}:reload", HelperOperationKind.DAEMON_RELOAD),
            HelperOperation(f"{operation_id}:restart", HelperOperationKind.RESTART_UNIT, unit=OLLAMA_UNIT),
        ))
        now = utc_now()
        expiry_candidates = [now + timedelta(minutes=5)]
        if plan.expires_at is not None:
            expiry_candidates.append(plan.expires_at)
        if approval.expires_at is not None:
            expiry_candidates.append(approval.expires_at)
        request = HelperRequest(
            PROTOCOL_VERSION, operation_id, plan.change_set.host_id, plan.plan_id,
            plan.change_set.content_hash, tuple(operations), now, min(expiry_candidates),
            approval_id=approval.approval_id, backup_id=manifest.backup_id,
            manifest_hash=manifest.manifest_hash,
        ).with_hash()
        validate_request(request, request.request_hash, now=now)
        return PreparedHelperApply(request, tuple(contents))


class PrivilegedSafeApplyCoordinator:
    """Backup/apply/validate/rollback workflow for the fixed local root change."""

    def __init__(
        self,
        backups: PrivilegedBackupStore,
        apply_factory: ApprovedHelperRequestFactory,
        rollback_factory: PrivilegedRollbackRequestFactory,
        invoker: HelperInvoker,
        validator: RuntimeValidatorPort,
        journal: LocalOperationJournal,
        audit: AuditPort | None = None,
    ) -> None:
        self.backups = backups
        self.apply_factory = apply_factory
        self.rollback_factory = rollback_factory
        self.invoker = invoker
        self.validator = validator
        self.journal = journal
        self.audit = audit

    def execute(self, plan: OptimizationPlan, approval: ApprovalRecord, operation_id: str, cancellation: CancellationToken) -> ApplyOutcome:
        if plan.change_set is None or not approval.is_valid_for(plan):
            raise AdapterError("invalid_approval", "approval does not match the current privileged plan")
        manifest: BackupManifest | None = None
        apply_request: HelperRequest | None = None
        try:
            manifest = self.backups.create(BackupRequest(
                operation_id, plan.plan_id, plan.change_set.host_id, None,
                plan.change_set, plan.backup_policy,
            ), cancellation)
            checks = self.backups.verify(manifest, cancellation)
            if not _passed(checks):
                return ApplyOutcome(PlanStatus.APPROVED, manifest, checks, "backup verification failed")
            prepared = self.apply_factory.prepare(plan, approval, operation_id, manifest=manifest)
            apply_request = prepared.request
            write = prepared.request.operations[0]
            self.journal.create(
                operation_id, plan.plan_id, plan.change_set.host_id, plan.change_set.content_hash,
                (JournalTarget(write.target, write.before_hash, write.staged_content_hash),),  # type: ignore[arg-type]
                approval_id=approval.approval_id, backup_id=manifest.backup_id,
                manifest_hash=manifest.manifest_hash, request_hash=prepared.request.request_hash,
            )
            results = self.invoker.invoke(prepared.request, prepared.staged_contents, cancellation)
            if not _helper_passed(results):
                if results and not results[0].completed:
                    self.journal.update(operation_id, JournalStatus.ROLLING_BACK)
                    self.journal.update(operation_id, JournalStatus.ROLLED_BACK)
                    return ApplyOutcome(PlanStatus.ROLLED_BACK, manifest, _helper_validations(results, "apply"), "privileged apply failed")
                return self._rollback(plan, approval, manifest, prepared.request, operation_id, (), "privileged apply failed", cancellation)
            self.journal.update(operation_id, JournalStatus.VALIDATING)
            validations = self.validator.validate(plan.change_set, cancellation)
            if _passed(validations):
                self.journal.update(operation_id, JournalStatus.COMMITTED)
                return ApplyOutcome(PlanStatus.COMMITTED, manifest, validations)
            return self._rollback(plan, approval, manifest, prepared.request, operation_id, validations, "runtime validation failed", cancellation)
        except (AdapterError, OSError, OperationCancelled) as error:
            if manifest is None:
                return ApplyOutcome(PlanStatus.APPROVED, None, error=str(error))
            try:
                self.journal.load(operation_id)
            except (AdapterError, OSError):
                return ApplyOutcome(PlanStatus.RECOVERY_REQUIRED, manifest, error=str(error))
            if apply_request is None:
                return ApplyOutcome(PlanStatus.RECOVERY_REQUIRED, manifest, error=str(error))
            return self._rollback(plan, approval, manifest, apply_request, operation_id, (), str(error), cancellation)

    def _rollback(self, plan, approval, manifest, apply_request, operation_id, validations, error, cancellation):
        try:
            current = self.journal.load(operation_id)
            if current.status in {JournalStatus.APPLYING, JournalStatus.VALIDATING}:
                self.journal.update(operation_id, JournalStatus.ROLLING_BACK)
            rollback = self.rollback_factory.prepare(
                plan, approval, manifest, f"{operation_id}-rollback", apply_request, self.backups, cancellation
            )
            self.journal.bind_rollback(operation_id, rollback.request.request_hash)
            results = self.invoker.invoke(rollback.request, rollback.staged_contents, cancellation)
            restored = _helper_validations(results, "rollback")
            status = PlanStatus.ROLLED_BACK if _helper_passed(results) else PlanStatus.RECOVERY_REQUIRED
        except (AdapterError, OSError, OperationCancelled) as rollback_error:
            restored = (_validation("rollback.exception", False, getattr(rollback_error, "code", type(rollback_error).__name__)),)
            status = PlanStatus.RECOVERY_REQUIRED
        try:
            self.journal.update(operation_id, JournalStatus.ROLLED_BACK if status is PlanStatus.ROLLED_BACK else JournalStatus.RECOVERY_REQUIRED)
        except (AdapterError, OSError):
            status = PlanStatus.RECOVERY_REQUIRED
        return ApplyOutcome(status, manifest, validations + restored, error)


def _validate_manifest_binding(plan, approval, manifest, operation_id):
    if plan.change_set is None or (
        manifest.backup_id != operation_id
        or manifest.plan_id != plan.plan_id
        or manifest.host_id != plan.change_set.host_id
        or manifest.change_set_hash != plan.change_set.content_hash
        or manifest.encryption != plan.backup_policy
        or not manifest.complete
        or not approval.is_valid_for(plan)
    ):
        raise AdapterError("workflow_binding_mismatch", "backup manifest is not bound to the approved plan")


def _passed(results):
    return bool(results) and all(item.status is ValidationStatus.PASSED for item in results)


def _helper_passed(results):
    return bool(results) and all(item.completed for item in results)


def _validation(check, passed, actual):
    return ValidationResult(check, "helper", check, ValidationStatus.PASSED if passed else ValidationStatus.FAILED, "completed", actual, Severity.INFO if passed else Severity.HIGH, LocalizedMessage(f"validation.{check}"))


def _helper_validations(results, prefix):
    return tuple(_validation(f"{prefix}.{item.kind.value}", item.completed, item.error_code or "completed") for item in results)
