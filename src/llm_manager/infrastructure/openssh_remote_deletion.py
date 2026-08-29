from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Callable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.domain.models import BackupManifest, utc_now

from .openssh_staging import REMOTE_HELPER, RemoteHelperReadinessGate
from .process import SubprocessRunner
from .remote_backup import RemoteRecoveryCopyPort, _validate_receipt
from .remote_deletion import (
    MAX_REMOTE_DELETION_BYTES, RemoteDeletionOutcome,
    decode_remote_deletion_result, encode_remote_deletion_request,
    new_remote_deletion_request,
)
from .ssh_remote_staging import REMOTE_USER_STAGING_ROOT, RemoteUserStagingRunner


_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class RemoteDeletionRootInvoker(Protocol):
    def invoke(self, request_id: str, request_hash: str,
               cancellation: CancellationToken) -> None: ...


@dataclass(slots=True)
class OpenSshRemoteDeletionInvoker:
    alias: str
    runner: SubprocessRunner
    readiness_gate: RemoteHelperReadinessGate
    control_socket: str | None = None
    timeout_ms: int = 30_000

    def __post_init__(self):
        if self.alias.startswith("-") or not _ALIAS.fullmatch(self.alias):
            raise ValueError("invalid OpenSSH alias")
        if self.control_socket is not None and (
            not self.control_socket.startswith("/")
            or any(character in self.control_socket for character in "\r\n\x00")
        ):
            raise ValueError("invalid OpenSSH control socket")

    def invoke(self, request_id, request_hash, cancellation):
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_deletion_identity", "deletion identity is invalid")
        if cancellation.cancelled:
            raise OperationCancelled("remote deletion cancelled")
        self.readiness_gate.assert_ready(cancellation)
        socket = ("-S", self.control_socket) if self.control_socket else ()
        command = shlex.join(("sudo", "-n", "--", REMOTE_HELPER,
                              "invoke-deletion", request_id, request_hash))
        result = self.runner.run(CommandRequest(
            ("ssh", *socket, "-o", "BatchMode=yes", "--", self.alias, command),
            self.timeout_ms, "ssh.remote-deletion.invoke",
        ), cancellation)
        if result.timed_out:
            raise AdapterError("remote_deletion_timeout", "remote deletion timed out")
        if result.exit_code != 0:
            raise AdapterError("remote_deletion_failed", "remote deletion helper failed")


@dataclass(slots=True)
class OpenSshRemoteDeletionPort:
    staging: RemoteUserStagingRunner
    invoker: RemoteDeletionRootInvoker
    receipts: RemoteRecoveryCopyPort
    request_id_factory: Callable[[BackupManifest], str]
    clock: Callable = utc_now

    def delete(self, manifest: BackupManifest, cancellation: CancellationToken) -> None:
        if cancellation.cancelled:
            raise OperationCancelled("remote deletion cancelled")
        receipt = self.receipts.load(manifest, cancellation)
        _validate_receipt(manifest, receipt)
        request = new_remote_deletion_request(
            self.request_id_factory(manifest), manifest, receipt, now=self.clock()
        )
        base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
        self.staging.prepare_private_directory(base)
        self.staging.upload_private_file(
            f"{base}/request.json", encode_remote_deletion_request(request)
        )
        if cancellation.cancelled:
            raise OperationCancelled("remote deletion cancelled")
        invocation_error = None
        try:
            self.invoker.invoke(request.request_id, request.request_hash, cancellation)
        except OperationCancelled:
            raise
        except (AdapterError, OSError, ValueError) as error:
            invocation_error = error
        try:
            result = decode_remote_deletion_result(self.staging.read_private_file(
                f"{base}/result.json", MAX_REMOTE_DELETION_BYTES
            ))
        except (AdapterError, OSError, ValueError):
            if invocation_error is not None:
                raise invocation_error
            raise
        expected = (
            request.request_id, request.request_hash, request.backup_id,
            request.host_id, request.host_fingerprint, request.manifest_hash,
            request.remote_receipt_hash, request.key_reference,
        )
        actual = (
            result.request_id, result.request_hash, result.backup_id,
            result.host_id, result.host_fingerprint, result.manifest_hash,
            result.remote_receipt_hash, result.key_reference,
        )
        if actual != expected:
            raise AdapterError("remote_deletion_binding_mismatch", "deletion result changed identity")
        if result.outcome in {RemoteDeletionOutcome.DELETED,
                              RemoteDeletionOutcome.ALREADY_ABSENT}:
            return
        if result.outcome is RemoteDeletionOutcome.UNKNOWN:
            raise OSError(result.error_code or "remote deletion state unknown")
        raise AdapterError(result.error_code or "remote_deletion_failed",
                           "remote deletion was rejected")
