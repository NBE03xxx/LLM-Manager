"""Rollback-only GUI gate with a real NIC cut while rollback response is held.

This is a fresh operation and evidence namespace.  The apply response is
delivered normally.  After validation fails, a test-only relay holds only the
successful rollback response while the Ubuntu live NIC is down for four
seconds.  No mutation is retried and no AdapterError is injected.
"""
import json
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / 'docs/validation/cross-vm-rollback-r3-2026-09-13.py'
source = SOURCE.read_text()
source = source.replace('-r3', '-network-rollback')
source = source.replace(
    "source=source.replace('-r2','-network-rollback')",
    "source=source.replace('-r2','-network-rollback'); source=source.replace('cross-vm-rollback-network-rollback','cross-vm-network-rollback')",
)
namespace = {'__file__': str(SOURCE), '__name__': 'network_rollback_lifecycle'}
exec(compile(source, str(SOURCE), 'exec'), namespace)

OUT = namespace['namespace']['OUT']
GUEST = namespace['namespace']['GUEST']
ubuntu = namespace['namespace']['ubuntu']
MAC = '52:54:00:f8:49:29'
READY = GUEST + '/hold/rollback-ready.json'

RELAY = '''import json,subprocess,sys,time
from pathlib import Path
assert len(sys.argv)==5
assert sys.argv[1:3]==['/usr/bin/llm-manager-remote-helper','user-rollback']
result=subprocess.run(sys.argv[1:],capture_output=True,timeout=30)
if result.returncode==0:
 p=Path(__file__).with_name('rollback-ready.json')
 with p.open('x') as f: json.dump({'verb':'user-rollback','request_id':sys.argv[3],'request_hash':sys.argv[4],'helper_exit_code':result.returncode},f)
 time.sleep(10)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
'''

OBSERVER = '''class TransportObserver:
    def __init__(self, inner): self.inner=inner
    def run(self, request, cancellation):
        if request.correlation_id != 'ssh.user_rollback.invoke':
            return self.inner.run(request,cancellation)
        import shlex
        argv=request.argv
        assert argv[0]=='ssh'
        command='python3 '+shlex.quote(RELAY_PATH)+' '+argv[-1]
        modified=replace(request,argv=('ssh','-o','ServerAliveInterval=1','-o','ServerAliveCountMax=1',*argv[1:-1],command))
        result=self.inner.run(modified,cancellation)
        (OUT/'rollback-transport.json').write_text(json.dumps({'exit_code':result.exit_code,'timed_out':result.timed_out,'duration_ms':result.duration_ms,'stderr':result.stderr_redacted},indent=2)+'\\n')
        if result.exit_code!=0 or result.timed_out: events.append('rollback.transport_failed')
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
    namespace['setup']()
    relay = OUT / 'hold-rollback-response.py'
    relay.write_text(RELAY)
    ubuntu.execute('/usr/bin/install', ['-d', '-m', '0700', '-o', '1000', '-g', '1000', GUEST+'/hold'])
    ubuntu.transfer(str(relay), GUEST+'/hold/helper.py')
    ubuntu.execute('/bin/chmod', ['0644', GUEST+'/hold/helper.py'])
    gate = OUT / 'gate.py'
    text = gate.read_text()
    start, end = text.index('class LostReply:'), text.index('class Factory(')
    text = text[:start] + 'RELAY_PATH=' + repr(GUEST+'/hold/helper.py') + '\n' + OBSERVER + text[end:]
    text = text.replace(
        "valid=valid and events.count('rollback.invoke')==(MODE=='rollback')",
        "valid=valid and events.count('rollback.invoke')==1\n    valid=valid and events.count('rollback.transport_failed')==1",
    )
    compile(text, 'network-rollback-gate.py', 'exec')
    gate.write_text(text)
    namespace['namespace']['debian'].transfer(str(gate), GUEST+'/gate.py')
    print('Rollback-only transport observer and finite response relay ready.', flush=True)


def watch():
    assert not (OUT/'network.json').exists()
    assert ubuntu.virsh('domif-getlink', ubuntu.VM, MAC).strip() == MAC+' up'
    print('Watcher ready; waiting for successful rollback helper completion.', flush=True)
    deadline = time.monotonic() + 600
    marker = None
    observation = None
    while time.monotonic() < deadline:
        raw = ubuntu.python(
            'import json,time; from pathlib import Path; p=Path('+repr(READY)+'); '
            'print(json.dumps({"marker":json.loads(p.read_text()),"age":time.time()-p.stat().st_mtime}) if p.exists() else "null")'
        )
        observation = json.loads(raw)
        marker = observation['marker'] if observation else None
        if marker:
            break
        time.sleep(.25)
    assert marker and marker['helper_exit_code'] == 0, 'no successful rollback marker; no network cut'
    if not 0 <= observation['age'] < 2:
        namespace['namespace']['save']('network-not-cut.json', {
            'reason': 'stale rollback marker; response may already be delivered',
            'observation': observation,
            'link': ubuntu.virsh('domif-getlink', ubuntu.VM, MAC).strip(),
        })
        print('Stale marker: no NIC cut. Do not count as a network gate.', flush=True)
        return
    namespace['namespace']['save']('rollback-helper-completion.json', marker)
    command = (
        "import subprocess,time; time.sleep(7); "
        "subprocess.run(['virsh','domif-setlink','ubuntu26.04','52:54:00:f8:49:29','up'],check=True,timeout=10)"
    )
    watchdog = subprocess.Popen(
        [sys.executable, '-I', '-c', command], start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    record = {'helper_marker': marker, 'link_before': 'up'}
    try:
        ubuntu.virsh('domif-setlink', ubuntu.VM, MAC, 'down')
        record['down_at_monotonic'] = time.monotonic()
        record['link_during'] = ubuntu.virsh('domif-getlink', ubuntu.VM, MAC).strip()
        assert record['link_during'] == MAC+' down'
        time.sleep(4)
    finally:
        ubuntu.virsh('domif-setlink', ubuntu.VM, MAC, 'up')
        record['up_at_monotonic'] = time.monotonic()
        _, error = watchdog.communicate(timeout=15)
        record['watchdog_exit'] = watchdog.returncode
        record['watchdog_stderr'] = error.decode()
        record['link_after'] = ubuntu.virsh('domif-getlink', ubuntu.VM, MAC).strip()
        namespace['namespace']['save']('network.json', record)
    assert record['link_after'] == MAC+' up' and watchdog.returncode == 0
    print(json.dumps(record, indent=2), flush=True)


def collect():
    namespace['namespace']['collect']()
    exit_path = OUT/'rollback-exit.json'
    if not exit_path.exists():
        return
    remote_path = GUEST+'/evidence/rollback/rollback-transport.json'
    value = namespace['namespace']['debian'].python(
        'from pathlib import Path; print(Path('+repr(remote_path)+').read_text())'
    )
    namespace['namespace']['save']('rollback-transport.json', json.loads(value))
    result = json.loads((OUT/'rollback-result.json').read_text())
    if (OUT/'network-not-cut.json').exists():
        print('Rollback completed but no current network cut: retain as non-qualifying attempt.', flush=True)
        return
    transport = json.loads(value)
    assert result['status'] == 'rolled_back'
    assert result['events'].count('apply.invoke') == 1
    assert result['events'].count('rollback.invoke') == 1
    assert result['events'].count('rollback.transport_failed') == 1
    assert transport['exit_code'] == 255 and not transport['timed_out']
    assert json.loads((OUT/'network.json').read_text())['link_after'] == MAC+' up'
    print('Actual rollback SSH exit 255, link restoration and rolled_back reconciliation verified.', flush=True)


def collect_failed():
    """Preserve a terminal pre-cut failure without retrying its mutation."""
    try:
        namespace['namespace']['collect']()
    except AssertionError:
        pass
    result = json.loads((OUT/'rollback-result.json').read_text())
    transport_path = OUT/'rollback-transport.json'
    if not transport_path.exists():
        remote_path = GUEST+'/evidence/rollback/rollback-transport.json'
        value = namespace['namespace']['debian'].python(
            'from pathlib import Path; print(Path('+repr(remote_path)+').read_text())'
        )
        namespace['namespace']['save']('rollback-transport.json', json.loads(value))
    transport = json.loads(transport_path.read_text())
    assert result['status'] == 'recovery_required'
    assert transport['exit_code'] == 1 and not transport['timed_out']
    marker_exists = ubuntu.python(
        'from pathlib import Path; print(Path('+repr(READY)+').exists())'
    ).strip() == 'True'
    assert not marker_exists
    namespace['namespace']['save']('network-not-cut.json', {
        'reason': 'rollback helper exited 1 before the success marker; NIC cut was not attempted',
        'rollback_status': result['status'],
        'rollback_transport': transport,
        'link': ubuntu.virsh('domif-getlink', ubuntu.VM, MAC).strip(),
        'mutation_retried': False,
    })
    print('Terminal failure evidence collected; network was not cut and mutation was not retried.', flush=True)


def cleanup():
    assert (OUT/'network.json').exists() or (OUT/'network-not-cut.json').exists()
    assert ubuntu.virsh('domif-getlink', ubuntu.VM, MAC).strip() == MAC+' up'
    code = """from pathlib import Path
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
    assert json.loads(ubuntu.python(code)) == [], 'finite rollback relay still running; wait, do not kill/retry'
    namespace['namespace']['cleanup']()


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'setup': setup()
    elif action == 'watch': watch()
    elif action == 'launch': namespace['namespace']['launch']('rollback')
    elif action == 'status': namespace['namespace']['status']('rollback')
    elif action == 'collect': collect()
    elif action == 'collect-failed': collect_failed()
    elif action == 'cleanup': cleanup()
    elif action == 'diagnose': namespace['diagnose']()
    elif action in {'prepare', 'inspect'}: namespace['namespace'][action]()
    elif action == 'clocks': namespace['clocks']()
    else: raise ValueError(action)
