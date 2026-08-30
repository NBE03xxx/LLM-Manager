from __future__ import annotations

import os
import stat
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import BackupManifest

from .backup import (
    MAX_MANIFEST_BYTES, _atomic_write, _manifest_bytes,
    decode_backup_manifest_evidence,
)
from .backup_deletion import (
    BackupDeletionRequest, BackupDeletionResult, validate_backup_deletion_result,
)


class BackupManifestEvidenceStore:
    """Keep canonical manifest identity after backup contents are deleted."""

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe backup manifest evidence root")

    def save(
        self, deletion_request: BackupDeletionRequest, manifest: BackupManifest
    ) -> BackupManifest:
        self._request_binding(deletion_request, manifest)
        self._prepare()
        path = self._path(deletion_request.request_hash)
        content = _manifest_bytes(manifest)
        if len(content) > MAX_MANIFEST_BYTES:
            raise AdapterError("invalid_manifest_evidence", "evidence exceeds size limit")
        if path.exists() or path.is_symlink():
            current = self._load(deletion_request.request_hash)
            self._request_binding(deletion_request, current)
            if current != manifest:
                raise AdapterError("manifest_evidence_collision", "evidence identity was reused")
            return current
        _atomic_write(path, content, 0o600)
        current = self._load(deletion_request.request_hash)
        self._request_binding(deletion_request, current)
        return current

    def load(self, deletion_result: BackupDeletionResult) -> BackupManifest:
        validate_backup_deletion_result(deletion_result)
        manifest = self._load(deletion_result.request_hash)
        self._result_binding(deletion_result, manifest)
        return manifest

    def _load(self, request_hash: str) -> BackupManifest:
        self._root_metadata()
        path = self._path(request_hash)
        if path.is_symlink() or not path.is_file():
            raise AdapterError("manifest_evidence_not_found", "evidence is missing")
        metadata = path.stat(follow_symlinks=False)
        if (stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.getuid()
                or metadata.st_size > MAX_MANIFEST_BYTES):
            raise AdapterError("unsafe_manifest_evidence", "evidence metadata is unsafe")
        manifest = decode_backup_manifest_evidence(path.read_bytes())
        return manifest

    def _prepare(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._root_metadata()

    def _root_metadata(self) -> None:
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_manifest_evidence", "evidence root is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError("unsafe_manifest_evidence", "evidence root metadata is unsafe")

    def _path(self, request_hash: str) -> Path:
        if len(request_hash) != 64 or any(character not in "0123456789abcdef" for character in request_hash):
            raise AdapterError("invalid_manifest_evidence", "request hash is invalid")
        return self.root / f"{request_hash}.json"

    @staticmethod
    def _request_binding(deletion_request, manifest) -> None:
        if (deletion_request.with_hash().request_hash != deletion_request.request_hash
                or manifest.host_fingerprint is None or (
            manifest.backup_id, manifest.host_id, manifest.host_fingerprint,
            manifest.manifest_hash,
        ) != (
            deletion_request.backup_id, deletion_request.host_id,
            deletion_request.host_fingerprint, deletion_request.manifest_hash,
        )):
            raise AdapterError("manifest_evidence_binding_mismatch", "manifest changed identity")

    @staticmethod
    def _result_binding(deletion_result, manifest) -> None:
        if manifest.host_fingerprint is None or (
            manifest.backup_id, manifest.host_id, manifest.host_fingerprint,
            manifest.manifest_hash,
        ) != (
            deletion_result.backup_id, deletion_result.host_id,
            deletion_result.host_fingerprint, deletion_result.manifest_hash,
        ):
            raise AdapterError("manifest_evidence_binding_mismatch", "manifest changed identity")
