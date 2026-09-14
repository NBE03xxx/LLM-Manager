"""Manual normal GUI + real live NIC cut, with a fresh operation namespace.

Uses the proven four-second link watcher and ten-second stdout relay.  The
production planner and approval workflow remain driven by visible controls.
"""
import importlib.util
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
base_path=REPO/'docs/validation/full-gui-ssh-2026-09-13.py'
source=base_path.read_text().replace('phase6-full-gui','phase6-full-gui-net')
source=source.replace('full-gui-ssh-2026-09-13','full-gui-network-2026-09-14')
source=source.replace('/tmp/phase6-full-gui-net-opencode-1.18.25.tar.gz',
                      '/tmp/phase6-full-gui-opencode-1.18.25.tar.gz')
gui={'__file__':str(base_path),'__name__':'normal_network_gui'}
exec(compile(source,str(base_path),'exec'),gui)
ns=gui['ns']
ns['ARCHIVE']=Path('/tmp/phase6-full-gui-opencode-1.18.25.tar.gz')
OUT,GUEST=gui['OUT'],gui['GUEST']
spec=importlib.util.spec_from_file_location('link_gate',REPO/'docs/validation/cross-vm-network-2026-09-13.py')
network=importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)
network.ns=ns
network.OUT,network.GUEST,network.vm=OUT,GUEST,ns['ubuntu']
network.READY=GUEST+'/hold/ready.json'

OBSERVER=r'''from dataclasses import replace
from llm_manager.infrastructure.process import SubprocessRunner
original_run=SubprocessRunner.run
transport_events=[]
def measured_run(self,request,cancellation):
 import shlex
 invocation=request.correlation_id=='ssh.user_apply.invoke'
 if invocation:
  argv=request.argv
  assert argv[0]=='ssh'
  command='python3 '+shlex.quote(RELAY_PATH)+' '+argv[-1]
  request=replace(request,argv=('ssh','-o','ServerAliveInterval=1','-o','ServerAliveCountMax=1',*argv[1:-1],command))
 result=original_run(self,request,cancellation)
 if invocation or request.correlation_id=='ssh.staging.download':
  transport_events.append({'correlation_id':request.correlation_id,'exit_code':result.exit_code,
   'timed_out':result.timed_out,'duration_ms':result.duration_ms,'stderr':result.stderr_redacted})
  (OUT/'transport-events.json').write_text(json.dumps(transport_events,indent=2)+'\n')
 return result
SubprocessRunner.run=measured_run
'''

def setup():
    gui['setup']()
    relay=OUT/'hold-response.py'
    relay.write_text(network.RELAY)
    ns['ubuntu'].execute('/usr/bin/install',['-d','-m','0700','-o','1000','-g','1000',GUEST+'/hold'])
    ns['ubuntu'].transfer(str(relay),GUEST+'/hold/helper.py')
    ns['ubuntu'].execute('/bin/chmod',['0644',GUEST+'/hold/helper.py'])
    gate=OUT/'gate.py'
    text=gate.read_text()
    assert text.count('history=[]')==1
    text=text.replace('history=[]', 'history=[]\nRELAY_PATH='+repr(GUEST+'/hold/helper.py')+'\n'+OBSERVER)
    text=text.replace("'transport_injected':False", "'transport_injected':True,'transport_condition':'stdout relay and short keepalive; actual NIC cut'")
    compile(text,'full-gui-network.py','exec')
    gate.write_text(text)
    ns['debian'].transfer(str(gate),GUEST+'/gate.py')
    print('Manual GUI and response relay ready. Start watcher before GUI launch.',flush=True)

def collect():
    gui['collect']()
    result=json.loads((OUT/'commit-result.json').read_text())
    events=json.loads((OUT/'commit-transport-events.json').read_text())
    calls=[e for e in events if e['correlation_id']=='ssh.user_apply.invoke']
    assert len(calls)==1 and calls[0]['exit_code']==255 and not calls[0]['timed_out']
    assert result['status']=='committed' and not result['plan_injected'] and not result['approval_injected']
    link=json.loads((OUT/'network.json').read_text())
    assert link['link_after']==network.MAC+' up' and link['watchdog_exit']==0
    code='from pathlib import Path; import json; p=Path('+repr(GUEST+'/state/llm-manager')+'); print(json.dumps({str(f.relative_to(p)):json.loads(f.read_text()) for pattern in ["journal/*.json","remote-recovery/receipts/*.json","backups/*/*/manifest.json"] for f in p.glob(pattern)}))'
    ns['save']('operation-evidence.json',json.loads(ns['debian'].python(code)))
    print('Normal GUI planning/approval and real SSH exit 255 reconciliation verified.',flush=True)

if __name__=='__main__':
    action=sys.argv[1]
    if action=='setup': setup()
    elif action=='watch': network.watch()
    elif action=='collect': collect()
    elif action=='cleanup': network.cleanup()
    elif action in {'launch','status'}: ns[action]('commit')
    elif action in {'prepare','inspect'}: ns[action]()
    else: raise ValueError(action)
