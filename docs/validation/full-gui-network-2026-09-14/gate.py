import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QLabel,QPushButton,QComboBox,QCheckBox
from llm_manager.ui import qt_app
OUT=Path(__file__).parent/'evidence'/'commit'
OUT.mkdir(parents=True,exist_ok=False)
history=[]
RELAY_PATH='/tmp/phase6-full-gui-net-20260913/hold/helper.py'
from dataclasses import replace
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
     'plan_injected':False,'approval_injected':False,'transport_injected':True,'transport_condition':'stdout relay and short keepalive; actual NIC cut'}
   (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
   self.grab().save(str(OUT/'results.png'))
   print(json.dumps(result),flush=True)
   self.close()
   QApplication.instance().exit(0 if outcome.status.value=='committed' else 1)
qt_app.MainWindow=ObservedWindow
sys.exit(qt_app.main(['llm-manager']))
