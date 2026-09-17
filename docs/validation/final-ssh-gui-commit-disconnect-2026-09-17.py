"""Fresh final-artifact SSH commit/disconnect GUI Gate.

Keep the reviewed final artifact identity while assigning a new snapshot,
guest workspace, operation namespace, and evidence directory.  The NIC
watcher is deliberately long-lived because sudo authentication is interactive.
"""
import json
from pathlib import Path
import subprocess
import sys
import time


BASE = Path(__file__).with_name("final-ssh-gui-commit-disconnect-2026-09-16.py")
source = BASE.read_text()
source = source.replace("phase6-final-ssh-commit-net", "phase6-final-ssh-commit-net3")
source = source.replace(
    "final-ssh-gui-commit-disconnect-2026-09-16",
    "final-ssh-gui-commit-disconnect-2026-09-17",
)
gate = {"__file__": str(BASE), "__name__": "final_ssh_commit_disconnect_20260917"}
exec(compile(source, str(BASE), "exec"), gate)

ns = gate["ns"]
network = gate["network"]
old_guest = gate["GUEST"]
GUEST = "/tmp/phase6-final-ssh-commit-net3-20260917"
gate["GUEST"] = GUEST
ns["GUEST"] = GUEST
ns["SNAP"] = "phase6-final-ssh-commit-net3-20260917"
ns["ENV"] = [value.replace(old_guest, GUEST) for value in ns["ENV"]]
ns["menu"].TARGET = GUEST + ".deb"
gate["scope"]["GUEST"] = GUEST
gate["scope"]["gui"]["GUEST"] = GUEST
network.GUEST = GUEST
network.READY = GUEST + "/hold/ready.json"


def watch_long() -> None:
    """Cut the NIC on a fresh successful helper marker, waiting up to one hour."""
    out = gate["OUT"]
    vm = network.vm
    mac = network.MAC
    assert not (out / "network.json").exists()
    assert vm.virsh("domif-getlink", vm.VM, mac).strip() == mac + " up"
    print("Watcher ready; waiting up to one hour for successful helper completion.", flush=True)
    deadline = time.monotonic() + 3600
    marker = None
    observation = None
    while time.monotonic() < deadline:
        raw = vm.python(
            "import json,time; from pathlib import Path; p=Path(" + repr(network.READY) + "); "
            "print(json.dumps({'marker':json.loads(p.read_text()),'age':time.time()-p.stat().st_mtime}) "
            "if p.exists() else 'null')"
        )
        observation = json.loads(raw)
        marker = observation["marker"] if observation else None
        if marker:
            break
        time.sleep(0.25)
    assert marker and marker["helper_exit_code"] == 0, "no successful helper marker; no network cut"
    if not 0 <= observation["age"] < 2:
        ns["save"]("network-not-cut.json", {
            "reason": "stale marker; response may already be delivered",
            "observation": observation,
            "link": vm.virsh("domif-getlink", vm.VM, mac).strip(),
        })
        print("Stale marker: no NIC cut. Do not count as a network gate.", flush=True)
        return
    ns["save"]("helper-completion.json", marker)
    command = (
        "import subprocess,time; time.sleep(7); "
        "subprocess.run(['virsh','domif-setlink','ubuntu26.04','52:54:00:f8:49:29','up'],"
        "check=True,timeout=10)"
    )
    watchdog = subprocess.Popen(
        [sys.executable, "-I", "-c", command],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    record = {"helper_marker": marker, "link_before": "up"}
    try:
        vm.virsh("domif-setlink", vm.VM, mac, "down")
        record["down_at_monotonic"] = time.monotonic()
        record["link_during"] = vm.virsh("domif-getlink", vm.VM, mac).strip()
        assert record["link_during"] == mac + " down"
        time.sleep(4)
    finally:
        vm.virsh("domif-setlink", vm.VM, mac, "up")
        record["up_at_monotonic"] = time.monotonic()
        _, error = watchdog.communicate(timeout=15)
        record["watchdog_exit"] = watchdog.returncode
        record["watchdog_stderr"] = error.decode()
        record["link_after"] = vm.virsh("domif-getlink", vm.VM, mac).strip()
        ns["save"]("network.json", record)
    assert record["link_after"] == mac + " up" and watchdog.returncode == 0
    print(json.dumps(record, indent=2), flush=True)


def mark_pre_mutation_failure() -> None:
    """Record a failed interactive backup preflight without retrying mutation."""
    out = gate["OUT"]
    result = json.loads((out / "commit-result.json").read_text())
    events = json.loads((out / "commit-transport-events.json").read_text())
    target = json.loads((out / "target-after.json").read_text())
    apply_calls = [item for item in events if item["correlation_id"] == "ssh.user_apply.invoke"]
    assert result["status"] == "approved"
    assert result["error"] == "both SSH backup copies must verify"
    assert not apply_calls
    assert target["sha256"] == "fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7"
    assert ns["ubuntu"].virsh("domif-getlink", ns["ubuntu"].VM, network.MAC).strip() == network.MAC + " up"
    gate["save"]("network-not-cut.json", {
        "reason": "interactive backup preflight did not produce two verified SSH backup copies",
        "status": result["status"],
        "error": result["error"],
        "staging_download_count": len(events),
        "apply_invoke_count": 0,
        "target_initial_hash_unchanged": True,
        "mutation_retried": False,
        "qualifying_disconnect_gate": False,
        "link": network.MAC + " up",
    })
    print("Pre-mutation backup preflight failure retained as non-qualifying evidence.", flush=True)


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "prepare":
        gate["prepare"]()
    elif action == "setup":
        gate["scope"]["setup"]()
    elif action == "watch":
        watch_long()
    elif action == "collect":
        gate["scope"]["collect"]()
    elif action == "cleanup":
        network.cleanup()
    elif action in {"launch", "status"}:
        ns[action]("commit")
    elif action == "inspect":
        ns["inspect"]()
    elif action == "mark-pre-mutation-failure":
        mark_pre_mutation_failure()
    elif action == "atspi":
        gate["atspi"](sys.argv[2:])
    elif action == "pointer":
        gate["pointer"](int(sys.argv[2]), int(sys.argv[3]))
    else:
        raise ValueError(action)
