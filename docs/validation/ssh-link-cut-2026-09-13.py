"""Bounded host-to-guest NIC-cut cancellation gate; not an Apply/Qt gate.

Explicit opt-in: --execute. Only a finite remote sleep is started. The live NIC
is restored by both finally and a separate watchdog process; persistent config
is never changed. Run only for the identified disposable test VM.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from llm_manager.application.errors import OperationCancelled
from llm_manager.application.ports import CancellationToken, CommandRequest
from llm_manager.infrastructure import process

VM = "ubuntu26.04"
MAC = "52:54:00:f8:49:29"
TARGET = "yoshimi@192.168.122.48"
OUT = Path(__file__).with_suffix("").with_suffix(".json")
BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ssh_cancel", BASE / "packaging/measure-ssh-cancel.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def virsh(*args):
    return subprocess.check_output(["virsh", *args], text=True, timeout=10).strip()


def main():
    assert sys.argv[1:] == ["--execute"], "requires explicit --execute"
    assert not OUT.exists(), "preserve existing evidence"
    assert virsh("domstate", VM) == "running"
    assert MAC in virsh("domiflist", VM)
    baseline = virsh("domif-getlink", VM, MAC)
    assert baseline == f"{MAC} up"
    runner = process.SubprocessRunner(process.ProcessPolicy({"ssh"}))
    before = runner.run(CommandRequest(helper.ssh_argv(TARGET, "id -u"), 5000, "gate.before"), CancellationToken())
    assert before.exit_code == 0 and before.stdout.strip() == "1000"
    token, ready = CancellationToken(), threading.Event()
    state, children, errors = {}, [], []
    marker = bytearray()
    real_popen, real_read = subprocess.Popen, os.read

    def popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        if args[0][0] == "ssh":
            children.append(child)
        return child

    def read(fd, size):
        data = real_read(fd, size)
        if children and children[0].stdout and not children[0].stdout.closed and fd == children[0].stdout.fileno():
            marker.extend(data)
            match = re.search(rb"PHASE6_READY:([1-9][0-9]*)\n", marker)
            if match:
                state["remote_pid"] = int(match[1])
                ready.set()
        return data

    def cut():
        watchdog = None
        try:
            assert ready.wait(5), "remote ready marker missing; do not cut"
            # Independent process survives errors/termination of the main gate.
            watchdog = real_popen([sys.executable, "-I", "-c",
                "import subprocess,time; time.sleep(3); "
                "subprocess.run(['virsh','domif-setlink'," + repr(VM) + "," + repr(MAC) + ", 'up'],check=True,timeout=10)"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
            virsh("domif-setlink", VM, MAC, "down")
            state["link_during_cancel"] = virsh("domif-getlink", VM, MAC)
            assert state["link_during_cancel"] == f"{MAC} down"
            time.sleep(.2)
            state["cancel_at"] = time.monotonic()
            token.cancel()
            time.sleep(.3)
        except BaseException as exc:
            errors.append(repr(exc))
            token.cancel()
        finally:
            try:
                virsh("domif-setlink", VM, MAC, "up")
            except BaseException as exc:
                errors.append("restore: " + repr(exc))
            if watchdog:
                _, err = watchdog.communicate(timeout=15)
                if watchdog.returncode:
                    errors.append("watchdog: " + err.decode())

    thread = threading.Thread(target=cut)
    cancelled = False
    thread.start()
    try:
        with patch.object(process.subprocess, "Popen", side_effect=popen), patch.object(os, "read", side_effect=read):
            try:
                runner.run(CommandRequest(helper.ssh_argv(TARGET,
                    "sh -c 'printf \"PHASE6_READY:%s\\n\" \"$$\"; exec sleep 4'"),
                    6000, "gate.link-cut"), token)
            except OperationCancelled:
                cancelled = True
        finished = time.monotonic()
    finally:
        thread.join(timeout=30)
        virsh("domif-setlink", VM, MAC, "up")
    assert not thread.is_alive() and not errors, errors
    assert cancelled and "cancel_at" in state and len(children) == 1
    try:
        os.waitpid(children[0].pid, os.WNOHANG)
    except ChildProcessError:
        pass
    else:
        raise AssertionError("SSH child not reaped")
    restored = virsh("domif-getlink", VM, MAC)
    assert restored == baseline
    deadline = time.monotonic() + 10
    while True:
        result = runner.run(CommandRequest(helper.ssh_argv(TARGET,
            f"ps -p {state['remote_pid']} -o pid="), 3000, "gate.after"), CancellationToken())
        if result.exit_code == 1 and not result.timed_out and not result.stdout.strip() and not result.stderr_redacted.strip():
            break
        assert time.monotonic() < deadline, "remote child absence not confirmed"
        time.sleep(.2)
    latency = round((finished - state["cancel_at"]) * 1000, 3)
    assert 0 <= latency < 500, latency
    evidence = {
        "scope": "source ff7913b production SubprocessRunner; host-to-Ubuntu virtual NIC cut; finite sleep; no Qt, Apply, physical cable or installed artifact claim",
        "vm": VM, "target": TARGET, "link_before": baseline,
        "link_during_cancel": state["link_during_cancel"], "link_after": restored,
        "cancel_to_local_reaped_ms": latency, "local_child_reaped": True,
        "remote_finite_child_absent": True, "new_strict_ssh_succeeded": True,
        "vm_state_after": virsh("domstate", VM), "errors": errors,
    }
    OUT.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
