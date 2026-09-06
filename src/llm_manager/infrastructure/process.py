from __future__ import annotations

import os
import selectors
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

    def __post_init__(self) -> None:
        if self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")


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
        try:
            stdout_bytes, stderr_bytes, timed_out = _read_bounded(
                process,
                self.policy.max_output_bytes,
                deadline,
                cancellation,
            )
        except OperationCancelled:
            _stop_and_reap(process, terminate=True)
            raise
        except AdapterError:
            _stop_and_reap(process, terminate=False)
            raise
        return CommandResult(
            argv_redacted=redact_argv(request.argv),
            exit_code=None if timed_out else process.returncode,
            stdout=_decode(stdout_bytes),
            stderr_redacted=redact_text(_decode(stderr_bytes)),
            timed_out=timed_out,
            duration_ms=_elapsed_ms(started),
        )


def _read_bounded(
    process: subprocess.Popen[bytes],
    limit: int,
    deadline: float,
    cancellation: CancellationToken,
) -> tuple[bytes, bytes, bool]:
    if process.stdout is None or process.stderr is None:
        raise AdapterError("command_failed", "command output pipes are unavailable")
    streams = (process.stdout, process.stderr)
    stdout_fd, stderr_fd = (stream.fileno() for stream in streams)
    buffers = {stdout_fd: bytearray(), stderr_fd: bytearray()}
    selector = selectors.DefaultSelector()
    try:
        for stream in streams:
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map() or process.poll() is None:
            if cancellation.cancelled:
                raise OperationCancelled("command cancelled")
            remaining = deadline - monotonic()
            if remaining <= 0:
                _stop_and_reap(process, terminate=False)
                return bytes(buffers[stdout_fd]), bytes(buffers[stderr_fd]), True
            if not selector.get_map():
                # EOF is not process completion. Keep cancellation and the
                # deadline active while waiting for a child that closed its pipes.
                try:
                    process.wait(timeout=min(remaining, 0.05))
                except subprocess.TimeoutExpired:
                    pass
                continue
            for key, _events in selector.select(min(remaining, 0.05)):
                buffer = buffers[key.fd]
                chunk = os.read(key.fd, min(64 * 1024, limit - len(buffer) + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                buffer.extend(chunk)
                if len(buffer) > limit:
                    raise AdapterError(
                        "command_output_too_large",
                        "command stdout or stderr exceeded the configured limit",
                    )
        return bytes(buffers[stdout_fd]), bytes(buffers[stderr_fd]), False
    finally:
        selector.close()


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))


def _stop_and_reap(process: subprocess.Popen[bytes], *, terminate: bool) -> None:
    if process.poll() is None:
        process.terminate() if terminate else process.kill()
    for stream in (process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            stream.close()
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
