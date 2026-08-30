from __future__ import annotations

import re
import shlex
import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
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
    decode_remote_retention_request,
    decode_remote_retention_result,
    encode_remote_retention_request,
    encode_remote_retention_result,
)
from .ssh_remote_staging import REMOTE_USER_STAGING_ROOT, RemoteUserStagingRunner
from .backup import _atomic_write


_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class RemoteRetentionRootInvoker(Protocol):
    def invoke(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None: ...


class RemoteRetentionAttemptStore:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe remote retention attempt root")

    def save(self, request: RemoteRetentionRequest) -> RemoteRetentionRequest:
        self._prepare()
        path = self._path(request.request_id, ".json")
        if path.exists() or path.is_symlink():
            current = self.load(request.request_id)
            if current != request:
                raise AdapterError("remote_retention_attempt_collision", "attempt identity was reused")
            return current
        _atomic_write(path, encode_remote_retention_request(request), 0o600)
        return self.load(request.request_id)

    def load(self, request_id: str) -> RemoteRetentionRequest:
        if not self.root.exists() and not self.root.is_symlink():
            raise AdapterError("remote_retention_attempt_not_found", "attempt is missing")
        self._root()
        path = self._path(request_id, ".json")
        self._file(path)
        content = path.read_bytes()
        try:
            value = json.loads(content.decode("utf-8"))
            digest = value["request_hash"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise AdapterError("invalid_remote_retention_attempt", "attempt is malformed") from error
        if not isinstance(digest, str):
            raise AdapterError("invalid_remote_retention_attempt", "attempt hash is invalid")
        return decode_remote_retention_request(content, expected_hash=digest, now=None)

    def mark_cleaned(self, request: RemoteRetentionRequest) -> None:
        self._root()
        path = self._path(request.request_id, ".cleaned")
        content = json.dumps({"request_hash": request.request_hash}, sort_keys=True,
                             separators=(",", ":")).encode()
        if path.exists() or path.is_symlink():
            self._file(path)
            if path.read_bytes() != content:
                raise AdapterError("invalid_remote_retention_cleanup", "cleanup marker changed")
            return
        _atomic_write(path, content, 0o600)

    def cleanup_pending(self, request: RemoteRetentionRequest) -> bool:
        path = self._path(request.request_id, ".cleaned")
        if not path.exists() and not path.is_symlink():
            return True
        self._file(path)
        expected = json.dumps({"request_hash": request.request_hash}, sort_keys=True,
                              separators=(",", ":")).encode()
        if path.read_bytes() != expected:
            raise AdapterError("invalid_remote_retention_cleanup", "cleanup marker changed")
        return False

    def _prepare(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self._root()

    def _root(self):
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_remote_retention_attempt", "attempt root is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError("unsafe_remote_retention_attempt", "attempt root metadata is unsafe")

    @staticmethod
    def _file(path):
        if path.is_symlink() or not path.is_file():
            raise AdapterError("unsafe_remote_retention_attempt", "attempt file is unsafe")
        metadata = path.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.getuid() or metadata.st_size > MAX_REMOTE_RETENTION_BYTES:
            raise AdapterError("unsafe_remote_retention_attempt", "attempt file metadata is unsafe")

    def _path(self, request_id, suffix):
        if not _IDENTIFIER.fullmatch(request_id):
            raise AdapterError("invalid_remote_retention_identity", "retention ID is invalid")
        return self.root / f"{request_id}{suffix}"


class RemoteRetentionResultStore:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        if self.root == Path("/") or self.root.is_symlink():
            raise ValueError("unsafe remote retention result root")

    def save(self, result: RemoteRetentionResult) -> RemoteRetentionResult:
        content = encode_remote_retention_result(result)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        path = self._path(result.request_id)
        if path.exists() or path.is_symlink():
            current = self.load(result.request_id)
            if current != result:
                raise AdapterError("remote_retention_result_collision", "result identity was reused")
            return current
        _atomic_write(path, content, 0o600)
        return self.load(result.request_id)

    def load(self, request_id: str) -> RemoteRetentionResult:
        path = self._path(request_id)
        if not self.root.exists() and not self.root.is_symlink():
            raise AdapterError("remote_retention_result_not_found", "result is missing")
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_remote_retention_result", "result root is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError("unsafe_remote_retention_result", "result root metadata is unsafe")
        if not path.exists() and not path.is_symlink():
            raise AdapterError("remote_retention_result_not_found", "result is missing")
        RemoteRetentionAttemptStore._file(path)
        return decode_remote_retention_result(path.read_bytes())

    def list_for_host(
        self, host_id: str, host_fingerprint: str
    ) -> tuple[RemoteRetentionResult, ...]:
        if not self.root.exists() and not self.root.is_symlink():
            return ()
        if self.root.is_symlink() or not self.root.is_dir():
            raise AdapterError("unsafe_remote_retention_result", "result root is unsafe")
        metadata = self.root.stat(follow_symlinks=False)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.getuid():
            raise AdapterError(
                "unsafe_remote_retention_result", "result root metadata is unsafe"
            )
        results = []
        for path in self.root.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise AdapterError("unsafe_remote_retention_result", "unexpected result entry")
            result = self.load(path.stem)
            if result.host_id == host_id:
                if result.host_fingerprint != host_fingerprint:
                    raise AdapterError("remote_retention_binding_mismatch", "host fingerprint changed")
                results.append(result)
        return tuple(sorted(results, key=lambda item: item.evaluated_at, reverse=True))

    def _path(self, request_id):
        if not _IDENTIFIER.fullmatch(request_id):
            raise AdapterError("invalid_remote_retention_identity", "retention ID is invalid")
        return self.root / f"{request_id}.json"


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
    attempts: RemoteRetentionAttemptStore | None = None
    results: RemoteRetentionResultStore | None = None
    clock: Callable[[], datetime] = utc_now

    def prune(
        self,
        request_id: str,
        host_id: str,
        host_fingerprint: str,
        cancellation: CancellationToken,
    ) -> RemoteRetentionResult:
        if self.attempts is not None:
            try:
                request = self.attempts.load(request_id)
                self._binding(request, host_id, host_fingerprint)
                return self._recover(request)
            except AdapterError as error:
                if error.code != "remote_retention_attempt_not_found":
                    raise
        now = self.clock()
        request = RemoteRetentionRequest(
            "1.0", REMOTE_RETENTION_PROTOCOL_VERSION, REMOTE_RETENTION_OPERATION,
            request_id, host_id, host_fingerprint, now, now,
            now + timedelta(minutes=5),
        ).with_hash()
        if self.attempts is not None:
            request = self.attempts.save(request)
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
                return self._persist_and_cleanup(request, self._read_result(base, request))
            except (AdapterError, OSError, ValueError):
                raise invocation_error
        return self._persist_and_cleanup(request, self._read_result(base, request))

    def _recover(self, request):
        if self.results is not None:
            try:
                result = self.results.load(request.request_id)
                self._result_binding(request, result)
                self._cleanup(request)
                return result
            except AdapterError as error:
                if error.code != "remote_retention_result_not_found":
                    raise
        base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
        return self._persist_and_cleanup(request, self._read_result(base, request))

    def _persist_and_cleanup(self, request, result):
        self._result_binding(request, result)
        saved = self.results.save(result) if self.results is not None else result
        self._cleanup(request)
        return saved

    def _cleanup(self, request):
        if self.attempts is None or self.results is None:
            return
        if not self.attempts.cleanup_pending(request):
            return
        base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
        try:
            self.staging.remove_private_tree(base)
            self.attempts.mark_cleaned(request)
        except (AdapterError, OSError, ValueError):
            pass

    def cleanup_pending(self, request_id):
        if self.attempts is None:
            return False
        return self.attempts.cleanup_pending(self.attempts.load(request_id))

    def retry_staging_cleanup(
        self, request_id: str, host_id: str, host_fingerprint: str,
        cancellation: CancellationToken,
    ) -> bool:
        if self.attempts is None or self.results is None:
            raise AdapterError("remote_retention_recovery_unavailable", "stores are required")
        request = self.attempts.load(request_id)
        self._binding(request, host_id, host_fingerprint)
        result = self.results.load(request_id)
        self._result_binding(request, result)
        if cancellation.cancelled:
            raise OperationCancelled("remote retention cleanup cancelled")
        if self.attempts.cleanup_pending(request):
            base = f"{REMOTE_USER_STAGING_ROOT}/{request.request_id}/{request.request_hash}"
            self.staging.remove_private_tree(base)
            self.attempts.mark_cleaned(request)
        return not self.attempts.cleanup_pending(request)

    @staticmethod
    def _binding(request, host_id, fingerprint):
        if request.host_id != host_id or request.host_fingerprint != fingerprint:
            raise AdapterError("remote_retention_binding_mismatch", "attempt host changed")

    @staticmethod
    def _result_binding(request, result):
        if (result.request_id, result.request_hash, result.host_id,
            result.host_fingerprint) != (request.request_id, request.request_hash,
            request.host_id, request.host_fingerprint):
            raise AdapterError("remote_retention_binding_mismatch", "result identity changed")

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
