"""Cancel dedicated real SSH sessions running only a finite remote sleep.

No target files or services are changed. Requires an already trusted alias and
noninteractive authentication. This is not an Apply or physical network-cut gate.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from unittest.mock import patch

from llm_manager.application.errors import OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.infrastructure import process
from llm_manager.infrastructure.openssh_identity import OpenSshHostIdentityResolver
from llm_manager.infrastructure.ssh_auth import SshAliasAuthRequest


def ssh_argv(alias: str, command: str) -> tuple[str, ...]:
    SshAliasAuthRequest(alias)
    return ("ssh", "-S", "none", "-o", "BatchMode=yes", "-o",
            "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no", "-o",
            "RemoteCommand=none", "-o", "RequestTTY=no", "--", alias, command)


def sample(alias: str) -> dict[str, object]:
    runner = process.SubprocessRunner(process.ProcessPolicy({"ssh"}))
    identity = OpenSshHostIdentityResolver(runner).resolve(alias, CancellationToken())
    if identity.authentication_required:
        raise ValueError("noninteractive SSH authentication required")
    ready = threading.Event()
    done = threading.Event()
    token = CancellationToken()
    observed = {}
    children = []
    marker = bytearray()
    original_read, original_popen = os.read, process.subprocess.Popen

    def popen(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child

    def read(fd, size):
        chunk = original_read(fd, size)
        if children and children[0].stdout is not None and not children[0].stdout.closed:
            if fd == children[0].stdout.fileno():
                marker.extend(chunk)
                match = re.search(rb"PHASE6_READY:([1-9][0-9]*)\n", marker)
                if match:
                    observed["remote_pid"] = int(match[1])
                    ready.set()
        return chunk

    def cancel():
        if ready.wait(2) and not done.wait(.2):
            observed["cancel_at"] = time.monotonic()
            token.cancel()

    # The shell's PID is preserved by exec. The remote child exits naturally
    # within 3 seconds even if local SSH cancellation does not terminate it.
    command = "sh -c 'printf \"PHASE6_READY:%s\\n\" \"$$\"; exec sleep 3'"
    thread = threading.Thread(target=cancel)
    started = time.monotonic()
    cpu = time.process_time()
    cancelled = False
    thread.start()
    try:
        # Observe the actual child and pipe bytes without changing either.
        with patch.object(process.subprocess, "Popen", side_effect=popen), patch.object(os, "read", side_effect=read):
            try:
                runner.run(CommandRequest(ssh_argv(alias, command), 5000, "phase6.ssh.cancel"), token)
            except OperationCancelled:
                cancelled = True
        finished = time.monotonic()
        cpu_ms = (time.process_time() - cpu) * 1000
    finally:
        done.set()
        thread.join()
    assert cancelled and "cancel_at" in observed and len(children) == 1
    try:
        os.waitpid(children[0].pid, os.WNOHANG)
    except ChildProcessError:
        pass
    else:
        raise AssertionError("local SSH child was not reaped")
    # Read-only observation, never kill a PID remotely (including reused PIDs).
    deadline = time.monotonic() + 5
    while True:
        result = runner.run(CommandRequest(
            ssh_argv(alias, f"ps -p {observed['remote_pid']} -o pid="),
            3000, "phase6.ssh.remote-child-check"), CancellationToken())
        if result.exit_code == 1 and not result.timed_out and not result.stdout.strip() and not result.stderr_redacted.strip():
            break
        if time.monotonic() >= deadline:
            raise AssertionError("remote child absence could not be verified")
        time.sleep(.2)
    return {
        "elapsed_until_cancelled_ms": round((finished - started) * 1000, 3),
        "cancel_to_local_reaped_ms": round((finished - observed["cancel_at"]) * 1000, 3),
        "parent_cpu_ms": round(cpu_ms, 3),
        "remote_ready_before_cancel": True,
        "local_ssh_reaped": True,
        "remote_child_absent_after_bounded_wait": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alias")
    args = parser.parse_args()
    print(json.dumps({
        "scope": "production SubprocessRunner cancellation of dedicated SSH; finite remote sleep; no Qt/Apply/network-cut",
        "samples": [sample(args.alias) for _ in range(3)],
    }, indent=2))


if __name__ == "__main__":
    main()
