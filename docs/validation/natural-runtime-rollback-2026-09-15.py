"""Normal GUI SSH rollback caused by a real temporary runtime outage.

The production validator is not replaced and no validation result is injected.
An Ubuntu-side watcher temporarily renames the real OpenCode binary after it
observes the approved config mutation, then restores it after rollback restores
the original config hash.  Never relaunch a saved Apply or watcher PID.
"""
import base64
import hashlib
import json
from pathlib import Path
import re
import sys


REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "docs/validation/full-gui-ssh-2026-09-13.py"
source = BASE.read_text()
source = source.replace("phase6-full-gui", "phase6-natural-rollback")
source = source.replace("full-gui-ssh-2026-09-13", "natural-runtime-rollback-2026-09-15")
source = source.replace("20260913", "20260915")
source = source.replace("local-master-v1", "phase6-natural-rollback-20260915")
source = source.replace("['commit']", "['rollback']")
source = source.replace("{'commit':'committed'}", "{'rollback':'rolled_back'}")
source = source.replace("OUT/'commit-results.png'", "OUT/'rollback-results.png'")
gate = {"__file__": str(BASE), "__name__": "natural_runtime_rollback_lifecycle"}
exec(compile(source, str(BASE), "exec"), gate)
ns = gate["ns"]
OUT = gate["OUT"]
old_guest = ns["GUEST"]
GUEST = "/tmp/phase6-natural-rollback-20260915"
ns["GUEST"] = GUEST
ns["SNAP"] = "phase6-natural-rollback-20260915"
ns["ENV"] = [value.replace(old_guest, GUEST) for value in ns["ENV"]]
ns["menu"].TARGET = GUEST + ".deb"
gate["GUEST"] = GUEST

LOCAL_DEB = Path(
    "/tmp/llm-manager-candidate-7f846f5-20260915/llm-manager_0.1.0_all.deb"
)
LOCAL_HASH = "ecc099a6ae285d99fe1990cc1335dbff10f17019a766d8527566819f850eba9a"
REMOTE_DEB = Path(
    "/tmp/llm-manager-candidate-7f846f5-20260915/"
    "llm-manager-remote-helper_0.1.0_all.deb"
)
REMOTE_HASH = "4ca5e152c2738c1fa2ca92eaf5ab4802ecfd88438f15f54780117f463b9edbb2"
ns["REMOTE"] = REMOTE_DEB
ns["REMOTE_HASH"] = REMOTE_HASH
ns["menu"].DEB = LOCAL_DEB
ns["menu"].DIGEST = LOCAL_HASH
ns["ARCHIVE"] = Path("/tmp/phase6-full-gui-opencode-1.18.25.tar.gz")


def save(name: str, value) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


TRANSPORT_OBSERVER = r'''
from llm_manager.infrastructure.process import SubprocessRunner
original_run=SubprocessRunner.run
transport_events=[]
def measured_run(self,request,cancellation):
 result=original_run(self,request,cancellation)
 if request.correlation_id in {'ssh.user_apply.invoke','ssh.user_rollback.invoke','ssh.staging.download'}:
  transport_events.append({'correlation_id':request.correlation_id,'exit_code':result.exit_code,
   'timed_out':result.timed_out,'duration_ms':result.duration_ms,'stderr':result.stderr_redacted})
  (OUT/'transport-events.json').write_text(json.dumps(transport_events,indent=2)+'\n')
 return result
SubprocessRunner.run=measured_run
'''

HARNESS = gate["HARNESS"]
HARNESS = HARNESS.replace("'evidence'/'commit'", "'evidence'/'rollback'")
HARNESS = HARNESS.replace("history=[]", "history=[]\n" + TRANSPORT_OBSERVER)
HARNESS = HARNESS.replace(
    "'plan_injected':False,'approval_injected':False,'transport_injected':False",
    "'plan_injected':False,'approval_injected':False,'transport_injected':False,"
    "'validation_injected':False,'external_runtime_outage':True,"
    "'transport_events':transport_events",
)
HARNESS = HARNESS.replace(
    "QApplication.instance().exit(0 if outcome.status.value=='committed' else 1)",
    "QApplication.instance().exit(0 if outcome.status.value=='rolled_back' else 1)",
)
compile(HARNESS, "natural-runtime-rollback-observer.py", "exec")
gate["HARNESS"] = HARNESS


WATCHER = r'''import hashlib,json,os,time
from pathlib import Path
config=Path('/home/yoshimi/.config/opencode/opencode.jsonc')
binary=Path('/usr/local/bin/opencode')
held=Path('/usr/local/bin/opencode.phase6-natural-rollback')
root=Path('/tmp/phase6-natural-rollback-20260915')
result=root/'runtime-watcher-result.json'
assert config.is_file() and not config.is_symlink()
assert binary.is_file() and not binary.is_symlink() and not held.exists()
before=hashlib.sha256(config.read_bytes()).hexdigest()
binary_hash=hashlib.sha256(binary.read_bytes()).hexdigest()
binary_mode=binary.stat().st_mode & 0o777
started=time.time_ns()
deadline=time.monotonic()+1800
detected=None
restored=None
try:
 while time.monotonic()<deadline:
  current=hashlib.sha256(config.read_bytes()).hexdigest()
  if current!=before:
   detected={'wall_time_ns':time.time_ns(),'after_sha256':current}
   os.rename(binary,held)
   break
  time.sleep(0.001)
 else: raise TimeoutError('approved config mutation not observed')
 while time.monotonic()<deadline:
  current=hashlib.sha256(config.read_bytes()).hexdigest()
  if current==before:
   assert held.is_file() and not held.is_symlink() and not binary.exists()
   os.rename(held,binary)
   assert hashlib.sha256(binary.read_bytes()).hexdigest()==binary_hash
   assert binary.stat().st_mode & 0o777==binary_mode
   restored={'wall_time_ns':time.time_ns(),'config_sha256':current}
   break
  time.sleep(0.001)
 else: raise TimeoutError('rollback restoration not observed')
 result.write_text(json.dumps({'status':'restored','started_wall_time_ns':started,
  'before_sha256':before,'binary_sha256':binary_hash,'binary_mode':oct(binary_mode),
  'mutation_detected':detected,'runtime_restored':restored},indent=2)+'\n')
except BaseException as error:
 if held.is_file() and not held.is_symlink() and not binary.exists(): os.rename(held,binary)
 result.write_text(json.dumps({'status':'failed','error':type(error).__name__,
  'before_sha256':before,'binary_sha256':binary_hash},indent=2)+'\n')
 raise
'''


def prepare() -> None:
    ns["prepare"]()
    save("candidate-identity.json", {
        "source_commit": "7f846f5fb1134be7df06490f30a5216ab414ae0d",
        "local_sha256": LOCAL_HASH,
        "remote_sha256": REMOTE_HASH,
        "scope": "pre-final functional candidate; later release metadata commits are not embedded",
    })


def setup() -> None:
    gate["setup"]()
    watcher = OUT / "runtime-watcher.py"
    watcher.write_text(WATCHER)
    ns["ubuntu"].transfer(str(watcher), GUEST + "/runtime-watcher.py")
    pid = ns["ubuntu"].qga("guest-exec", {
        "path": "/usr/bin/python3",
        "arg": ["-I", GUEST + "/runtime-watcher.py"],
        "capture-output": True,
    })["pid"]
    save("runtime-watcher-pid.json", {"pid": pid})
    print("Normal GUI and real-runtime outage watcher ready; no Apply started.", flush=True)


def launch() -> None:
    assert not (OUT / "rollback-pid.json").exists(), "never resend Apply"
    ns["launch"]("rollback")


def status() -> None:
    ns["status"]("rollback")


def watcher_status(require_exit: bool = False) -> dict:
    saved = OUT / "runtime-watcher-exit.json"
    if saved.exists():
        result = json.loads(saved.read_text())
    else:
        pid = json.loads((OUT / "runtime-watcher-pid.json").read_text())["pid"]
        result = ns["ubuntu"].qga("guest-exec-status", {"pid": pid})
        if result.get("exited"):
            save(saved.name, result)
    if require_exit:
        assert result.get("exited") and result.get("exitcode") == 0, result
    print(json.dumps(result, indent=2), flush=True)
    return result


def _download_evidence() -> None:
    names = json.loads(ns["debian"].python(
        "from pathlib import Path; import json; print(json.dumps([f.name for f in Path("
        + repr(GUEST + "/evidence/rollback")
        + ").iterdir() if f.is_file()]))"
    ))
    for name in names:
        assert Path(name).name == name
        handle = ns["debian"].qga("guest-file-open", {
            "path": GUEST + "/evidence/rollback/" + name, "mode": "r",
        })
        data = bytearray()
        try:
            while True:
                block = ns["debian"].qga("guest-file-read", {"handle": handle, "count": 65536})
                data.extend(base64.b64decode(block.get("buf-b64", "")))
                if block.get("eof"):
                    break
        finally:
            ns["debian"].qga("guest-file-close", {"handle": handle})
        (OUT / ("rollback-" + name)).write_bytes(data)


def collect() -> None:
    ns["status"]("rollback")
    assert (OUT / "rollback-exit.json").exists()
    watcher_status(require_exit=True)
    _download_evidence()
    result = json.loads((OUT / "rollback-result.json").read_text())
    assert result["status"] == "rolled_back", result
    assert not result["plan_injected"] and not result["approval_injected"]
    assert not result["transport_injected"] and not result["validation_injected"]
    events = result["transport_events"]
    assert sum(e["correlation_id"] == "ssh.user_apply.invoke" for e in events) == 1
    assert sum(e["correlation_id"] == "ssh.user_rollback.invoke" for e in events) == 1
    validations = {item["check"]: item for item in result["validations"]}
    assert validations["opencode.installed"]["status"] == "failed", validations
    assert validations["opencode.installed"]["actual"] == "not_installed", validations
    watcher = json.loads(ns["ubuntu"].python(
        "from pathlib import Path; print(Path(" + repr(GUEST + "/runtime-watcher-result.json")
        + ").read_text(),end='')"
    ))
    save("runtime-watcher-result.json", watcher)
    assert watcher["status"] == "restored"
    value = json.loads(ns["ubuntu"].python(r'''from pathlib import Path
import hashlib,json,subprocess
p=Path('/home/yoshimi/.config/opencode/opencode.jsonc')
b=Path('/usr/local/bin/opencode')
print(json.dumps({'config_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
 'config':json.loads(p.read_text()),'binary_sha256':hashlib.sha256(b.read_bytes()).hexdigest(),
 'binary_mode':oct(b.stat().st_mode & 0o777),'held_exists':Path('/usr/local/bin/opencode.phase6-natural-rollback').exists(),
 'version':subprocess.check_output([str(b),'--version'],text=True).strip()}))'''))
    save("target-and-runtime-after.json", value)
    assert value["config_sha256"] == watcher["before_sha256"]
    assert value["binary_sha256"] == watcher["binary_sha256"]
    assert value["binary_mode"] == watcher["binary_mode"] == "0o755"
    assert not value["held_exists"] and value["version"] == "1.18.25"
    code = "from pathlib import Path; import json; p=Path(" + repr(GUEST + "/state/llm-manager") + "); print(json.dumps({str(f.relative_to(p)):json.loads(f.read_text()) for pattern in ['journal/*.json','remote-recovery/receipts/*.json','backups/*/*/manifest.json'] for f in p.glob(pattern)}))"
    save("operation-evidence.json", json.loads(ns["debian"].python(code)))
    print("Real runtime outage produced one production validation failure and one verified rollback.", flush=True)


def inspect() -> None:
    ns["inspect"]()
    watcher_status()


def _secret_call(object_path: str, method: str, *args: str) -> str:
    return ns["debian"].execute("/usr/sbin/runuser", [
        "-u", "user", "--", "/usr/bin/env",
        "XDG_RUNTIME_DIR=/run/user/1000",
        "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
        "/usr/bin/gdbus", "call", "--session",
        "--dest", "org.freedesktop.secrets", "--object-path", object_path,
        "--method", method, *args,
    ])


def secret_status(name: str = "production-key-status.json") -> list[dict]:
    searched = _secret_call(
        "/org/freedesktop/secrets",
        "org.freedesktop.Secret.Service.SearchItems",
        "{'application': 'llm-manager', 'purpose': 'backup-encryption', "
        "'key-reference': 'local-master-v1'}",
    )
    paths = re.findall(r"objectpath '([^']+)'", searched)
    items = []
    for path in paths:
        properties = _secret_call(
            path, "org.freedesktop.DBus.Properties.GetAll", "org.freedesktop.Secret.Item"
        )
        items.append({"path": path, "properties_gvariant": properties})
    save(name, items)
    print(json.dumps(items, indent=2), flush=True)
    return items


def secret_cleanup() -> None:
    items = secret_status("production-key-before-correction.json")
    assert len(items) == 1, items
    properties = items[0]["properties_gvariant"]
    for expected in ("application", "llm-manager", "purpose", "backup-encryption",
                     "key-reference", "local-master-v1"):
        assert expected in properties, items
    _secret_call(items[0]["path"], "org.freedesktop.Secret.Item.Delete")
    after = secret_status("production-key-after-cleanup-audit.json")
    assert not after
    cleanup_path = OUT / "cleanup-result.json"
    cleanup_result = json.loads(cleanup_path.read_text())
    cleanup_result["dedicated_debian_secret_service_item_removed"] = False
    cleanup_result["gate_created_local_master_v1_removed_after_reference_audit"] = True
    cleanup_result["cleanup_claim_corrected"] = True
    save(cleanup_path.name, cleanup_result)
    (OUT / "SHA256SUMS").write_text("".join(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + str(path.relative_to(OUT)) + "\n"
        for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"
    ))


def cleanup() -> None:
    watcher_status(require_exit=True)
    ns["cleanup"]()
    # Production composition always uses local-master-v1.  The inherited
    # harness searches a phase-specific reference, so audit and remove the
    # item whose absence was asserted immediately before this Gate.
    secret_cleanup()
    (OUT / "SHA256SUMS").write_text("".join(
        hashlib.sha256(path.read_bytes()).hexdigest() + "  " + str(path.relative_to(OUT)) + "\n"
        for path in sorted(OUT.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"
    ))


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "prepare":
        prepare()
    elif action == "setup":
        setup()
    elif action == "launch":
        launch()
    elif action == "status":
        status()
    elif action == "watcher-status":
        watcher_status()
    elif action == "collect":
        collect()
    elif action == "inspect":
        inspect()
    elif action == "secret-status":
        secret_status()
    elif action == "secret-cleanup":
        secret_cleanup()
    elif action == "cleanup":
        cleanup()
    else:
        raise ValueError(action)
