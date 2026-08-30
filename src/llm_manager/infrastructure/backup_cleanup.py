from __future__ import annotations

from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken

from .backup_deletion import BackupDeletionResult, BackupDeletionResultStore
from .backup_inventory import BackupListAction
from .openssh_remote_retention import RemoteRetentionResultStore


class RetentionCleanupPort(Protocol):
    def cleanup_pending(self, request_id: str) -> bool: ...

    def retry_staging_cleanup(
        self, request_id: str, host_id: str, host_fingerprint: str,
        cancellation: CancellationToken,
    ) -> bool: ...


class DeletionCleanupPort(Protocol):
    def staging_cleanup_pending(self, result: BackupDeletionResult) -> bool: ...

    def retry_staging_cleanup(
        self, result: BackupDeletionResult, cancellation: CancellationToken,
    ) -> bool: ...


class BackupCleanupActionService:
    """Execute only a cleanup action selected from immutable inventory evidence."""

    def __init__(
        self,
        retention_results: RemoteRetentionResultStore,
        deletion_results: BackupDeletionResultStore,
        retention: RetentionCleanupPort,
        deletion: DeletionCleanupPort,
    ) -> None:
        self.retention_results = retention_results
        self.deletion_results = deletion_results
        self.retention = retention
        self.deletion = deletion

    def execute(
        self,
        action: BackupListAction,
        host_id: str,
        host_fingerprint: str,
        cancellation: CancellationToken,
        *,
        backup_id: str | None = None,
    ) -> bool:
        if cancellation.cancelled:
            raise OperationCancelled("backup cleanup cancelled")
        if action is BackupListAction.RETRY_RETENTION_STAGING_CLEANUP:
            if backup_id is not None:
                raise AdapterError("invalid_backup_cleanup_action", "retention cleanup is host-wide")
            results = self.retention_results.list_for_host(host_id, host_fingerprint)
            if not results:
                raise AdapterError("remote_retention_result_not_found", "result is missing")
            result = results[0]
            if not self.retention.cleanup_pending(result.request_id):
                raise AdapterError("backup_cleanup_not_pending", "cleanup is not pending")
            return self.retention.retry_staging_cleanup(
                result.request_id, host_id, host_fingerprint, cancellation
            )
        if action is BackupListAction.RETRY_STAGING_CLEANUP:
            if backup_id is None:
                raise AdapterError("invalid_backup_cleanup_action", "backup ID is required")
            result = next(
                (
                    value for value in self.deletion_results.list_for_host(
                        host_id, host_fingerprint
                    )
                    if value.backup_id == backup_id
                ),
                None,
            )
            if result is None:
                raise AdapterError("deletion_result_not_found", "result is missing")
            if not self.deletion.staging_cleanup_pending(result):
                raise AdapterError("backup_cleanup_not_pending", "cleanup is not pending")
            return self.deletion.retry_staging_cleanup(result, cancellation)
        raise AdapterError("invalid_backup_cleanup_action", "action is not cleanup-only")
