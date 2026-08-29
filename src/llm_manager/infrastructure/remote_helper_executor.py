from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import BackupItem, BackupManifest, EncryptionInfo, utc_now

from .backup import BackupRestoreItem, MAX_ITEM_BYTES, _atomic_write, _within
from .remote_backup import SandboxRemoteRecoveryStore, encode_remote_receipt
from .remote_helper import decode_remote_request


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class RemoteRecoveryHelperExecutor:
    """Root-side executor for the single remote recovery-copy operation."""

    def __init__(
        self,
        staging_root: Path,
        backend: SandboxRemoteRecoveryStore,
        invoking_uid: int,
        *,
        clock=utc_now,
    ) -> None:
        self.staging_root = staging_root.absolute()
        self.backend = backend
        self.invoking_uid = invoking_uid
        self.clock = clock

    def execute(
        self,
        request_id: str,
        request_hash: str,
        cancellation: CancellationToken,
    ) -> bytes:
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_invocation", "remote helper identity is invalid")
        directory = self.staging_root / request_id / request_hash
        self._private_directory(self.staging_root, "staging root")
        self._private_directory(directory.parent, "request directory")
        self._private_directory(directory, "request hash directory")
        if not _within(directory.resolve(), self.staging_root.resolve()):
            raise AdapterError("unsafe_remote_staging", "remote helper staging escaped its root")
        request_path = directory / "request.json"
        content = self._private_file(request_path, 1024 * 1024)
        request = decode_remote_request(
            content, expected_hash=request_hash, now=self.clock()
        )
        if request.request_id != request_id or request.key_reference != self.backend.key_reference:
            raise AdapterError("remote_request_binding_mismatch", "remote request invocation or key changed")
        result_path = directory / "result.json"
        if result_path.exists() or result_path.is_symlink():
            raise AdapterError("remote_result_exists", "remote helper result is immutable")
        items_directory = directory / "items"
        self._private_directory(items_directory, "items directory")
        expected_names = {
            f"{index:04d}-{digest}.bin"
            for index, (_, digest) in enumerate(request.item_hashes)
            if digest is not None
        }
        if {path.name for path in items_directory.iterdir()} != expected_names:
            raise AdapterError("remote_staging_mismatch", "remote staged item set is incomplete or unexpected")
        restore_items: list[BackupRestoreItem] = []
        manifest_items: list[BackupItem] = []
        for index, (target, digest) in enumerate(request.item_hashes):
            if cancellation.cancelled:
                from llm_manager.application.errors import OperationCancelled
                raise OperationCancelled("remote helper execution cancelled")
            item_content = None
            existed = digest is not None
            if digest is not None:
                item_content = self._private_file(
                    items_directory / f"{index:04d}-{digest}.bin", MAX_ITEM_BYTES
                )
                if hashlib.sha256(item_content).hexdigest() != digest:
                    raise AdapterError("remote_staging_mismatch", "remote staged item hash changed")
            restore_items.append(BackupRestoreItem(target, existed, item_content, digest, None, None, None))
            manifest_items.append(BackupItem(target, existed, None, digest))
        manifest = BackupManifest(
            request.backup_id, "1.0", request.plan_id, request.change_set_hash,
            request.host_id, request.host_fingerprint, tuple(manifest_items),
            request.local_manifest_hash, "/local-authoritative-copy",
            EncryptionInfo(enabled=False), protected=request.protected,
            created_at=request.backup_created_at,
            retention_expires_at=request.retention_expires_at, complete=True,
        )
        receipt = self.backend.create(manifest, tuple(restore_items), cancellation)
        result = encode_remote_receipt(receipt)
        _atomic_write(result_path, result, 0o600)
        os.chown(result_path, self.invoking_uid, -1, follow_symlinks=False)
        return result

    def _private_directory(self, path: Path, label: str) -> None:
        if path.is_symlink() or not path.is_dir():
            raise AdapterError("unsafe_remote_staging", f"{label} is missing or unsafe")
        metadata = path.stat(follow_symlinks=False)
        if metadata.st_uid != self.invoking_uid or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise AdapterError("unsafe_remote_staging", f"{label} owner or mode is unsafe")

    def _private_file(self, path: Path, max_bytes: int) -> bytes:
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_remote_staging", "remote staged file is missing or unsafe")
        metadata = path.stat(follow_symlinks=False)
        if (
            metadata.st_uid != self.invoking_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > max_bytes
        ):
            raise AdapterError("unsafe_remote_staging", "remote staged file owner, mode, or size is unsafe")
        return path.read_bytes()
