import hashlib
import json
import os
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from llm_manager.application.approval import CreateApprovalRecord
from llm_manager.application.apply_availability import ApplyRoute, AssessProductionApplyAvailability
from llm_manager.application.errors import AdapterError
from llm_manager.application.host_discovery import HostCandidate
from llm_manager.application.optimization import stable_hash
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.enums import ChangeOperation, HostKind, PlanStatus
from llm_manager.domain.models import Change, ChangeSet, EncryptionInfo, OptimizationPlan, OptimizationProfile, utc_now
from llm_manager.ui.composition import DiagnosticTaskFactory, SshUserApplyTaskFactory
from llm_manager.ui.qt_window import MainWindow
from llm_manager.ui.workflow import GuiPresenter, GuiState, GuiStep, WorkflowStatus

ROOT=Path('/tmp/phase6-cross-vm-net-20260913/evidence')
TARGET=Path('/home/yoshimi/.config/opencode/opencode.jsonc')
MODE=sys.argv[1]
assert MODE in {'commit','rollback'}
OUT=ROOT/MODE
OUT.mkdir(parents=True,exist_ok=False,mode=0o700)
events=[]
outcomes=[]

RELAY_PATH='/tmp/phase6-cross-vm-net-20260913/hold/helper.py'
class TransportObserver:
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
        (OUT/'transport.json').write_text(json.dumps({'exit_code':result.exit_code,'timed_out':result.timed_out,'duration_ms':result.duration_ms,'stderr':result.stderr_redacted},indent=2)+'\n')
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

class Factory(SshUserApplyTaskFactory):
    def _coordinator(self,*args):
        coordinator=super()._coordinator(*args)
        proxy=LostReply(coordinator.apply_transport.runner)
        coordinator.apply_transport.runner=proxy
        coordinator.rollback_transport.runner=proxy
        return coordinator
    def __call__(self,*args):
        task=super().__call__(*args)
        def run(token):
            outcome=task(token)
            outcomes.append(outcome)
            return outcome
        return run

candidate=HostCandidate('ssh:phase6-cross-vm-net',HostKind.SSH,'Disposable Ubuntu SSH','phase6-cross-vm-net')
diagnostics=DiagnosticTaskFactory.production((candidate,))
report=diagnostics(candidate.host_id)(CancellationToken())
assert report.host.fingerprint
import subprocess
def remote_bytes():
    p=subprocess.run(['ssh','-o','BatchMode=yes','phase6-cross-vm-net',"python3 -c \"from pathlib import Path; p=Path('/home/yoshimi/.config/opencode/opencode.jsonc'); print(p.read_bytes().hex() if p.exists() else 'ABSENT')\""],capture_output=True,text=True,check=True,timeout=10)
    value=p.stdout.strip()
    return None if value=='ABSENT' else bytes.fromhex(value)
before=remote_bytes()
if MODE=='commit': assert before in {None,b'{"autoupdate": false}\n'}
else: assert before==b'{"autoupdate": false}\n'
payload='{"autoupdate": false}\n' if MODE=='commit' else '{ invalid json\n'
change=Change('gate-change',str(TARGET),ChangeOperation.CREATE_FILE if before is None else ChangeOperation.REPLACE_FILE,
              None,payload,hashlib.sha256(before).hexdigest() if before is not None else None,
              'Disposable verification payload',validation_checks=('opencode.config.parse',),
              replacement_text=payload)
changes=ChangeSet('gate-changes',candidate.host_id,(change,),stable_hash((change,)))
now=utc_now()
plan=OptimizationPlan('phase6-'+MODE,report.report_id,stable_hash(report),
    OptimizationProfile('gate',1,'Disposable Gate',('stability',)),'1',(),(),changes,
    PlanStatus.DRAFT,now,now+timedelta(minutes=10),
    EncryptionInfo(True,'AES-256-GCM',1,'phase6-cross-vm-net-20260913','local_secret_service'))
approval=CreateApprovalRecord().execute(plan,'gate-approval-'+MODE,'disposable-vm-gate',True,False)
production=SshUserApplyTaskFactory.production(diagnostics)
factory=Factory(diagnostics,production.transfer_runner,OUT/'state',OUT/'staging',production.helper_probe,production.terminal)
presenter=GuiPresenter()
app=QApplication([])
window=MainWindow(diagnostics,presenter=presenter,apply_task_factory=factory,
                  hosts=(candidate,),apply_availability_service=AssessProductionApplyAvailability(
                      frozenset({ApplyRoute.LOCAL_USER,ApplyRoute.SSH_USER})))
presenter._state=GuiState(step=GuiStep.RESULTS,status=WorkflowStatus.SUCCESS,
    selected_host_id=candidate.host_id,report=report,plan_hash=changes.content_hash,
    approved_plan_hash=changes.content_hash,approval_id=approval.approval_id)
window._recommendation_plan=plan
window._approval_record=approval
window._render()
window._navigation.setCurrentRow(list(GuiStep).index(GuiStep.RESULTS))
window.resize(960,640)
window.show()
button=window.findChild(QPushButton,'run-sandbox-apply')
assert button.isEnabled()
summary=window.findChild(QLabel,'results-summary')
expected=PlanStatus.COMMITTED if MODE=='commit' else PlanStatus.ROLLED_BACK

def finish():
    if not outcomes or window._active_host_id is not None: return
    poll.stop()
    outcome=outcomes[0]
    checks=[{'check':v.check,'status':v.status.value,'actual':v.actual} for v in outcome.validations]
    result={'mode':MODE,'status':outcome.status.value,'error':outcome.error,'events':events,
            'validations':checks,'gui_summary':summary.text(),'fingerprint':report.host.fingerprint,
            'target_sha256':hashlib.sha256(remote_bytes()).hexdigest() if remote_bytes() is not None else None}
    (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    window.grab().save(str(OUT/'results.png'))
    valid=outcome.status==expected and expected.value in summary.text() and summary.isVisible() and events.count('apply.invoke')==1
    valid=valid and events.count('rollback.invoke')==(MODE=='rollback')
    valid=valid and events.count('apply.transport_failed')==1
    valid=valid and remote_bytes()==b'{"autoupdate": false}\n'
    print(json.dumps({'status':outcome.status.value,'verified':valid,'output':str(OUT)}),flush=True)
    window.close()
    app.exit(0 if valid else 1)

poll=QTimer()
poll.timeout.connect(finish)
poll.start(100)
# User starts after network watcher is ready.
sys.exit(app.exec())
