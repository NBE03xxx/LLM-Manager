"""Final artifact normal-GUI SSH commit with a live NIC reply cut.

Derive the already reviewed full-GUI network Gate while assigning a fresh
namespace, snapshot, operation, and evidence directory.  The production GUI
creates the plan and approval; only the successful helper reply is delayed.
"""
import hashlib
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "docs/validation/full-gui-network-2026-09-14.py"
source = BASE.read_text()
source = source.replace("phase6-full-gui-net", "phase6-final-ssh-commit-net")
source = source.replace(
    "full-gui-network-2026-09-14", "final-ssh-gui-commit-disconnect-2026-09-16"
)
source = source.replace("20260913", "20260916")
scope = {"__file__": str(BASE), "__name__": "final_ssh_commit_disconnect_lifecycle"}
exec(compile(source, str(BASE), "exec"), scope)

ns = scope["ns"]
OUT = scope["OUT"]
network = scope["network"]
old_guest = ns["GUEST"]
GUEST = "/tmp/phase6-final-ssh-commit-net-20260916"
ns["GUEST"] = GUEST
ns["SNAP"] = "phase6-final-ssh-commit-net-20260916"
ns["ENV"] = [value.replace(old_guest, GUEST) for value in ns["ENV"]]
ns["menu"].TARGET = GUEST + ".deb"
scope["GUEST"] = GUEST
scope["gui"]["GUEST"] = GUEST
network.GUEST = GUEST
network.READY = GUEST + "/hold/ready.json"

LOCAL_DEB = Path("/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager_0.1.0_all.deb")
LOCAL_HASH = "63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1"
REMOTE_DEB = Path("/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager-remote-helper_0.1.0_all.deb")
REMOTE_HASH = "ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4"

ns["REMOTE"] = REMOTE_DEB
ns["REMOTE_HASH"] = REMOTE_HASH
ns["menu"].DEB = LOCAL_DEB
ns["menu"].DIGEST = LOCAL_HASH


def save(name: str, value) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def prepare() -> None:
    ns["prepare"]()
    assert hashlib.sha256(LOCAL_DEB.read_bytes()).hexdigest() == LOCAL_HASH
    assert hashlib.sha256(REMOTE_DEB.read_bytes()).hexdigest() == REMOTE_HASH
    save("artifact-identity.json", {
        "source_commit": "5b7d4de03e495fe630deab952de043f945a22bd7",
        "local_sha256": LOCAL_HASH,
        "remote_sha256": REMOTE_HASH,
        "release_set": "final artifact; unsigned and unpublished",
    })


def resume_setup_after_transfer_path_fix() -> None:
    """Continue after the first setup stopped before transferring the GUI harness."""
    old = scope["gui"]["setup"]
    try:
        scope["gui"]["setup"] = lambda: None
        scope["setup"]()
    finally:
        scope["gui"]["setup"] = old
    save("setup-resume.json", {
        "reason": "derived outer GUI GUEST retained the historical date",
        "stopped_before_gui_launch": True,
        "stopped_before_mutation": True,
        "completed_setup_replayed": False,
        "correct_guest": GUEST,
    })


def atspi(args: list[str]) -> None:
    guest = GUEST + "/atspi.py"
    helper = REPO / "docs/validation/local-user-restore-gui-final-2026-09-16-attempt2/atspi.py"
    exists = ns["debian"].python("from pathlib import Path; print(Path(" + repr(guest) + ").exists())").strip()
    if exists != "True":
        ns["debian"].transfer(str(helper), guest)
        ns["debian"].execute("/bin/chown", ["1000:1000", guest])
    print(ns["user"](ns["debian"], "user", "import runpy,sys; sys.argv=" + repr([guest, *args]) + "; runpy.run_path(" + repr(guest) + ",run_name='__main__')"), flush=True)


def pointer(x: int, y: int) -> None:
    code = (
        "import gi,json; gi.require_version('Atspi','2.0'); from gi.repository import Atspi; "
        "Atspi.init(); ok=Atspi.generate_mouse_event(" + str(x) + "," + str(y) + ",'b1c'); "
        "print(json.dumps({'x':" + str(x) + ",'y':" + str(y) + ",'ok':bool(ok)}))"
    )
    print(ns["user"](ns["debian"], "user", code), flush=True)


def mark_nonqualifying_no_cut() -> None:
    events = json.loads((OUT / "commit-transport-events.json").read_text())
    calls = [item for item in events if item["correlation_id"] == "ssh.user_apply.invoke"]
    assert len(calls) == 1 and calls[0]["exit_code"] == 0 and not calls[0]["timed_out"]
    assert ns["ubuntu"].virsh("domif-getlink", ns["ubuntu"].VM, network.MAC).strip() == network.MAC + " up"
    marker = json.loads(ns["ubuntu"].python(
        "from pathlib import Path; print(Path(" + repr(network.READY) + ").read_text())"
    ))
    save("network-not-cut.json", {
        "reason": "interactive authentication crossed a task turn and the foreground watcher session did not persist",
        "helper_marker": marker,
        "apply_exit_code": calls[0]["exit_code"],
        "mutation_retried": False,
        "qualifying_disconnect_gate": False,
        "link": network.MAC + " up",
    })
    print("Committed operation retained as non-qualifying evidence; no NIC cut and no retry.", flush=True)


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "prepare":
        prepare()
    elif action == "setup":
        scope["setup"]()
    elif action == "resume-setup":
        resume_setup_after_transfer_path_fix()
    elif action == "watch":
        network.watch()
    elif action == "collect":
        scope["collect"]()
    elif action == "cleanup":
        network.cleanup()
    elif action in {"launch", "status"}:
        ns[action]("commit")
    elif action == "inspect":
        ns["inspect"]()
    elif action == "atspi":
        atspi(sys.argv[2:])
    elif action == "pointer":
        pointer(int(sys.argv[2]), int(sys.argv[3]))
    elif action == "mark-nonqualifying":
        mark_nonqualifying_no_cut()
    else:
        raise ValueError(action)
