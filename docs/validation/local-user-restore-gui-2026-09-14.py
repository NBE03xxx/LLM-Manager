"""One-shot Debian normal-user production GUI Apply and manual restore gate.

The application is the installed qt_app.main composition.  The in-process
observer only records visible/state snapshots.  GUI actions are performed by
an independent AT-SPI client and never inject plans, approvals, or widget state.
"""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "docs/validation/local-user-restore-gui-2026-09-14"
GUEST = "/tmp/phase6-local-user-restore-gui-20260914"
SNAP = "phase6-local-user-restore-gui-20260914"
DEB = Path("/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb")
DEB_HASH = "351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243"
REMOTE_DEB = Path("/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager-remote-helper_0.1.0_all.deb")
REMOTE_DEB_HASH = "830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d"
ARCHIVE = Path("/tmp/phase6-full-gui-opencode-1.18.25.tar.gz")
ARCHIVE_HASH = "58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78"
INITIAL = b'{"autoupdate": false, "compaction": {"auto": false, "prune": false}}\n'
ENV = [
    "XDG_RUNTIME_DIR=/run/user/1000",
    "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus",
    "DISPLAY=:0", "WAYLAND_DISPLAY=wayland-0", "XDG_SESSION_TYPE=wayland",
    "QT_QPA_PLATFORM=wayland", "QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1",
    "LANG=C.utf8", "LC_ALL=C.utf8", "PYTHONDONTWRITEBYTECODE=1",
    "XDG_CONFIG_HOME=" + GUEST + "/config",
    "XDG_STATE_HOME=" + GUEST + "/state",
    "XDG_CACHE_HOME=" + GUEST + "/cache",
    "HOME=" + GUEST + "/home",
    "PATH=" + GUEST + "/bin:/usr/bin:/bin",
]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, REPO / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


life = load("local_restore_debian", "docs/validation/debian-display-b15a984-2026-09-12/lifecycle.py")
vm = life.vm


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def user(code):
    return vm.execute("/usr/sbin/runuser", [
        "-u", "user", "--", "/usr/bin/env", *ENV,
        "/usr/bin/python3", "-I", "-c", code,
    ])


def transfer(source, target):
    vm.transfer(str(source), target)


OBSERVER = r'''import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel,QPushButton,QComboBox,QCheckBox,QListWidget
from llm_manager.ui import qt_app
OUT=Path(__file__).parent/'evidence-success'
OUT.mkdir(mode=0o700,parents=True,exist_ok=False)
history=[]
class ObservedWindow(qt_app.MainWindow):
 def __init__(self,*a,**k):
  super().__init__(*a,**k); self.previous=None
  self.timer=QTimer(self); self.timer.timeout.connect(self.observe); self.timer.start(100)
 def observe(self):
  state=self._presenter.state
  record={'step':state.step.value,'busy':state.busy,'error':state.error_code,
   'host_id':state.selected_host_id,'approved':state.approved,
   'apply_status':getattr(getattr(self._apply_outcome,'status',None),'value',None),
   'restore_state':getattr(getattr(self._restore_outcome,'state',None),'value',None),
   'inventory':[{'backup_id':getattr(x,'backup_id',None),'state':getattr(x,'state',None),
    'restore_state':getattr(x,'restore_state',None),'restore_attention':getattr(x,'restore_requires_attention',None)} for x in self._backup_inventory_items],
   'labels':{x.objectName():x.text() for x in self.findChildren(QLabel) if x.isVisible()},
   'buttons':{x.objectName():{'enabled':x.isEnabled(),'text':x.text()} for x in self.findChildren(QPushButton) if x.isVisible()},
   'combos':{x.objectName():x.currentText() for x in self.findChildren(QComboBox) if x.isVisible()},
   'checks':{x.objectName():x.isChecked() for x in self.findChildren(QCheckBox) if x.isVisible()},
   'lists':{x.objectName():[x.item(i).text() for i in range(x.count())] for x in self.findChildren(QListWidget) if x.isVisible()}}
  if record!=self.previous:
   self.previous=record; history.append(record)
   (OUT/'history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n')
   self.grab().save(str(OUT/('step-%03d.png'%len(history))))
   if any(x.get('restore_state')=='committed' for x in record['inventory']):
    (OUT/'final-observed.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
qt_app.MainWindow=ObservedWindow
sys.exit(qt_app.main(['llm-manager']))
'''


ATSPI = r'''import json,sys,time
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
Atspi.init()
mode=sys.argv[1]
def safe(call,default=None):
 try:return call()
 except Exception:return default
def walk(node,depth=0):
 yield node
 if depth>=12:return
 for i in range(safe(node.get_child_count,0) or 0):
  child=safe(lambda:node.get_child_at_index(i))
  if child is not None:yield from walk(child,depth+1)
def nodes():
 desktop=Atspi.get_desktop(0); result=[]
 for i in range(desktop.get_child_count()):
  app=desktop.get_child_at_index(i)
  values=list(walk(app))
  if any((safe(x.get_name,'') or '')=='LLM Manager' for x in values):result.extend(values)
 return result
def describe(node):
 box=safe(lambda:node.get_extents(Atspi.CoordType.SCREEN))
 states=safe(node.get_state_set)
 return {'name':safe(node.get_name,'') or '','role':safe(node.get_role_name,'unknown') or 'unknown',
  'actions':[safe(lambda i=i:node.get_action_name(i),'') for i in range(safe(node.get_n_actions,0) or 0)],
  'children':safe(node.get_child_count,0) or 0,
  'extents':None if box is None else [box.x,box.y,box.width,box.height],
  'focused':bool(states and states.contains(Atspi.StateType.FOCUSED))}
deadline=time.monotonic()+20
while time.monotonic()<deadline:
 values=nodes()
 if values:break
 time.sleep(.2)
else:raise SystemExit('LLM Manager accessibility tree not found')
if mode=='dump':
 print(json.dumps([describe(x) for x in values if describe(x)['name']],ensure_ascii=False));raise SystemExit
name=sys.argv[2]; role=sys.argv[3] if len(sys.argv)>3 else None
found=[x for x in values if (safe(x.get_name,'') or '')==name and (role is None or safe(x.get_role_name,'')==role)]
if len(found)!=1:raise SystemExit(json.dumps({'wanted':[name,role],'found':[describe(x) for x in found]},ensure_ascii=False))
node=found[0]
if mode=='action':
 count=safe(node.get_n_actions,0) or 0
 if count<1:raise SystemExit(json.dumps(describe(node),ensure_ascii=False))
 index=int(sys.argv[4]) if len(sys.argv)>4 else 0
 if index>=count:raise SystemExit(json.dumps(describe(node),ensure_ascii=False))
 ok=node.do_action(index)
 print(json.dumps({'operation':'action','node':describe(node),'index':index,'ok':bool(ok)},ensure_ascii=False))
elif mode=='select':
 index=int(sys.argv[4]); iface=node.get_selection_iface(); ok=iface.select_child(index)
 print(json.dumps({'operation':'select','node':describe(node),'index':index,'ok':bool(ok)},ensure_ascii=False))
elif mode=='focus':
 ok=node.grab_focus()
 print(json.dumps({'operation':'focus','node':describe(node),'ok':bool(ok)},ensure_ascii=False))
elif mode=='parent-select':
 parent=node.get_parent(); iface=parent.get_selection_iface(); index=node.get_index_in_parent()
 if iface is None:raise SystemExit(json.dumps({'node':describe(node),'parent':describe(parent)},ensure_ascii=False))
 ok=iface.select_child(index)
 print(json.dumps({'operation':'parent-select','node':describe(node),'parent':describe(parent),'index':index,'ok':bool(ok)},ensure_ascii=False))
elif mode=='value':
 iface=node.get_value_iface()
 if iface is None:raise SystemExit(json.dumps(describe(node),ensure_ascii=False))
 before=iface.get_current_value(); ok=iface.set_current_value(float(sys.argv[4])); after=iface.get_current_value()
 print(json.dumps({'operation':'value','node':describe(node),'before':before,'after':after,'ok':bool(ok)},ensure_ascii=False))
elif mode=='click':
 box=node.get_extents(Atspi.CoordType.SCREEN)
 # Qt/AT-SPI on this 125%-scaled Wayland session reports client-local
 # logical extents while generated pointer events use physical coordinates.
 x=386+box.x+max(1,box.width//2); y=251+box.y+max(1,box.height//2)
 ok=Atspi.generate_mouse_event(x,y,'b1c')
 print(json.dumps({'operation':'click','node':describe(node),'point':[x,y],'ok':bool(ok)},ensure_ascii=False))
else:raise SystemExit('bad mode')
'''


def prepare():
    assert vm.virsh("domstate", vm.VM).strip() == "running"
    assert SNAP not in vm.virsh("snapshot-list", vm.VM, "--name").splitlines()
    assert hashlib.sha256(DEB.read_bytes()).hexdigest() == DEB_HASH
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_HASH
    assert vm.python("from pathlib import Path; print(Path('/run/user/1000/wayland-0').is_socket())").strip() == "True"
    if not OUT.exists():
        OUT.mkdir()
        save("baseline.json", life.inventory())
        (OUT / "session-before.txt").write_text(vm.execute("/usr/bin/loginctl", ["show-session", "2", "-p", "Name", "-p", "Type", "-p", "Active", "-p", "State", "-p", "LockedHint"]))
        save("artifact-identity.json", {"source_commit":"ff7913bb97e896f7992720b9a43c2382970a5fc8", "local_deb_sha256":DEB_HASH, "opencode_archive_sha256":ARCHIVE_HASH})
    else:
        # The first internal-snapshot attempt was rejected before any guest
        # mutation.  Permit only this exact, recorded pre-mutation resume.
        assert {p.name for p in OUT.iterdir()} == {"baseline.json", "session-before.txt", "artifact-identity.json"}
        assert life.inventory() == json.loads((OUT/"baseline.json").read_text())
    checks = json.loads(vm.python("from pathlib import Path; import json; print(json.dumps({str(p):p.exists() or p.is_symlink() for p in [Path(" + repr(GUEST) + "),Path(" + repr(GUEST + '.deb') + ")]}))"))
    assert not any(checks.values()), checks
    disk_before=vm.virsh("domblklist",vm.VM,"--details")
    print(vm.virsh("snapshot-create-as", vm.VM, SNAP, "Disposable local user GUI restore gate", "--disk-only", "--atomic"), flush=True)
    disk_after=vm.virsh("domblklist",vm.VM,"--details")
    assert disk_after != disk_before
    save("snapshot.json",{"name":SNAP,"kind":"external-disk-only","before":disk_before,"after":disk_after})
    transfer(DEB, GUEST + ".deb")
    transfer(ARCHIVE, GUEST + "-opencode.tar.gz")
    for target, digest in ((GUEST+".deb",DEB_HASH),(GUEST+"-opencode.tar.gz",ARCHIVE_HASH)):
        assert vm.python("import hashlib; print(hashlib.sha256(open("+repr(target)+",'rb').read()).hexdigest())").strip() == digest
    sim = vm.execute("/usr/bin/apt-get", ["-s","--no-install-recommends","install",GUEST+".deb"])
    (OUT/"apt-install-simulation.txt").write_text(sim)
    added=sorted(line.split()[1] for line in sim.splitlines() if line.startswith("Inst "))
    assert "llm-manager" in added and not any(line.startswith("Remv ") for line in sim.splitlines())
    save("added.json",added)
    raw=vm.execute("/usr/bin/apt-get",["-y","--no-install-recommends","install",GUEST+".deb"])
    (OUT/"apt-install.txt.gz").write_bytes(gzip.compress(raw.encode(),mtime=0))
    assert vm.execute("/usr/bin/dpkg",["-V","llm-manager"]) == ""
    vm.execute("/bin/mkdir",["-m","0700",GUEST])
    vm.execute("/bin/chown",["1000:1000",GUEST])
    user("""from pathlib import Path
import hashlib,tarfile
root=Path("""+repr(GUEST)+""")
for name in ('bin','config','state','cache'): (root/name).mkdir(mode=0o700)
archive=Path("""+repr(GUEST+"-opencode.tar.gz")+""")
assert hashlib.sha256(archive.read_bytes()).hexdigest()=="""+repr(ARCHIVE_HASH)+"""
with tarfile.open(archive) as t:
 m=t.getmembers(); assert len(m)==1 and m[0].name=='opencode' and m[0].isfile()
 with (root/'bin/opencode').open('xb') as f:f.write(t.extractfile(m[0]).read())
(root/'bin/opencode').chmod(0o700)
p=root/'config/opencode/opencode.jsonc'; p.parent.mkdir(mode=0o700)
with p.open('xb') as f:f.write("""+repr(INITIAL)+""")
p.chmod(0o600)
""")
    assert user("import subprocess; print(subprocess.check_output(['opencode','--version'],text=True),end='')").strip() == "1.18.25"
    initial_hash=hashlib.sha256(INITIAL).hexdigest()
    save("initial-config.json",{"sha256":initial_hash,"config":json.loads(INITIAL)})
    print("Snapshot, installed candidate, isolated XDG roots, and OpenCode 1.18.25 ready.",flush=True)


def setup():
    assert SNAP in vm.virsh("snapshot-list",vm.VM,"--name").splitlines()
    paths=json.loads(vm.python("from pathlib import Path; import json; print(json.dumps({str(p):p.exists() for p in [Path("+repr(GUEST+"/evidence")+"),Path("+repr(GUEST+"/preflight-evidence")+"),Path("+repr(GUEST+"/evidence-success")+"),Path("+repr(GUEST+"/preflight2-evidence")+"),Path("+repr(GUEST+"/home")+")]}))"))
    if paths[GUEST+"/evidence"]:
        assert not paths[GUEST+"/preflight-evidence"] and not paths[GUEST+"/home"]
        vm.execute("/bin/mv",[GUEST+"/evidence",GUEST+"/preflight-evidence"])
    if (OUT/"preflight2-gui-exit.json").exists() and paths[GUEST+"/evidence-success"]:
        assert not paths[GUEST+"/preflight2-evidence"]
        vm.execute("/bin/mv",[GUEST+"/evidence-success",GUEST+"/preflight2-evidence"])
    if not paths[GUEST+"/home"]:
        vm.execute("/bin/mkdir",["-m","0700",GUEST+"/home"])
        vm.execute("/bin/chown",["1000:1000",GUEST+"/home"])
    user("""from pathlib import Path
import hashlib,shutil
source=Path("""+repr(GUEST+"/bin/opencode")+"""); target=Path.home()/'.opencode/bin/opencode'
target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
if not target.exists(): shutil.copyfile(source,target); target.chmod(0o700)
assert not target.is_symlink() and target.stat().st_uid==1000 and target.stat().st_mode & 0o022==0
assert hashlib.sha256(target.read_bytes()).hexdigest()==hashlib.sha256(source.read_bytes()).hexdigest()
""")
    print(user("""import secretstorage
c=secretstorage.dbus_init(); a={'application':'llm-manager','purpose':'backup-encryption','key-reference':'local-master-v1'}
assert not list(secretstorage.search_items(c,a)); print('Dedicated production key reference absent')
"""))
    home=user("from pathlib import Path; import shutil,json; print(json.dumps({'home':str(Path.home()),'which':shutil.which('opencode')}))")
    assert json.loads(home)=={"home":GUEST+"/home","which":GUEST+"/bin/opencode"},home
    compile(OBSERVER,"local-user-restore-observer.py","exec")
    compile(ATSPI,"local-user-restore-atspi.py","exec")
    (OUT/"gate.py").write_text(OBSERVER)
    (OUT/"atspi.py").write_text(ATSPI)
    transfer(OUT/"gate.py",GUEST+"/gate.py")
    transfer(OUT/"atspi.py",GUEST+"/atspi.py")
    vm.execute("/bin/chown",["1000:1000",GUEST+"/gate.py",GUEST+"/atspi.py"])
    print("Observer and independent AT-SPI driver ready; no operation started.",flush=True)


def launch():
    assert not (OUT/"gui-pid.json").exists(), "never relaunch this one-shot workflow"
    pid=vm.qga("guest-exec",{"path":"/usr/sbin/runuser","arg":["-u","user","--","/usr/bin/env",*ENV,"/usr/bin/python3","-I",GUEST+"/gate.py"],"capture-output":True})["pid"]
    save("gui-pid.json",{"pid":pid})
    print("Normal installed qt_app.main launched as UID 1000; no mutation retry.",flush=True)


def atspi(*args):
    return vm.execute("/usr/sbin/runuser",["-u","user","--","/usr/bin/env",*ENV,"/usr/bin/python3","-I",GUEST+"/atspi.py",*args])


def status():
    if (OUT/"gui-exit.json").exists(): print((OUT/"gui-exit.json").read_text()); return
    pid=json.loads((OUT/"gui-pid.json").read_text())["pid"]
    result=vm.qga("guest-exec-status",{"pid":pid})
    if result.get("exited"):
        save("gui-exit.json",result)
        print(base64.b64decode(result.get("out-data","")).decode())
        print(base64.b64decode(result.get("err-data","")).decode())
    else: print("GUI running; do not relaunch.")


def pull_evidence():
    names=json.loads(vm.python("from pathlib import Path; import json; print(json.dumps([p.name for p in Path("+repr(GUEST+"/evidence-success")+").iterdir() if p.is_file()]))"))
    for name in names:
        assert Path(name).name==name
        handle=vm.qga("guest-file-open",{"path":GUEST+"/evidence-success/"+name,"mode":"r"}); data=bytearray()
        try:
            while True:
                block=vm.qga("guest-file-read",{"handle":handle,"count":65536}); data.extend(base64.b64decode(block.get("buf-b64","")))
                if block.get("eof"):break
        finally: vm.qga("guest-file-close",{"handle":handle})
        (OUT/("gui-"+name)).write_bytes(data)


def collect():
    status()
    assert (OUT/"gui-exit.json").exists()
    result=json.loads((OUT/"gui-exit.json").read_text())
    assert result.get("exitcode")==0 and not result.get("out-truncated") and not result.get("err-truncated"),result
    pull_evidence()
    value=json.loads(user("""from pathlib import Path
import hashlib,json
root=Path("""+repr(GUEST)+"""); target=root/'config/opencode/opencode.jsonc'; state=root/'state/llm-manager'
def records(pattern): return {str(p.relative_to(state)):json.loads(p.read_text()) for p in state.glob(pattern)}
print(json.dumps({'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'target':json.loads(target.read_text()),
 'journals':records('journal/*.json'),'manifests':records('backups/*/*/manifest.json'),
 'restore_executions':records('restore-executions/*.json'),'audit':records('audit/*.json')}))
"""))
    save("operation-evidence.json",value)
    initial=json.loads((OUT/"initial-config.json").read_text())
    assert value["target_sha256"]==initial["sha256"] and value["target"]==initial["config"]
    assert len(value["journals"])==1 and next(iter(value["journals"].values()))["status"]=="committed"
    assert len(value["manifests"])==1 and next(iter(value["manifests"].values()))["complete"] is True
    results=[x for n,x in value["restore_executions"].items() if n.endswith(".result.json")]
    attempts=[x for n,x in value["restore_executions"].items() if n.endswith(".attempt.json")]
    assert len(results)==len(attempts)==1 and results[0]["state"]=="committed"
    history=json.loads((OUT/"gui-history.json").read_text())
    assert any(x.get("apply_status")=="committed" for x in history)
    assert any(x.get("restore_state")=="committed" for x in history)
    final=json.loads((OUT/"gui-final-observed.json").read_text())
    assert any(x.get("restore_state")=="committed" for x in final["inventory"])
    save("gate-result.json",{"initial_hash_restored":True,"apply_operations":1,"restore_attempts":1,"restore_results":1,"execution_evidence":"committed","explicit_refresh_inventory_observed":True,"observer_injected_plan":False,"observer_injected_approval":False,"observer_injected_gui_state":False})
    print("One Apply, one committed manual restore, exact initial hash, and refreshed inventory verified.",flush=True)


def verify_saved():
    """Verify all saved operation bindings without touching the cleaned guest."""
    evidence=json.loads((OUT/"operation-evidence.json").read_text())
    journal=next(iter(evidence["journals"].values()))
    manifest=next(iter(evidence["manifests"].values()))
    attempt=next(value for name,value in evidence["restore_executions"].items() if name.endswith(".attempt.json"))
    result=next(value for name,value in evidence["restore_executions"].items() if name.endswith(".result.json"))
    audit=[value for _,value in sorted(evidence["audit"].items())]

    def canonical(value):
        return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()

    def bound_hash(value,field):
        unsigned=dict(value); unsigned[field]=""
        return hashlib.sha256(canonical(unsigned)).hexdigest()

    assert bound_hash(journal,"journal_hash")==journal["journal_hash"]
    assert bound_hash(manifest,"manifest_hash")==manifest["manifest_hash"]
    assert bound_hash(attempt,"attempt_hash")==attempt["attempt_hash"]
    assert bound_hash(result,"evidence_hash")==result["evidence_hash"]

    item=manifest["items"][0]; target=journal["targets"][0]
    assert (journal["operation_id"],journal["plan_id"],journal["host_id"],journal["change_set_hash"]) == (
        manifest["backup_id"],manifest["plan_id"],manifest["host_id"],manifest["change_set_hash"])
    assert target["target"]==item["target"]==attempt["target"]==result["target"]
    assert target["before_hash"]==item["sha256"]==evidence["target_sha256"]
    assert target["after_hash"]!=target["before_hash"]
    assert (attempt["authorization_hash"],attempt["host_id"],attempt["backup_id"],attempt["manifest_hash"]) == (
        result["authorization_hash"],result["host_id"],result["backup_id"],result["manifest_hash"])
    assert result["attempt_hash"]==attempt["attempt_hash"]
    assert (attempt["host_id"],attempt["backup_id"],attempt["manifest_hash"]) == (
        manifest["host_id"],manifest["backup_id"],manifest["manifest_hash"])
    assert manifest["complete"] is True and result["state"]=="committed" and result["error_code"] is None
    assert manifest["encryption"]=={
        "enabled":True,"envelope_version":1,"key_reference":"local-master-v1",
        "key_scope":"local_secret_service","scheme":"AES-256-GCM",
    }
    assert item["content_ref"].endswith(".enc")

    expected=("apply.approved","backup.verified","apply.committed","restore.started","restore.committed")
    previous=None
    for sequence,(event,event_type) in enumerate(zip(audit,expected,strict=True),start=1):
        assert event["sequence"]==sequence and event["event_type"]==event_type
        assert event["previous_hash"]==previous
        assert bound_hash(event,"event_hash")==event["event_hash"]
        previous=event["event_hash"]
    fields=[dict(event["fields"]) for event in audit]
    assert all(event["correlation_id"]==journal["plan_id"] for event in audit[:3])
    assert all(field["host_id"]==manifest["host_id"] for field in fields)
    assert fields[1]["backup_id"]==fields[2]["backup_id"]==manifest["backup_id"]
    assert all(event["correlation_id"]==attempt["authorization_hash"] for event in audit[3:])
    assert all(field["backup_id"]==manifest["backup_id"] and field["binding_hash"]==attempt["authorization_hash"] for field in fields[3:])

    cleanup_result=json.loads((OUT/"cleanup-result.json").read_text())
    assert cleanup_result["dedicated_secret_service_item_removed"] is True
    save("binding-verification.json",{
        "canonical_hashes_verified":["journal","manifest","restore_attempt","restore_result",*expected],
        "apply_manifest_binding_verified":True,"restore_manifest_binding_verified":True,
        "audit_chain_and_correlations_verified":True,"encrypted_content_reference_verified":True,
        "secret_service_key_reference":"local-master-v1",
        "secret_service_lifecycle_assertions":{"absent_before_setup":True,"exactly_one_before_cleanup":True,"absent_after_cleanup":True},
        "initial_target_hash_restored":True,"apply_operations":1,"restore_attempts":1,"restore_results":1,
    })
    print("Saved manifest, journal, restore execution, audit chain, and Secret Service lifecycle bindings verified.",flush=True)


def final_audit():
    """Read-only post-cleanup audit; never recreates or replays the operation."""
    assert hashlib.sha256(DEB.read_bytes()).hexdigest()==DEB_HASH
    assert hashlib.sha256(REMOTE_DEB.read_bytes()).hexdigest()==REMOTE_DEB_HASH
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()==ARCHIVE_HASH
    baseline=json.loads((OUT/"baseline.json").read_text())
    current=life.inventory()
    assert current==baseline
    session=vm.execute("/usr/bin/loginctl",["show-session","2","-p","Name","-p","Type","-p","Active","-p","State","-p","LockedHint"])
    assert session==(OUT/"session-before.txt").read_text()
    dedicated=json.loads(vm.python("""from pathlib import Path
import json
paths=[Path("""+repr(GUEST)+"""),Path("""+repr(GUEST+".deb")+"""),Path("""+repr(GUEST+"-opencode.tar.gz")+""")]
print(json.dumps({str(path):path.exists() or path.is_symlink() for path in paths}))
"""))
    assert not any(dedicated.values())
    key_search=user("""import subprocess
print(subprocess.check_output(['/usr/bin/gdbus','call','--session','--dest','org.freedesktop.secrets',
 '--object-path','/org/freedesktop/secrets','--method','org.freedesktop.Secret.Service.SearchItems',
 \"{'application': 'llm-manager', 'purpose': 'backup-encryption', 'key-reference': 'local-master-v1'}\"],text=True),end='')
""")
    assert key_search.strip()=="(@ao [], @ao [])",key_search
    assert SNAP not in vm.virsh("snapshot-list",vm.VM,"--name").splitlines()
    debian_disks=vm.virsh("domblklist",vm.VM,"--details")
    assert "/var/lib/libvirt/images/debian13.qcow2" in debian_disks and SNAP not in debian_disks
    ubuntu_snapshots=vm.virsh("snapshot-list","ubuntu26.04","--name").splitlines()
    assert "phase4-pre-local-deb-20260831" in ubuntu_snapshots
    assert vm.virsh("domstate",vm.VM).strip()=="running"
    assert vm.virsh("domstate","ubuntu26.04").strip()=="running"
    artifact={"source_commit":"ff7913bb97e896f7992720b9a43c2382970a5fc8","local_deb_sha256":DEB_HASH,
              "remote_helper_deb_sha256":REMOTE_DEB_HASH,"opencode_archive_sha256":ARCHIVE_HASH}
    save("artifact-identity.json",artifact)
    save("final-read-only-audit.json",{
        "debian_vm_state":"running","ubuntu_vm_state":"running","baseline_exact_match":True,
        "session_exact_match":True,"dedicated_paths_absent":True,"dedicated_secret_service_items":0,
        "secret_service_query":"gdbus SearchItems returned locked=[] unlocked=[]",
        "dedicated_snapshot_absent":True,"debian_base_disk_active":True,
        "ubuntu_baseline_snapshot_preserved":True,"artifact_hashes_verified":artifact,
    })
    print("Final read-only VM, snapshot, disk, artifact, key, path, package, and session audit passed.",flush=True)


def checksums():
    (OUT/"SHA256SUMS").write_text("".join(
        hashlib.sha256(path.read_bytes()).hexdigest()+"  "+path.name+"\n"
        for path in sorted(OUT.iterdir()) if path.is_file() and path.name!="SHA256SUMS"
    ))
    print("Evidence checksums regenerated.",flush=True)


def inspect():
    value=json.loads(vm.python("""import json
from pathlib import Path
rows=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  argv=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\\0')[:-1]]
  if any(x.endswith('/gate.py') or x=='/usr/bin/llm-manager' for x in argv):rows.append({'pid':int(p.name),'argv':argv})
 except (FileNotFoundError,PermissionError,UnicodeDecodeError):pass
print(json.dumps({'processes':rows}))
"""))
    save("remaining-processes.json",value)
    print(json.dumps(value),flush=True)


def cleanup():
    assert (OUT/"gate-result.json").exists()
    inspect()
    assert not json.loads((OUT/"remaining-processes.json").read_text())["processes"]
    user("""import secretstorage,shutil
from pathlib import Path
root=Path("""+repr(GUEST)+"""); assert root.is_dir() and not root.is_symlink() and root.stat().st_uid==1000
c=secretstorage.dbus_init(); a={'application':'llm-manager','purpose':'backup-encryption','key-reference':'local-master-v1'}
items=list(secretstorage.search_items(c,a)); assert len(items)==1
for item in items:item.delete()
assert not list(secretstorage.search_items(c,a)); shutil.rmtree(root)
""")
    vm.python("from pathlib import Path; p=Path("+repr(GUEST+"-opencode.tar.gz")+"); assert p.is_file() and not p.is_symlink(); p.unlink()")
    baseline=json.loads((OUT/"baseline.json").read_text()); added=json.loads((OUT/"added.json").read_text())
    sim=vm.execute("/usr/bin/apt-get",["-s","purge",*added]); (OUT/"apt-purge-simulation.txt").write_text(sim)
    removals=sorted(set(line.split()[1] for line in sim.splitlines() if line.startswith(("Remv ","Purg "))))
    assert removals==added and not any(line.startswith("Inst ") for line in sim.splitlines())
    raw=vm.execute("/usr/bin/apt-get",["-y","purge",*added]); (OUT/"apt-purge.txt.gz").write_bytes(gzip.compress(raw.encode(),mtime=0))
    vm.python("from pathlib import Path; p=Path("+repr(GUEST+".deb")+"); assert p.is_file() and not p.is_symlink(); p.unlink()")
    cleaned=life.inventory(); save("cleaned.json",cleaned); assert cleaned==baseline
    assert vm.execute("/usr/bin/dpkg",["--audit"])==""
    (OUT/"apt-check.txt").write_text(vm.execute("/usr/bin/apt-get",["check"]))
    (OUT/"session-after.txt").write_text(vm.execute("/usr/bin/loginctl",["show-session","2","-p","Name","-p","Type","-p","Active","-p","State","-p","LockedHint"]))
    assert (OUT/"session-after.txt").read_text()==(OUT/"session-before.txt").read_text()
    assert SNAP in vm.virsh("snapshot-list",vm.VM,"--name").splitlines()
    print(vm.virsh("blockcommit",vm.VM,"vda","--active","--pivot","--verbose"),flush=True)
    print(vm.virsh("snapshot-delete",vm.VM,SNAP,"--metadata"),flush=True)
    assert SNAP not in vm.virsh("snapshot-list",vm.VM,"--name").splitlines()
    save("cleanup-result.json",{"baseline_exact_match":True,"dedicated_secret_service_item_removed":True,"dedicated_state_removed":True,"packages_purged":added,"snapshot_deleted":True,"vm_state":vm.virsh("domstate",vm.VM).strip()})
    (OUT/"SHA256SUMS").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+p.name+"\n" for p in sorted(OUT.iterdir()) if p.is_file() and p.name!="SHA256SUMS"))
    print("Dedicated key/state/package/paths removed; Debian baseline and session exactly restored.",flush=True)


def cleanup_finish():
    """Resume only after cleanup stopped on one baseline-created empty directory."""
    assert SNAP in vm.virsh("snapshot-list",vm.VM,"--name").splitlines()
    baseline=json.loads((OUT/"baseline.json").read_text())
    current=life.inventory()
    differences={k:(baseline["entries"].get(k),current["entries"].get(k)) for k in set(baseline["entries"])|set(current["entries"]) if baseline["entries"].get(k)!=current["entries"].get(k)}
    assert current["packages"]==baseline["packages"] and current["manual"]==baseline["manual"]
    assert differences=={"/home/user/.config/opencode":(None,current["entries"]["/home/user/.config/opencode"])}
    vm.execute("/usr/sbin/runuser",["-u","user","--","/usr/bin/rmdir","/home/user/.config/opencode"])
    cleaned=life.inventory(); save("cleaned.json",cleaned); assert cleaned==baseline
    assert vm.execute("/usr/bin/dpkg",["--audit"])==""
    (OUT/"apt-check.txt").write_text(vm.execute("/usr/bin/apt-get",["check"]))
    (OUT/"session-after.txt").write_text(vm.execute("/usr/bin/loginctl",["show-session","2","-p","Name","-p","Type","-p","Active","-p","State","-p","LockedHint"]))
    assert (OUT/"session-after.txt").read_text()==(OUT/"session-before.txt").read_text()
    print(vm.virsh("blockcommit",vm.VM,"vda","--active","--pivot","--verbose"),flush=True)
    print(vm.virsh("snapshot-delete",vm.VM,SNAP,"--metadata"),flush=True)
    assert SNAP not in vm.virsh("snapshot-list",vm.VM,"--name").splitlines()
    save("cleanup-result.json",{"baseline_exact_match":True,"dedicated_secret_service_item_removed":True,"dedicated_state_removed":True,"packages_purged":json.loads((OUT/"added.json").read_text()),"snapshot_deleted":True,"vm_state":vm.virsh("domstate",vm.VM).strip(),"empty_nondedicated_directory_removed":True})
    (OUT/"SHA256SUMS").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+p.name+"\n" for p in sorted(OUT.iterdir()) if p.is_file() and p.name!="SHA256SUMS"))
    print("Exact Debian baseline/session restored; external snapshot committed and deleted.",flush=True)


if __name__=="__main__":
    action=sys.argv[1]
    if action=="prepare":prepare()
    elif action=="setup":setup()
    elif action=="launch":launch()
    elif action=="status":status()
    elif action=="dump":print(atspi("dump"))
    elif action=="atspi":print(atspi(*sys.argv[2:]))
    elif action=="collect":collect()
    elif action=="verify-saved":verify_saved()
    elif action=="final-audit":final_audit()
    elif action=="inspect":inspect()
    elif action=="cleanup":cleanup()
    elif action=="cleanup-finish":cleanup_finish()
    elif action=="checksums":checksums()
    else:raise ValueError(action)
