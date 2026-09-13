"""Fresh rollback-only cross-VM gate; operator clicks Apply when ready.

Reuse the recorded lifecycle with a new namespace, directory, snapshot, and
operation. Never retry the previous failed operation. No product source edits.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / 'docs/validation/cross-vm-ssh-2026-09-13.py'
source = SOURCE.read_text()
source = source.replace('phase6-cross-vm', 'phase6-cross-vm-r2')
source = source.replace('cross-vm-ssh-2026-09-13', 'cross-vm-rollback-r2-2026-09-13')
# Keep using the previously hash-verified host archive, with a fresh guest path.
source = source.replace("ARCHIVE = Path('/tmp/phase6-cross-vm-r2-opencode-1.18.30.tar.gz')",
                        "ARCHIVE = Path('/tmp/phase6-cross-vm-opencode-1.18.30.tar.gz')")
source = source.replace("['commit', 'rollback']", "['rollback']")
source = source.replace("['commit','rollback']", "['rollback']")
source = source.replace("{'commit':'committed', 'rollback':'rolled_back'}", "{'rollback':'rolled_back'}")
source = source.replace("assert len(items)==1", "assert len(items)<=1")
namespace = {'__file__': str(SOURCE), '__name__': 'rollback_r2_lifecycle'}
exec(compile(source, str(SOURCE), 'exec'), namespace)


def setup():
    namespace['setup']()
    vm = namespace['ubuntu']
    # A fresh, known-good fixture replaces the previous successful commit case.
    # Only the disposable Ubuntu snapshot is modified, as the target user.
    namespace['user'](vm, 'yoshimi', '''from pathlib import Path
p=Path('/home/yoshimi/.config/opencode/opencode.jsonc')
assert not p.exists() and not p.is_symlink()
p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
with p.open('x') as f: f.write('{"autoupdate": false}\\n')
p.chmod(0o600)
''')
    output = namespace['OUT']
    gate = output / 'gate.py'
    text = gate.read_text()
    assert text.count('QTimer.singleShot(500,button.click)') == 1
    text = text.replace('QTimer.singleShot(500,button.click)',
                        '# User clicks Run Apply after preparing to authenticate.')
    gate.write_text(text)
    namespace['debian'].transfer(str(gate), namespace['GUEST']+'/gate.py')
    namespace['save']('fixture.json', {'content':'{"autoupdate": false}\n',
        'owner_uid':1000, 'mode':'0600', 'apply_not_started':True,
        'start_policy':'User clicks Run Apply; normal product authorization timeout unchanged'})
    print('Known-good fixture and manual-start GUI prepared.', flush=True)


def diagnose():
    namespace['inspect']()
    vm = namespace['debian']
    print(vm.python("""from pathlib import Path
import json
p=Path("""+repr(namespace['GUEST']+'/evidence/rollback')+""")
print(json.dumps([{'path':str(f.relative_to(p)),'bytes':f.stat().st_size} for f in p.rglob('*') if f.is_file()]))
"""))
    value = namespace['ubuntu'].python("""from pathlib import Path
import json,stat,subprocess
rows=[]
for root in ['/home/yoshimi/.local/state/llm-manager/remote-helper','/var/lib/llm-manager']:
 p=Path(root)
 for f in [p]+list(p.rglob('*')):
  if f.exists():
   s=f.lstat(); rows.append({'path':str(f),'uid':s.st_uid,'mode':oct(stat.S_IMODE(s.st_mode)),'bytes':s.st_size})
logs=subprocess.run(['journalctl','--since','-10min','_COMM=sudo','--no-pager','-o','cat'],capture_output=True,text=True,check=True).stdout
print(json.dumps({'metadata_only':rows,'sudo_helper_lines':[x for x in logs.splitlines() if 'llm-manager-remote-helper' in x]}))
""")
    import json
    namespace['save']('remote-diagnostic.json', json.loads(value))
    print(value)


def clocks():
    import json
    rows={}
    for name in ['debian','ubuntu']:
        rows[name]=json.loads(namespace[name].python("""import json,subprocess
from datetime import datetime,timezone
from pathlib import Path
value={'now':datetime.now(timezone.utc).isoformat(),'sync':subprocess.run(['timedatectl','show','-p','NTPSynchronized','-p','NTP'],capture_output=True,text=True).stdout}
root=Path('/home/yoshimi/.local/state/llm-manager/remote-helper')
value['requests']=[{k:v for k,v in json.loads(p.read_text()).items() if k in {'requested_at','expires_at','backup_created_at','request_id'}} for p in root.glob('*/*/request.json')]
print(json.dumps(value))
"""))
    namespace['save']('clocks.json',rows)
    print(json.dumps(rows,indent=2))


def auth_timing():
    import json
    raw=namespace['ubuntu'].python("""import json,subprocess
from datetime import datetime,timezone
from pathlib import Path
rows=[]
log=subprocess.run(['journalctl','-n','50','_COMM=sudo','--no-pager','-o','json'],capture_output=True,text=True,check=True).stdout
for line in log.splitlines():
 v=json.loads(line); msg=v.get('MESSAGE','')
 if 'llm-manager-remote-helper invoke-recovery ssh-user-68bfd26243344bf78a481dd86db69324 ' in msg:
  rows.append({'time_utc':datetime.fromtimestamp(int(v['__REALTIME_TIMESTAMP'])/1000000,timezone.utc).isoformat(),'message':msg})
print(json.dumps(rows))
""")
    rows=json.loads(raw)
    namespace['save']('sudo-auth-timing.json',rows)
    print(json.dumps(rows,indent=2))
    assert len(rows)==1
    # Pure decoder only: never invoke the helper or write a remote result.
    from datetime import datetime
    sys.path.insert(0,str(REPO/'src'))
    from llm_manager.infrastructure.remote_helper import decode_remote_request
    from llm_manager.application.errors import AdapterError
    request=namespace['ubuntu'].python("""from pathlib import Path
p=Path('/home/yoshimi/.local/state/llm-manager/remote-helper/ssh-user-68bfd26243344bf78a481dd86db69324/462e0370be445768afffb30e01c744de337538a0a249ff1574f3f9ec4d8bd729/request.json')
print(p.read_text(),end='')
""").encode()
    value=json.loads(request)
    at=datetime.fromisoformat(rows[0]['time_utc'])
    try:
        decode_remote_request(request,expected_hash=value['request_hash'],now=at)
    except AdapterError as error:
        result={'sudo_time_utc':at.isoformat(),'requested_at':value['requested_at'],
                'seconds_before_requested_at':(datetime.fromisoformat(value['requested_at'])-at).total_seconds(),
                'decoder_error_code':error.code,'decoder_error':str(error),'helper_not_reinvoked':True}
    else:
        raise AssertionError('decoder accepted request at recorded invocation time')
    namespace['save']('request-time-rejection.json',result)
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'setup': setup()
    elif action == 'launch': namespace['launch']('rollback')
    elif action == 'status': namespace['status']('rollback')
    elif action == 'diagnose': diagnose()
    elif action == 'clocks': clocks()
    elif action == 'auth-timing': auth_timing()
    elif action in {'prepare','collect','inspect','cleanup'}: namespace[action]()
    else: raise ValueError(action)
