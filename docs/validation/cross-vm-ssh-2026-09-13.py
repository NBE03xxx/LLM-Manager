"""Explicit actions for Debian GUI -> Ubuntu SSH candidate verification.

Historical gate helpers are reused only for QGA and bounded package lifecycle.
Never run against other machines or retry a started Apply operation.
"""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / 'docs/validation/cross-vm-ssh-2026-09-13'
GUEST = '/tmp/phase6-cross-vm-20260913'
SNAP = 'phase6-cross-vm-20260913'
ALIAS = 'phase6-cross-vm'
ARCHIVE = Path('/tmp/phase6-cross-vm-opencode-1.18.30.tar.gz')
ARCHIVE_HASH = '60c92147d0d86ca606dda8a77260d3c87e0ef959eb2d8dbffb34df6d8a64e063'
REMOTE = Path('/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager-remote-helper_0.1.0_all.deb')
REMOTE_HASH = '830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d'
ENV = ['XDG_RUNTIME_DIR=/run/user/1000', 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
       'DISPLAY=:0', 'WAYLAND_DISPLAY=wayland-0', 'XDG_SESSION_TYPE=wayland', 'LANG=C.utf8',
       'LC_ALL=C.utf8', 'XDG_CONFIG_HOME='+GUEST+'/config', 'QT_QPA_PLATFORM=wayland']


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, REPO / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ubuntu = load('cross_ubuntu', 'docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py')
menu = load('cross_debian', 'docs/validation/debian-menu-ff7913b-2026-09-13.py')
menu.OUT = OUT / 'debian'
menu.TARGET = GUEST + '.deb'
debian = menu.gate.vm


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


def user(vm, name, code):
    return vm.execute('/usr/sbin/runuser', ['-u', name, '--', '/usr/bin/env', *ENV,
                                         '/usr/bin/python3', '-I', '-c', code])


def prepare():
    assert not OUT.exists()
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_HASH
    assert hashlib.sha256(REMOTE.read_bytes()).hexdigest() == REMOTE_HASH
    assert ubuntu.virsh('domstate', ubuntu.VM).strip() == 'running'
    assert SNAP not in ubuntu.virsh('snapshot-list', ubuntu.VM, '--name').splitlines()
    OUT.mkdir()
    save('ubuntu-baseline.json', ubuntu.inventory())
    print(ubuntu.virsh('snapshot-create-as', ubuntu.VM, SNAP, 'Disposable cross-VM SSH candidate gate', '--atomic'), flush=True)
    ubuntu.execute('/bin/mkdir', ['-m', '0755', GUEST])
    ubuntu.transfer(str(REMOTE), GUEST+'/helper.deb')
    ubuntu.execute('/bin/chmod', ['0644', GUEST+'/helper.deb'])
    sim = ubuntu.execute('/usr/bin/apt-get', ['-s', '--no-install-recommends', 'install', GUEST+'/helper.deb'])
    (OUT/'ubuntu-apt-simulation.txt').write_text(sim)
    assert menu.selected(sim, ('Inst',)) == ['llm-manager-remote-helper']
    assert not menu.selected(sim, ('Remv', 'Purg'))
    raw = ubuntu.execute('/usr/bin/apt-get', ['-y', '--no-install-recommends', 'install', GUEST+'/helper.deb'])
    (OUT/'ubuntu-apt-install.txt.gz').write_bytes(gzip.compress(raw.encode(), mtime=0))
    assert ubuntu.execute('/usr/bin/dpkg', ['-V', 'llm-manager-remote-helper']) == ''
    # Existing host trust, no key or known-host copying from host to either VM.
    subprocess.run(['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
                    str(ARCHIVE), 'yoshimi@192.168.122.48:/tmp/phase6-cross-vm-opencode-1.18.30.tar.gz'], check=True, timeout=60)
    ubuntu.python("""import hashlib,tarfile
from pathlib import Path
p=Path('/tmp/phase6-cross-vm-opencode-1.18.30.tar.gz')
assert hashlib.sha256(p.read_bytes()).hexdigest()=="""+repr(ARCHIVE_HASH)+"""
target=Path('/usr/local/bin/opencode')
assert not target.exists() and not target.is_symlink()
with tarfile.open(p) as t:
 m=t.getmembers(); assert len(m)==1 and m[0].name=='opencode' and m[0].isfile()
 with target.open('xb') as f: f.write(t.extractfile(m[0]).read())
target.chmod(0o755)
""")
    assert ubuntu.execute('/usr/sbin/runuser', ['-u', 'yoshimi', '--', '/usr/local/bin/opencode', '--version']).strip() == '1.18.30'
    menu.prepare()
    print('Both candidate packages ready; configure isolated test SSH next.', flush=True)


def setup():
    # Debian SSH config must be absent; no existing config overwritten.
    checks = json.loads(debian.python("""import json
from pathlib import Path
print(json.dumps({str(p):p.exists() or p.is_symlink() for p in [Path('/home/user/.ssh/config'),Path('"""+GUEST+"""')]}))
"""))
    assert not any(checks.values()), checks
    save('debian-test-paths-before.json', checks)
    public = ubuntu.execute('/bin/cat', ['/etc/ssh/ssh_host_ed25519_key.pub']).strip()
    user(debian, 'user', """from pathlib import Path
import subprocess
p=Path("""+repr(GUEST)+"""); p.mkdir(mode=0o700)
subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(p/'identity')],check=True)
(p/'known_hosts').write_text('192.168.122.48 '+"""+repr(public)+"""+'\\n')
(p/'known_hosts').chmod(0o600)
cfg=Path('/home/user/.ssh/config')
assert cfg.parent.is_dir() and not cfg.parent.is_symlink()
text='Host phase6-cross-vm\\n  HostName 192.168.122.48\\n  User yoshimi\\n  IdentityFile '+str(p/'identity')+'\\n  IdentitiesOnly yes\\n  UserKnownHostsFile '+str(p/'known_hosts')+'\\n  StrictHostKeyChecking yes\\n  UpdateHostKeys no\\n  ControlMaster no\\n'
with cfg.open('x') as f: f.write(text)
cfg.chmod(0o600)
""")
    key = user(debian, 'user', 'from pathlib import Path; print(Path('+repr(GUEST+'/identity.pub')+').read_text(),end="")')
    user(ubuntu, 'yoshimi', """from pathlib import Path
p=Path('/home/yoshimi/.ssh/authorized_keys'); assert not p.is_symlink()
with p.open('a') as f: f.write('\\n'+"""+repr(key)+""")
p.chmod(0o600)
""")
    result = debian.execute('/usr/sbin/runuser', ['-u', 'user', '--', '/usr/bin/ssh', '-o', 'BatchMode=yes', ALIAS, 'id -u; opencode --version'])
    assert result.splitlines() == ['1000', '1.18.30'], result
    save('cross-ssh-ready.json', {'uid':1000,'opencode_version':'1.18.30','strict_host_key':True})
    # Check only our dedicated Secret Service reference, never read key bytes.
    print(user(debian, 'user', """import secretstorage
c=secretstorage.dbus_init()
attrs={'application':'llm-manager','purpose':'backup-encryption','key-reference':'phase6-cross-vm-20260913'}
assert not list(secretstorage.search_items(c,attrs))
print('Dedicated Secret Service reference absent')
"""))
    # Adapt the saved test harness, retaining its documented plan/exception injection.
    source = (REPO/'docs/validation/ssh-gui-2026-09-11/gate.py').read_text()
    source = source.replace('/tmp/phase6-gui-visible2-evidence-20260911', GUEST+'/evidence')
    source = source.replace('phase6-gui-gate', ALIAS).replace('phase6-gui-20260911', 'phase6-cross-vm-20260913')
    source = source.replace('before=TARGET.read_bytes() if TARGET.exists() else None',
        "import subprocess\ndef remote_bytes():\n    p=subprocess.run(['ssh','-o','BatchMode=yes','phase6-cross-vm',\"python3 -c \\\"from pathlib import Path; p=Path('/home/yoshimi/.config/opencode/opencode.jsonc'); print(p.read_bytes().hex() if p.exists() else 'ABSENT')\\\"\"],capture_output=True,text=True,check=True,timeout=10)\n    value=p.stdout.strip()\n    return None if value=='ABSENT' else bytes.fromhex(value)\nbefore=remote_bytes()")
    source = source.replace('hashlib.sha256(TARGET.read_bytes()).hexdigest() if TARGET.exists() else None', 'hashlib.sha256(remote_bytes()).hexdigest() if remote_bytes() is not None else None')
    source = source.replace("TARGET.read_bytes()==b'", "remote_bytes()==b'")
    compile(source, 'cross-vm-gate.py', 'exec')
    (OUT/'gate.py').write_text(source)
    debian.transfer(str(OUT/'gate.py'), GUEST+'/gate.py')
    debian.execute('/bin/chown', ['1000:1000', GUEST+'/gate.py'])
    print('Cross-VM SSH and isolated harness ready; no Apply started.', flush=True)


def launch(mode):
    assert mode in {'commit','rollback'}
    assert not (OUT/(mode+'-pid.json')).exists(), 'never resend a mutation'
    pid = debian.qga('guest-exec', {'path':'/usr/sbin/runuser', 'arg':['-u','user','--','/usr/bin/env',*ENV,
        '/usr/bin/python3','-I',GUEST+'/gate.py',mode], 'capture-output':True})['pid']
    save(mode+'-pid.json', {'pid':pid})
    print('Started '+mode+' guest PID '+str(pid)+'; inspect authorization screen now.', flush=True)


def status(mode):
    path = OUT/(mode+'-exit.json')
    if path.exists():
        print(path.read_text()); return
    pid = json.loads((OUT/(mode+'-pid.json')).read_text())['pid']
    result = debian.qga('guest-exec-status', {'pid':pid})
    if result.get('exited'):
        save(mode+'-exit.json', result)
        for field in ['out-data','err-data']:
            print(base64.b64decode(result.get(field,'')).decode())
    else:
        print('Running; no mutation retry.')


def collect():
    for mode in ['commit', 'rollback']:
        status(mode)
        if not (OUT/(mode+'-exit.json')).exists():
            print(mode+' still running; collect again after completion, never relaunch.', flush=True)
            return
        result = json.loads((OUT/(mode+'-exit.json')).read_text())
        assert result.get('exitcode') in {0,1} and not result.get('out-truncated') and not result.get('err-truncated'), result
        for name in ['result.json', 'results.png']:
            source = GUEST+'/evidence/'+mode+'/'+name
            handle = debian.qga('guest-file-open', {'path':source, 'mode':'r'})
            data = bytearray()
            try:
                while True:
                    block = debian.qga('guest-file-read', {'handle':handle, 'count':65536})
                    data.extend(base64.b64decode(block.get('buf-b64','')))
                    if block.get('eof'): break
            finally:
                debian.qga('guest-file-close', {'handle':handle})
            (OUT/(mode+'-'+name)).write_bytes(data)
    expected = {'commit':'committed', 'rollback':'rolled_back'}
    for mode, value in expected.items():
        result = json.loads((OUT/(mode+'-result.json')).read_text())
        if mode == 'rollback' and result['status'] == 'approved':
            assert not result['events'], 'inspect any mutation before further action'
            print('Rollback case stopped before Apply; retain failed evidence.', flush=True)
        else:
            assert result['status'] == value and result['events'].count('apply.invoke') == 1
            assert result['events'].count('rollback.invoke') == (mode == 'rollback')
    print('Results and GUI images collected; inspect statuses individually.', flush=True)


def inspect():
    for label, vm in [('debian',debian),('ubuntu',ubuntu)]:
        value = json.loads(vm.python("""import json
from pathlib import Path
rows=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try:
  argv=(p/'cmdline').read_bytes().split(b'\\0')[:-1]
  if argv and (argv[0].endswith(b'/ssh') or argv[0]==b'ssh' or argv[0].endswith(b'/sudo') or argv[0]==b'sudo'):
   if any(b'phase6-cross-vm' in a or b'llm-manager-remote-helper' in a for a in argv):
    rows.append({'pid':int(p.name),'argv':[a.decode() for a in argv]})
 except (FileNotFoundError,PermissionError): pass
print(json.dumps(rows))
"""))
        save(label+'-remaining-processes.json',value)
        print(label, json.dumps(value), flush=True)


def cleanup():
    # Refuse cleanup while a gate might still be using its backups or keys.
    for mode in ['commit','rollback']:
        result = json.loads((OUT/(mode+'-exit.json')).read_text())
        assert result.get('exited') and result.get('exitcode') in {0,1}
    inspect()
    assert not json.loads((OUT/'debian-remaining-processes.json').read_text())
    assert not json.loads((OUT/'ubuntu-remaining-processes.json').read_text())
    assert (OUT/'rollback-results.png').exists()
    user(debian, 'user', """import secretstorage,shutil
from pathlib import Path
import os
p=Path("""+repr(GUEST)+""")
assert p.is_dir() and not p.is_symlink() and p.stat().st_uid==1000
cfg=Path('/home/user/.ssh/config')
expected='Host phase6-cross-vm\\n  HostName 192.168.122.48\\n  User yoshimi\\n  IdentityFile '+str(p/'identity')+'\\n  IdentitiesOnly yes\\n  UserKnownHostsFile '+str(p/'known_hosts')+'\\n  StrictHostKeyChecking yes\\n  UpdateHostKeys no\\n  ControlMaster no\\n'
assert not cfg.is_symlink() and cfg.read_text()==expected
c=secretstorage.dbus_init()
attrs={'application':'llm-manager','purpose':'backup-encryption','key-reference':'phase6-cross-vm-20260913'}
items=list(secretstorage.search_items(c,attrs)); assert len(items)==1
for item in items: item.delete()
assert not list(secretstorage.search_items(c,attrs))
cfg.unlink()
shutil.rmtree(p)
print('Only dedicated test key, alias, encrypted test backups and runtime removed')
""")
    menu.finish()
    assert SNAP in ubuntu.virsh('snapshot-list', ubuntu.VM, '--name').splitlines()
    print(ubuntu.virsh('snapshot-revert', ubuntu.VM, SNAP, '--running'), flush=True)
    restored = ubuntu.inventory()
    save('ubuntu-restored.json', restored)
    assert restored == json.loads((OUT/'ubuntu-baseline.json').read_text())
    print(ubuntu.virsh('snapshot-delete', ubuntu.VM, SNAP), flush=True)
    save('cleanup-result.json', {'ubuntu_baseline_exact_match':True, 'debian_baseline_exact_match':True,
        'dedicated_debian_secret_service_item_removed':True,
        'ubuntu_state':ubuntu.virsh('domstate', ubuntu.VM).strip(),
        'debian_state':debian.virsh('domstate', debian.VM).strip()})
    (OUT/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(OUT))+'\n'
        for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
    print('Both VM baselines restored; temporary Ubuntu snapshot deleted.', flush=True)


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'prepare': prepare()
    elif action == 'setup': setup()
    elif action == 'launch': launch(sys.argv[2])
    elif action == 'status': status(sys.argv[2])
    elif action == 'collect': collect()
    elif action == 'cleanup': cleanup()
    elif action == 'inspect': inspect()
    else: raise ValueError(action)
