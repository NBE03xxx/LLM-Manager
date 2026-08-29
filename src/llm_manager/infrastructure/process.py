from __future__ import annotations

import subprocess
from collections.abc import Collection
from dataclasses import dataclass
from time import monotonic

from llm_manager.application.errors import AdapterError, OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest, CommandResult

from .redaction import redact_argv, redact_text


@dataclass(frozen=True, slots=True)
class ProcessPolicy:
    allowed_executables: Collection[str]
    max_output_bytes: int = 4 * 1024 * 1024


@dataclass(slots=True)
class SubprocessRunner:
    policy: ProcessPolicy

    def run(self, request: CommandRequest, cancellation: CancellationToken) -> CommandResult:
        if cancellation.cancelled:
            raise OperationCancelled("command cancelled before start")
        executable = request.argv[0]
        if executable not in self.policy.allowed_executables:
            raise AdapterError("command_not_allowed", f"executable is not allowed: {executable}")
        started = monotonic()
        try:
            process = subprocess.Popen(
                request.argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/local/bin:/usr/bin:/bin"},
            )
        except OSError as error:
            raise AdapterError("command_failed", redact_text(str(error))) from error
        deadline = started + request.timeout_ms / 1000
        while True:
            if cancellation.cancelled:
                _terminate(process)
                raise OperationCancelled("command cancelled")
            remaining = deadline - monotonic()
            if remaining <= 0:
                process.kill()
                stdout_bytes, stderr_bytes = process.communicate()
                return CommandResult(
                    redact_argv(request.argv),
                    None,
                    _decode_limited(stdout_bytes, self.policy.max_output_bytes),
                    redact_text(_decode_limited(stderr_bytes, self.policy.max_output_bytes)),
                    True,
                    _elapsed_ms(started),
                )
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=min(remaining, 0.05))
                break
            except subprocess.TimeoutExpired:
                continue
        return CommandResult(
            argv_redacted=redact_argv(request.argv),
            exit_code=process.returncode,
            stdout=_decode_limited(stdout_bytes, self.policy.max_output_bytes),
            stderr_redacted=redact_text(_decode_limited(stderr_bytes, self.policy.max_output_bytes)),
            timed_out=False,
            duration_ms=_elapsed_ms(started),
        )


def _decode_limited(value: bytes, limit: int) -> str:
    return value[:limit].decode("utf-8", errors="replace")


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _terminate(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.communicate(timeout=0.5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
