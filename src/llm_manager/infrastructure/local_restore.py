from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken
from llm_manager.application.restore_preflight import PreparedRestoreAuthorization
from llm_manager.domain.models import BackupManifest, utc_now

from .backup import LocalBackupStore, _atomic_write, _fsync_directory


class LocalRestoreState(StrEnum):
    COMMITTED = "committed"


@dataclass(frozen=True, slots=True)
class LocalRestoreResult:
    state: LocalRestoreState
    host_id: str
    backup_id: str
    manifest_hash: str
    authorization_hash: str
    target: str
    completed_at: datetime


@dataclass(slots=True)
class SingleTargetLocalRestoreExecutor:
    backups: LocalBackupStore

    def execute(
        self,
        authorization: PreparedRestoreAuthorization,
        cancellation: CancellationToken,
        now: datetime | None = None,
    ) -> LocalRestoreResult:
        current = now or utc_now()
        if cancellation.cancelled:
            raise OperationCancelled("local restore cancelled")
        if (
            authorization.with_hash() != authorization
            or current >= authorization.expires_at
            or len(authorization.targets) != 1
        ):
            raise AdapterError("invalid_restore_authorization", "restore authorization is invalid")
        manifests = self.backups.list_manifests_strict(authorization.host_id)
        manifest = next(
            (item for item in manifests if item.backup_id == authorization.backup_id), None
        )
        self._binding(authorization, manifest)
        if self.backups.observe_restore_targets(manifest) != authorization.current_targets:
            raise AdapterError("stale_restore_target", "restore target changed after approval")
        items = self.backups.restore_items(manifest, cancellation)
        if cancellation.cancelled:
            raise OperationCancelled("local restore cancelled")
        if self.backups.observe_restore_targets(manifest) != authorization.current_targets:
            raise AdapterError("stale_restore_target", "restore target changed while preparing")
        if len(items) != 1 or items[0].target != authorization.targets[0]:
            raise AdapterError("restore_binding_mismatch", "restore content changed identity")
        item = items[0]
        target = Path(item.target)
        if item.existed:
            if item.content is None or hashlib.sha256(item.content).hexdigest() != item.sha256:
                raise AdapterError("invalid_backup", "restore content integrity failed")
            _atomic_write(target, item.content, item.mode or 0o600)
        else:
            if item.content is not None or item.sha256 is not None:
                raise AdapterError("invalid_backup", "absent restore item contains content")
            target.unlink(missing_ok=True)
            _fsync_directory(target.parent)
        return LocalRestoreResult(
            LocalRestoreState.COMMITTED, authorization.host_id, authorization.backup_id,
            authorization.manifest_hash, authorization.authorization_hash,
            item.target, current,
        )

    @staticmethod
    def _binding(
        authorization: PreparedRestoreAuthorization, manifest: BackupManifest | None
    ) -> None:
        if manifest is None or (
            manifest.host_id,
            manifest.backup_id,
            manifest.manifest_hash,
            tuple(item.target for item in manifest.items),
        ) != (
            authorization.host_id,
            authorization.backup_id,
            authorization.manifest_hash,
            authorization.targets,
        ):
            raise AdapterError("restore_binding_mismatch", "restore manifest changed identity")
