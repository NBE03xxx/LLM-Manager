from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken

from .remote_user_apply import (
    MAX_REMOTE_USER_APPLY_REQUEST_BYTES,
    RemoteUserApplyResult,
    decode_remote_user_apply_request,
    decode_remote_user_apply_result,
    validate_remote_user_apply_result,
)
from .ssh_remote_staging import REMOTE_USER_STAGING_ROOT


class SshUserApplyStagingRunner(Protocol):
    """Fixed staging operations; deliberately excludes recovery sudo invocation."""

    def prepare_private_directory(self, relative_path: str) -> None: ...
    def upload_private_file(self, relative_path: str, content: bytes) -> None: ...
    def invoke_user_apply(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None: ...
    def read_private_file(self, relative_path: str, max_bytes: int) -> bytes: ...
    def remove_private_tree(self, relative_path: str) -> None: ...


@dataclass(slots=True)
class UserOnlySshApplyTransport:
    runner: SshUserApplyStagingRunner
    clock: Callable[[], datetime]

    def apply(
        self, request_content: bytes, payload: bytes, cancellation: CancellationToken
    ) -> RemoteUserApplyResult:
        request = self._request(request_content)
        if hashlib.sha256(payload).hexdigest() != request.after_hash:
            raise AdapterError("remote_user_apply_payload_mismatch", "payload does not match request")
        base = self._base(request.request_id, request.request_hash)
        _cancel(cancellation)
        self.runner.prepare_private_directory(base)
        _cancel(cancellation)
        self.runner.upload_private_file(
            f"{base}/items/0000-{request.after_hash}.bin", payload
        )
        _cancel(cancellation)
        # Request-last publication keeps partial payloads non-actionable.
        self.runner.upload_private_file(f"{base}/request.json", request_content)
        _cancel(cancellation)
        self.runner.invoke_user_apply(request.request_id, request.request_hash, cancellation)
        _cancel(cancellation)
        return self._read_bound_result(request, base)

    def read_result(
        self, request_content: bytes, cancellation: CancellationToken
    ) -> RemoteUserApplyResult:
        request = self._request(request_content)
        _cancel(cancellation)
        return self._read_bound_result(
            request, self._base(request.request_id, request.request_hash)
        )

    def cleanup(self, request_content: bytes) -> None:
        request = self._request(request_content)
        self.runner.remove_private_tree(self._base(request.request_id, request.request_hash))

    def _read_bound_result(self, request, base: str) -> RemoteUserApplyResult:
        result = decode_remote_user_apply_result(
            self.runner.read_private_file(
                f"{base}/result.json", MAX_REMOTE_USER_APPLY_REQUEST_BYTES
            )
        )
        validate_remote_user_apply_result(request, result)
        return result

    def _request(self, content: bytes):
        try:
            import json
            value = json.loads(content.decode("utf-8"))
            expected_hash = value["request_hash"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            raise AdapterError("invalid_remote_user_apply_request", "apply request is malformed") from error
        if not isinstance(expected_hash, str):
            raise AdapterError("invalid_remote_user_apply_request", "apply request hash is invalid")
        return decode_remote_user_apply_request(
            content, expected_hash=expected_hash, now=self.clock()
        )

    @staticmethod
    def _base(request_id: str, request_hash: str) -> str:
        return f"{REMOTE_USER_STAGING_ROOT}/{request_id}/{request_hash}"


def _cancel(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise OperationCancelled("SSH user apply staging cancelled")
