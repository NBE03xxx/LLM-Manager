from __future__ import annotations

from llm_manager.application.errors import AdapterError

from .backup_deletion import BackupDeletionResultStore, BackupDeletionView
from .backup_inventory import (
    BackupInventoryEvidence, LocalRetentionResultStore, RetentionRunEvidence,
)
from .openssh_remote_deletion import RemoteDeletionAttemptStore
from .openssh_remote_retention import (
    RemoteRetentionAttemptStore, RemoteRetentionResultStore,
)


class BackupEvidenceRepository:
    """Load latest private evidence after restart without performing mutation."""

    def __init__(
        self,
        local_retention: LocalRetentionResultStore,
        remote_retention: RemoteRetentionResultStore,
        deletion_results: BackupDeletionResultStore,
        *,
        remote_retention_attempts: RemoteRetentionAttemptStore | None = None,
        remote_deletion_attempts: RemoteDeletionAttemptStore | None = None,
    ) -> None:
        self.local_retention = local_retention
        self.remote_retention = remote_retention
        self.deletion_results = deletion_results
        self.remote_retention_attempts = remote_retention_attempts
        self.remote_deletion_attempts = remote_deletion_attempts

    def load_for_host(
        self, host_id: str, host_fingerprint: str
    ) -> BackupInventoryEvidence:
        local = self.local_retention.list_for_host(host_id)
        remote = self.remote_retention.list_for_host(host_id, host_fingerprint)
        remote_result = remote[0] if remote else None
        retention_pending = False
        if remote_result is not None and self.remote_retention_attempts is not None:
            request = self.remote_retention_attempts.load(remote_result.request_id)
            if (
                request.request_hash, request.host_id, request.host_fingerprint,
            ) != (
                remote_result.request_hash, remote_result.host_id,
                remote_result.host_fingerprint,
            ):
                raise AdapterError(
                    "remote_retention_binding_mismatch", "attempt changed result identity"
                )
            retention_pending = self.remote_retention_attempts.cleanup_pending(request)
        latest = {}
        for result in self.deletion_results.list_for_host(host_id, host_fingerprint):
            latest.setdefault(result.backup_id, result)
        views = []
        for result in latest.values():
            pending = (
                self.remote_deletion_attempts.cleanup_pending_for_result(result)
                if self.remote_deletion_attempts is not None else False
            )
            views.append(BackupDeletionView(result, pending))
        views.sort(key=lambda item: item.result.completed_at, reverse=True)
        return BackupInventoryEvidence(
            RetentionRunEvidence(
                local[0] if local else None, remote_result, retention_pending,
            ),
            tuple(views),
        )
