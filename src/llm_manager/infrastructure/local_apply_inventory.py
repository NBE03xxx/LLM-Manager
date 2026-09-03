from __future__ import annotations

from dataclasses import dataclass

from llm_manager.application.errors import OperationCancelled
from llm_manager.application.ports import CancellationToken

from .backup import LocalBackupStore
from .backup_inventory import BackupListAction
from .backup_reconciliation import CopyPresence
from .journal import JournalStatus, LocalOperationJournal


@dataclass(frozen=True, slots=True)
class LocalApplyInventoryItem:
    backup_id: str
    state: JournalStatus | str
    local_presence: CopyPresence
    remote_presence: CopyPresence
    protected: bool
    requires_attention: bool
    allowed_actions: tuple[BackupListAction, ...]


@dataclass(slots=True)
class LocalApplyInventoryService:
    backups: LocalBackupStore
    journals: LocalOperationJournal

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
        identifiers = set(manifests) | set(journals)
        result = []
        for backup_id in identifiers:
            manifest = manifests.get(backup_id)
            journal = journals.get(backup_id)
            attention = (
                manifest is None
                or journal is None
                or journal.status is JournalStatus.RECOVERY_REQUIRED
                or (journal is not None and journal.change_set_hash != manifest.change_set_hash)
            )
            result.append(LocalApplyInventoryItem(
                backup_id=backup_id,
                state=journal.status if journal is not None else "backup_only",
                local_presence=(CopyPresence.PRESENT if manifest is not None else CopyPresence.ABSENT),
                remote_presence=CopyPresence.ABSENT,
                protected=manifest.protected if manifest is not None else False,
                requires_attention=attention,
                allowed_actions=(BackupListAction.REFRESH_INVENTORY,),
            ))
        return tuple(sorted(result, key=lambda item: item.backup_id, reverse=True))
