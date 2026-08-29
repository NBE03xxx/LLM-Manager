from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from llm_manager.application.errors import AdapterError
from llm_manager.domain.models import utc_now

from .backup import MAX_ITEM_BYTES, _atomic_write, _fsync_directory, _within
from .helper_protocol import HelperOperation, HelperOperationKind, HelperRequest, encode_request, validate_request


class HelperStagingStore:
    """Stages content under fixed derived paths; request data never supplies a staging path."""

    def __init__(self, root: Path, owner_uid: int | None = None) -> None:
        self.root = root.absolute()
        self.owner_uid = os.getuid() if owner_uid is None else owner_uid

    def stage(self, request: HelperRequest, operation_id: str, content: bytes) -> Path:
        validate_request(request, request.request_hash, now=utc_now())
        operation = _operation(request, operation_id)
        if operation.kind not in {HelperOperationKind.ATOMIC_REPLACE, HelperOperationKind.RESTORE_FILE}:
            raise AdapterError("invalid_staging_operation", "operation does not accept staged content")
        if len(content) > MAX_ITEM_BYTES:
            raise AdapterError("item_too_large", "staged content exceeds 16 MiB")
        digest = hashlib.sha256(content).hexdigest()
        if digest != operation.staged_content_hash:
            raise AdapterError("staged_hash_mismatch", "content does not match the declared staged hash")
        directory = self._operation_directory(request.operation_id, create=True)
        path = directory / f"{operation.operation_id}.content"
        if path.exists() or path.is_symlink():
            raise AdapterError("staged_content_exists", "staged content is immutable once written")
        _atomic_write(path, content, 0o600)
        return path

    def stage_request(self, request: HelperRequest) -> Path:
        validate_request(request, request.request_hash, now=utc_now())
        directory = self._operation_directory(request.operation_id, create=True)
        path = directory / "request.json"
        if path.exists() or path.is_symlink():
            raise AdapterError("staged_request_exists", "helper request is immutable once written")
        _atomic_write(path, encode_request(request), 0o600)
        return path

    def verify(self, request: HelperRequest, operation: HelperOperation) -> bytes:
        validate_request(request, request.request_hash, now=utc_now())
        if operation.kind not in {HelperOperationKind.ATOMIC_REPLACE, HelperOperationKind.RESTORE_FILE}:
            raise AdapterError("invalid_staging_operation", "operation does not accept staged content")
        directory = self._operation_directory(request.operation_id, create=False)
        path = directory / f"{operation.operation_id}.content"
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_staging", "staged content is missing or not a regular file")
        file_stat = path.stat(follow_symlinks=False)
        if file_stat.st_uid != self.owner_uid or stat.S_IMODE(file_stat.st_mode) != 0o600:
            raise AdapterError("unsafe_staging", "staged content owner or mode is unsafe")
        if file_stat.st_size > MAX_ITEM_BYTES:
            raise AdapterError("item_too_large", "staged content exceeds 16 MiB")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != operation.staged_content_hash:
            raise AdapterError("staged_hash_mismatch", "staged content changed after request creation")
        return content

    def cleanup(self, operation_id: str) -> None:
        directory = self._operation_directory(operation_id, create=False)
        entries = tuple(directory.iterdir())
        for path in entries:
            if path.is_symlink() or not path.is_file() or (path.suffix != ".content" and path.name != "request.json"):
                raise AdapterError("unsafe_staging", "unexpected staging entry prevents cleanup")
        for path in entries:
            path.unlink()
        directory.rmdir()
        _fsync_directory(self.root)

    def _operation_directory(self, operation_id: str, *, create: bool) -> Path:
        if not operation_id or Path(operation_id).name != operation_id:
            raise AdapterError("invalid_operation_id", "staging operation ID must be a path component")
        self._validate_root(create=create)
        directory = self.root / operation_id
        if create:
            if not directory.exists():
                directory.mkdir(mode=0o700)
                os.chmod(directory, 0o700)
        if directory.is_symlink() or not directory.is_dir():
            raise AdapterError("unsafe_staging", "operation staging directory is unsafe")
        directory_stat = directory.stat(follow_symlinks=False)
        if directory_stat.st_uid != self.owner_uid or stat.S_IMODE(directory_stat.st_mode) != 0o700:
            raise AdapterError("unsafe_staging", "operation staging directory owner or mode is unsafe")
        if not _within(directory.resolve(), self.root.resolve()):
            raise AdapterError("unsafe_staging", "operation staging directory escaped its root")
        return directory

    def _validate_root(self, *, create: bool) -> None:
        if create and not self.root.exists():
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.root, 0o700)
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_staging", "staging root is unsafe")
        root_stat = self.root.stat(follow_symlinks=False)
        if root_stat.st_uid != self.owner_uid or stat.S_IMODE(root_stat.st_mode) != 0o700:
            raise AdapterError("unsafe_staging", "staging root owner or mode is unsafe")


def _operation(request: HelperRequest, operation_id: str) -> HelperOperation:
    matches = [item for item in request.operations if item.operation_id == operation_id]
    if len(matches) != 1:
        raise AdapterError("operation_not_found", "staging operation is not uniquely declared")
    return matches[0]
