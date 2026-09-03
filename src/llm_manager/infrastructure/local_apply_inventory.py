from __future__ import annotations

from dataclasses import dataclass

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.application.restore_preview import CreateRestorePreview, RestorePreview

from .backup import LocalBackupStore
from .backup_inventory import BackupListAction
from .backup_reconciliation import CopyPresence
from .journal import JournalStatus, LocalOperationJournal
from .restore_execution import RestoreExecutionStore


@dataclass(frozen=True, slots=True)
class LocalApplyInventoryItem:
    backup_id: str
    state: JournalStatus | str
    local_presence: CopyPresence
    remote_presence: CopyPresence
    protected: bool
    requires_attention: bool
    allowed_actions: tuple[BackupListAction, ...]
    restore_state: str | None = None
    restore_requires_attention: bool = False


@dataclass(slots=True)
class LocalApplyInventoryService:
    backups: LocalBackupStore
    journals: LocalOperationJournal
    restore_executions: RestoreExecutionStore | None = None

    def list_for_host(
        self, host_id: str, cancellation: CancellationToken
    ) -> tuple[LocalApplyInventoryItem, ...]:
        if cancellation.cancelled:
            raise OperationCancelled("local apply inventory cancelled")
        manifests = {item.backup_id: item for item in self.backups.list_manifests_strict(host_id)}
        if cancellation.cancelled:
            raise OperationCancelled("local apply inventory cancelled")
        journals = {
            item.operation_id: item for item in self.journals.list_for_host_strict(host_id)
        }
        restore_by_backup: dict[str, list[object]] = {}
        if self.restore_executions is not None:
            for value in self.restore_executions.list_strict():
                if value.attempt.host_id != host_id:
                    raise AdapterError(
                        "restore_execution_binding_mismatch", "restore host changed identity"
                    )
                restore_by_backup.setdefault(value.attempt.backup_id, []).append(value)
        identifiers = set(manifests) | set(journals) | set(restore_by_backup)
        result = []
        for backup_id in identifiers:
            manifest = manifests.get(backup_id)
            journal = journals.get(backup_id)
            restore_values = restore_by_backup.get(backup_id, [])
            restore_attention = any(value.requires_attention for value in restore_values)
            restore_state = (
                str(getattr(restore_values[0].state, "value", restore_values[0].state))
                if restore_values else None
            )
            attention = (
                manifest is None
                or journal is None
                or journal.status is JournalStatus.RECOVERY_REQUIRED
                or (journal is not None and journal.change_set_hash != manifest.change_set_hash)
                or restore_attention
            )
            result.append(LocalApplyInventoryItem(
                backup_id=backup_id,
                state=journal.status if journal is not None else "backup_only",
                local_presence=(CopyPresence.PRESENT if manifest is not None else CopyPresence.ABSENT),
                remote_presence=CopyPresence.ABSENT,
                protected=manifest.protected if manifest is not None else False,
                requires_attention=attention,
                allowed_actions=(BackupListAction.REFRESH_INVENTORY,),
                restore_state=restore_state,
                restore_requires_attention=restore_attention,
            ))
        return tuple(sorted(result, key=lambda item: item.backup_id, reverse=True))

    def preview_restore(
        self, host_id: str, backup_id: str, cancellation: CancellationToken
    ) -> RestorePreview:
        if cancellation.cancelled:
            raise OperationCancelled("restore preview cancelled")
        manifests = self.backups.list_manifests_strict(host_id)
        manifest = next((item for item in manifests if item.backup_id == backup_id), None)
        if manifest is None:
            raise AdapterError("backup_not_found", "backup is unavailable for restore preview")
        return CreateRestorePreview().execute(manifest)
