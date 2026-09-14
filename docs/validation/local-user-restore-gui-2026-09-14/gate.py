import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel,QPushButton,QComboBox,QCheckBox,QListWidget
from llm_manager.ui import qt_app
OUT=Path(__file__).parent/'evidence-success'
OUT.mkdir(mode=0o700,parents=True,exist_ok=False)
history=[]
class ObservedWindow(qt_app.MainWindow):
 def __init__(self,*a,**k):
  super().__init__(*a,**k); self.previous=None
  self.timer=QTimer(self); self.timer.timeout.connect(self.observe); self.timer.start(100)
 def observe(self):
  state=self._presenter.state
  record={'step':state.step.value,'busy':state.busy,'error':state.error_code,
   'host_id':state.selected_host_id,'approved':state.approved,
   'apply_status':getattr(getattr(self._apply_outcome,'status',None),'value',None),
   'restore_state':getattr(getattr(self._restore_outcome,'state',None),'value',None),
   'inventory':[{'backup_id':getattr(x,'backup_id',None),'state':getattr(x,'state',None),
    'restore_state':getattr(x,'restore_state',None),'restore_attention':getattr(x,'restore_requires_attention',None)} for x in self._backup_inventory_items],
   'labels':{x.objectName():x.text() for x in self.findChildren(QLabel) if x.isVisible()},
   'buttons':{x.objectName():{'enabled':x.isEnabled(),'text':x.text()} for x in self.findChildren(QPushButton) if x.isVisible()},
   'combos':{x.objectName():x.currentText() for x in self.findChildren(QComboBox) if x.isVisible()},
   'checks':{x.objectName():x.isChecked() for x in self.findChildren(QCheckBox) if x.isVisible()},
   'lists':{x.objectName():[x.item(i).text() for i in range(x.count())] for x in self.findChildren(QListWidget) if x.isVisible()}}
  if record!=self.previous:
   self.previous=record; history.append(record)
   (OUT/'history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n')
   self.grab().save(str(OUT/('step-%03d.png'%len(history))))
   if any(x.get('restore_state')=='committed' for x in record['inventory']):
    (OUT/'final-observed.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
qt_app.MainWindow=ObservedWindow
sys.exit(qt_app.main(['llm-manager']))
