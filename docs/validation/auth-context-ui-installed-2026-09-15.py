"""Installed-candidate visual Gate for LOCAL/REMOTE authentication context.

The remote phase runs one normal GUI SSH Apply operation.  The local phase
opens the production read-only root-backup inventory PolicyKit action and must
be cancelled after its message is observed.  Never relaunch either saved PID.
"""
import hashlib
import json
from pathlib import Path
import sys
import time


REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "docs/validation/full-gui-ssh-2026-09-13.py"
source = BASE.read_text()
source = source.replace("phase6-full-gui", "phase6-auth-context-ui")
source = source.replace(
    "full-gui-ssh-2026-09-13", "auth-context-ui-installed-2026-09-15"
)
source = source.replace("20260913", "20260915")
gate = {"__file__": str(BASE), "__name__": "auth_context_ui_lifecycle"}
exec(compile(source, str(BASE), "exec"), gate)
ns = gate["ns"]
OUT = gate["OUT"]
old_guest = ns["GUEST"]
GUEST = "/tmp/phase6-auth-context-ui-20260915"
ns["GUEST"] = GUEST
ns["SNAP"] = "phase6-auth-context-ui-20260915"
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
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def prepare() -> None:
    ns["prepare"]()
    save(
        "candidate-identity.json",
        {
            "source_commit": "7f846f5fb1134be7df06490f30a5216ab414ae0d",
            "local_sha256": LOCAL_HASH,
            "remote_sha256": REMOTE_HASH,
        },
    )
    save(
        "debian/artifact-identity.json",
        {
            "source_commit": "7f846f5fb1134be7df06490f30a5216ab414ae0d",
            "sha256": LOCAL_HASH,
            "package": "llm-manager",
            "version": "0.1.0",
        },
    )


def setup() -> None:
    existing = json.loads(ns["user"](ns["debian"], "user", r'''import json,secretstorage
c=secretstorage.dbus_init()
a={'application':'llm-manager','purpose':'backup-encryption','key-reference':'local-master-v1'}
print(json.dumps([{'attributes':i.get_attributes(),'label':i.get_label(),'locked':i.is_locked()}
 for i in secretstorage.search_items(c,a)]))
'''))
    save("production-key-before.json", existing)
    # The normal-GUI test uses its own phase6-auth-context-ui reference.  An
    # existing production key is neither read nor deleted by this Gate.
    ns["setup"]()
    ns["user"](ns["ubuntu"], "yoshimi", r'''from pathlib import Path
p=Path('/home/yoshimi/.config/opencode/opencode.jsonc')
assert not p.exists() and not p.is_symlink()
p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
with p.open('x') as f: f.write('{"autoupdate": false, "compaction": {"auto": false, "prune": false}}\n')
p.chmod(0o600)
''')
    harness = gate["HARNESS"]
    compile(harness, "auth-context-ui-observer.py", "exec")
    (OUT / "gate.py").write_text(harness)
    ns["debian"].transfer(str(OUT / "gate.py"), GUEST + "/gate.py")
    print("Isolated SSH and normal GUI observer ready; no Apply started.", flush=True)


def launch_remote() -> None:
    assert not (OUT / "commit-pid.json").exists(), "never resend remote Apply"
    ns["launch"]("commit")


def collect_remote() -> None:
    gate["collect"]()


def launch_local() -> None:
    path = OUT / "local-policykit-pid.json"
    assert not path.exists(), "never relaunch local PolicyKit request"
    pid = ns["debian"].qga(
        "guest-exec",
        {
            "path": "/usr/sbin/runuser",
            "arg": [
                "-u", "user", "--", "/usr/bin/env", *ns["ENV"],
                "/usr/bin/pkexec", "/usr/bin/llm-manager-restore-review", "list",
            ],
            "capture-output": True,
        },
    )["pid"]
    save(path.name, {"pid": pid, "operation": "read-only root backup inventory"})
    print(f"Started local PolicyKit PID {pid}; observe once, then cancel.", flush=True)


def launch_local_desktop() -> None:
    """Retry only after the direct request exited 127 before authorization."""
    direct = json.loads((OUT / "local-policykit-exit.json").read_text())
    assert direct.get("exited") and direct.get("exitcode") == 127, direct
    path = OUT / "local-policykit-desktop-pid.json"
    assert not path.exists(), "never relaunch desktop PolicyKit request"
    pid = ns["debian"].qga(
        "guest-exec",
        {
            "path": "/usr/sbin/runuser",
            "arg": [
                "-u", "user", "--", "/usr/bin/env", *ns["ENV"],
                "/usr/bin/gnome-terminal",
                "--title=LLM-Manager — LOCAL PolicyKit check",
                "--", "/usr/bin/pkexec",
                "/usr/bin/llm-manager-restore-review", "list",
            ],
            "capture-output": True,
        },
    )["pid"]
    save(path.name, {
        "pid": pid,
        "operation": "read-only root backup inventory from active desktop terminal",
        "prior_direct_request": "rejected before authorization with exit 127",
    })
    print(f"Started desktop PolicyKit launcher PID {pid}; observe once, then cancel.", flush=True)


def local_status() -> None:
    saved = OUT / "local-policykit-exit.json"
    if saved.exists():
        print(saved.read_text(), end="")
        return
    pid = json.loads((OUT / "local-policykit-pid.json").read_text())["pid"]
    result = ns["debian"].qga("guest-exec-status", {"pid": pid})
    if result.get("exited"):
        save(saved.name, result)
        print(saved.read_text(), end="")
    else:
        print("Local PolicyKit request is still running; do not relaunch.", flush=True)


ATSPI = r'''import json,time
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
Atspi.init()
def safe(call,default=None):
 try:return call()
 except Exception:return default
def walk(node,depth=0):
 yield node
 if depth>=12:return
 for i in range(safe(node.get_child_count,0) or 0):
  child=safe(lambda:node.get_child_at_index(i))
  if child is not None:yield from walk(child,depth+1)
desktop=Atspi.get_desktop(0); rows=[]
for i in range(desktop.get_child_count()):
 app=desktop.get_child_at_index(i); app_name=safe(app.get_name,'') or ''
 for node in walk(app):
  name=safe(node.get_name,'') or ''
  if name and any(token.lower() in name.lower() for token in
      ('llm-manager','remote','local authentication','authenticate','authorization')):
   rows.append({'application':app_name,'name':name,
                'role':safe(node.get_role_name,'unknown') or 'unknown'})
print(json.dumps(rows,ensure_ascii=False))
'''


def observe(stage: str) -> None:
    expected = {
        "remote": "LLM-Manager — REMOTE sudo — phase6-auth-context-ui",
        "local": "LOCAL authentication",
    }[stage]
    command = [
        "-u", "user", "--", "/usr/bin/env", *ns["ENV"],
        "/usr/bin/python3", "-I", "-c", ATSPI,
    ]
    rows = []
    for _ in range(40):
        rows = json.loads(ns["debian"].execute("/usr/sbin/runuser", command))
        if any(expected in row["name"] for row in rows):
            break
        time.sleep(0.5)
    else:
        raise RuntimeError(f"authentication context not visible: {expected!r}; rows={rows!r}")
    save(f"{stage}-atspi.json", rows)
    ns["debian"].virsh("screenshot", ns["debian"].VM, str(OUT / f"{stage}-screen.png"))
    print(json.dumps([row for row in rows if expected in row["name"]], ensure_ascii=False))


def _verify_local_completion() -> None:
    assert (OUT / "local-atspi.json").exists()
    remaining = json.loads(ns["debian"].python(r'''import json
from pathlib import Path
rows=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try:
  argv=[x.decode(errors='replace') for x in (p/'cmdline').read_bytes().split(bytes([0]))[:-1]]
  if any(x.endswith('/llm-manager-restore-review') or x.endswith('/pkexec') for x in argv):
   rows.append({'pid':int(p.name),'argv':argv})
 except (FileNotFoundError,PermissionError): pass
print(json.dumps(rows))
'''))
    save("local-policykit-remaining.json", remaining)
    assert not remaining, remaining


def _verify_production_key_after() -> None:
    value = json.loads(ns["user"](ns["debian"], "user", r'''import json,re,subprocess
def call(method,*args):
 p=subprocess.run(['/usr/bin/gdbus','call','--session','--dest','org.freedesktop.secrets',
  '--object-path','/org/freedesktop/secrets','--method',method,*args],
  capture_output=True,text=True,check=True)
 return p.stdout.strip()
production="{'application': 'llm-manager', 'purpose': 'backup-encryption', 'key-reference': 'local-master-v1'}"
dedicated="{'application': 'llm-manager', 'purpose': 'backup-encryption', 'key-reference': 'phase6-auth-context-ui-20260913'}"
search=call('org.freedesktop.Secret.Service.SearchItems',production)
dedicated_search=call('org.freedesktop.Secret.Service.SearchItems',dedicated)
paths=re.findall(r'/org/freedesktop/secrets/collection/[A-Za-z0-9_/-]+',search)
assert len(paths)==1 and '@ao []' in search,search
assert not re.findall(r'/org/freedesktop/secrets/collection/[A-Za-z0-9_/-]+',dedicated_search),dedicated_search
p=subprocess.run(['/usr/bin/gdbus','call','--session','--dest','org.freedesktop.secrets',
 '--object-path',paths[0],'--method','org.freedesktop.DBus.Properties.GetAll',
 'org.freedesktop.Secret.Item'],capture_output=True,text=True,check=True)
print(json.dumps({'search':search,'dedicated_search':dedicated_search,
 'object_path':paths[0],'properties':p.stdout.strip()}))
'''))
    before = json.loads((OUT / "production-key-before.json").read_text())
    assert len(before) == 1
    expected = before[0]
    properties = value["properties"]
    assert "'Locked': <false>" in properties
    assert f"'Label': <'{expected['label']}'>" in properties
    for key, item in expected["attributes"].items():
        assert f"'{key}': '{item}'" in properties
    save("production-key-after.json", {
        **expected,
        "object_path": value["object_path"],
        "nonsecret_properties_match_before": True,
        "dedicated_key_absent": True,
    })
    save("production-key-after-gdbus.json", value)


def finalize_cleanup() -> None:
    result = json.loads((OUT / "cleanup-result.json").read_text())
    assert result["ubuntu_baseline_exact_match"]
    assert result["debian_baseline_exact_match"]
    _verify_local_completion()
    _verify_production_key_after()
    (OUT / "SHA256SUMS").write_text("".join(
        hashlib.sha256(path.read_bytes()).hexdigest()
        + "  " + str(path.relative_to(OUT)) + "\n"
        for path in sorted(OUT.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS"
    ))
    print("Cleanup finalized; baselines and existing production key preserved.", flush=True)


def remove_prior_performance_key() -> None:
    """Remove the exact orphan created during the 2026-09-14 performance Gate."""
    value = json.loads(ns["user"](ns["debian"], "user", r'''import json,re,subprocess
def run(object_path,method,*args):
 p=subprocess.run(['/usr/bin/gdbus','call','--session','--dest','org.freedesktop.secrets',
  '--object-path',object_path,'--method',method,*args],capture_output=True,text=True,check=True)
 return p.stdout.strip()
query="{'application': 'llm-manager', 'purpose': 'backup-encryption', 'key-reference': 'local-master-v1'}"
before=run('/org/freedesktop/secrets','org.freedesktop.Secret.Service.SearchItems',query)
paths=re.findall(r'/org/freedesktop/secrets/collection/[A-Za-z0-9_/-]+',before)
assert len(paths)==1 and '@ao []' in before,before
properties=run(paths[0],'org.freedesktop.DBus.Properties.GetAll','org.freedesktop.Secret.Item')
for expected in ["'Locked': <false>","'application': 'llm-manager'",
 "'key-reference': 'local-master-v1'","'purpose': 'backup-encryption'",
 "'Label': <'LLM-Manager backup encryption key'>","'Created': <uint64 1789394900>",
 "'Modified': <uint64 1789394900>"]:
 assert expected in properties,(expected,properties)
deleted=run(paths[0],'org.freedesktop.Secret.Item.Delete')
after=run('/org/freedesktop/secrets','org.freedesktop.Secret.Service.SearchItems',query)
assert not re.findall(r'/org/freedesktop/secrets/collection/[A-Za-z0-9_/-]+',after),after
print(json.dumps({'object_path':paths[0],'nonsecret_properties':properties,
 'created_epoch':1789394900,'delete_result':deleted,'search_after':after}))
'''))
    save("prior-performance-key-cleanup.json", {
        **value,
        "provenance": "created immediately before performance sample-01; cleanup searched a mismatched dedicated reference",
        "secret_read": False,
        "recoverable": False,
    })
    (OUT / "SHA256SUMS").write_text("".join(
        hashlib.sha256(path.read_bytes()).hexdigest()
        + "  " + str(path.relative_to(OUT)) + "\n"
        for path in sorted(OUT.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS"
    ))
    print("Removed the exact orphaned performance-Gate key; reference is absent.", flush=True)


def cleanup() -> None:
    local_status()
    result = json.loads((OUT / "local-policykit-exit.json").read_text())
    assert result.get("exited") and result.get("exitcode") == 127, result
    _verify_local_completion()
    ns["cleanup"]()
    finalize_cleanup()


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "prepare":
        prepare()
    elif action == "setup":
        setup()
    elif action == "launch-remote":
        launch_remote()
    elif action == "remote-status":
        ns["status"]("commit")
    elif action == "collect-remote":
        collect_remote()
    elif action == "launch-local":
        launch_local()
    elif action == "launch-local-desktop":
        launch_local_desktop()
    elif action == "local-status":
        local_status()
    elif action == "observe":
        observe(sys.argv[2])
    elif action == "inspect":
        ns["inspect"]()
    elif action == "cleanup":
        cleanup()
    elif action == "finalize-cleanup":
        finalize_cleanup()
    elif action == "remove-prior-performance-key":
        remove_prior_performance_key()
    else:
        raise ValueError(action)
