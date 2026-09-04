from __future__ import annotations

import hashlib
from dataclasses import dataclass

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import BackupRequest, CancellationToken, HostPort
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import BackupManifest, ValidationResult

from .backup import BackupRestoreItem, LocalBackupStore, MAX_ITEM_BYTES


@dataclass(slots=True)
class SshSnapshotLocalBackupStore:
    """Capture a stable remote snapshot into the local authoritative store."""

    local: LocalBackupStore
    host: HostPort
    allowed_targets: frozenset[str]

    def create(
        self, request: BackupRequest, cancellation: CancellationToken
    ) -> BackupManifest:
        _cancel(cancellation)
        observed = self.host.identify(cancellation)
        if (
            observed.kind is not HostKind.SSH
            or observed.host_id != request.host_id
            or not request.host_fingerprint
            or observed.fingerprint != request.host_fingerprint
        ):
            raise AdapterError("host_identity_changed", "SSH host identity changed before backup")
        targets = tuple(dict.fromkeys(change.target for change in request.change_set.changes))
        if not targets or set(targets) - self.allowed_targets:
            raise AdapterError("ssh_backup_target_not_allowed", "SSH backup target is not allowlisted")
        captured = tuple(self._capture(target, cancellation) for target in targets)
        return self.local.create_captured(request, captured, cancellation)

    def verify(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[ValidationResult, ...]:
        return self.local.verify(manifest, cancellation)

    def restore_items(
        self, manifest: BackupManifest, cancellation: CancellationToken
    ) -> tuple[BackupRestoreItem, ...]:
        return self.local.restore_items(manifest, cancellation)

    def _capture(
        self, target: str, cancellation: CancellationToken
    ) -> BackupRestoreItem:
        before = self.host.stat(target, cancellation)
        if before.path != target or before.is_symlink:
            raise AdapterError("unsafe_ssh_backup_target", "SSH target metadata is unsafe")
        if not before.exists:
            if before.sha256 is not None:
                raise AdapterError("unsafe_ssh_backup_target", "absent SSH target has a hash")
            after = self.host.stat(target, cancellation)
            if after != before:
                raise AdapterError("ssh_backup_snapshot_changed", "SSH target changed during backup")
            return BackupRestoreItem(target, False, None, None, None, None, None)
        if before.sha256 is None:
            raise AdapterError("unsafe_ssh_backup_target", "existing SSH target has no hash")
        _cancel(cancellation)
        content = self.host.read_file(target, MAX_ITEM_BYTES, cancellation)
        digest = hashlib.sha256(content).hexdigest()
        after = self.host.stat(target, cancellation)
        if after != before or digest != before.sha256:
            raise AdapterError("ssh_backup_snapshot_changed", "SSH target changed during backup")
        return BackupRestoreItem(
            target, True, content, digest, before.mode, before.uid, before.gid
        )


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("SSH backup capture cancelled")
