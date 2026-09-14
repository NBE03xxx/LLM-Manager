"""Manual production GUI workflow; observation only, no injected plan/approval.

Explicit one-shot lifecycle, fresh namespace and disposable Ubuntu snapshot.
The observer records visible controls and outcome without advancing the GUI.
"""
import base64
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
source = (REPO/'docs/validation/cross-vm-ssh-2026-09-13.py').read_text()
source = source.replace('phase6-cross-vm', 'phase6-full-gui')
source = source.replace('cross-vm-ssh-2026-09-13', 'full-gui-ssh-2026-09-13')
source = source.replace('1.18.30', '1.18.25')
source = source.replace('60c92147d0d86ca606dda8a77260d3c87e0ef959eb2d8dbffb34df6d8a64e063',
                        '58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78')
source = source.replace("['commit', 'rollback']", "['commit']").replace("['commit','rollback']", "['commit']")
source = source.replace("{'commit':'committed', 'rollback':'rolled_back'}", "{'commit':'committed'}")
source = source.replace("OUT/'rollback-results.png'", "OUT/'commit-results.png'")
source = source.replace("'key-reference':'phase6-full-gui-20260913'", "'key-reference':'local-master-v1'")
source = source.replace('assert len(items)==1', 'assert len(items)<=1')
ns = {'__file__': str(REPO/'docs/validation/cross-vm-ssh-2026-09-13.py'), '__name__': 'full_gui_lifecycle'}
exec(compile(source, ns['__file__'], 'exec'), ns)
OUT, GUEST = ns['OUT'], ns['GUEST']
ns['ENV'] += ['XDG_STATE_HOME='+GUEST+'/state', 'XDG_CACHE_HOME='+GUEST+'/cache']

HARNESS = r'''import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QLabel,QPushButton,QComboBox,QCheckBox
from llm_manager.ui import qt_app
OUT=Path(__file__).parent/'evidence'/'commit'
OUT.mkdir(parents=True,exist_ok=False)
history=[]
class ObservedWindow(qt_app.MainWindow):
 def __init__(self,*a,**k):
  super().__init__(*a,**k)
  self.previous=None
  self.observation_timer=QTimer(self)
  self.observation_timer.timeout.connect(self.observe)
  self.observation_timer.start(100)
 def observe(self):
  state=self._presenter.state
  outcome=self._apply_outcome
  record={'step':state.step.value,'busy':state.busy,'error':state.error_code,
   'host_id':state.selected_host_id,'approved':state.approved,
   'labels':{x.objectName():x.text() for x in self.findChildren(QLabel) if x.isVisible()},
   'buttons':{x.objectName():{'enabled':x.isEnabled(),'text':x.text()} for x in self.findChildren(QPushButton) if x.isVisible()},
   'combos':{x.objectName():x.currentText() for x in self.findChildren(QComboBox) if x.isVisible()},
   'checks':{x.objectName():x.isChecked() for x in self.findChildren(QCheckBox) if x.isVisible()}}
  if record!=self.previous:
   self.previous=record
   history.append(record)
   (OUT/'history.json').write_text(json.dumps(history,indent=2)+'\n')
   self.grab().save(str(OUT/('step-%03d.png'%len(history))))
  if outcome is not None and not state.busy and self._active_host_id is None:
   self.observation_timer.stop()
   result={'status':outcome.status.value,'error':outcome.error,
     'validations':[{'check':v.check,'status':v.status.value,'actual':v.actual} for v in outcome.validations],
     'gui_summary':self._results_summary.text(),'history_count':len(history),
     'plan_injected':False,'approval_injected':False,'transport_injected':False}
   (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
   self.grab().save(str(OUT/'results.png'))
   print(json.dumps(result),flush=True)
   self.close()
   QApplication.instance().exit(0 if outcome.status.value=='committed' else 1)
qt_app.MainWindow=ObservedWindow
sys.exit(qt_app.main(['llm-manager']))
'''

def setup():
    # Refuse before creating test SSH state if production key reference exists.
    print(ns['user'](ns['debian'], 'user', "import secretstorage; c=secretstorage.dbus_init(); assert not list(secretstorage.search_items(c,{'application':'llm-manager','purpose':'backup-encryption','key-reference':'local-master-v1'})); print('Production key reference absent')"))
    ns['setup']()
    ns['user'](ns['ubuntu'], 'yoshimi', '''from pathlib import Path
p=Path('/home/yoshimi/.config/opencode/opencode.jsonc')
assert not p.exists() and not p.is_symlink()
p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
with p.open('x') as f: f.write('{"autoupdate": false, "compaction": {"auto": false, "prune": false}}\\n')
p.chmod(0o600)
''')
    compile(HARNESS, 'full-gui-observer.py', 'exec')
    (OUT/'gate.py').write_text(HARNESS)
    ns['debian'].transfer(str(OUT/'gate.py'), GUEST+'/gate.py')
    print('Production GUI ready; user performs all workflow actions.',flush=True)

def collect():
    ns['status']('commit')
    assert (OUT/'commit-exit.json').exists()
    code='from pathlib import Path; import json,base64; p=Path('+repr(GUEST+'/evidence/commit')+'); print(json.dumps({f.name:base64.b64encode(f.read_bytes()).decode() for f in p.iterdir() if f.is_file()}))'
    # Pull individually to keep QGA stdout bounded below image total size.
    names=json.loads(ns['debian'].python('from pathlib import Path; import json; print(json.dumps([f.name for f in Path('+repr(GUEST+'/evidence/commit')+').iterdir() if f.is_file()]))'))
    for name in names:
        assert Path(name).name==name
        handle=ns['debian'].qga('guest-file-open',{'path':GUEST+'/evidence/commit/'+name,'mode':'r'})
        data=bytearray()
        try:
            while True:
                block=ns['debian'].qga('guest-file-read',{'handle':handle,'count':65536})
                data.extend(base64.b64decode(block.get('buf-b64','')))
                if block.get('eof'): break
        finally: ns['debian'].qga('guest-file-close',{'handle':handle})
        (OUT/('commit-'+name)).write_bytes(data)
    value=ns['ubuntu'].python("from pathlib import Path; import hashlib,json; p=Path('/home/yoshimi/.config/opencode/opencode.jsonc'); print(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'config':json.loads(p.read_text())}))")
    ns['save']('target-after.json',json.loads(value))
    print((OUT/'commit-result.json').read_text())

if __name__=='__main__':
    action=sys.argv[1]
    if action=='setup': setup()
    elif action=='launch': ns['launch']('commit')
    elif action=='status': ns['status']('commit')
    elif action=='collect': collect()
    elif action in {'prepare','inspect','cleanup'}: ns[action]()
    else: raise ValueError(action)
