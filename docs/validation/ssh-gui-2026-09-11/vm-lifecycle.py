import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

VM = 'ubuntu26.04'
SNAP = 'phase6-ssh-gui-20260911'
OUT = Path('/home/yoshimi/WorkSpace/LLM-Manager/docs/validation/ssh-gui-2026-09-11')
ARTIFACTS = [
    ('/tmp/llm-manager-release-candidate-4722cfa/llm-manager_0.1.0_all.deb', '25e227fbab536be66a3f40fda81f40cc9ecae2a091a5f8fe41015358b2e6b181'),
    ('/tmp/llm-manager-release-candidate-4722cfa/llm-manager-remote-helper_0.1.0_all.deb', '45dcd8eb852317aed1da212a7bb0c1f3d008aee5d1aae38b09f980df8e56a1d1'),
    ('/tmp/phase6-opencode-1.18.30-linux-x64-baseline.tar.gz', '60c92147d0d86ca606dda8a77260d3c87e0ef959eb2d8dbffb34df6d8a64e063'),
]

def virsh(*args):
    return subprocess.check_output(['virsh', *args], text=True)

def qga(command, args):
    return json.loads(virsh('qemu-agent-command', VM, json.dumps({'execute': command, 'arguments': args})))['return']

def execute(path, args):
    pid = qga('guest-exec', {'path': path, 'arg': args, 'capture-output': True})['pid']
    for _ in range(120):
        result = qga('guest-exec-status', {'pid': pid})
        if result.get('exited'):
            assert not result.get('out-truncated') and not result.get('err-truncated'), result
            out = base64.b64decode(result.get('out-data', '')).decode()
            err = base64.b64decode(result.get('err-data', '')).decode()
            assert result.get('exitcode') == 0, (result, out, err)
            return out
        time.sleep(.25)
    raise RuntimeError(f'Pending guest PID {pid}; inspect before retry')

def python(code):
    return execute('/usr/bin/python3', ['-I', '-c', code])

def inventory():
    return json.loads(python('''import subprocess,json,hashlib,os
from pathlib import Path
packages=sorted(subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\\t${Version}\\t${db:Status-Status}\\n'],text=True).splitlines())
manual=sorted(subprocess.check_output(['apt-mark','showmanual'],text=True).splitlines())
roots=['/home/yoshimi/.config/opencode','/home/yoshimi/.ssh','/var/lib/llm-manager','/usr/local/bin/opencode']
entries={}
for root in roots:
 p=Path(root)
 paths=[p]+(sorted(p.rglob('*')) if p.is_dir() else [])
 for f in paths:
  if not f.exists() and not f.is_symlink(): entries[str(f)]=None; continue
  s=f.lstat()
  entries[str(f)]={'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,'hash':hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() and not f.is_symlink() else None}
print(json.dumps({'packages':packages,'manual':manual,'entries':entries}))
'''))

def transfer(source, target):
    handle=qga('guest-file-open', {'path': target, 'mode': 'w'})
    try:
        data=Path(source).read_bytes()
        for pos in range(0,len(data),32768):
            chunk=data[pos:pos+32768]
            assert qga('guest-file-write', {'handle':handle,'buf-b64':base64.b64encode(chunk).decode()})['count']==len(chunk)
    finally:
        qga('guest-file-close', {'handle':handle})

def main(action):
    if action=='prepare':
        assert virsh('domstate', VM).strip()=='running'
        assert SNAP not in virsh('snapshot-list',VM,'--name').splitlines()
        for source, digest in ARTIFACTS:
            assert hashlib.sha256(Path(source).read_bytes()).hexdigest()==digest
        OUT.mkdir(exist_ok=False)
        (OUT/'baseline.json').write_text(json.dumps(inventory(),indent=2)+'\n')
        print(virsh('snapshot-create-as',VM,SNAP,'Phase 6 disposable SSH GUI gate; restore running desktop', '--atomic'),flush=True)
        execute('/usr/bin/mkdir',['-m','0700','/tmp/phase6-ssh-gui-20260911'])
        print('Snapshot ready; baseline saved.',flush=True)
    elif action=='install':
        assert SNAP in virsh('snapshot-list',VM,'--name').splitlines()
        for source,digest in ARTIFACTS[:2]:
            target='/tmp/phase6-ssh-gui-20260911/'+Path(source).name
            transfer(source,target)
            assert python('import hashlib; print(hashlib.sha256(open('+repr(target)+',"rb").read()).hexdigest())').strip()==digest
        debs=['/tmp/phase6-ssh-gui-20260911/'+Path(p).name for p,_ in ARTIFACTS[:2]]
        simulation=execute('/usr/bin/apt-get',['-s','--no-install-recommends','install',*debs])
        (OUT/'apt-simulation.txt').write_text(simulation)
        assert not any(row.startswith('Remv ') for row in simulation.splitlines())
        assert all(row.split()[1] in {'llm-manager','llm-manager-remote-helper'} for row in simulation.splitlines() if row.startswith('Inst '))
        (OUT/'apt-install.txt').write_text(execute('/usr/bin/apt-get',['-y','--no-install-recommends','install',*debs]))
        print(execute('/usr/bin/dpkg',['-V','llm-manager','llm-manager-remote-helper']))
        print('Both candidate packages installed.')
    elif action=='opencode':
        assert SNAP in virsh('snapshot-list',VM,'--name').splitlines()
        print(python('''import hashlib,tarfile,os
from pathlib import Path
archive=Path('/tmp/phase6-opencode-1.18.30-linux-x64-baseline.tar.gz')
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='60c92147d0d86ca606dda8a77260d3c87e0ef959eb2d8dbffb34df6d8a64e063'
target=Path('/usr/local/bin/opencode')
assert not target.exists() and not target.is_symlink()
with tarfile.open(archive) as t:
 members=t.getmembers()
 assert len(members)==1 and members[0].name=='opencode' and members[0].isfile()
 with target.open('xb') as out: out.write(t.extractfile(members[0]).read())
target.chmod(0o755)
print('OpenCode CLI installed root:root 0755')
'''))
        print(execute('/usr/sbin/runuser',['-u','yoshimi','--','/usr/local/bin/opencode','--version']))
    elif action=='ssh-setup':
        assert SNAP in virsh('snapshot-list',VM,'--name').splitlines()
        public=execute('/bin/cat',['/etc/ssh/ssh_host_ed25519_key.pub']).strip()
        code='''from pathlib import Path
import subprocess
p=Path('/home/yoshimi/.ssh')
assert p.is_dir() and not p.is_symlink()
gate=p/'phase6-gui-20260911'
gate.mkdir(mode=0o700)
subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(gate/'identity')],check=True)
(gate/'known_hosts').write_text('127.0.0.1 '+PUBLIC+'\\n')
(gate/'known_hosts').chmod(0o600)
auth=p/'authorized_keys'
assert not auth.is_symlink()
with auth.open('a') as f: f.write('\\n'+(gate/'identity.pub').read_text())
auth.chmod(0o600)
config=p/'config'
assert not config.is_symlink()
previous=config.read_text() if config.exists() else ''
assert 'phase6-gui-gate' not in previous
config.write_text('Host phase6-gui-gate\\n  HostName 127.0.0.1\\n  User yoshimi\\n  IdentityFile '+str(gate/'identity')+'\\n  IdentitiesOnly yes\\n  UserKnownHostsFile '+str(gate/'known_hosts')+'\\n  StrictHostKeyChecking yes\\n  UpdateHostKeys no\\nHost *\\n'+previous)
config.chmod(0o600)
print('Disposable alias/key prepared inside snapshot')
'''.replace('PUBLIC',repr(public))
        print(execute('/usr/sbin/runuser',['-u','yoshimi','--','/usr/bin/python3','-I','-c',code]))
        print(execute('/usr/sbin/runuser',['-u','yoshimi','--','/usr/bin/ssh','-o','BatchMode=yes','phase6-gui-gate','opencode --version']))
    elif action=='restore':
        assert SNAP in virsh('snapshot-list',VM,'--name').splitlines()
        print(virsh('snapshot-revert',VM,SNAP,'--running'),flush=True)
        after=inventory()
        (OUT/'restored.json').write_text(json.dumps(after,indent=2)+'\n')
        assert after==json.loads((OUT/'baseline.json').read_text())
        print(virsh('snapshot-delete',VM,SNAP))
        print('Baseline exact match; temporary snapshot deleted; VM running.')

if __name__=='__main__': main(sys.argv[1])
