from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.domain.models import utc_now

from .openssh_staging import REMOTE_HELPER, RemoteHelperReadinessGate
from .process import SubprocessRunner
from .remote_retention import (
    MAX_REMOTE_RETENTION_BYTES,
    REMOTE_RETENTION_OPERATION,
    REMOTE_RETENTION_PROTOCOL_VERSION,
    RemoteRetentionRequest,
    RemoteRetentionResult,
    decode_remote_retention_result,
    encode_remote_retention_request,
)
from .ssh_remote_staging import REMOTE_USER_STAGING_ROOT, RemoteUserStagingRunner


_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class RemoteRetentionRootInvoker(Protocol):
    def invoke(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None: ...


@dataclass(slots=True)
class OpenSshRemoteRetentionInvoker:
    alias: str
    runner: SubprocessRunner
    readiness_gate: RemoteHelperReadinessGate
    control_socket: str | None = None
    timeout_ms: int = 30_000

    def __post_init__(self) -> None:
        if self.alias.startswith("-") or not _ALIAS.fullmatch(self.alias):
            raise ValueError("invalid OpenSSH alias")
        if self.control_socket is not None and (
            not self.control_socket.startswith("/")
            or any(character in self.control_socket for character in "\r\n\x00")
        ):
            raise ValueError("invalid OpenSSH control socket")

    def invoke(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None:
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_retention_identity", "retention identity is invalid")
        if cancellation.cancelled:
            raise OperationCancelled("remote retention cancelled")
        self.readiness_gate.assert_ready(cancellation)
        socket = ("-S", self.control_socket) if self.control_socket else ()
        command = shlex.join(
            ("sudo", "-n", "--", REMOTE_HELPER, "invoke-retention", request_id, request_hash)
        )
        result = self.runner.run(
            CommandRequest(
                ("ssh", *socket, "-o", "BatchMode=yes", "--", self.alias, command),
                self.timeout_ms,
                "ssh.remote-retention.invoke",
            ),
            cancellation,
        )
        if result.timed_out:
            raise AdapterError("remote_retention_timeout", "remote retention timed out")
        if result.exit_code != 0:
            raise AdapterError("remote_retention_failed", "remote retention helper failed")


@dataclass(slots=True)
class OpenSshRemoteRetentionPort:
    staging: RemoteUserStagingRunner
    invoker: RemoteRetentionRootInvoker
    clock: Callable[[], datetime] = utc_now

    def prune(
        self,
        request_id: str,
        host_id: str,
        host_fingerprint: str,
        cancellation: CancellationToken,
    ) -> RemoteRetentionResult:
        now = self.clock()
        request = RemoteRetentionRequest(
            "1.0", REMOTE_RETENTION_PROTOCOL_VERSION, REMOTE_RETENTION_OPERATION,
            request_id, host_id, host_fingerprint, now, now,
            now + timedelta(minutes=5),
        ).with_hash()
        content = encode_remote_retention_request(request)
        base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
        if cancellation.cancelled:
            raise OperationCancelled("remote retention cancelled")
        self.staging.prepare_private_directory(base)
        self.staging.upload_private_file(f"{base}/request.json", content)
        if cancellation.cancelled:
            raise OperationCancelled("remote retention cancelled")
        try:
            self.invoker.invoke(request.request_id, request.request_hash, cancellation)
        except OperationCancelled:
            raise
        except (AdapterError, OSError, ValueError) as invocation_error:
            try:
                return self._read_result(base, request)
            except (AdapterError, OSError, ValueError):
                raise invocation_error
        return self._read_result(base, request)

    def _read_result(
        self, base: str, request: RemoteRetentionRequest
    ) -> RemoteRetentionResult:
        result = decode_remote_retention_result(
            self.staging.read_private_file(
                f"{base}/result.json", MAX_REMOTE_RETENTION_BYTES
            )
        )
        if (
            result.request_id != request.request_id
            or result.request_hash != request.request_hash
            or result.host_id != request.host_id
            or result.host_fingerprint != request.host_fingerprint
        ):
            raise AdapterError(
                "remote_retention_binding_mismatch", "retention result does not match request"
            )
        return result
