from __future__ import annotations

import re
import shlex
import subprocess
from dataclasses import dataclass
from time import monotonic, sleep
from typing import Callable, Protocol

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest

from .openssh_staging import REMOTE_HELPER
from .process import SubprocessRunner
from .ssh_auth import TerminalSpec


_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class RemoteHelperCompletionProbe(Protocol):
    def completed(
        self, request_id: str, request_hash: str, cancellation: CancellationToken
    ) -> bool: ...


@dataclass(slots=True)
class OpenSshRemoteSudoInvoker:
    runner: SubprocessRunner
    terminal: TerminalSpec
    completion: RemoteHelperCompletionProbe
    timeout_seconds: int = 120
    poll_seconds: float = 0.25
    clock: Callable[[], float] = monotonic
    sleeper: Callable[[float], None] = sleep

    def invoke(
        self,
        alias: str,
        control_socket: str | None,
        request_id: str,
        request_hash: str,
        cancellation: CancellationToken,
    ) -> None:
        _validate(alias, control_socket, request_id, request_hash)
        if cancellation.cancelled:
            raise OperationCancelled("remote helper invocation cancelled")
        socket = ("-S", control_socket) if control_socket else ()
        fixed_helper = (REMOTE_HELPER, "invoke-recovery", request_id, request_hash)
        probe = self.runner.run(
            CommandRequest(
                ("ssh", *socket, "-o", "BatchMode=yes", "--", alias, "sudo -n -v"),
                15_000,
                "ssh.remote-helper.sudo-probe",
            ),
            cancellation,
        )
        if not probe.timed_out and probe.exit_code == 0:
            result = self.runner.run(
                CommandRequest(
                    (
                        "ssh", *socket, "-o", "BatchMode=yes", "--", alias,
                        shlex.join(("sudo", "-n", "--", *fixed_helper)),
                    ),
                    30_000,
                    "ssh.remote-helper.passwordless",
                ),
                cancellation,
            )
            if result.timed_out:
                raise AdapterError("remote_helper_timeout", "remote helper timed out")
            if result.exit_code != 0:
                raise AdapterError("remote_helper_failed", "remote helper failed")
            return
        if cancellation.cancelled:
            raise OperationCancelled("remote helper invocation cancelled")
        interactive_command = (
            "ssh", *socket, "-t", "--", alias,
            shlex.join(("sudo", "--", *fixed_helper)),
        )
        try:
            subprocess.Popen(
                self.terminal.launch_argv("LLM-Manager remote authorization", interactive_command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as error:
            raise AdapterError("terminal_launch_failed", "remote authorization terminal could not start") from error
        deadline = self.clock() + self.timeout_seconds
        while self.clock() < deadline:
            if cancellation.cancelled:
                raise OperationCancelled("remote helper invocation cancelled")
            if self.completion.completed(request_id, request_hash, cancellation):
                return
            self.sleeper(self.poll_seconds)
        raise AdapterError("remote_authorization_timeout", "remote helper authorization did not complete")


def _validate(
    alias: str, control_socket: str | None, request_id: str, request_hash: str
) -> None:
    if alias.startswith("-") or not _ALIAS.fullmatch(alias):
        raise AdapterError("invalid_remote_invocation", "OpenSSH alias is invalid")
    if control_socket is not None and (
        not control_socket.startswith("/")
        or any(character in control_socket for character in "\r\n\x00")
    ):
        raise AdapterError("invalid_remote_invocation", "OpenSSH control socket is invalid")
    if not _IDENTIFIER.fullmatch(request_id) or not _DIGEST.fullmatch(request_hash):
        raise AdapterError("invalid_remote_invocation", "remote helper identity is invalid")
