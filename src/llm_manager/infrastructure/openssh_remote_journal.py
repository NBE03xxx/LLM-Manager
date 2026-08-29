from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest

from .openssh_staging import REMOTE_HELPER, RemoteHelperReadinessGate
from .process import SubprocessRunner
from .remote_journal import MAX_REMOTE_JOURNAL_EVIDENCE_BYTES


_ALIAS = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_.@:-]{0,254}")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(slots=True)
class OpenSshRemoteJournalPort:
    """Fetch canonical root journal evidence through one fixed helper command."""

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
        if self.timeout_ms <= 0:
            raise ValueError("OpenSSH journal timeout must be positive")

    def load_journal_evidence(
        self,
        operation_id: str,
        request_hash: str,
        cancellation: CancellationToken,
    ) -> bytes:
        if not _IDENTIFIER.fullmatch(operation_id) or not _DIGEST.fullmatch(request_hash):
            raise AdapterError("invalid_remote_journal_identity", "journal identity is invalid")
        if cancellation.cancelled:
            raise OperationCancelled("remote journal retrieval cancelled")
        self.readiness_gate.assert_ready(cancellation)
        socket = ("-S", self.control_socket) if self.control_socket else ()
        remote_command = shlex.join(
            ("sudo", "-n", "--", REMOTE_HELPER, "read-journal-evidence", operation_id, request_hash)
        )
        result = self.runner.run(
            CommandRequest(
                ("ssh", *socket, "-o", "BatchMode=yes", "--", self.alias, remote_command),
                self.timeout_ms,
                "ssh.remote-journal.read",
            ),
            cancellation,
        )
        if result.timed_out:
            raise AdapterError("remote_journal_timeout", "remote journal retrieval timed out")
        if result.exit_code != 0:
            raise AdapterError("remote_journal_failed", "remote journal retrieval failed")
        content = result.stdout.encode("utf-8")
        if len(content) > MAX_REMOTE_JOURNAL_EVIDENCE_BYTES:
            raise AdapterError("remote_journal_too_large", "remote journal evidence exceeds 1 MiB")
        return content
