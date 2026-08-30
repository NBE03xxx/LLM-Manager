from __future__ import annotations

import re
import shlex
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.domain.models import BackupManifest, utc_now

from .openssh_staging import REMOTE_HELPER, RemoteHelperReadinessGate
from .process import SubprocessRunner
from .remote_backup import RemoteRecoveryCopyPort, _validate_receipt
from .remote_deletion import (
    MAX_REMOTE_DELETION_BYTES, RemoteDeletionOutcome,
    RemoteDeletionRequest,
    decode_remote_deletion_request,
    decode_remote_deletion_result, encode_remote_deletion_request,
    new_remote_deletion_request,
)
from .backup import _atomic_write
from .ssh_remote_staging import REMOTE_USER_STAGING_ROOT, RemoteUserStagingRunner


_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class RemoteDeletionRootInvoker(Protocol):
    def invoke(self, request_id: str, request_hash: str,
               cancellation: CancellationToken) -> None: ...


class RemoteDeletionAttemptStore:
    """Persist remote request identity before mutation and cleanup completion after it."""

    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe remote deletion attempt root")

    def save(self, request: RemoteDeletionRequest) -> RemoteDeletionRequest:
        self._prepare_root()
        path = self._path(request.request_id)
        content = encode_remote_deletion_request(request)
        if path.exists() or path.is_symlink():
            existing = self.load(request.request_id)
            if existing != request:
                raise AdapterError("remote_deletion_attempt_collision", "attempt identity was reused")
            return existing
        _atomic_write(path, content, 0o600)
        return self.load(request.request_id)

    def load(self, request_id: str) -> RemoteDeletionRequest:
        path = self._path(request_id)
        if not self.root.exists() and not self.root.is_symlink():
            raise AdapterError("remote_deletion_attempt_not_found", "attempt is missing")
        self._root_metadata()
        if not path.exists() and not path.is_symlink():
            raise AdapterError("remote_deletion_attempt_not_found", "attempt is missing")
        self._private_file(path)
        content = path.read_bytes()
        try:
            value = json.loads(content.decode("utf-8"))
            expected_hash = value["request_hash"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise AdapterError("invalid_remote_deletion_attempt", "attempt is malformed") from error
        if not isinstance(expected_hash, str):
            raise AdapterError("invalid_remote_deletion_attempt", "attempt hash is invalid")
        return decode_remote_deletion_request(content, expected_hash=expected_hash, now=None)

    def mark_cleaned(self, request: RemoteDeletionRequest) -> None:
        self._root_metadata()
        path = self._cleaned_path(request.request_id)
        content = json.dumps(
            {"request_hash": request.request_hash}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if path.exists() or path.is_symlink():
            self._private_file(path)
            if path.read_bytes() != content:
                raise AdapterError("invalid_remote_deletion_cleanup", "cleanup marker changed")
            return
        _atomic_write(path, content, 0o600)

    def cleanup_pending(self, request: RemoteDeletionRequest) -> bool:
        path = self._cleaned_path(request.request_id)
        if not path.exists() and not path.is_symlink():
            return True
        self._private_file(path)
        expected = json.dumps(
            {"request_hash": request.request_hash}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if path.read_bytes() != expected:
            raise AdapterError("invalid_remote_deletion_cleanup", "cleanup marker changed")
        return False

    def _prepare_root(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._root_metadata()

    def _root_metadata(self):
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_remote_deletion_attempt", "attempt root is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError("unsafe_remote_deletion_attempt", "attempt root metadata is unsafe")

    @staticmethod
    def _private_file(path):
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_remote_deletion_attempt", "attempt file is unsafe")
        metadata = path.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.getuid() or metadata.st_size > MAX_REMOTE_DELETION_BYTES:
            raise AdapterError("unsafe_remote_deletion_attempt", "attempt file metadata is unsafe")

    def _path(self, request_id):
        if not _IDENTIFIER.fullmatch(request_id):
            raise AdapterError("invalid_remote_deletion_identity", "attempt ID is invalid")
        return self.root / f"{request_id}.json"

    def _cleaned_path(self, request_id):
        if not _IDENTIFIER.fullmatch(request_id):
            raise AdapterError("invalid_remote_deletion_identity", "attempt ID is invalid")
        return self.root / f"{request_id}.cleaned"


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
    attempts: RemoteDeletionAttemptStore
    request_id_factory: Callable[[BackupManifest], str]
    clock: Callable = utc_now

    def delete(self, manifest: BackupManifest, cancellation: CancellationToken) -> None:
        if cancellation.cancelled:
            raise OperationCancelled("remote deletion cancelled")
        request_id = self.request_id_factory(manifest)
        try:
            request = self.attempts.load(request_id)
            self._validate_manifest(request, manifest)
            self._accept_result(request, self._read_result(request))
            return
        except AdapterError as error:
            if error.code != "remote_deletion_attempt_not_found":
                raise
        receipt = self.receipts.load(manifest, cancellation)
        _validate_receipt(manifest, receipt)
        request = self.attempts.save(new_remote_deletion_request(
            request_id, manifest, receipt, now=self.clock()
        ))
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
            result = self._read_result(request)
        except (AdapterError, OSError, ValueError) as read_error:
            if invocation_error is not None:
                raise invocation_error
            if isinstance(read_error, AdapterError) and read_error.code in {
                "remote_staging_read_failed", "remote_staging_timeout",
                "remote_result_too_large",
            }:
                raise OSError("remote deletion result is not observable") from read_error
            raise
        self._accept_result(request, result)

    def cleanup(self, deletion_request, manifest, cancellation):
        request = self.attempts.load(self.request_id_factory(manifest))
        self._validate_manifest(request, manifest)
        self._read_result(request)
        if cancellation.cancelled:
            raise OperationCancelled("remote deletion cleanup cancelled")
        base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
        self.staging.remove_private_tree(base)
        self.attempts.mark_cleaned(request)

    def cleanup_pending(self, deletion_request, manifest):
        request = self.attempts.load(self.request_id_factory(manifest))
        self._validate_manifest(request, manifest)
        return self.attempts.cleanup_pending(request)

    def _read_result(self, request):
        base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
        result = decode_remote_deletion_result(self.staging.read_private_file(
            f"{base}/result.json", MAX_REMOTE_DELETION_BYTES
        ))
        self._validate_result_binding(request, result)
        return result

    @staticmethod
    def _validate_manifest(request, manifest):
        if (request.backup_id, request.host_id, request.host_fingerprint,
            request.manifest_hash) != (manifest.backup_id, manifest.host_id,
            manifest.host_fingerprint, manifest.manifest_hash):
            raise AdapterError("remote_deletion_binding_mismatch", "attempt changed manifest")

    @staticmethod
    def _accept_result(request, result):
        OpenSshRemoteDeletionPort._validate_result_binding(request, result)
        if result.outcome in {RemoteDeletionOutcome.DELETED,
                              RemoteDeletionOutcome.ALREADY_ABSENT}:
            return
        if result.outcome is RemoteDeletionOutcome.UNKNOWN:
            raise OSError(result.error_code or "remote deletion state unknown")
        raise AdapterError(result.error_code or "remote_deletion_failed",
                           "remote deletion was rejected")

    @staticmethod
    def _validate_result_binding(request, result):
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
