"""One-shot Debian normal-GUI local-root restore and PolicyKit Gate.

The encrypted root backup is a prerequisite fixture because local-root Apply
is outside release scope. From inventory onward, installed qt_app.main and its
dedicated PolicyKit clients are unmodified. The observer records UI only.
"""
import base64, gzip, hashlib, importlib.util, json, sys
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
OUT=REPO/'docs/validation/local-root-restore-gui-2026-09-14'
GUEST='/tmp/phase6-local-root-restore-gui-20260914'
SNAP='phase6-local-root-restore-gui-20260914'
DEB=Path('/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb')
DEB_HASH='351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243'
REMOTE=Path('/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager-remote-helper_0.1.0_all.deb')
REMOTE_HASH='830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d'
ARCHIVE=Path('/tmp/phase6-full-gui-opencode-1.18.25.tar.gz')
ARCHIVE_HASH='58a3729a6f3432dd6d2917fcc4a949788891a035818646ad480e12c947f56e78'
TARGET='/etc/systemd/system/ollama.service.d/90-llm-manager.conf'
UNIT='/etc/systemd/system/ollama.service'
STATE='/var/lib/llm-manager/local-root-restore'
ORIGINAL=b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'
CHANGED=b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\nEnvironment="OLLAMA_FLASH_ATTENTION=1"\n'
ENV=['XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
 'DISPLAY=:0','WAYLAND_DISPLAY=wayland-0','XDG_SESSION_TYPE=wayland','QT_QPA_PLATFORM=wayland',
 'QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1','LANG=C.utf8','LC_ALL=C.utf8','PYTHONDONTWRITEBYTECODE=1',
 'XDG_CONFIG_HOME='+GUEST+'/config','XDG_STATE_HOME='+GUEST+'/state',
 'XDG_CACHE_HOME='+GUEST+'/cache','HOME='+GUEST+'/home','PATH=/usr/bin:/bin']

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,REPO/path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

life=load('root_gui_life','docs/validation/debian-display-b15a984-2026-09-12/lifecycle.py')
vm=life.vm
def save(name,value): (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def transfer(source,target): vm.transfer(str(source),target)
def user(code): return vm.execute('/usr/sbin/runuser',['-u','user','--','/usr/bin/env',*ENV,'/usr/bin/python3','-I','-c',code])

API='''import json,os,socket
from http.server import BaseHTTPRequestHandler,HTTPServer
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/api/version': value={'version':'0.33.2'}
  elif self.path=='/api/tags': value={'models':[]}
  else: self.send_error(404); return
  body=json.dumps(value,separators=(',',':')).encode(); self.send_response(200)
  self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body)))
  self.end_headers(); self.wfile.write(body)
 def log_message(self,*args): pass
server=HTTPServer(('127.0.0.1',11434),H)
address=os.environ['NOTIFY_SOCKET']; address=('\\0'+address[1:]) if address.startswith('@') else address
notice=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM); notice.connect(address); notice.sendall(b'READY=1'); notice.close()
server.serve_forever()
'''

OBSERVER='''import json,sys
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
   self.previous=value; history.append(value); (out/'history.json').write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\\n')
   for i,top in enumerate([x for x in QApplication.topLevelWidgets() if x.isVisible()]): top.grab().save(str(out/('step-%03d-window-%02d.png'%(len(history),i))))
qt_app.MainWindow=Window
raise SystemExit(qt_app.main(['llm-manager']))
'''

FIXTURE='''import hashlib,json,os
from datetime import timedelta
from pathlib import Path
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.infrastructure.helper_protocol import HelperOperation,HelperOperationKind,HelperRequest
from llm_manager.infrastructure.root_apply_capture import capture_before_replace
from llm_manager.infrastructure.root_restore_execution import open_production_source_parent
from llm_manager.infrastructure.root_target_lock import locked_root_target
from llm_manager.planning.ollama import DROP_IN_PATH
root=Path('''+repr(GUEST)+'''); target=Path(DROP_IN_PATH); original='''+repr(ORIGINAL)+'''; changed='''+repr(CHANGED)+'''
assert os.geteuid()==0 and target.read_bytes()==original
now=utc_now(); digest=lambda value:hashlib.sha256(value).hexdigest()
request=HelperRequest(1,'rootapply-gui-20260914','local:'+os.uname().nodename,'plan-root-gui-20260914',digest(b'root-gui-change-set'),(
 HelperOperation('write-root-gui',HelperOperationKind.ATOMIC_REPLACE,target=DROP_IN_PATH,before_hash=digest(original),staged_content_hash=digest(changed),expected_mode=0o644,expected_uid=0,expected_gid=0),
 HelperOperation('reload-root-gui',HelperOperationKind.DAEMON_RELOAD),HelperOperation('restart-root-gui',HelperOperationKind.RESTART_UNIT,unit='ollama.service')),
 now,now+timedelta(minutes=5),approval_id='approval-root-gui-20260914',backup_id='root-gui-backup-20260914',manifest_hash=digest(b'root-gui-manifest')).with_hash()
fd=open_production_source_parent()
try:
 with locked_root_target(fd):
  capture_before_replace(request,fd); temporary=target.with_name('.90-llm-manager.conf.phase6-root-gui')
  with temporary.open('xb') as stream: stream.write(changed); stream.flush(); os.fsync(stream.fileno())
  temporary.chmod(0o644); os.replace(temporary,target); os.fsync(fd)
finally: os.close(fd)
from llm_manager.infrastructure.root_backup_evidence import RootBackupEvidenceReader,open_production_directory
origin_fd=open_production_directory()
try: evidence,_envelope=RootBackupEvidenceReader(origin_fd).inspect(request.backup_id,CancellationToken())
finally: os.close(origin_fd)
(root/'fixture.json').write_text(json.dumps({'backup_id':evidence.backup_id,'record_hash':evidence.record_hash,'source_apply_request_hash':request.request_hash,'source_manifest_hash':request.manifest_hash,'original_sha256':digest(original),'changed_sha256':digest(changed),'target':DROP_IN_PATH},sort_keys=True)+'\\n')
os.chown(root/'fixture.json',1000,1000); os.chmod(root/'fixture.json',0o600)
'''

def prepare():
    assert vm.virsh('domstate','debian13').strip()=='running' and SNAP not in vm.virsh('snapshot-list','debian13','--name').splitlines()
    assert hashlib.sha256(DEB.read_bytes()).hexdigest()==DEB_HASH and hashlib.sha256(REMOTE.read_bytes()).hexdigest()==REMOTE_HASH
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()==ARCHIVE_HASH
    absent=json.loads(vm.python("from pathlib import Path;import json;print(json.dumps({p:Path(p).exists() or Path(p).is_symlink() for p in "+repr([GUEST,GUEST+'.deb',STATE,UNIT,TARGET])+"}))")); assert not any(absent.values()),absent
    OUT.mkdir(); save('baseline.json',life.inventory())
    (OUT/'session-before.txt').write_text(vm.execute('/usr/bin/loginctl',['show-session','2','-p','Name','-p','Type','-p','Active','-p','State','-p','LockedHint']))
    save('artifact-identity.json',{'source_commit':'ff7913bb97e896f7992720b9a43c2382970a5fc8','local_deb_sha256':DEB_HASH,'remote_helper_deb_sha256':REMOTE_HASH,'opencode_archive_sha256':ARCHIVE_HASH})
    before=vm.virsh('domblklist','debian13','--details'); vm.virsh('snapshot-create-as','debian13',SNAP,'Disposable local root GUI restore Gate','--disk-only','--atomic')
    after=vm.virsh('domblklist','debian13','--details'); assert after!=before; save('snapshot.json',{'name':SNAP,'kind':'external-disk-only','before':before,'after':after})
    transfer(DEB,GUEST+'.deb'); simulation=vm.execute('/usr/bin/apt-get',['-s','--no-install-recommends','install',GUEST+'.deb'])
    (OUT/'apt-install-simulation.txt').write_text(simulation); added=sorted(line.split()[1] for line in simulation.splitlines() if line.startswith('Inst ')); save('added.json',added)
    raw=vm.execute('/usr/bin/apt-get',['-y','--no-install-recommends','install',GUEST+'.deb']); (OUT/'apt-install.txt.gz').write_bytes(gzip.compress(raw.encode(),mtime=0)); assert vm.execute('/usr/bin/dpkg',['-V','llm-manager'])==''
    vm.execute('/bin/mkdir',['-m','0700',GUEST]); vm.execute('/bin/chown',['1000:1000',GUEST]); user("from pathlib import Path\nroot=Path("+repr(GUEST)+")\n[(root/name).mkdir(mode=0o700) for name in ('config','state','cache','home')]")
    for name,content in [('api.py',API),('fixture.py',FIXTURE),('observer.py',OBSERVER)]:
        (OUT/name).write_text(content); transfer(OUT/name,GUEST+'/'+name)
    transfer(REPO/'docs/validation/local-user-restore-gui-2026-09-14/atspi.py',GUEST+'/atspi.py')
    vm.execute('/bin/chown',['1000:1000',GUEST+'/observer.py',GUEST+'/atspi.py']); vm.execute('/bin/chmod',['0600',GUEST+'/api.py',GUEST+'/fixture.py',GUEST+'/observer.py',GUEST+'/atspi.py'])
    print('Candidate installed in external snapshot; no root restore operation exists.',flush=True)

def fixture():
    assert (OUT/'snapshot.json').exists() and not (OUT/'fixture-result.json').exists()
    setup=json.loads(vm.execute('/usr/bin/llm-manager-restore-setup',['initialize'])); assert setup['status']=='initialized'
    vm.python("from pathlib import Path\nunit=Path("+repr(UNIT)+"); unit.write_text('[Unit]\\nDescription=Phase 6 root restore GUI API fixture\\n[Service]\\nType=notify\\nNotifyAccess=main\\nExecStart=/usr/bin/python3 "+GUEST+"/api.py\\n'); unit.chmod(0o644)\ntarget=Path("+repr(TARGET)+"); target.parent.mkdir(mode=0o755,parents=True,exist_ok=True); target.write_bytes("+repr(ORIGINAL)+"); target.chmod(0o644)")
    vm.execute('/usr/bin/python3',['-I',GUEST+'/fixture.py'])
    value=json.loads(vm.python("from pathlib import Path;import hashlib,json;p=Path("+repr(TARGET)+");print(json.dumps({'target_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'fixture':json.loads(Path("+repr(GUEST+'/fixture.json')+").read_text()),'root_state':sorted(str(x.relative_to("+repr(STATE)+")) for x in Path("+repr(STATE)+").rglob('*'))}))")); assert value['target_sha256']==hashlib.sha256(CHANGED).hexdigest(); save('fixture-result.json',value)
    print('Encrypted origin captured and target changed once; GUI restore not started.',flush=True)

def fixture_resume():
    """Resume only the record collection after capture/change already succeeded."""
    assert (OUT/'snapshot.json').exists() and not (OUT/'fixture-result.json').exists()
    code="""import hashlib,json,os
from pathlib import Path
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.local_root_key_provisioning import open_production_key_directory
from llm_manager.infrastructure.root_backup_capture import LocalRootBackupKeys,decrypt_root_backup
from llm_manager.infrastructure.root_backup_evidence import RootBackupEvidenceReader,open_production_directory
root=Path("""+repr(GUEST)+"""); original="""+repr(ORIGINAL)+"""; changed="""+repr(CHANGED)+"""; digest=lambda value:hashlib.sha256(value).hexdigest()
backups=Path("""+repr(STATE+'/backups')+"""); executions=Path("""+repr(STATE+'/executions')+"""); audit=Path("""+repr(STATE+'/audit')+""")
assert sorted(p.name for p in backups.iterdir())==['root-gui-backup-20260914.bin','root-gui-backup-20260914.json']
assert list(executions.iterdir())==[] and list(audit.iterdir())==[] and Path("""+repr(TARGET)+""").read_bytes()==changed
origin_fd=open_production_directory(); key_fd=open_production_key_directory()
try:
 evidence,envelope=RootBackupEvidenceReader(origin_fd).inspect('root-gui-backup-20260914',CancellationToken())
 plaintext=decrypt_root_backup(evidence,envelope,AesGcmBackupCipher(LocalRootBackupKeys(key_fd)))
finally: os.close(origin_fd); os.close(key_fd)
assert plaintext==original
(root/'fixture.json').write_text(json.dumps({'backup_id':evidence.backup_id,'record_hash':evidence.record_hash,'source_apply_request_hash':evidence.source_apply_request_hash,'source_manifest_hash':evidence.source_manifest_hash,'original_sha256':digest(original),'changed_sha256':digest(changed),'target':evidence.target},sort_keys=True)+'\\n')
os.chown(root/'fixture.json',1000,1000); os.chmod(root/'fixture.json',0o600)
"""
    path=OUT/'fixture-resume.py'; path.write_text(code); transfer(path,GUEST+'/fixture-resume.py'); vm.execute('/bin/chmod',['0600',GUEST+'/fixture-resume.py']); vm.execute('/usr/bin/python3',['-I',GUEST+'/fixture-resume.py'])
    value=json.loads(vm.python("from pathlib import Path;import hashlib,json;p=Path("+repr(TARGET)+");print(json.dumps({'target_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'fixture':json.loads(Path("+repr(GUEST+'/fixture.json')+").read_text()),'root_state':sorted(str(x.relative_to("+repr(STATE)+")) for x in Path("+repr(STATE)+").rglob('*'))}))")); assert value['target_sha256']==hashlib.sha256(CHANGED).hexdigest(); save('fixture-result.json',value)
    print('Existing encrypted origin verified; execution/audit remain empty; record collection resumed without mutation retry.',flush=True)

def launch():
    assert (OUT/'fixture-result.json').exists() and not (OUT/'gui-pid.json').exists()
    pid=vm.qga('guest-exec',{'path':'/usr/sbin/runuser','arg':['-u','user','--','/usr/bin/env',*ENV,'/usr/bin/python3','-I',GUEST+'/observer.py'],'capture-output':True})['pid']; save('gui-pid.json',{'pid':pid}); print('Normal installed qt_app.main launched as UID 1000.',flush=True)

def active_launch():
    """Relaunch via the active desktop terminal after the inactive preflight deny."""
    assert (OUT/'gui-exit.json').exists() and not (OUT/'active-gui-pid.json').exists()
    assert not json.loads(vm.python("from pathlib import Path;import json;print(json.dumps([p.name for p in Path("+repr(STATE+'/executions')+").iterdir()]))"))
    for name in ('gui-pid.json','gui-exit.json'):
        (OUT/name).rename(OUT/('inactive-preflight-'+name))
    exists=vm.python("from pathlib import Path;print(Path("+repr(GUEST+'/evidence')+").exists())").strip()=='True'
    if exists: vm.execute('/bin/mv',[GUEST+'/evidence',GUEST+'/inactive-preflight-evidence'])
    transfer(OUT/'observer.py',GUEST+'/observer.py'); vm.execute('/bin/chown',['1000:1000',GUEST+'/observer.py']); vm.execute('/bin/chmod',['0600',GUEST+'/observer.py'])
    pid=vm.qga('guest-exec',{'path':'/usr/sbin/runuser','arg':['-u','user','--','/usr/bin/env','XDG_RUNTIME_DIR=/run/user/1000','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus','DISPLAY=:0','WAYLAND_DISPLAY=wayland-0','/usr/bin/gnome-terminal','--wait','--','/usr/bin/env',*ENV,'/usr/bin/python3','-I',GUEST+'/observer.py'],'capture-output':True})['pid']
    save('active-gui-pid.json',{'pid':pid})
    print('GUI launch requested through the active desktop GNOME Terminal.',flush=True)

def atspi(*args): return user("import runpy,sys;sys.argv="+repr([GUEST+'/atspi.py',*args])+";runpy.run_path("+repr(GUEST+'/atspi.py')+",run_name='__main__')")
def status():
    pid=json.loads((OUT/'gui-pid.json').read_text())['pid']; result=vm.qga('guest-exec-status',{'pid':pid})
    if result.get('exited'): save('gui-exit.json',result); print(base64.b64decode(result.get('out-data','')).decode()); print(base64.b64decode(result.get('err-data','')).decode())
    else: print('GUI running; do not relaunch.')

def inspect_state():
    """Read-only inventory used to resolve fail-closed GUI uncertainty."""
    code="""from pathlib import Path
import hashlib,json
root=Path("""+repr(STATE)+""")
print(json.dumps([{'path':str(p.relative_to(root)),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.rglob('*')) if p.is_file()]))
"""
    value=json.loads(vm.python(code)); save('root-state-inventory.json',value); print(json.dumps(value))

def active_status():
    if (OUT/'active-gui-exit.json').exists():
        print((OUT/'active-gui-exit.json').read_text()); return
    pid=json.loads((OUT/'active-gui-pid.json').read_text())['pid']
    result=vm.qga('guest-exec-status',{'pid':pid})
    if result.get('exited'):
        save('active-gui-exit.json',result)
        print(base64.b64decode(result.get('out-data','')).decode())
        print(base64.b64decode(result.get('err-data','')).decode())
    else: print('Active-session GUI running; do not relaunch.')

def _pull_file(source,target):
    handle=vm.qga('guest-file-open',{'path':source,'mode':'r'}); data=bytearray()
    try:
        while True:
            block=vm.qga('guest-file-read',{'handle':handle,'count':65536})
            data.extend(base64.b64decode(block.get('buf-b64','')))
            if block.get('eof'): break
    finally: vm.qga('guest-file-close',{'handle':handle})
    target.write_bytes(data)

def pull_evidence():
    names=json.loads(vm.python("from pathlib import Path;import json;print(json.dumps([p.name for p in Path("+repr(GUEST+'/evidence')+").iterdir() if p.is_file()]))"))
    for name in names:
        assert Path(name).name==name
        _pull_file(GUEST+'/evidence/'+name,OUT/('gui-'+name))

def collect():
    active_status()
    result=json.loads((OUT/'active-gui-exit.json').read_text())
    assert result.get('exitcode')==0 and not result.get('out-truncated') and not result.get('err-truncated'),result
    pull_evidence()
    code="""from pathlib import Path
import base64,hashlib,json,os
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.serialization import to_primitive
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.local_root_key_provisioning import open_production_key_directory
from llm_manager.infrastructure.root_backup_capture import LocalRootBackupKeys,decrypt_root_backup
from llm_manager.infrastructure.root_backup_evidence import RootBackupEvidenceReader,open_production_directory
from llm_manager.infrastructure.root_restore_audit import RootRestoreAuditLog,open_production_audit_directory
from llm_manager.infrastructure.root_restore_store import RootRestoreStore,open_production_execution_directory
state=Path("""+repr(STATE)+"""); target=Path("""+repr(TARGET)+"""); cancel=CancellationToken()
request_ids=[p.name[:-12] for p in (state/'executions').glob('*.review.json')]
assert len(request_ids)==1
origin_fd=open_production_directory(); key_fd=open_production_key_directory(); execution_fd=open_production_execution_directory(); audit_fd=open_production_audit_directory()
try:
 reader=RootBackupEvidenceReader(origin_fd); discovered,_=reader.inspect('root-gui-backup-20260914',cancel)
 evidence,envelope=reader.read('root-gui-backup-20260914',discovered.record_hash,cancel)
 plaintext=decrypt_root_backup(evidence,envelope,AesGcmBackupCipher(LocalRootBackupKeys(key_fd)))
 view=RootRestoreStore(execution_fd).load_execution(request_ids[0],cancel)
 events=RootRestoreAuditLog(audit_fd).read_all()
finally:
 os.close(origin_fd);os.close(key_fd);os.close(execution_fd);os.close(audit_fd)
def raw(pattern): return {p.name:json.loads(p.read_text()) for p in sorted((state/'executions').glob(pattern))}
st=target.stat()
print(json.dumps({'request_id':request_ids[0],'target':{'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'content_b64':base64.b64encode(target.read_bytes()).decode(),'mode':st.st_mode&0o777,'uid':st.st_uid,'gid':st.st_gid},'backup':to_primitive(evidence),'plaintext_sha256':hashlib.sha256(plaintext).hexdigest(),'execution':to_primitive(view),'audit':to_primitive(events),'records':raw('*.json')}))
"""
    value=json.loads(vm.python(code)); save('operation-evidence.json',value)
    service={'is_active':vm.execute('/usr/bin/systemctl',['is-active','ollama.service']).strip(),
             'show':vm.execute('/usr/bin/systemctl',['show','ollama.service','-p','ActiveState','-p','SubState','-p','MainPID','-p','Environment']),
             'version':json.loads(vm.execute('/usr/bin/curl',['--fail','--silent','--show-error','http://127.0.0.1:11434/api/version'])),
             'tags':json.loads(vm.execute('/usr/bin/curl',['--fail','--silent','--show-error','http://127.0.0.1:11434/api/tags']))}
    save('service-evidence.json',service)
    (OUT/'service-journal.txt').write_text(vm.execute('/usr/bin/journalctl',['-u','ollama.service','--no-pager','-n','80','-o','short-iso-precise']))
    original_hash=hashlib.sha256(ORIGINAL).hexdigest(); fixture=json.loads((OUT/'fixture-result.json').read_text())['fixture']
    assert value['target']=={'sha256':original_hash,'content_b64':base64.b64encode(ORIGINAL).decode(),'mode':0o644,'uid':0,'gid':0}
    assert value['plaintext_sha256']==original_hash and value['backup']['original']['sha256']==original_hash
    review=value['records'][value['request_id']+'.review.json']['payload']; request=review['approved_request']
    attempt=value['execution']['attempt']; committed=value['execution']['result']; events=value['audit']
    assert attempt and committed and committed['state']=='committed' and committed['error_code'] is None
    assert len([n for n in value['records'] if n.endswith('.review.json')])==1
    assert len([n for n in value['records'] if n.endswith('.attempt.json')])==1
    assert len([n for n in value['records'] if n.endswith('.result.json')])==1
    assert request['backup_id']==value['backup']['backup_id']==fixture['backup_id']
    assert review['origin_record_hash']==value['backup']['record_hash']==fixture['record_hash']
    assert review['source_apply_request_hash']==value['backup']['source_apply_request_hash']==fixture['source_apply_request_hash']
    assert request['manifest_hash']==value['backup']['source_manifest_hash']==fixture['source_manifest_hash']
    assert request['target']==TARGET and request['backup']['sha256']==original_hash
    assert attempt['request_id']==committed['request_id']==value['request_id']
    assert attempt['request_hash']==committed['request_hash']==request['request_hash']
    assert [event['event_type'] for event in events]==['root_restore.started','root_restore.finished']
    assert all(event['correlation_id']==value['request_id'] for event in events)
    assert all(dict(event['fields'])['request_hash']==request['request_hash'] for event in events)
    assert dict(events[-1]['fields'])=={'error_code':None,'request_hash':request['request_hash'],'state':'committed'}
    assert service['is_active']=='active' and service['version']=={'version':'0.33.2'} and service['tags']=={'models':[]}
    history=json.loads((OUT/'gui-history.json').read_text())
    assert any(any(label[1]=='The saved result reports that restore and validation completed.' for label in window['labels']) for state in history for window in state['windows'])
    save('gate-result.json',{'root_restore_attempts':1,'root_restore_results':1,'root_restore_state':'committed','root_audit_events':2,'initial_hash_restored':True,'service_validated':True,'observer_injected_plan':False,'observer_injected_approval':False,'observer_injected_gui_state':False})
    print('One root restore attempt/result, committed audit chain, exact original hash, and restarted API verified.',flush=True)

def cleanup():
    assert (OUT/'gate-result.json').exists()
    processes=json.loads(vm.python("""from pathlib import Path
import json
rows=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit(): continue
 try:
  argv=[x.decode() for x in (p/'cmdline').read_bytes().split(b'\\0')[:-1]]
  if any(x.endswith('/observer.py') for x in argv): rows.append({'pid':int(p.name),'argv':argv})
 except (FileNotFoundError,PermissionError,UnicodeDecodeError): pass
print(json.dumps(rows))
""")); save('remaining-processes.json',processes); assert not processes,processes
    vm.execute('/usr/bin/systemctl',['disable','--now','ollama.service'])
    code="""from pathlib import Path
import shutil
for raw in """+repr([TARGET,UNIT,STATE,GUEST,GUEST+'.deb'])+""":
 p=Path(raw)
 assert p.exists() and not p.is_symlink(),raw
 if p.is_dir(): shutil.rmtree(p)
 else: p.unlink()
"""
    vm.python(code); vm.execute('/usr/bin/systemctl',['daemon-reload']); vm.execute('/usr/bin/systemctl',['reset-failed'])
    added=json.loads((OUT/'added.json').read_text())
    simulation=vm.execute('/usr/bin/apt-get',['-s','purge',*added]); (OUT/'apt-purge-simulation.txt').write_text(simulation)
    removals=sorted(set(line.split()[1] for line in simulation.splitlines() if line.startswith(('Remv ','Purg '))))
    assert removals==added and not any(line.startswith('Inst ') for line in simulation.splitlines()),removals
    raw=vm.execute('/usr/bin/apt-get',['-y','purge',*added]); (OUT/'apt-purge.txt.gz').write_bytes(gzip.compress(raw.encode(),mtime=0))
    baseline=json.loads((OUT/'baseline.json').read_text()); cleaned=life.inventory(); save('cleaned.json',cleaned); assert cleaned==baseline
    assert vm.execute('/usr/bin/dpkg',['--audit'])==''
    (OUT/'apt-check.txt').write_text(vm.execute('/usr/bin/apt-get',['check']))
    session=vm.execute('/usr/bin/loginctl',['show-session','2','-p','Name','-p','Type','-p','Active','-p','State','-p','LockedHint'])
    (OUT/'session-after.txt').write_text(session); assert session==(OUT/'session-before.txt').read_text()
    assert SNAP in vm.virsh('snapshot-list','debian13','--name').splitlines()
    print(vm.virsh('blockcommit','debian13','vda','--active','--pivot','--verbose'),flush=True)
    print(vm.virsh('snapshot-delete','debian13',SNAP,'--metadata'),flush=True)
    assert SNAP not in vm.virsh('snapshot-list','debian13','--name').splitlines()
    save('cleanup-result.json',{'baseline_exact_match':True,'dedicated_root_key_and_state_removed':True,'dedicated_unit_and_target_removed':True,'packages_purged':added,'snapshot_deleted':True,'vm_state':vm.virsh('domstate','debian13').strip()})
    print('Dedicated root key/state/unit/target/package/path removed; Debian baseline and session exactly restored.',flush=True)

def final_audit():
    assert hashlib.sha256(DEB.read_bytes()).hexdigest()==DEB_HASH
    assert hashlib.sha256(REMOTE.read_bytes()).hexdigest()==REMOTE_HASH
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()==ARCHIVE_HASH
    baseline=json.loads((OUT/'baseline.json').read_text()); assert life.inventory()==baseline
    session=vm.execute('/usr/bin/loginctl',['show-session','2','-p','Name','-p','Type','-p','Active','-p','State','-p','LockedHint'])
    assert session==(OUT/'session-before.txt').read_text()
    paths=json.loads(vm.python("from pathlib import Path;import json;print(json.dumps({p:Path(p).exists() or Path(p).is_symlink() for p in "+repr([GUEST,GUEST+'.deb',STATE,UNIT,TARGET])+"}))")); assert not any(paths.values()),paths
    assert SNAP not in vm.virsh('snapshot-list','debian13','--name').splitlines()
    disks=vm.virsh('domblklist','debian13','--details'); assert '/var/lib/libvirt/images/debian13.qcow2' in disks and SNAP not in disks
    assert 'phase4-pre-local-deb-20260831' in vm.virsh('snapshot-list','ubuntu26.04','--name').splitlines()
    assert vm.virsh('domstate','debian13').strip()=='running' and vm.virsh('domstate','ubuntu26.04').strip()=='running'
    save('final-read-only-audit.json',{'debian_vm_state':'running','ubuntu_vm_state':'running','baseline_exact_match':True,'session_exact_match':True,'dedicated_paths_root_key_state_unit_target_absent':True,'dedicated_snapshot_absent':True,'debian_base_disk_active':True,'ubuntu_baseline_snapshot_preserved':True,'artifact_hashes_verified':{'source_commit':'ff7913bb97e896f7992720b9a43c2382970a5fc8','local_deb_sha256':DEB_HASH,'remote_helper_deb_sha256':REMOTE_HASH,'opencode_archive_sha256':ARCHIVE_HASH}})
    print('Final read-only VM, snapshot, disk, artifact, root state, path, package, and session audit passed.',flush=True)

def cleanup_finish():
    """Resume after cleanup stopped before snapshot pivot on one empty parent."""
    assert SNAP in vm.virsh('snapshot-list','debian13','--name').splitlines()
    parent='/var/lib/llm-manager'
    detail=json.loads(vm.python("from pathlib import Path;import json;p=Path("+repr(parent)+");print(json.dumps({'exists':p.is_dir() and not p.is_symlink(),'entries':[x.name for x in p.iterdir()] if p.is_dir() else None,'mode':p.stat().st_mode&0o777 if p.exists() else None,'uid':p.stat().st_uid if p.exists() else None,'gid':p.stat().st_gid if p.exists() else None}))"))
    assert detail=={'exists':True,'entries':[],'mode':0o700,'uid':0,'gid':0},detail
    vm.execute('/bin/rmdir',[parent])
    baseline=json.loads((OUT/'baseline.json').read_text()); cleaned=life.inventory(); save('cleaned.json',cleaned); assert cleaned==baseline
    assert vm.execute('/usr/bin/dpkg',['--audit'])==''
    (OUT/'apt-check.txt').write_text(vm.execute('/usr/bin/apt-get',['check']))
    session=vm.execute('/usr/bin/loginctl',['show-session','2','-p','Name','-p','Type','-p','Active','-p','State','-p','LockedHint'])
    (OUT/'session-after.txt').write_text(session); assert session==(OUT/'session-before.txt').read_text()
    print(vm.virsh('blockcommit','debian13','vda','--active','--pivot','--verbose'),flush=True)
    print(vm.virsh('snapshot-delete','debian13',SNAP,'--metadata'),flush=True)
    assert SNAP not in vm.virsh('snapshot-list','debian13','--name').splitlines()
    added=json.loads((OUT/'added.json').read_text())
    save('cleanup-result.json',{'baseline_exact_match':True,'dedicated_root_key_and_state_removed':True,'dedicated_unit_and_target_removed':True,'empty_parent_removed':True,'packages_purged':added,'snapshot_deleted':True,'vm_state':vm.virsh('domstate','debian13').strip()})
    print('Empty dedicated parent removed; Debian baseline/session restored and snapshot deleted.',flush=True)

def checksums():
    (OUT/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
    print('Evidence checksums regenerated.',flush=True)

if __name__=='__main__':
    action=sys.argv[1]
    if action=='prepare':prepare()
    elif action=='fixture':fixture()
    elif action=='fixture-resume':fixture_resume()
    elif action=='launch':launch()
    elif action=='active-launch':active_launch()
    elif action=='atspi':print(atspi(*sys.argv[2:]))
    elif action=='status':status()
    elif action=='inspect-state':inspect_state()
    elif action=='active-status':active_status()
    elif action=='collect':collect()
    elif action=='cleanup':cleanup()
    elif action=='cleanup-finish':cleanup_finish()
    elif action=='final-audit':final_audit()
    elif action=='checksums':checksums()
    else:raise ValueError(action)
