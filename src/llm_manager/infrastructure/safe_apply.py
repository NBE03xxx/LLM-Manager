from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import AuditPort, BackupRequest, BackupStorePort, CancellationToken
from llm_manager.domain.enums import ChangeOperation, PlanStatus, Severity, ValidationStatus
from llm_manager.domain.models import ApprovalRecord, BackupManifest, Change, ChangeSet, LocalizedMessage, OptimizationPlan, ValidationResult
from llm_manager.domain.workflow import PlanStateMachine
from llm_manager.planning.opencode import locate_scalar_spans

from .backup import MAX_ITEM_BYTES, _atomic_write, _fsync_directory, _within
from .journal import JournalStatus, JournalTarget, LocalOperationJournal


@dataclass(frozen=True, slots=True)
class AppliedFile:
    target: str
    sha256: str
    validation_checks: tuple[str, ...] = ()


class AtomicFileExecutor:
    """Applies an approved user-level ChangeSet within explicit sandbox roots."""

    def __init__(self, allowed_roots: tuple[Path, ...]) -> None:
        self.allowed_roots = tuple(root.resolve() for root in allowed_roots)

    def apply(self, change_set: ChangeSet, cancellation: CancellationToken) -> tuple[AppliedFile, ...]:
        planned = self.prepare(change_set, cancellation)
        for item in planned:
            _cancel(cancellation)
            changes = [change for change in change_set.changes if change.target == item.target]
            target = self._target(item.target)
            content = self._current(target, changes)
            rendered = self._render(content, changes)
            mode = (target.stat().st_mode & 0o7777) if target.exists() else 0o600
            _atomic_write(target, rendered, mode)
        return planned

    def prepare(self, change_set: ChangeSet, cancellation: CancellationToken) -> tuple[AppliedFile, ...]:
        grouped: dict[str, list[Change]] = {}
        for change in change_set.changes:
            if change.requires_root or change.operation not in {ChangeOperation.CREATE_FILE, ChangeOperation.REPLACE_FILE}:
                raise AdapterError("unsupported_change", "atomic user executor accepts only non-root file writes")
            grouped.setdefault(change.target, []).append(change)
        planned: list[AppliedFile] = []
        for target_text, changes in grouped.items():
            _cancel(cancellation)
            target = self._target(target_text)
            content = self._current(target, changes)
            rendered = self._render(content, changes)
            if len(rendered) > MAX_ITEM_BYTES:
                raise AdapterError("item_too_large", "rendered target exceeds 16 MiB")
            checks = tuple(dict.fromkeys(check for change in changes for check in change.validation_checks))
            planned.append(AppliedFile(str(target), hashlib.sha256(rendered).hexdigest(), checks))
        return tuple(planned)

    def _target(self, text: str) -> Path:
        path = Path(text)
        if not path.is_absolute() or path.is_symlink():
            raise AdapterError("invalid_target", "target must be an absolute non-symlink path")
        parent = path.parent.resolve()
        if not any(_within(parent, root) for root in self.allowed_roots):
            raise AdapterError("target_not_allowed", "target is outside allowed roots")
        return parent / path.name

    def _current(self, target: Path, changes: list[Change]) -> bytes:
        hashes = {change.before_hash for change in changes}
        if len(hashes) != 1:
            raise AdapterError("inconsistent_precondition", "changes for one target have different before hashes")
        expected = next(iter(hashes))
        if target.exists():
            if not target.is_file():
                raise AdapterError("unsupported_target", "target is not a regular file")
            content = target.read_bytes()
            actual = hashlib.sha256(content).hexdigest()
            if expected is None or actual != expected:
                raise AdapterError("stale_plan", "target content changed after planning")
            return content
        if expected is not None or any(change.operation is not ChangeOperation.CREATE_FILE for change in changes):
            raise AdapterError("stale_plan", "target existence changed after planning")
        return b""

    @staticmethod
    def _render(content: bytes, changes: list[Change]) -> bytes:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise AdapterError("unsupported_encoding", "target is not UTF-8") from error
        spans: list[tuple[int, int, str]] = []
        for change in changes:
            if change.replacement_text is None:
                raise AdapterError("missing_replacement", "file change has no replacement text")
            span = change.source_span or (0, len(text))
            spans.append((span[0], span[1], change.replacement_text))
        spans.sort(reverse=True)
        previous_start = len(text) + 1
        for start, end, replacement in spans:
            if end > len(text) or end > previous_start:
                raise AdapterError("overlapping_changes", "source spans overlap or exceed target")
            text = text[:start] + replacement + text[end:]
            previous_start = start
        return text.encode("utf-8")


class FileValidator:
    def validate(self, applied: tuple[AppliedFile, ...], cancellation: CancellationToken) -> tuple[ValidationResult, ...]:
        results: list[ValidationResult] = []
        for item in applied:
            _cancel(cancellation)
            path = Path(item.target)
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
            passed = actual == item.sha256
            results.append(_result(f"file:{item.target}", passed, item.sha256, actual))
            if actual is None:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                results.append(_result(f"file.utf8:{item.target}", False, "UTF-8", type(error).__name__))
                continue
            if any(check.startswith("opencode.") for check in item.validation_checks):
                try:
                    locate_scalar_spans(content)
                    results.append(_result(f"opencode.parse:{item.target}", True, "valid JSONC", "valid JSONC"))
                except AdapterError as error:
                    results.append(_result(f"opencode.parse:{item.target}", False, "valid JSONC", error.code))
            if any(check.startswith(("systemd.", "ollama.")) for check in item.validation_checks):
                valid, detail = _validate_systemd_drop_in(content)
                results.append(_result(f"systemd.drop_in:{item.target}", valid, "valid dedicated drop-in", detail))
        return tuple(results)


@dataclass(frozen=True, slots=True)
class ApplyOutcome:
    status: PlanStatus
    manifest: BackupManifest | None
    validations: tuple[ValidationResult, ...] = ()
    error: str | None = None


class SafeApplyCoordinator:
    def __init__(self, backups: BackupStorePort, executor: AtomicFileExecutor, validator: FileValidator, audit: AuditPort | None = None, journal: LocalOperationJournal | None = None) -> None:
        self.backups = backups
        self.executor = executor
        self.validator = validator
        self.audit = audit
        self.journal = journal

    def execute(self, plan: OptimizationPlan, approval: ApprovalRecord, backup_id: str, cancellation: CancellationToken) -> ApplyOutcome:
        if plan.change_set is None or not approval.is_valid_for(plan):
            raise AdapterError("invalid_approval", "approval does not match the current plan")
        self._audit("apply.approved", plan, (("approval_id", approval.approval_id),))
        machine = PlanStateMachine(plan.plan_id, PlanStatus.APPROVED)
        manifest: BackupManifest | None = None
        operation_id = backup_id
        try:
            manifest = self.backups.create(BackupRequest(backup_id, plan.plan_id, plan.change_set.host_id, None, plan.change_set), cancellation)
            backup_checks = self.backups.verify(manifest, cancellation)
            if not _passed(backup_checks):
                self._audit("backup.failed", plan, (("backup_id", backup_id),))
                return ApplyOutcome(PlanStatus.APPROVED, manifest, backup_checks, "backup verification failed")
            self._audit("backup.verified", plan, (("backup_id", backup_id),))
            prepared = self.executor.prepare(plan.change_set, cancellation)
            if self.journal is not None:
                before_hashes = {change.target: change.before_hash for change in plan.change_set.changes}
                self.journal.create(
                    operation_id,
                    plan.plan_id,
                    plan.change_set.host_id,
                    plan.change_set.content_hash,
                    tuple(JournalTarget(item.target, before_hashes[item.target], item.sha256) for item in prepared),
                )
            machine = machine.transition_to(PlanStatus.BACKED_UP).transition_to(PlanStatus.APPLYING)
            applied = self.executor.apply(plan.change_set, cancellation)
            if not self._journal_update(operation_id, JournalStatus.VALIDATING):
                return self._rollback(machine, manifest, cancellation, (), "journal update failed", plan, operation_id)
            machine = machine.transition_to(PlanStatus.VALIDATING)
            validations = self.validator.validate(applied, cancellation)
            if _passed(validations):
                if not self._journal_update(operation_id, JournalStatus.COMMITTED):
                    return self._rollback(machine, manifest, cancellation, validations, "journal commit failed", plan, operation_id)
                outcome = ApplyOutcome(machine.transition_to(PlanStatus.COMMITTED).status, manifest, validations)
                self._audit("apply.committed", plan, (("backup_id", backup_id),))
                return outcome
            return self._rollback(machine, manifest, cancellation, validations, "validation failed", plan, operation_id)
        except (AdapterError, OSError, OperationCancelled) as error:
            if manifest is None or machine.status is PlanStatus.APPROVED:
                self._audit("backup.failed", plan, (("error_code", getattr(error, "code", type(error).__name__)),))
                return ApplyOutcome(machine.status, manifest, error=str(error))
            return self._rollback(machine, manifest, cancellation, (), str(error), plan, operation_id)

    def _rollback(self, machine: PlanStateMachine, manifest: BackupManifest, cancellation: CancellationToken, validations: tuple[ValidationResult, ...], error: str, plan: OptimizationPlan, operation_id: str) -> ApplyOutcome:
        if machine.status is PlanStatus.VALIDATING:
            machine = machine.transition_to(PlanStatus.ROLLING_BACK)
        elif machine.status is PlanStatus.APPLYING:
            machine = machine.transition_to(PlanStatus.ROLLING_BACK)
        journal_ok = self._journal_update(operation_id, JournalStatus.ROLLING_BACK)
        try:
            restored = self.backups.restore(manifest, cancellation)
            status = PlanStatus.ROLLED_BACK if _passed(restored) and journal_ok else PlanStatus.RECOVERY_REQUIRED
        except (AdapterError, OSError, OperationCancelled) as restore_error:
            restored = (_result("rollback.exception", False, "restored", getattr(restore_error, "code", type(restore_error).__name__)),)
            status = PlanStatus.RECOVERY_REQUIRED
        machine = machine.transition_to(status)
        self._journal_update(operation_id, JournalStatus.ROLLED_BACK if status is PlanStatus.ROLLED_BACK else JournalStatus.RECOVERY_REQUIRED)
        self._audit("rollback.completed" if status is PlanStatus.ROLLED_BACK else "rollback.recovery_required", plan, (("backup_id", manifest.backup_id),))
        return ApplyOutcome(machine.status, manifest, validations + restored, error)

    def _audit(self, event_type: str, plan: OptimizationPlan | None, fields: tuple[tuple[str, object], ...]) -> None:
        if self.audit is None:
            return
        correlation_id = plan.plan_id if plan is not None else "safe-apply"
        base = (("plan_id", plan.plan_id), ("host_id", plan.change_set.host_id if plan and plan.change_set else None)) if plan else ()
        self.audit.append(event_type, correlation_id, base + fields)

    def _journal_update(self, operation_id: str, status: JournalStatus) -> bool:
        if self.journal is None:
            return True
        try:
            self.journal.update(operation_id, status)
            return True
        except (AdapterError, OSError):
            return False


def _passed(results: tuple[ValidationResult, ...]) -> bool:
    return bool(results) and all(item.status is ValidationStatus.PASSED for item in results)


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("safe apply cancelled")


def _result(check: str, passed: bool, expected: str | None, actual: str | None) -> ValidationResult:
    return ValidationResult(check, "file", check, ValidationStatus.PASSED if passed else ValidationStatus.FAILED, expected, actual, Severity.INFO if passed else Severity.HIGH, LocalizedMessage(f"validation.{check}"))


def _validate_systemd_drop_in(content: str) -> tuple[bool, str]:
    section_seen = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line == "[Service]" and not section_seen:
            section_seen = True
            continue
        if not section_seen or not line.startswith('Environment="') or not line.endswith('"'):
            return False, "unsupported directive"
        value = line[len('Environment="'):-1]
        if "=" not in value or any(character in value for character in "\n\r\x00\""):
            return False, "invalid environment assignment"
    return (section_seen, "valid dedicated drop-in" if section_seen else "missing [Service]")
