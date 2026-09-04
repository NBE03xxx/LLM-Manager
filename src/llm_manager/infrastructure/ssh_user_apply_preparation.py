from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.optimization import stable_hash
from llm_manager.application.ports import BackupRequest, CancellationToken
from llm_manager.domain.enums import ChangeOperation, ValidationStatus
from llm_manager.domain.models import (
    ApprovalRecord, BackupManifest, DiagnosticReport, OptimizationPlan, utc_now,
)

from .backup import BackupRestoreItem, MAX_ITEM_BYTES
from .remote_user_apply import (
    REMOTE_USER_APPLY_OPERATION,
    REMOTE_USER_APPLY_PROTOCOL_VERSION,
    RemoteUserApplyRequest,
    encode_remote_user_apply_request,
)
from .remote_user_rollback import (
    REMOTE_USER_ROLLBACK_OPERATION,
    REMOTE_USER_ROLLBACK_PROTOCOL_VERSION,
    RemoteUserRollbackRequest,
    encode_remote_user_rollback_request,
)
from .safe_apply import render_file_changes


class SshDualBackupPort(Protocol):
    def create(self, request: BackupRequest, cancellation: CancellationToken) -> BackupManifest: ...
    def verify(self, manifest: BackupManifest, cancellation: CancellationToken): ...
    def restore_items(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[BackupRestoreItem, ...]: ...


@dataclass(frozen=True, slots=True)
class PreparedSshUserApply:
    manifest: BackupManifest
    request: RemoteUserApplyRequest
    request_content: bytes
    payload: bytes


@dataclass(frozen=True, slots=True)
class PreparedSshUserRollback:
    request: RemoteUserRollbackRequest
    request_content: bytes
    restore_content: bytes | None


@dataclass(slots=True)
class PrepareSshUserApply:
    backups: SshDualBackupPort
    target_map: dict[str, str]
    clock: Callable = utc_now

    def execute(
        self,
        plan: OptimizationPlan,
        report: DiagnosticReport,
        approval: ApprovalRecord,
        backup_id: str,
        cancellation: CancellationToken,
    ) -> PreparedSshUserApply:
        _cancel(cancellation)
        if (
            plan.change_set is None
            or not approval.is_valid_for(plan)
            or plan.report_id != report.report_id
            or plan.report_hash != stable_hash(report)
            or plan.change_set.host_id != report.host.host_id
            or not report.host.fingerprint
        ):
            raise AdapterError("invalid_approval", "approval does not match SSH user plan")
        changes = plan.change_set.changes
        targets = tuple(dict.fromkeys(change.target for change in changes))
        if (
            len(targets) != 1
            or targets[0] not in self.target_map
            or any(
                change.requires_root
                or change.operation not in {ChangeOperation.CREATE_FILE, ChangeOperation.REPLACE_FILE}
                for change in changes
            )
        ):
            raise AdapterError("unsupported_ssh_user_change", "SSH user Apply requires one allowlisted file")
        manifest = self.backups.create(
            BackupRequest(
                backup_id, plan.plan_id, plan.change_set.host_id,
                report.host.fingerprint, plan.change_set, plan.backup_policy,
            ),
            cancellation,
        )
        checks = self.backups.verify(manifest, cancellation)
        if not checks or any(check.status is not ValidationStatus.PASSED for check in checks):
            raise AdapterError("backup_verification_failed", "both SSH backup copies must verify")
        items = self.backups.restore_items(manifest, cancellation)
        if len(items) != 1 or items[0].target != targets[0]:
            raise AdapterError("backup_binding_mismatch", "verified backup target changed")
        item = items[0]
        before_hashes = {change.before_hash for change in changes}
        if len(before_hashes) != 1 or before_hashes != {item.sha256}:
            raise AdapterError("backup_binding_mismatch", "verified backup is stale")
        content = item.content if item.existed else b""
        if content is None:
            raise AdapterError("backup_binding_mismatch", "verified backup content is missing")
        payload = render_file_changes(content, list(changes))
        if len(payload) > MAX_ITEM_BYTES:
            raise AdapterError("item_too_large", "rendered SSH target exceeds 16 MiB")
        now = self.clock()
        request = RemoteUserApplyRequest(
            REMOTE_USER_APPLY_PROTOCOL_VERSION,
            REMOTE_USER_APPLY_OPERATION,
            backup_id,
            plan.plan_id,
            plan.change_set.content_hash,
            backup_id,
            manifest.manifest_hash,
            plan.change_set.host_id,
            manifest.host_fingerprint or "",
            self.target_map[targets[0]],
            item.sha256,
            hashlib.sha256(payload).hexdigest(),
            now,
            now + timedelta(minutes=5),
        ).with_hash()
        return PreparedSshUserApply(
            manifest, request, encode_remote_user_apply_request(request), payload
        )


@dataclass(slots=True)
class PrepareSshUserRollback:
    backups: SshDualBackupPort
    clock: Callable = utc_now

    def execute(
        self,
        plan: OptimizationPlan,
        report: DiagnosticReport,
        approval: ApprovalRecord,
        prepared_apply: PreparedSshUserApply,
        rollback_id: str,
        cancellation: CancellationToken,
    ) -> PreparedSshUserRollback:
        _cancel(cancellation)
        change_set = plan.change_set
        manifest = prepared_apply.manifest
        apply_request = prepared_apply.request
        if (
            change_set is None
            or approval.plan_id != plan.plan_id
            or approval.report_hash != plan.report_hash
            or approval.change_set_hash != change_set.content_hash
            or approval.backup_policy_hash != plan.backup_policy.content_hash
            or (not plan.backup_policy.enabled and not approval.plaintext_backup_acknowledged)
            or plan.report_id != report.report_id
            or plan.report_hash != stable_hash(report)
            or not report.host.fingerprint
            or manifest.backup_id != apply_request.backup_id
            or manifest.plan_id != plan.plan_id
            or manifest.change_set_hash != change_set.content_hash
            or manifest.host_id != report.host.host_id
            or manifest.host_fingerprint != report.host.fingerprint
            or manifest.manifest_hash != apply_request.local_manifest_hash
            or apply_request.request_hash == ""
            or hashlib.sha256(prepared_apply.payload).hexdigest() != apply_request.after_hash
        ):
            raise AdapterError("rollback_binding_mismatch", "rollback inputs do not match Apply preparation")
        checks = self.backups.verify(manifest, cancellation)
        if not checks or any(check.status is not ValidationStatus.PASSED for check in checks):
            raise AdapterError("backup_verification_failed", "both SSH backup copies must verify for rollback")
        items = self.backups.restore_items(manifest, cancellation)
        if len(items) != 1 or len(manifest.items) != 1:
            raise AdapterError("rollback_binding_mismatch", "rollback requires one backup item")
        item = items[0]
        recorded = manifest.items[0]
        absolute_targets = {change.target for change in change_set.changes}
        before_hashes = {change.before_hash for change in change_set.changes}
        if (
            absolute_targets != {item.target}
            or item.target != recorded.target
            or (item.existed, item.sha256, item.mode) != (
                recorded.existed, recorded.sha256, recorded.mode
            )
            or before_hashes != {item.sha256}
            or (item.existed and (item.content is None or item.mode is None))
            or (not item.existed and item.content is not None)
        ):
            raise AdapterError("rollback_binding_mismatch", "rollback backup item changed")
        if item.content is not None and hashlib.sha256(item.content).hexdigest() != item.sha256:
            raise AdapterError("rollback_binding_mismatch", "rollback backup content hash changed")
        now = self.clock()
        expiry = now + timedelta(minutes=5)
        request = RemoteUserRollbackRequest(
            REMOTE_USER_ROLLBACK_PROTOCOL_VERSION,
            REMOTE_USER_ROLLBACK_OPERATION,
            rollback_id,
            apply_request.request_hash,
            plan.plan_id,
            change_set.content_hash,
            manifest.backup_id,
            manifest.manifest_hash,
            manifest.host_id,
            manifest.host_fingerprint or "",
            apply_request.target,
            apply_request.after_hash,
            item.existed,
            item.sha256,
            item.mode,
            now,
            expiry,
        ).with_hash()
        return PreparedSshUserRollback(
            request, encode_remote_user_rollback_request(request), item.content
        )

def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("SSH user Apply preparation cancelled")
