import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QCheckBox,QLabel,QListWidget,QPlainTextEdit,QPushButton
from llm_manager.ui import qt_app
out=Path(__file__).parent/'evidence'; out.mkdir(mode=0o700,parents=True,exist_ok=False); history=[]
class Window(qt_app.MainWindow):
 def __init__(self,*a,**k):
  super().__init__(*a,**k); self.previous=None; self.timer=QTimer(self); self.timer.timeout.connect(self.observe); self.timer.start(100)
 def observe(self):
  windows=[]
  for top in QApplication.topLevelWidgets():
   if not top.isVisible(): continue
   windows.append({'class':type(top).__name__,'title':top.windowTitle(),
    'labels':[(x.objectName(),x.text()) for x in top.findChildren(QLabel) if x.isVisible()],
    'buttons':[(x.objectName(),x.text(),x.isEnabled()) for x in top.findChildren(QPushButton) if x.isVisible()],
    'checks':[(x.objectName(),x.text(),x.isChecked(),x.isEnabled()) for x in top.findChildren(QCheckBox) if x.isVisible()],
    'lists':[(x.objectName(),[x.item(i).text() for i in range(x.count())],x.currentRow()) for x in top.findChildren(QListWidget) if x.isVisible()],
    'text':[(x.objectName(),x.toPlainText()) for x in top.findChildren(QPlainTextEdit) if x.isVisible()]})
  value={'windows':windows}
  if value!=self.previous:
   self.previous=value; history.append(value); (out/'history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n')
   for i,top in enumerate([x for x in QApplication.topLevelWidgets() if x.isVisible()]): top.grab().save(str(out/('step-%03d-window-%02d.png'%(len(history),i))))
qt_app.MainWindow=Window
raise SystemExit(qt_app.main(['llm-manager']))
