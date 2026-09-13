"""Commit-only GUI gate with a real NIC cut while helper response is held.

The helper is unchanged. A test-only relay delays stdout for ten seconds after
the real helper exits. SSH keepalives detect the actual four-second link outage.
No AdapterError is injected and no mutation is retried.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

REPO=Path(__file__).resolve().parents[2]
SOURCE=REPO/'docs/validation/cross-vm-ssh-2026-09-13.py'
source=SOURCE.read_text().replace('phase6-cross-vm','phase6-cross-vm-net')
source=source.replace('cross-vm-ssh-2026-09-13','cross-vm-network-2026-09-13')
source=source.replace("ARCHIVE = Path('/tmp/phase6-cross-vm-net-opencode-1.18.30.tar.gz')",
                      "ARCHIVE = Path('/tmp/phase6-cross-vm-opencode-1.18.30.tar.gz')")
source=source.replace("['commit', 'rollback']","['commit']").replace("['commit','rollback']","['commit']")
source=source.replace("{'commit':'committed', 'rollback':'rolled_back'}","{'commit':'committed'}")
source=source.replace("OUT/'rollback-results.png'","OUT/'commit-results.png'")
source=source.replace('assert len(items)==1','assert len(items)<=1')
ns={'__file__':str(SOURCE),'__name__':'network_lifecycle'}
exec(compile(source,str(SOURCE),'exec'),ns)
OUT,GUEST,vm=ns['OUT'],ns['GUEST'],ns['ubuntu']
MAC='52:54:00:f8:49:29'
READY=GUEST+'/hold/ready.json'

RELAY='''import json,subprocess,sys,time
from pathlib import Path
assert len(sys.argv)==5
assert sys.argv[1:3]==['/usr/bin/llm-manager-remote-helper','user-apply']
result=subprocess.run(sys.argv[1:],capture_output=True,timeout=30)
if result.returncode==0:
 p=Path(__file__).with_name('ready.json')
 with p.open('x') as f: json.dump({'verb':'user-apply','request_id':sys.argv[3],'request_hash':sys.argv[4],'helper_exit_code':result.returncode},f)
 time.sleep(10)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
'''

OBSERVER='''class TransportObserver:
    def __init__(self, inner): self.inner=inner
    def run(self, request, cancellation):
        if request.correlation_id != 'ssh.user_apply.invoke':
            return self.inner.run(request,cancellation)
        import shlex
        argv=request.argv
        assert argv[0]=='ssh'
        command='python3 '+shlex.quote(RELAY_PATH)+' '+argv[-1]
        modified=replace(request,argv=('ssh','-o','ServerAliveInterval=1','-o','ServerAliveCountMax=1',*argv[1:-1],command))
        result=self.inner.run(modified,cancellation)
        (OUT/'transport.json').write_text(json.dumps({'exit_code':result.exit_code,'timed_out':result.timed_out,'duration_ms':result.duration_ms,'stderr':result.stderr_redacted},indent=2)+'\\n')
        if result.exit_code!=0 or result.timed_out: events.append('apply.transport_failed')
        return result

class LostReply:
    def __init__(self, inner):
        self.inner=inner
        self.inner.runner=TransportObserver(self.inner.runner)
    def __getattr__(self,name): return getattr(self.inner,name)
    def invoke_user_apply(self,*args):
        events.append('apply.invoke')
        return self.inner.invoke_user_apply(*args)
    def invoke_user_rollback(self,*args):
        events.append('rollback.invoke')
        return self.inner.invoke_user_rollback(*args)
    def read_private_file(self,path,limit):
        if path.endswith('/result.json'): events.append('result.read')
        return self.inner.read_private_file(path,limit)

'''


def setup():
    ns['setup']()
    relay=OUT/'hold-response.py'
    relay.write_text(RELAY)
    vm.execute('/usr/bin/install',['-d','-m','0700','-o','1000','-g','1000',GUEST+'/hold'])
    vm.transfer(str(relay),GUEST+'/hold/helper.py')
    vm.execute('/bin/chmod',['0644',GUEST+'/hold/helper.py'])
    gate=OUT/'gate.py'
    text=gate.read_text()
    start,end=text.index('class LostReply:'),text.index('class Factory(')
    text=text[:start]+'RELAY_PATH='+repr(GUEST+'/hold/helper.py')+'\n'+OBSERVER+text[end:]
    text=text.replace('QTimer.singleShot(500,button.click)','# User starts after network watcher is ready.')
    text=text.replace("valid=valid and remote_bytes()", "valid=valid and events.count('apply.transport_failed')==1\n    valid=valid and remote_bytes()")
    compile(text,'network-gate.py','exec')
    gate.write_text(text)
    ns['debian'].transfer(str(gate),GUEST+'/gate.py')
    print('Real transport observer and finite response relay ready.',flush=True)


def watch():
    assert not (OUT/'network.json').exists()
    assert vm.virsh('domif-getlink',vm.VM,MAC).strip()==MAC+' up'
    print('Watcher ready; waiting for successful helper completion.',flush=True)
    deadline=time.monotonic()+600
    marker=None
    while time.monotonic()<deadline:
        raw=vm.python('import json,time; from pathlib import Path; p=Path('+repr(READY)+'); print(json.dumps({"marker":json.loads(p.read_text()),"age":time.time()-p.stat().st_mtime}) if p.exists() else "null")')
        observation=json.loads(raw)
        marker=observation['marker'] if observation else None
        if marker: break
        time.sleep(.25)
    assert marker and marker['helper_exit_code']==0,'no successful helper marker; no network cut'
    if not 0<=observation['age']<2:
        ns['save']('network-not-cut.json',{'reason':'stale marker; response may already be delivered',
            'observation':observation,'link':vm.virsh('domif-getlink',vm.VM,MAC).strip()})
        print('Stale marker: no NIC cut. Do not count as a network gate.',flush=True)
        return
    ns['save']('helper-completion.json',marker)
    # Out-of-band restoration independent of SSH and this watcher process.
    command="import subprocess,time; time.sleep(7); subprocess.run(['virsh','domif-setlink','ubuntu26.04','52:54:00:f8:49:29','up'],check=True,timeout=10)"
    watchdog=subprocess.Popen([sys.executable,'-I','-c',command],start_new_session=True,
                              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    record={'helper_marker':marker,'link_before':'up'}
    try:
        vm.virsh('domif-setlink',vm.VM,MAC,'down')
        record['down_at_monotonic']=time.monotonic()
        record['link_during']=vm.virsh('domif-getlink',vm.VM,MAC).strip()
        assert record['link_during']==MAC+' down'
        time.sleep(4)
    finally:
        vm.virsh('domif-setlink',vm.VM,MAC,'up')
        record['up_at_monotonic']=time.monotonic()
        _,err=watchdog.communicate(timeout=15)
        record['watchdog_exit']=watchdog.returncode
        record['watchdog_stderr']=err.decode()
        record['link_after']=vm.virsh('domif-getlink',vm.VM,MAC).strip()
        ns['save']('network.json',record)
    assert record['link_after']==MAC+' up' and watchdog.returncode==0
    print(json.dumps(record,indent=2),flush=True)


def collect():
    ns['collect']()
    exit_path=OUT/'commit-exit.json'
    if not exit_path.exists(): return
    value=ns['debian'].python('from pathlib import Path; print(Path('+repr(GUEST+'/evidence/commit/transport.json')+').read_text())')
    ns['save']('transport.json',json.loads(value))
    result=json.loads((OUT/'commit-result.json').read_text())
    if (OUT/'network-not-cut.json').exists():
        assert json.loads(value)['exit_code']==0
        print('Successful Apply but no network cut: retain as non-qualifying attempt.',flush=True)
        return
    assert result['events'].count('apply.transport_failed')==1
    assert json.loads(value)['exit_code']==255 and not json.loads(value)['timed_out']
    assert json.loads((OUT/'network.json').read_text())['link_after']==MAC+' up'
    print('Actual SSH exit 255, link restoration and committed reconciliation verified.',flush=True)


def cleanup():
    assert (OUT/'network.json').exists() or (OUT/'network-not-cut.json').exists()
    assert vm.virsh('domif-getlink',vm.VM,MAC).strip()==MAC+' up'
    # Relay is finite; never remove its files while it is running.
    code="""from pathlib import Path
import json
rows=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try:
  a=(p/'cmdline').read_bytes().split(b'\\0')
  if len(a)>1 and a[1]=="""+repr((GUEST+'/hold/helper.py').encode())+""": rows.append(int(p.name))
 except (FileNotFoundError,PermissionError): pass
print(json.dumps(rows))
"""
    assert json.loads(vm.python(code))==[],'finite relay still running; wait, do not kill/retry'
    ns['cleanup']()


if __name__=='__main__':
    action=sys.argv[1]
    if action=='setup': setup()
    elif action=='watch': watch()
    elif action=='launch': ns['launch']('commit')
    elif action=='status': ns['status']('commit')
    elif action=='collect': collect()
    elif action=='cleanup': cleanup()
    elif action in {'prepare','inspect'}: ns[action]()
    else: raise ValueError(action)
