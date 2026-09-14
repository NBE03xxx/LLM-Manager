import json,os,re,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QLabel,QPushButton,QComboBox,QCheckBox
from llm_manager.infrastructure.process import SubprocessRunner
from llm_manager.ui import qt_app
SAMPLE=os.environ['LLM_MANAGER_PERF_SAMPLE']
assert re.fullmatch(r'sample-0[1-5]',SAMPLE)
OUT=Path(__file__).parent/'evidence'/SAMPLE
OUT.mkdir(parents=True,exist_ok=False)
timing={'schema_version':1,'sample':SAMPLE,'gui_started_monotonic_ns':time.monotonic_ns()}
transport=[]
original_run=SubprocessRunner.run
def measured_run(self,request,cancellation):
 started=time.monotonic_ns()
 result=original_run(self,request,cancellation)
 if request.argv and request.argv[0] in {'ssh','scp'}:
  transport.append({'correlation_id':request.correlation_id,
   'elapsed_ms':round((time.monotonic_ns()-started)/1_000_000,3),
   'reported_duration_ms':result.duration_ms,'exit_code':result.exit_code,
   'timed_out':result.timed_out})
  (OUT/'transport.json').write_text(json.dumps(transport,indent=2)+'\n')
 return result
SubprocessRunner.run=measured_run
history=[]
class ObservedWindow(qt_app.MainWindow):
 def __init__(self,*a,**k):
  super().__init__(*a,**k)
  self.previous=None
  self.observation_timer=QTimer(self)
  self.observation_timer.timeout.connect(self.observe)
  self.observation_timer.start(100)
 def _run_apply(self):
  timing.setdefault('apply_clicked_monotonic_ns',time.monotonic_ns())
  (OUT/'timing.json').write_text(json.dumps(timing,indent=2)+'\n')
  return super()._run_apply()
 def _apply_finished(self,result):
  timing['apply_finished_signal_monotonic_ns']=time.monotonic_ns()
  timing['apply_elapsed_including_authorization_ms']=round(
   (timing['apply_finished_signal_monotonic_ns']-timing['apply_clicked_monotonic_ns'])/1_000_000,3)
  (OUT/'timing.json').write_text(json.dumps(timing,indent=2)+'\n')
  return super()._apply_finished(result)
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
   observed=dict(record)
   observed['observed_monotonic_ns']=time.monotonic_ns()
   history.append(observed)
   (OUT/'history.json').write_text(json.dumps(history,indent=2)+'\n')
   self.grab().save(str(OUT/('step-%03d.png'%len(history))))
  if outcome is not None and not state.busy and self._active_host_id is None:
   self.observation_timer.stop()
   result={'status':outcome.status.value,'error':outcome.error,
    'validations':[{'check':v.check,'status':v.status.value,'actual':v.actual} for v in outcome.validations],
    'gui_summary':self._results_summary.text(),'history_count':len(history),
    'plan_injected':False,'approval_injected':False,'transport_injected':False,
    'timing':timing,'transport':transport}
   (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
   self.grab().save(str(OUT/'results.png'))
   print(json.dumps(result),flush=True)
   self.close()
   QApplication.instance().exit(0 if outcome.status.value=='committed' else 1)
qt_app.MainWindow=ObservedWindow
sys.exit(qt_app.main(['llm-manager']))
