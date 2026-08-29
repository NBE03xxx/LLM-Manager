from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest, CommandResult, FileStat
from llm_manager.domain.enums import HostKind
from llm_manager.domain.models import HostCapabilities, HostInfo
from llm_manager.infrastructure.process import SubprocessRunner

_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_READ_COMMANDS = frozenset(
    {"cat", "curl", "df", "lscpu", "lspci", "nvidia-smi", "rocm-smi", "ollama", "opencode", "stat", "systemctl", "uname"}
)


@dataclass(slots=True)
class OpenSshHostAdapter:
    alias: str
    runner: SubprocessRunner
    display_name: str | None = None
    timeout_ms: int = 10_000
    allowed_remote_executables: frozenset[str] = frozenset()
    verified_fingerprint: str | None = None
    control_socket: str | None = None

    def __post_init__(self) -> None:
        if self.alias.startswith("-") or not _ALIAS.fullmatch(self.alias):
            raise ValueError("invalid OpenSSH host alias")
        for executable in self.allowed_remote_executables:
            if not executable.startswith("/") or any(char in executable for char in "\n\r\x00"):
                raise ValueError("additional remote executable must be a safe absolute path")
        if self.verified_fingerprint is not None and not re.fullmatch(
            r"SHA256:[A-Za-z0-9+/]{43}", self.verified_fingerprint
        ):
            raise ValueError("verified_fingerprint must be an OpenSSH SHA256 fingerprint")
        if self.control_socket is not None and (
            not self.control_socket.startswith("/") or any(char in self.control_socket for char in "\n\r\x00")
        ):
            raise ValueError("control_socket must be a safe absolute path")

    def identify(self, cancellation: CancellationToken) -> HostInfo:
        result = self.execute_readonly(
            CommandRequest(("uname", "-n"), self.timeout_ms, "ssh.identify"), cancellation
        )
        if result.timed_out:
            raise AdapterError("timeout", "SSH identity probe timed out")
        if result.exit_code != 0:
            raise AdapterError("authentication_failed", "SSH identity probe failed")
        hostname = result.stdout.strip()
        if not hostname:
            raise AdapterError("parse_failed", "SSH identity returned an empty hostname")
        return HostInfo(
            host_id=f"ssh:{self.alias}",
            kind=HostKind.SSH,
            display_name=self.display_name or self.alias,
            capabilities=self.capabilities(),
            hostname=hostname,
            ssh_alias=self.alias,
            # An alias is not an identity proof. Only a fingerprint verified by
            # the system OpenSSH/known_hosts boundary may be injected here.
            fingerprint=self.verified_fingerprint,
        )

    def capabilities(self) -> HostCapabilities:
        return HostCapabilities(can_execute=True, can_read_files=True, service_manager="systemd")

    def execute_readonly(self, request: CommandRequest, cancellation: CancellationToken) -> CommandResult:
        if cancellation.cancelled:
            raise OperationCancelled("operation cancelled")
        if request.argv[0] not in _READ_COMMANDS and request.argv[0] not in self.allowed_remote_executables:
            raise AdapterError("command_not_allowed", f"remote executable is not allowed: {request.argv[0]}")
        remote_command = shlex.join(("env", "LC_ALL=C", "LANG=C", *request.argv))
        socket_args = ("-S", self.control_socket) if self.control_socket else ()
        outer = CommandRequest(
            ("ssh", *socket_args, "-o", "BatchMode=yes", "--", self.alias, remote_command),
            request.timeout_ms,
            request.correlation_id,
        )
        return self.runner.run(outer, cancellation)

    def stat(self, path: str, cancellation: CancellationToken) -> FileStat:
        self._validate_path(path)
        result = self.execute_readonly(
            CommandRequest(
                ("stat", "--printf=%F|%a|%u|%g|%s", "--", path),
                self.timeout_ms,
                "ssh.stat",
            ),
            cancellation,
        )
        if result.timed_out:
            raise AdapterError("timeout", "SSH stat probe timed out")
        if result.exit_code != 0:
            return FileStat(path, False)
        try:
            kind, mode, uid, gid, size = result.stdout.split("|")
            parsed_mode = int(mode, 8)
            parsed_uid = int(uid)
            parsed_gid = int(gid)
            parsed_size = int(size)
        except (TypeError, ValueError) as error:
            raise AdapterError("parse_failed", "SSH stat returned invalid metadata") from error
        is_symlink = kind == "symbolic link"
        content = None
        if kind == "regular file" and 0 <= parsed_size <= 4 * 1024 * 1024:
            content = self._read_optional(path, 4 * 1024 * 1024, cancellation)
        import hashlib

        return FileStat(
            path,
            True,
            sha256=hashlib.sha256(content).hexdigest() if content is not None else None,
            mode=parsed_mode,
            uid=parsed_uid,
            gid=parsed_gid,
            is_symlink=is_symlink,
        )

    def read_file(self, path: str, max_bytes: int, cancellation: CancellationToken) -> bytes:
        content = self._read_optional(path, max_bytes, cancellation)
        if content is None:
            raise FileNotFoundError(path)
        return content

    def _read_optional(self, path: str, max_bytes: int, cancellation: CancellationToken) -> bytes | None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._validate_path(path)
        result = self.execute_readonly(
            CommandRequest(("cat", "--", path), self.timeout_ms, "ssh.read_file"), cancellation
        )
        if result.exit_code != 0:
            return None
        content = result.stdout.encode("utf-8")
        if len(content) > max_bytes:
            raise ValueError("file exceeds max_bytes")
        return content

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith("/") or any(character in path for character in "\r\n\x00"):
            raise ValueError("remote path must be an absolute safe path")
