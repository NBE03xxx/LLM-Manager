from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken

from .remote_user_rollback import (
    MAX_REMOTE_USER_ROLLBACK_REQUEST_BYTES,
    RemoteUserRollbackRequest,
    RemoteUserRollbackResult,
    decode_remote_user_rollback_request,
    decode_remote_user_rollback_result,
    validate_remote_user_rollback_result,
)
from .ssh_remote_staging import REMOTE_USER_STAGING_ROOT


class SshUserRollbackStagingRunner(Protocol):
    def prepare_private_directory(self, relative_path: str) -> None: ...
    def upload_private_file(self, relative_path: str, content: bytes) -> None: ...
    def invoke_user_rollback(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None: ...
    def read_private_file(self, relative_path: str, max_bytes: int) -> bytes: ...
    def remove_private_tree(self, relative_path: str) -> None: ...


@dataclass(slots=True)
class UserOnlySshRollbackTransport:
    runner: SshUserRollbackStagingRunner
    clock: Callable[[], datetime]

    def rollback(
        self,
        request_content: bytes,
        restore_content: bytes | None,
        cancellation: CancellationToken,
    ) -> RemoteUserRollbackResult:
        request = self._request(request_content)
        if request.restore_existed != (restore_content is not None):
            raise AdapterError("remote_user_rollback_payload_mismatch", "rollback payload presence differs")
        if restore_content is not None and hashlib.sha256(restore_content).hexdigest() != request.restore_hash:
            raise AdapterError("remote_user_rollback_payload_mismatch", "rollback payload hash differs")
        base = self._base(request)
        _cancel(cancellation)
        self.runner.prepare_private_directory(base)
        if restore_content is not None:
            _cancel(cancellation)
            self.runner.upload_private_file(
                f"{base}/items/0000-{request.restore_hash}.bin", restore_content
            )
        _cancel(cancellation)
        self.runner.upload_private_file(f"{base}/request.json", request_content)
        _cancel(cancellation)
        self.runner.invoke_user_rollback(request.request_id, request.request_hash, cancellation)
        _cancel(cancellation)
        return self._read(request, base)

    def read_result(
        self, request_content: bytes, cancellation: CancellationToken
    ) -> RemoteUserRollbackResult:
        request = self._request(request_content)
        _cancel(cancellation)
        return self._read(request, self._base(request))

    def cleanup(self, request_content: bytes) -> None:
        request = self._request(request_content)
        self.runner.remove_private_tree(self._base(request))

    def _request(self, content: bytes) -> RemoteUserRollbackRequest:
        try:
            value = json.loads(content.decode("utf-8"))
            expected_hash = value["request_hash"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_remote_user_rollback_request", "rollback request is malformed") from error
        if not isinstance(expected_hash, str):
            raise AdapterError("invalid_remote_user_rollback_request", "rollback request hash is invalid")
        return decode_remote_user_rollback_request(
            content, expected_hash=expected_hash, now=self.clock()
        )

    def _read(self, request: RemoteUserRollbackRequest, base: str) -> RemoteUserRollbackResult:
        result = decode_remote_user_rollback_result(
            self.runner.read_private_file(
                f"{base}/result.json", MAX_REMOTE_USER_ROLLBACK_REQUEST_BYTES
            )
        )
        validate_remote_user_rollback_result(request, result)
        return result

    @staticmethod
    def _base(request: RemoteUserRollbackRequest) -> str:
        return f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("SSH user rollback staging cancelled")
