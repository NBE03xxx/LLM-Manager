from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import ValidationStatus
from llm_manager.domain.models import BackupManifest


class CopyPresence(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class DualCopyState(StrEnum):
    BOTH_AVAILABLE = "both_available"
    LOCAL_ONLY = "local_only"
    REMOTE_ONLY = "remote_only"
    BOTH_DELETED = "both_deleted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BackupCopyReconciliation:
    backup_id: str
    host_id: str
    local: CopyPresence
    remote: CopyPresence
    state: DualCopyState
    requires_attention: bool


class BackupCopyObserver(Protocol):
    def observe(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> CopyPresence: ...


class LocalBackupCopyObserver:
    def __init__(self, store) -> None:
        self.store = store

    def observe(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> CopyPresence:
        if cancellation.cancelled:
            raise OperationCancelled("backup copy reconciliation cancelled")
        location = Path(manifest.storage_location)
        if not location.exists():
            return CopyPresence.ABSENT
        try:
            results = self.store.verify(manifest, cancellation)
        except OperationCancelled:
            raise
        except (AdapterError, OSError, ValueError):
            return CopyPresence.UNKNOWN
        return (
            CopyPresence.PRESENT
            if results and all(item.status is ValidationStatus.PASSED for item in results)
            else CopyPresence.UNKNOWN
        )


class RemoteBackupCopyObserver:
    def __init__(self, store) -> None:
        self.store = store

    def observe(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> CopyPresence:
        if cancellation.cancelled:
            raise OperationCancelled("backup copy reconciliation cancelled")
        try:
            self.store.load(manifest, cancellation)
            return CopyPresence.PRESENT
        except OperationCancelled:
            raise
        except AdapterError as error:
            if error.code == "remote_backup_not_found":
                return CopyPresence.ABSENT
            return CopyPresence.UNKNOWN
        except (OSError, ValueError):
            return CopyPresence.UNKNOWN


class DualCopyDeletionReconciler:
    """Observe deletion outcomes without deleting, retrying, or repairing either copy."""

    def __init__(self, local: BackupCopyObserver, remote: BackupCopyObserver) -> None:
        self.local = local
        self.remote = remote

    def reconcile(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> BackupCopyReconciliation:
        if cancellation.cancelled:
            raise OperationCancelled("backup copy reconciliation cancelled")
        local = self.local.observe(manifest, cancellation)
        if cancellation.cancelled:
            raise OperationCancelled("backup copy reconciliation cancelled")
        remote = self.remote.observe(manifest, cancellation)
        state = _combined(local, remote)
        return BackupCopyReconciliation(
            manifest.backup_id,
            manifest.host_id,
            local,
            remote,
            state,
            state not in {DualCopyState.BOTH_AVAILABLE, DualCopyState.BOTH_DELETED},
        )


def _combined(local: CopyPresence, remote: CopyPresence) -> DualCopyState:
    if CopyPresence.UNKNOWN in {local, remote}:
        return DualCopyState.UNKNOWN
    if local is CopyPresence.PRESENT and remote is CopyPresence.PRESENT:
        return DualCopyState.BOTH_AVAILABLE
    if local is CopyPresence.PRESENT:
        return DualCopyState.LOCAL_ONLY
    if remote is CopyPresence.PRESENT:
        return DualCopyState.REMOTE_ONLY
    return DualCopyState.BOTH_DELETED
