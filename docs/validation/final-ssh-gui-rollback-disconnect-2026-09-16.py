"""Final artifact normal-GUI natural rollback with a live NIC reply cut.

The production validator observes a real temporary OpenCode outage.  Apply is
delivered normally; only the successful rollback response is delayed while the
Ubuntu NIC is down.  No mutation or immutable-result read is retried.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "docs/validation/natural-runtime-rollback-2026-09-15.py"
source = BASE.read_text()
source = source.replace("phase6-natural-rollback", "phase6-final-ssh-rollback-net")
source = source.replace(
    "natural-runtime-rollback-2026-09-15", "final-ssh-gui-rollback-disconnect-2026-09-16"
)
source = source.replace("20260915", "20260916")
source = source.replace(
    "/tmp/llm-manager-candidate-7f846f5-20260915/llm-manager_0.1.0_all.deb",
    "/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager_0.1.0_all.deb",
)
source = source.replace(
    "ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a",
    "63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1",
)
source = source.replace(
    "/tmp/llm-manager-candidate-7f846f5-20260915/llm-manager-remote-helper_0.1.0_all.deb",
    "/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager-remote-helper_0.1.0_all.deb",
)
source = source.replace(
    "4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2",
    "ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4",
)
source = source.replace(
    '"source_commit": "7f846f5fb1134be7df06490f30a5216ab414ae0d"',
    '"source_commit": "5b7d4de03e495fe630deab952de043f945a22bd7"',
)
source = source.replace(
    '"scope": "pre-final functional candidate; later release metadata commits are not embedded"',
    '"scope": "final artifact; unsigned and unpublished"',
)
natural = {"__file__": str(BASE), "__name__": "final_ssh_rollback_disconnect_lifecycle"}
exec(compile(source, str(BASE), "exec"), natural)

ns = natural["ns"]
OUT = natural["OUT"]
GUEST = natural["GUEST"]
ubuntu = ns["ubuntu"]
MAC = "52:54:00:f8:49:29"
READY = GUEST + "/hold/rollback-ready.json"
LOCAL_DEB = Path("/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager_0.1.0_all.deb")
LOCAL_HASH = "63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1"
REMOTE_DEB = Path("/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager-remote-helper_0.1.0_all.deb")
REMOTE_HASH = "ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4"
natural["LOCAL_DEB"] = LOCAL_DEB
natural["LOCAL_HASH"] = LOCAL_HASH
natural["REMOTE_DEB"] = REMOTE_DEB
natural["REMOTE_HASH"] = REMOTE_HASH
ns["REMOTE"] = REMOTE_DEB
ns["REMOTE_HASH"] = REMOTE_HASH
ns["menu"].DEB = LOCAL_DEB
ns["menu"].DIGEST = LOCAL_HASH

RELAY = r'''import json,subprocess,sys,time
from pathlib import Path
assert len(sys.argv)==5
assert sys.argv[1:3]==['/usr/bin/llm-manager-remote-helper','user-rollback']
result=subprocess.run(sys.argv[1:],capture_output=True,timeout=30)
observation={'exit_code':result.returncode,'stdout':result.stdout.decode('utf-8','replace'),'stderr':result.stderr.decode('utf-8','replace')}
with Path(__file__).with_name('helper-observation.json').open('x') as f: json.dump(observation,f)
if result.returncode==0:
 decoded=json.loads(observation['stdout'])
 marker={'verb':'user-rollback','request_id':sys.argv[3],'request_hash':sys.argv[4],
  'helper_exit_code':result.returncode,'restored_hash':decoded.get('restored_hash')}
 with Path(__file__).with_name('rollback-ready.json').open('x') as f: json.dump(marker,f)
 time.sleep(10)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
'''

old = """def measured_run(self,request,cancellation):
 result=original_run(self,request,cancellation)
"""
new = """def measured_run(self,request,cancellation):
 from dataclasses import replace
 import shlex
 if request.correlation_id=='ssh.user_rollback.invoke':
  argv=request.argv
  assert argv[0]=='ssh'
  command='python3 '+shlex.quote(RELAY_PATH)+' '+argv[-1]
  request=replace(request,argv=('ssh','-o','ServerAliveInterval=1','-o','ServerAliveCountMax=1',*argv[1:-1],command))
 result=original_run(self,request,cancellation)
"""
HARNESS = natural["gate"]["HARNESS"]
assert HARNESS.count(old) == 1
HARNESS = HARNESS.replace("history=[]", "history=[]\nRELAY_PATH=" + repr(GUEST + "/hold/helper.py"), 1)
HARNESS = HARNESS.replace(old, new, 1)
HARNESS = HARNESS.replace(
    "'transport_injected':False,",
    "'transport_injected':True,'transport_condition':'rollback stdout relay and short keepalive; actual NIC cut',",
    1,
)
compile(HARNESS, "final-ssh-rollback-disconnect-observer.py", "exec")
natural["gate"]["HARNESS"] = HARNESS


def save(name: str, value) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def setup() -> None:
    natural["setup"]()
    relay = OUT / "hold-rollback-response.py"
    relay.write_text(RELAY)
    ubuntu.execute("/usr/bin/install", ["-d", "-m", "0700", "-o", "1000", "-g", "1000", GUEST + "/hold"])
    ubuntu.transfer(str(relay), GUEST + "/hold/helper.py")
    ubuntu.execute("/bin/chmod", ["0644", GUEST + "/hold/helper.py"])
    print("Runtime watcher and rollback response relay ready; start the NIC watcher before GUI launch.", flush=True)


def watch() -> None:
    assert not (OUT / "network.json").exists()
    assert ubuntu.virsh("domif-getlink", ubuntu.VM, MAC).strip() == MAC + " up"
    print("Watcher ready; waiting for successful rollback helper completion.", flush=True)
    deadline = time.monotonic() + 900
    marker = observation = None
    while time.monotonic() < deadline:
        raw = ubuntu.python(
            "import json,time; from pathlib import Path; p=Path(" + repr(READY) + "); "
            "print(json.dumps({'marker':json.loads(p.read_text()),'age':time.time()-p.stat().st_mtime}) if p.exists() else 'null')"
        )
        observation = json.loads(raw)
        marker = observation["marker"] if observation else None
        if marker:
            break
        time.sleep(0.25)
    assert marker and marker["helper_exit_code"] == 0, "no successful rollback marker; no network cut"
    if not 0 <= observation["age"] < 2:
        save("network-not-cut.json", {"reason": "stale rollback marker", "observation": observation})
        raise RuntimeError("stale marker; refusing NIC cut")
    save("rollback-helper-completion.json", marker)
    command = (
        "import subprocess,time; time.sleep(7); "
        "subprocess.run(['virsh','domif-setlink','ubuntu26.04','52:54:00:f8:49:29','up'],check=True,timeout=10)"
    )
    watchdog = subprocess.Popen(
        [sys.executable, "-I", "-c", command], start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    record = {"helper_marker": marker, "link_before": "up"}
    try:
        ubuntu.virsh("domif-setlink", ubuntu.VM, MAC, "down")
        record["down_at_monotonic"] = time.monotonic()
        record["link_during"] = ubuntu.virsh("domif-getlink", ubuntu.VM, MAC).strip()
        assert record["link_during"] == MAC + " down"
        time.sleep(4)
    finally:
        ubuntu.virsh("domif-setlink", ubuntu.VM, MAC, "up")
        record["up_at_monotonic"] = time.monotonic()
        _, error = watchdog.communicate(timeout=15)
        record["watchdog_exit"] = watchdog.returncode
        record["watchdog_stderr"] = error.decode()
        record["link_after"] = ubuntu.virsh("domif-getlink", ubuntu.VM, MAC).strip()
        save("network.json", record)
    assert record["link_after"] == MAC + " up" and watchdog.returncode == 0
    print(json.dumps(record, indent=2), flush=True)


def collect_natural_with_transport_observer() -> None:
    """Collect the natural rollback while accepting only the documented transport relay."""
    ns["status"]("rollback")
    assert (OUT / "rollback-exit.json").exists()
    natural["watcher_status"](require_exit=True)
    natural["_download_evidence"]()
    result = json.loads((OUT / "rollback-result.json").read_text())
    assert result["status"] == "rolled_back", result
    assert not result["plan_injected"] and not result["approval_injected"]
    assert result["transport_injected"] and not result["validation_injected"]
    assert result["transport_condition"] == "rollback stdout relay and short keepalive; actual NIC cut"
    assert result.get("remote_sudo_timeout_seconds") == 600
    assert result.get("remote_sudo_timeout_injected") is True
    events = result["transport_events"]
    assert sum(e["correlation_id"] == "ssh.user_apply.invoke" for e in events) == 1
    assert sum(e["correlation_id"] == "ssh.user_rollback.invoke" for e in events) == 1
    validations = {item["check"]: item for item in result["validations"]}
    assert validations["opencode.installed"]["status"] == "failed", validations
    assert validations["opencode.installed"]["actual"] == "not_installed", validations
    watcher = json.loads(ubuntu.python(
        "from pathlib import Path; print(Path(" + repr(GUEST + "/runtime-watcher-result.json")
        + ").read_text(),end='')"
    ))
    save("runtime-watcher-result.json", watcher)
    assert watcher["status"] == "restored"
    value = json.loads(ubuntu.python(r'''from pathlib import Path
import hashlib,json,subprocess
p=Path('/home/yoshimi/.config/opencode/opencode.jsonc')
b=Path('/usr/local/bin/opencode')
print(json.dumps({'config_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
 'config':json.loads(p.read_text()),'binary_sha256':hashlib.sha256(b.read_bytes()).hexdigest(),
 'binary_mode':oct(b.stat().st_mode & 0o777),'held_exists':Path('/usr/local/bin/opencode.phase6-final-ssh-rollback-net').exists(),
 'version':subprocess.check_output([str(b),'--version'],text=True).strip()}))'''))
    save("target-and-runtime-after.json", value)
    assert value["config_sha256"] == watcher["before_sha256"]
    assert value["binary_sha256"] == watcher["binary_sha256"]
    assert value["binary_mode"] == watcher["binary_mode"] == "0o755"
    assert not value["held_exists"] and value["version"] == "1.18.25"
    code = (
        "from pathlib import Path; import json; p=Path(" + repr(GUEST + "/state/llm-manager")
        + "); print(json.dumps({str(f.relative_to(p)):json.loads(f.read_text()) "
        "for pattern in ['journal/*.json','remote-recovery/receipts/*.json','backups/*/*/manifest.json'] "
        "for f in p.glob(pattern)}))"
    )
    save("operation-evidence.json", json.loads(ns["debian"].python(code)))
    print("Real runtime outage produced one production validation failure and one verified rollback.", flush=True)


def collect() -> None:
    collect_natural_with_transport_observer()
    result = json.loads((OUT / "rollback-result.json").read_text())
    events = result["transport_events"]
    rollback = [e for e in events if e["correlation_id"] == "ssh.user_rollback.invoke"]
    assert len(rollback) == 1 and rollback[0]["exit_code"] == 255 and not rollback[0]["timed_out"]
    assert result["status"] == "rolled_back"
    link = json.loads((OUT / "network.json").read_text())
    assert link["link_after"] == MAC + " up" and link["watchdog_exit"] == 0
    observation = json.loads(ubuntu.python(
        "from pathlib import Path; print(Path(" + repr(GUEST + "/hold/helper-observation.json") + ").read_text())"
    ))
    assert observation["exit_code"] == 0
    save("helper-observation.json", observation)
    print("Natural rollback SSH exit 255 and post-recovery immutable-result reconciliation verified.", flush=True)


def cleanup() -> None:
    assert json.loads((OUT / "network.json").read_text())["link_after"] == MAC + " up"
    natural["cleanup"]()


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "prepare":
        natural["prepare"]()
    elif action == "setup":
        setup()
    elif action == "watch":
        watch()
    elif action == "launch":
        natural["launch"]()
    elif action == "status":
        natural["status"]()
    elif action == "watcher-status":
        natural["watcher_status"]()
    elif action == "collect":
        collect()
    elif action == "inspect":
        natural["inspect"]()
    elif action == "cleanup":
        cleanup()
    else:
        raise ValueError(action)
