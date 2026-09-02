from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest

from .process import SubprocessRunner

_USER = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}")
_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_.:-]{0,253}[A-Za-z0-9])?")
_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_FINGERPRINT = re.compile(
    r"^debug\d+: Server host key: \S+ (?P<fingerprint>SHA256:[A-Za-z0-9+/]{43})$",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class SshAuthRequest:
    username: str
    host: str
    port: int = 22
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if not _USER.fullmatch(self.username):
            raise ValueError("invalid SSH username")
        if self.host.startswith("-") or not _HOST.fullmatch(self.host):
            raise ValueError("invalid SSH hostname or address")
        if not 1 <= self.port <= 65535:
            raise ValueError("invalid SSH port")
        if not 10 <= self.timeout_seconds <= 600:
            raise ValueError("SSH authentication timeout must be between 10 and 600 seconds")

    @property
    def target(self) -> str:
        return f"{self.username}@{self.host}"


@dataclass(frozen=True, slots=True)
class SshAliasAuthRequest:
    alias: str
    timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if self.alias.startswith("-") or _ALIAS.fullmatch(self.alias) is None:
            raise ValueError("invalid OpenSSH host alias")
        if not 10 <= self.timeout_seconds <= 600:
            raise ValueError("SSH authentication timeout must be between 10 and 600 seconds")


@dataclass(frozen=True, slots=True)
class TerminalSpec:
    executable: str
    kind: str

    def launch_argv(self, title: str, command: tuple[str, ...]) -> tuple[str, ...]:
        if self.kind == "ptyxis":
            return (self.executable, f"--title={title}", "--", *command)
        if self.kind == "gnome-terminal":
            return (self.executable, f"--title={title}", "--", *command)
        if self.kind == "x-terminal-emulator":
            return (self.executable, "-T", title, "-e", *command)
        raise ValueError(f"unsupported terminal kind: {self.kind}")


@dataclass(frozen=True, slots=True)
class SshControlSession:
    target: str
    port: int | None
    socket_path: str
    verified_fingerprint: str | None = None

    def ssh_prefix(self) -> tuple[str, ...]:
        port = ("-p", str(self.port)) if self.port is not None else ()
        return ("ssh", "-S", self.socket_path, *port, "--", self.target)


def detect_terminal(which=shutil.which) -> TerminalSpec | None:
    for executable, kind in (
        ("ptyxis", "ptyxis"),
        ("gnome-terminal", "gnome-terminal"),
        ("x-terminal-emulator", "x-terminal-emulator"),
    ):
        path = which(executable)
        if path:
            return TerminalSpec(path, kind)
    return None


@dataclass(slots=True)
class ExternalTerminalSshBroker:
    runner: SubprocessRunner
    runtime_root: Path
    terminal: TerminalSpec

    def authenticate(
        self, request: SshAuthRequest, cancellation: CancellationToken
    ) -> SshControlSession:
        return self._authenticate(
            request.target,
            request.port,
            request.host,
            request.timeout_seconds,
            cancellation,
        )

    def authenticate_alias(
        self, request: SshAliasAuthRequest, cancellation: CancellationToken
    ) -> SshControlSession:
        return self._authenticate(
            request.alias,
            None,
            request.alias,
            request.timeout_seconds,
            cancellation,
        )

    def _authenticate(
        self,
        target: str,
        port: int | None,
        title_host: str,
        timeout_seconds: int,
        cancellation: CancellationToken,
    ) -> SshControlSession:
        if cancellation.cancelled:
            raise OperationCancelled("SSH authentication cancelled before start")
        session_dir = self.runtime_root / "ssh"
        session_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(session_dir, 0o700)
        socket_path = session_dir / f"cm-{uuid4().hex[:16]}"
        log_path = session_dir / f"host-key-{uuid4().hex[:16]}.log"
        if len(os.fsencode(socket_path)) >= 100:
            raise AdapterError("control_path_too_long", "SSH control socket path is too long")
        log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(log_fd)
        session = SshControlSession(target, port, str(socket_path))
        port_args = ("-p", str(port)) if port is not None else ()
        ssh_command = (
            "ssh",
            "-v",
            "-E",
            str(log_path),
            "-M",
            "-S",
            session.socket_path,
            *port_args,
            "-o",
            "ControlMaster=yes",
            "-o",
            "ControlPersist=300",
            "-o",
            "BatchMode=no",
            "-o",
            "NumberOfPasswordPrompts=3",
            "-o",
            "ConnectTimeout=15",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UpdateHostKeys=no",
            "-N",
            "--",
            target,
        )
        title = f"LLM-Manager SSH authentication — {title_host}"
        try:
            subprocess.Popen(
                self.terminal.launch_argv(title, ssh_command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
            deadline = monotonic() + timeout_seconds
            while monotonic() < deadline:
                if cancellation.cancelled:
                    self.close(session, CancellationToken())
                    raise OperationCancelled("SSH authentication cancelled")
                if self._is_ready(session, cancellation):
                    try:
                        fingerprint = self._read_verified_fingerprint(log_path)
                    except AdapterError:
                        self.close(session, CancellationToken())
                        raise
                    return SshControlSession(target, port, str(socket_path), fingerprint)
                sleep(0.25)
            self.close(session, CancellationToken())
            raise AdapterError("authentication_timeout", "SSH authentication did not complete in time")
        except OSError as error:
            raise AdapterError("terminal_launch_failed", str(error)) from error
        finally:
            try:
                log_path.unlink(missing_ok=True)
            except OSError:
                pass

    def close(self, session: SshControlSession, cancellation: CancellationToken) -> None:
        port = ("-p", str(session.port)) if session.port is not None else ()
        request = CommandRequest(
            ("ssh", "-S", session.socket_path, "-O", "exit", *port, "--", session.target),
            5_000,
            "ssh.control.close",
        )
        try:
            self.runner.run(request, cancellation)
        except (AdapterError, OperationCancelled):
            pass

    def _is_ready(self, session: SshControlSession, cancellation: CancellationToken) -> bool:
        if not Path(session.socket_path).exists():
            return False
        port = ("-p", str(session.port)) if session.port is not None else ()
        result = self.runner.run(
            CommandRequest(
                ("ssh", "-S", session.socket_path, "-O", "check", *port, "--", session.target),
                3_000,
                "ssh.control.check",
            ),
            cancellation,
        )
        return not result.timed_out and result.exit_code == 0

    @staticmethod
    def _read_verified_fingerprint(log_path: Path) -> str:
        descriptor = None
        try:
            descriptor = os.open(log_path, os.O_RDONLY | os.O_NOFOLLOW)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_mode & 0o077
                or metadata.st_size > 1024 * 1024
            ):
                raise AdapterError("host_identity_unverified", "SSH host-key log is not private")
            content = os.read(descriptor, 1024 * 1024 + 1).decode("utf-8", errors="replace")
        except OSError as error:
            raise AdapterError("host_identity_unverified", "SSH host-key log is unavailable") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
        matches = {match.group("fingerprint") for match in _FINGERPRINT.finditer(content)}
        if len(matches) != 1:
            raise AdapterError("host_identity_unverified", "SSH master did not report one server host key")
        return matches.pop()
