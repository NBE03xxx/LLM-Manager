from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from llm_manager.application.errors import AdapterError
from llm_manager.application.ports import CancellationToken, CommandRequest

from .process import SubprocessRunner


REMOTE_HELPER = "/usr/bin/llm-manager-remote-helper"
_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class InteractiveRemoteHelperInvoker(Protocol):
    """Invoke the fixed helper using passwordless or external-terminal sudo flow."""

    def invoke(
        self,
        alias: str,
        control_socket: str | None,
        request_id: str,
        request_hash: str,
        cancellation: CancellationToken,
    ) -> None: ...


class RemoteHelperReadinessGate(Protocol):
    """Read-only compatibility check performed before remote staging and invoke."""

    def assert_ready(self, cancellation: CancellationToken) -> None: ...


@dataclass(slots=True)
class OpenSshUserStagingRunner:
    alias: str
    runner: SubprocessRunner
    invoker: InteractiveRemoteHelperInvoker
    runtime_root: Path
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
        if self.timeout_ms <= 0:
            raise ValueError("OpenSSH staging timeout must be positive")
        self.runtime_root = self.runtime_root.absolute()
        if self.runtime_root == Path("/") or self.runtime_root.is_symlink():
            raise ValueError("unsafe OpenSSH staging runtime root")

    def prepare_private_directory(self, relative_path: str) -> None:
        path = _relative_path(relative_path)
        self.readiness_gate.assert_ready(CancellationToken())
        self._ssh((REMOTE_HELPER, "user-stage-prepare", path), "ssh.staging.prepare")

    def upload_private_file(self, relative_path: str, content: bytes) -> None:
        path = _relative_path(relative_path)
        self._prepare_runtime()
        with tempfile.TemporaryDirectory(prefix="upload-", dir=self.runtime_root) as directory:
            source = Path(directory) / "content"
            source.write_bytes(content)
            os.chmod(source, 0o600)
            self._run(
                ("scp", *self._socket_args(), "-q", "-p", "--", str(source), f"{self.alias}:{path}"),
                "ssh.staging.upload",
            )

    def invoke_recovery_helper(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None:
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_invocation", "remote helper identity is invalid")
        self.readiness_gate.assert_ready(cancellation)
        self.invoker.invoke(
            self.alias, self.control_socket, request_id, request_hash, cancellation
        )

    def invoke_user_apply(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None:
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_invocation", "remote helper identity is invalid")
        if cancellation.cancelled:
            from llm_manager.application.errors import OperationCancelled
            raise OperationCancelled("remote user apply cancelled")
        self.readiness_gate.assert_ready(cancellation)
        self._ssh(
            (REMOTE_HELPER, "user-apply", request_id, request_hash),
            "ssh.user_apply.invoke",
        )

    def invoke_user_rollback(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> None:
        if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_invocation", "remote helper identity is invalid")
        if cancellation.cancelled:
            from llm_manager.application.errors import OperationCancelled
            raise OperationCancelled("remote user rollback cancelled")
        self.readiness_gate.assert_ready(cancellation)
        self._ssh(
            (REMOTE_HELPER, "user-rollback", request_id, request_hash),
            "ssh.user_rollback.invoke",
        )

    def read_private_file(self, relative_path: str, max_bytes: int) -> bytes:
        path = _relative_path(relative_path)
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._prepare_runtime()
        with tempfile.TemporaryDirectory(prefix="download-", dir=self.runtime_root) as directory:
            destination = Path(directory) / "content"
            self._run(
                ("scp", *self._socket_args(), "-q", "--", f"{self.alias}:{path}", str(destination)),
                "ssh.staging.download",
            )
            if destination.is_symlink() or not destination.is_file():
                raise AdapterError("remote_staging_read_failed", "downloaded remote result is missing or unsafe")
            if destination.stat().st_size > max_bytes:
                raise AdapterError("remote_result_too_large", "remote staging result exceeds its bound")
            return destination.read_bytes()

    def remove_private_tree(self, relative_path: str) -> None:
        path = _relative_path(relative_path)
        self._ssh((REMOTE_HELPER, "user-stage-remove", path), "ssh.staging.cleanup")

    def _ssh(self, remote_argv: tuple[str, ...], correlation_id: str) -> None:
        import shlex
        remote_command = shlex.join(remote_argv)
        self._run(
            ("ssh", *self._socket_args(), "-o", "BatchMode=yes", "--", self.alias, remote_command),
            correlation_id,
        )

    def _run(self, argv: tuple[str, ...], correlation_id: str) -> None:
        result = self.runner.run(
            CommandRequest(argv, self.timeout_ms, correlation_id), CancellationToken()
        )
        if result.timed_out:
            raise AdapterError("remote_staging_timeout", "OpenSSH staging operation timed out")
        if result.exit_code != 0:
            raise AdapterError("remote_staging_failed", "OpenSSH staging operation failed")

    def _socket_args(self) -> tuple[str, ...]:
        return ("-S", self.control_socket) if self.control_socket else ()

    def _prepare_runtime(self) -> None:
        self.runtime_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.runtime_root, 0o700)
        if self.runtime_root.is_symlink() or not self.runtime_root.is_dir():
            raise AdapterError("unsafe_staging_runtime", "OpenSSH staging runtime is unsafe")


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or any(character in value for character in "\r\n\x00")
        or not value.startswith(".local/state/llm-manager/remote-helper/")
    ):
        raise AdapterError("invalid_remote_staging_path", "remote staging path is outside its fixed root")
    return path.as_posix()
