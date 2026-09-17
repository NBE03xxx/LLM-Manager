"""Fresh final SSH commit/disconnect attempt with a detached finite watcher."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


BASE = Path(__file__).with_name("final-ssh-gui-commit-disconnect-2026-09-16.py")
source = BASE.read_text()
source = source.replace("phase6-final-ssh-commit-net", "phase6-final-ssh-commit-net2")
source = source.replace(
    "final-ssh-gui-commit-disconnect-2026-09-16",
    "final-ssh-gui-commit-disconnect-2026-09-16-attempt2",
)
gate = {"__file__": str(BASE), "__name__": "final_ssh_commit_disconnect_attempt2"}
exec(compile(source, str(BASE), "exec"), gate)


def start_watch() -> None:
    out = gate["OUT"]
    log = out / "watch.log"
    handle = log.open("xb")
    process = subprocess.Popen(
        [sys.executable, "-I", str(Path(__file__).resolve()), "watch"],
        stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
    )
    handle.close()
    gate["save"]("watch-pid.json", {"pid": process.pid, "detached": True})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        text = log.read_text(errors="replace")
        if "Watcher ready" in text:
            print(text, end="")
            return
        if process.poll() is not None:
            raise RuntimeError("watcher exited before ready: " + text)
        time.sleep(0.1)
    raise TimeoutError("detached watcher did not become ready")


def mark_pre_mutation_failure() -> None:
    out = gate["OUT"]
    result = json.loads((out / "commit-result.json").read_text())
    events = json.loads((out / "commit-transport-events.json").read_text())
    target = json.loads((out / "target-after.json").read_text())
    assert result["status"] == "approved" and result["error"] == "both SSH backup copies must verify"
    assert not [item for item in events if item["correlation_id"] == "ssh.user_apply.invoke"]
    assert target["sha256"] == "fcbdf78f1ce1c2bb87446df5f5fc64d9b6da5fd23824881109581152bfee98a7"
    network = gate["network"]
    assert gate["ns"]["ubuntu"].virsh("domif-getlink", gate["ns"]["ubuntu"].VM, network.MAC).strip() == network.MAC + " up"
    gate["save"]("network-not-cut.json", {
        "reason": "sudo authentication did not complete before backup verification deadline",
        "status": result["status"],
        "error": result["error"],
        "staging_download_count": len(events),
        "apply_invoke_count": 0,
        "target_initial_hash_unchanged": True,
        "mutation_retried": False,
        "qualifying_disconnect_gate": False,
        "link": network.MAC + " up",
    })
    print("Pre-mutation authentication timeout retained as non-qualifying evidence.", flush=True)


def resume_cleanup_after_empty_local_probe_dir() -> None:
    """Finish cleanup after local read-only diagnosis left one empty directory."""
    ns = gate["ns"]
    menu = ns["menu"]
    ns["debian"].execute("/usr/sbin/runuser", ["-u", "user", "--", "/usr/bin/python3", "-I", "-c", r'''
from pathlib import Path
p=Path('/home/user/.config/opencode')
assert p.is_dir() and not p.is_symlink() and p.stat().st_uid==1000
assert not list(p.iterdir())
p.rmdir()
'''])
    baseline = json.loads((menu.OUT / "baseline.json").read_text())
    cleaned = menu.gate.inventory()
    menu.save("cleaned-after-empty-local-probe-dir.json", cleaned)
    assert cleaned == baseline
    assert menu.gate.vm.execute("/usr/bin/dpkg", ["--audit"]) == ""
    menu.apt("apt-check-after-empty-dir", ["check"])
    (menu.OUT / "session-after.txt").write_text(menu.session())
    assert (menu.OUT / "session-after.txt").read_text() == (menu.OUT / "session-before.txt").read_text()
    menu.save("cleanup-result.json", {
        "purged_packages": json.loads((menu.OUT / "added.json").read_text()),
        "baseline_exact_match": True,
        "dpkg_audit_empty": True,
        "apt_check": True,
        "transferred_deb_removed": True,
        "empty_local_probe_directory_removed": "/home/user/.config/opencode",
        "vm_state": menu.gate.vm.virsh("domstate", menu.gate.vm.VM).strip(),
    })
    (menu.OUT / "SHA256SUMS").write_text("".join(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
        for path in sorted(menu.OUT.iterdir()) if path.is_file() and path.name != "SHA256SUMS"
    ))
    assert ns["SNAP"] in ns["ubuntu"].virsh("snapshot-list", ns["ubuntu"].VM, "--name").splitlines()
    print(ns["ubuntu"].virsh("snapshot-revert", ns["ubuntu"].VM, ns["SNAP"], "--running"), flush=True)
    restored = ns["ubuntu"].inventory()
    gate["save"]("ubuntu-restored.json", restored)
    assert restored == json.loads((gate["OUT"] / "ubuntu-baseline.json").read_text())
    print(ns["ubuntu"].virsh("snapshot-delete", ns["ubuntu"].VM, ns["SNAP"]), flush=True)
    gate["save"]("cleanup-result.json", {
        "ubuntu_baseline_exact_match": True,
        "debian_baseline_exact_match": True,
        "dedicated_debian_secret_service_item_removed": True,
        "empty_local_probe_directory_removed": True,
        "ubuntu_state": ns["ubuntu"].virsh("domstate", ns["ubuntu"].VM).strip(),
        "debian_state": ns["debian"].virsh("domstate", ns["debian"].VM).strip(),
    })
    (gate["OUT"] / "SHA256SUMS").write_text("".join(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + str(path.relative_to(gate["OUT"])) + "\n"
        for path in sorted(gate["OUT"].rglob("*")) if path.is_file() and path.name != "SHA256SUMS"
    ))
    print("Both VM baselines restored after removing the exact empty local probe directory.", flush=True)


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "start-watch":
        start_watch()
    elif action == "watch":
        gate["network"].watch()
    elif action in {"prepare", "setup", "resume-setup", "collect", "cleanup", "inspect", "mark-nonqualifying", "mark-pre-mutation-failure", "resume-cleanup"}:
        if action == "prepare": gate["prepare"]()
        elif action == "setup": gate["scope"]["setup"]()
        elif action == "resume-setup": gate["resume_setup_after_transfer_path_fix"]()
        elif action == "collect": gate["scope"]["collect"]()
        elif action == "cleanup": gate["network"].cleanup()
        elif action == "inspect": gate["ns"]["inspect"]()
        elif action == "mark-pre-mutation-failure": mark_pre_mutation_failure()
        elif action == "resume-cleanup": resume_cleanup_after_empty_local_probe_dir()
        else: gate["mark_nonqualifying_no_cut"]()
    elif action in {"launch", "status"}:
        gate["ns"][action]("commit")
    else:
        raise ValueError(action)
