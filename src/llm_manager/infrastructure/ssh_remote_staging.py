from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Callable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken

from .backup import BackupRestoreItem, MAX_ITEM_BYTES
from .remote_helper import decode_remote_request


REMOTE_USER_STAGING_ROOT = ".local/state/llm-manager/remote-helper"
MAX_REMOTE_RECEIPT_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class RemoteUserStagingRunner(Protocol):
    """Structured SSH operations implemented without accepting shell text."""

    def prepare_private_directory(self, relative_path: str) -> None: ...
    def upload_private_file(self, relative_path: str, content: bytes) -> None: ...
    def invoke_recovery_helper(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None: ...
    def read_private_file(self, relative_path: str, max_bytes: int) -> bytes: ...
    def remove_private_tree(self, relative_path: str) -> None: ...


@dataclass(slots=True)
class UserOnlySshRecoveryTransport:
    """Concrete user-only staging sequence for the remote recovery helper Port."""

    runner: RemoteUserStagingRunner
    clock: Callable[[], datetime]

    def __init__(self, runner: RemoteUserStagingRunner, *, clock: Callable[[], datetime]) -> None:
        self.runner = runner
        self.clock = clock

    def create_recovery_copy(
        self,
        request_content: bytes,
        staged_items: tuple[BackupRestoreItem, ...],
        cancellation: CancellationToken,
    ) -> bytes:
        request = self._request(request_content)
        base = _operation_path(request.request_id, request.request_hash)
        _cancel(cancellation)
        self.runner.prepare_private_directory(base)
        try:
            for index, item in enumerate(staged_items):
                _cancel(cancellation)
                if not item.existed:
                    continue
                if item.content is None or item.sha256 is None:
                    raise AdapterError("remote_staging_mismatch", "existing staged item has no content")
                if len(item.content) > MAX_ITEM_BYTES or hashlib.sha256(item.content).hexdigest() != item.sha256:
                    raise AdapterError("remote_staging_mismatch", "staged item size or hash is invalid")
                self.runner.upload_private_file(
                    f"{base}/items/{index:04d}-{item.sha256}.bin", item.content
                )
            _cancel(cancellation)
            # Request-last publication prevents the helper from observing a partial set.
            self.runner.upload_private_file(f"{base}/request.json", request_content)
            _cancel(cancellation)
            self.runner.invoke_recovery_helper(
                request.request_id, request.request_hash, cancellation
            )
            _cancel(cancellation)
            return self.runner.read_private_file(
                f"{base}/result.json", MAX_REMOTE_RECEIPT_BYTES
            )
        except (AdapterError, OperationCancelled, OSError, ValueError):
            raise

    def read_recovery_receipt(
        self,
        request_content: bytes,
        cancellation: CancellationToken,
    ) -> bytes:
        request = self._request(request_content)
        _cancel(cancellation)
        return self.runner.read_private_file(
            f"{_operation_path(request.request_id, request.request_hash)}/result.json",
            MAX_REMOTE_RECEIPT_BYTES,
        )

    def cleanup(self, request_content: bytes) -> None:
        """Explicit best-effort cleanup hook after the caller has persisted its receipt."""
        request = self._request(request_content)
        self.runner.remove_private_tree(_operation_path(request.request_id, request.request_hash))

    def _request(self, content: bytes):
        try:
            import json
            value = json.loads(content.decode("utf-8"))
            expected_hash = value["request_hash"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_remote_request", "remote staging request is malformed") from error
        if not isinstance(expected_hash, str):
            raise AdapterError("invalid_remote_request", "remote staging request hash is invalid")
        return decode_remote_request(content, expected_hash=expected_hash, now=self.clock())


@dataclass(frozen=True, slots=True)
class RemoteRecoveryResultCompletionProbe:
    """Poll only the immutable result path for an interactive sudo request."""

    runner: RemoteUserStagingRunner

    def completed(
        self,
        request_id: str,
        request_hash: str,
        cancellation: CancellationToken,
    ) -> bool:
        _cancel(cancellation)
        try:
            self.runner.read_private_file(
                f"{_operation_path(request_id, request_hash)}/result.json",
                MAX_REMOTE_RECEIPT_BYTES,
            )
        except AdapterError as error:
            if error.code == "remote_staging_failed":
                return False
            raise
        return True


def _operation_path(request_id: str, request_hash: str) -> str:
    if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
        raise AdapterError("invalid_remote_staging_path", "remote staging identity is unsafe")
    path = PurePosixPath(REMOTE_USER_STAGING_ROOT, request_id, request_hash)
    if path.is_absolute() or ".." in path.parts:
        raise AdapterError("invalid_remote_staging_path", "remote staging path is unsafe")
    return path.as_posix()


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("remote staging operation cancelled")
