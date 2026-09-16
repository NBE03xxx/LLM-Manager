"""Run final-artifact Debian normal-user GUI Apply/manual-restore actions."""
from pathlib import Path


REPO = Path("/home/yoshimi/WorkSpace/LLM-Manager")
SOURCE = REPO / "docs/validation/local-user-restore-gui-2026-09-14.py"
replacements = {
    "elif mode=='focus':": """elif mode=='clear-select':
 iface=node.get_selection_iface()
 if iface is None:raise SystemExit(json.dumps(describe(node),ensure_ascii=False))
 ok=iface.clear_selection()
 print(json.dumps({'operation':'clear-select','node':describe(node),'ok':bool(ok)},ensure_ascii=False))
elif mode=='focus':""",
    "name=sys.argv[2]; role=sys.argv[3] if len(sys.argv)>3 else None": """if mode=='raw-click':
 x=int(sys.argv[2]); y=int(sys.argv[3]); ok=Atspi.generate_mouse_event(x,y,'b1c')
 print(json.dumps({'operation':'raw-click','point':[x,y],'ok':bool(ok)},ensure_ascii=False));raise SystemExit
name=sys.argv[2]; role=sys.argv[3] if len(sys.argv)>3 else None""",
    "elif mode=='click':": """elif mode=='raw-click':
 x=int(sys.argv[2]); y=int(sys.argv[3]); ok=Atspi.generate_mouse_event(x,y,'b1c')
 print(json.dumps({'operation':'raw-click','point':[x,y],'ok':bool(ok)},ensure_ascii=False))
elif mode=='click':""",
    "def status():": """def sync_atspi():
    compile(ATSPI,\"local-user-restore-atspi.py\",\"exec\")
    (OUT/\"atspi.py\").write_text(ATSPI)
    transfer(OUT/\"atspi.py\",GUEST+\"/atspi.py\")
    vm.execute(\"/bin/chown\",[\"1000:1000\",GUEST+\"/atspi.py\"])
    print(\"Updated independent AT-SPI driver only; application state unchanged.\",flush=True)


def purge_abort_key():
    result=json.loads(user(\"\"\"import json,re,subprocess
def run(object_path,method,*args):
 p=subprocess.run(['/usr/bin/gdbus','call','--session','--dest','org.freedesktop.secrets',
  '--object-path',object_path,'--method',method,*args],capture_output=True,text=True,check=True)
 return p.stdout.strip()
query=\"{'application': 'llm-manager', 'purpose': 'backup-encryption', 'key-reference': 'local-master-final-v1'}\"
before=run('/org/freedesktop/secrets','org.freedesktop.Secret.Service.SearchItems',query)
paths=re.findall(r'/org/freedesktop/secrets/collection/[A-Za-z0-9_/-]+',before)
assert len(paths)<=1,before
properties=None
if paths:
 properties=run(paths[0],'org.freedesktop.DBus.Properties.GetAll','org.freedesktop.Secret.Item')
 assert \"'application': 'llm-manager'\" in properties and \"'purpose': 'backup-encryption'\" in properties and \"'key-reference': 'local-master-final-v1'\" in properties,properties
 run(paths[0],'org.freedesktop.Secret.Item.Delete')
after=run('/org/freedesktop/secrets','org.freedesktop.Secret.Service.SearchItems',query)
assert not re.findall(r'/org/freedesktop/secrets/collection/[A-Za-z0-9_/-]+',after),after
print(json.dumps({'before':len(paths),'after':0,'object_path':paths[0] if paths else None,'nonsecret_properties':properties}))
\"\"\"))
    assert result["before"]<=1 and result["after"]==0
    save("abort-key-cleanup.json",result)
    print("Aborted attempt dedicated Secret Service key absent.",flush=True)


def status():""",
    "def cleanup():": r'''def abort_cleanup():
    """Cleanly retire a recorded failed gate attempt without claiming success."""
    assert (OUT/"gui-exit.json").exists()
    pull_evidence()
    save("attempt-failure.json",{
        "reason":"restore preview expired during operator accessibility troubleshooting",
        "apply_committed":True,
        "restore_started":False,
        "release_gate_passed":False,
    })
    inspect()
    assert not json.loads((OUT/"remaining-processes.json").read_text())["processes"]
    user("""import secretstorage,shutil
from pathlib import Path
root=Path("""+repr(GUEST)+"""); assert root.is_dir() and not root.is_symlink() and root.stat().st_uid==1000
c=secretstorage.dbus_init(); a={'application':'llm-manager','purpose':'backup-encryption','key-reference':'local-master-v1'}
items=list(secretstorage.search_items(c,a)); assert len(items)<=1
for item in items:item.delete()
assert not list(secretstorage.search_items(c,a)); shutil.rmtree(root)
""")
    vm.python("from pathlib import Path; p=Path("+repr(GUEST+"-opencode.tar.gz")+"); p.unlink() if p.exists() else None")
    vm.python("from pathlib import Path; p=Path("+repr(GUEST+".deb")+"); p.unlink() if p.exists() else None")
    baseline=json.loads((OUT/"baseline.json").read_text()); added=json.loads((OUT/"added.json").read_text())
    sim=vm.execute("/usr/bin/apt-get",["-s","purge",*added]); (OUT/"abort-apt-purge-simulation.txt").write_text(sim)
    removals=sorted(set(line.split()[1] for line in sim.splitlines() if line.startswith(("Remv ","Purg "))))
    assert removals==added and not any(line.startswith("Inst ") for line in sim.splitlines())
    raw=vm.execute("/usr/bin/apt-get",["-y","purge",*added]); (OUT/"abort-apt-purge.txt.gz").write_bytes(gzip.compress(raw.encode(),mtime=0))
    cleaned=life.inventory()
    differences={k:(baseline["entries"].get(k),cleaned["entries"].get(k)) for k in set(baseline["entries"])|set(cleaned["entries"]) if baseline["entries"].get(k)!=cleaned["entries"].get(k)}
    if cleaned["packages"]==baseline["packages"] and cleaned["manual"]==baseline["manual"] and differences=={"/home/user/.config/opencode":(None,cleaned["entries"]["/home/user/.config/opencode"])}:
        vm.execute("/usr/sbin/runuser",["-u","user","--","/usr/bin/rmdir","/home/user/.config/opencode"])
        cleaned=life.inventory()
    save("abort-cleaned.json",cleaned); assert cleaned==baseline
    assert vm.execute("/usr/bin/dpkg",["--audit"])==""
    (OUT/"abort-apt-check.txt").write_text(vm.execute("/usr/bin/apt-get",["check"]))
    (OUT/"abort-session-after.txt").write_text(vm.execute("/usr/bin/loginctl",["show-session","2","-p","Name","-p","Type","-p","Active","-p","State","-p","LockedHint"]))
    assert (OUT/"abort-session-after.txt").read_text()==(OUT/"session-before.txt").read_text()
    assert SNAP in vm.virsh("snapshot-list",vm.VM,"--name").splitlines()
    print(vm.virsh("blockcommit",vm.VM,"vda","--active","--pivot","--verbose"),flush=True)
    print(vm.virsh("snapshot-delete",vm.VM,SNAP,"--metadata"),flush=True)
    assert SNAP not in vm.virsh("snapshot-list",vm.VM,"--name").splitlines()
    save("abort-cleanup-result.json",{"baseline_exact_match":True,"snapshot_deleted":True,"vm_state":vm.virsh("domstate",vm.VM).strip()})
    (OUT/"SHA256SUMS").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+p.name+"\n" for p in sorted(OUT.iterdir()) if p.is_file() and p.name!="SHA256SUMS"))
    print("Failed attempt recorded; dedicated state removed and exact Debian baseline restored.",flush=True)


def cleanup():''',
    'elif action=="status":status()': 'elif action=="status":status()\n    elif action=="sync-atspi":sync_atspi()\n    elif action=="purge-abort-key":purge_abort_key()',
    'elif action=="cleanup":cleanup()': 'elif action=="abort-cleanup":abort_cleanup()\n    elif action=="cleanup":cleanup()',
    "local-user-restore-gui-2026-09-14": "local-user-restore-gui-final-2026-09-16-attempt2",
    "/tmp/phase6-local-user-restore-gui-20260914":
        "/tmp/phase6-local-user-restore-gui-final-20260916-attempt2",
    "phase6-local-user-restore-gui-20260914":
        "phase6-local-user-restore-gui-final-20260916-attempt2",
    "/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb":
        "/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager_0.1.0_all.deb",
    "351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243":
        "63f4b1b43d0b72f4578f30282d99313b675c29166e37637f9d79040bdbafece1",
    "/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager-remote-helper_0.1.0_all.deb":
        "/tmp/llm-manager-final-5b7d4de-20260916/artifacts/llm-manager-remote-helper_0.1.0_all.deb",
    "830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d":
        "ee042ece330cc62febff1e4effdb59801ca55042bc845db54e0c5d78c8eea9e4",
    "ff7913bb97e896f7992720b9a43c2382970a5fc8":
        "5b7d4de03e495fe630deab952de043f945a22bd7",
}
source = SOURCE.read_text()
for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
    assert old in source, old
    source = source.replace(old, new)
assert "candidate-ff7913b" not in source
exec(compile(source, str(SOURCE), "exec"), {
    "__name__": "__main__",
    "__file__": str(Path(__file__)),
})
