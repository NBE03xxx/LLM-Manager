from __future__ import annotations

from typing import Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import BackupManifest

from .backup_deletion import BackupDeletionResultStore
from .backup_inventory import BackupListAction
from .backup_reconciliation import BackupReconciliationResult, BackupReconciliationRunner


class ReconciliationManifestPort(Protocol):
    def list_manifests(self, host_id: str) -> tuple[BackupManifest, ...]: ...


class BackupReconciliationActionService:
    """Dispatch only read-only reconciliation from a bound inventory action."""

    def __init__(
        self,
        manifests: ReconciliationManifestPort,
        deletion_results: BackupDeletionResultStore,
        runner: BackupReconciliationRunner,
    ) -> None:
        self.manifests = manifests
        self.deletion_results = deletion_results
        self.runner = runner

    def execute(
        self,
        action: BackupListAction,
        reconciliation_id: str,
        backup_id: str,
        host_id: str,
        host_fingerprint: str,
        cancellation: CancellationToken,
    ) -> BackupReconciliationResult:
        if action is not BackupListAction.RECONCILE_COPIES:
            raise AdapterError(
                "invalid_backup_reconciliation_action", "action is not read-only reconciliation"
            )
        if cancellation.cancelled:
            raise OperationCancelled("backup reconciliation cancelled")
        deletion = next(
            (
                result for result in self.deletion_results.list_for_host(
                    host_id, host_fingerprint
                )
                if result.backup_id == backup_id
            ),
            None,
        )
        if deletion is None:
            raise AdapterError("deletion_result_not_found", "result is missing")
        manifests = self.manifests.list_manifests(host_id)
        if (len({manifest.backup_id for manifest in manifests}) != len(manifests)
                or any(manifest.host_id != host_id for manifest in manifests)):
            raise AdapterError("reconciliation_binding_mismatch", "manifest inventory changed")
        manifest = next(
            (value for value in manifests if value.backup_id == backup_id), None
        )
        if manifest is None:
            raise AdapterError("reconciliation_manifest_not_found", "manifest is unavailable")
        if (manifest.host_fingerprint != host_fingerprint
                or manifest.manifest_hash != deletion.manifest_hash):
            raise AdapterError("reconciliation_binding_mismatch", "manifest changed identity")
        if cancellation.cancelled:
            raise OperationCancelled("backup reconciliation cancelled")
        return self.runner.reconcile(
            reconciliation_id, deletion, manifest, cancellation
        )
