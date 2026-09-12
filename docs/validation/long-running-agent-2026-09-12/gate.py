import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO = Path("/home/yoshimi/WorkSpace/LLM-Manager")
spec = importlib.util.spec_from_file_location(
    "vm_gate", REPO / "docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py"
)
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

OUT = REPO / "docs/validation/long-running-agent-2026-09-12"
ARCHIVE = Path("/tmp/llm-manager-long-agent-source-20260912.tar.gz")
ARCHIVE_SHA256 = "13470947c15393d8c001e6ce37dbf1922481bfd0f5aa1c308ad8913e4dbab113"
GUEST_ARCHIVE = "/tmp/phase6-long-running-agent-source.tar.gz"
GUEST_ROOT = "/tmp/phase6-long-running-agent-source"
STATE = OUT / "state.json"


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def status(pid):
    result = vm.qga("guest-exec-status", {"pid": pid})
    value = {"exited": bool(result.get("exited"))}
    if not value["exited"]:
        return value
    value.update(
        {
            "exit_code": result.get("exitcode"),
            "stdout": base64.b64decode(result.get("out-data", "")).decode(),
            "stderr": base64.b64decode(result.get("err-data", "")).decode(),
            "out_truncated": bool(result.get("out-truncated")),
            "err_truncated": bool(result.get("err-truncated")),
        }
    )
    return value


def prepare():
    assert vm.virsh("domstate", vm.VM).strip() == "running"
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_SHA256
    assert OUT.is_dir() and {path.name for path in OUT.iterdir()} == {"gate.py"}
    save("baseline.json", vm.inventory())
    vm.transfer(ARCHIVE, GUEST_ARCHIVE)
    assert vm.python(
        f"import hashlib; print(hashlib.sha256(open({GUEST_ARCHIVE!r},'rb').read()).hexdigest())"
    ).strip() == ARCHIVE_SHA256
    vm.execute("/usr/bin/rm", ["-rf", GUEST_ROOT])
    vm.execute("/usr/bin/mkdir", ["-m", "0755", GUEST_ROOT])
    vm.execute(
        "/usr/bin/tar",
        ["-xzf", GUEST_ARCHIVE, "-C", GUEST_ROOT, "--no-same-owner"],
    )
    save(
        "environment.json",
        {
            "archive_sha256": ARCHIVE_SHA256,
            "basis_commit": "8056850bf6c2747ca25dd26d006a003066ed9f3d",
            "overlay": [
                "src/llm_manager/ui/i18n.py",
                "src/llm_manager/ui/qt_window.py",
                "tests/test_ui_qt_runtime.py",
                "tests/test_ui_qt_window.py",
            ],
            "duration_seconds": 3600,
            "guest_root": GUEST_ROOT,
            "mutation_scope": "guest /tmp only",
        },
    )
    print("Long-running Agent source prepared in guest /tmp.")


def start():
    assert not STATE.exists()
    arguments = [
        "-u", "yoshimi", "--", "/usr/bin/env",
        "QT_QPA_PLATFORM=offscreen", "PYTHONDONTWRITEBYTECODE=1",
        f"PYTHONPATH={GUEST_ROOT}/src",
        "/usr/bin/python3", f"{GUEST_ROOT}/packaging/measure-long-running-agent.py",
    ]
    pid = vm.qga(
        "guest-exec",
        {"path": "/usr/sbin/runuser", "arg": arguments, "capture-output": True},
    )["pid"]
    save("state.json", {"guest_agent_pid": pid, "result_collected": False})
    print(f"Started 3600-second Gate as guest-agent PID {pid}.")


def repair_source():
    state = json.loads(STATE.read_text())
    try:
        failed = status(state["guest_agent_pid"])
    except Exception:
        # QEMU removes a completed guest-exec result after it has been read once.
        # The exact result below was returned by the preceding read-only poll.
        assert state["guest_agent_pid"] == 9204, state
        failed = {
            "exited": True,
            "exit_code": 2,
            "stdout": "",
            "stderr": (
                "/usr/bin/python3: can't open file "
                "'/tmp/phase6-long-running-agent-source/packaging/"
                "measure-long-running-agent.py': [Errno 2] No such file or directory\n"
            ),
            "out_truncated": False,
            "err_truncated": False,
        }
    assert failed["exited"] and failed["exit_code"] == 2, failed
    assert "measure-long-running-agent.py" in failed["stderr"], failed
    save("failed-launch.json", failed)
    STATE.unlink()
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_SHA256
    vm.transfer(ARCHIVE, GUEST_ARCHIVE)
    assert vm.python(
        f"import hashlib; print(hashlib.sha256(open({GUEST_ARCHIVE!r},'rb').read()).hexdigest())"
    ).strip() == ARCHIVE_SHA256
    vm.execute("/usr/bin/rm", ["-rf", GUEST_ROOT])
    vm.execute("/usr/bin/mkdir", ["-m", "0755", GUEST_ROOT])
    vm.execute(
        "/usr/bin/tar",
        ["-xzf", GUEST_ARCHIVE, "-C", GUEST_ROOT, "--no-same-owner"],
    )
    environment = json.loads((OUT / "environment.json").read_text())
    environment["archive_sha256"] = ARCHIVE_SHA256
    environment["initial_launch"] = "exit 2; measurement script absent from first archive"
    save("environment.json", environment)
    print("Failed launch recorded; corrected source archive prepared.")


def poll():
    state = json.loads(STATE.read_text())
    current = status(state["guest_agent_pid"])
    if current["exited"]:
        save("pending-result.json", current)
    print(json.dumps(current, ensure_ascii=False))


def collect():
    state = json.loads(STATE.read_text())
    pending = OUT / "pending-result.json"
    current = json.loads(pending.read_text()) if pending.exists() else status(
        state["guest_agent_pid"]
    )
    assert current["exited"], current
    save("process-result.json", current)
    assert not current["out_truncated"] and not current["err_truncated"], current
    assert current["exit_code"] == 0, current
    result = json.loads(current["stdout"])
    assert result["gate"] == "release", result
    assert result["requested_duration_seconds"] == 3600, result
    assert all(result["checks"].values()), result
    save("phase6-long-running-agent-2026-09-12.json", result)
    state["result_collected"] = True
    save("state.json", state)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cleanup():
    state = json.loads(STATE.read_text())
    assert state["result_collected"] is True
    vm.execute("/usr/bin/rm", ["-rf", GUEST_ROOT, GUEST_ARCHIVE])
    restored = vm.inventory()
    save("restored.json", restored)
    assert restored == json.loads((OUT / "baseline.json").read_text())
    assert vm.virsh("domstate", vm.VM).strip() == "running"
    print("Guest /tmp cleaned; baseline exact match; VM remains running.")


if __name__ == "__main__":
    {"prepare": prepare, "start": start, "repair-source": repair_source,
     "poll": poll, "collect": collect, "cleanup": cleanup}[sys.argv[1]]()
