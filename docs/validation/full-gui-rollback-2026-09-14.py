"""Manual production GUI workflow ending in a test-induced SSH rollback.

The diagnostic, recommendations, review, approval, Apply, backup, remote helper,
and rollback paths are production composition.  A wrapper records the real
runtime validation results, then appends one explicit failed Gate check so the
coordinator exercises its rollback branch without changing the target file.
"""
import base64
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
base_path = REPO / "docs/validation/full-gui-ssh-2026-09-13.py"
source = base_path.read_text()
source = source.replace("phase6-full-gui", "phase6-full-gui-rollback")
source = source.replace("full-gui-ssh-2026-09-13", "full-gui-rollback-2026-09-14")
source = source.replace('"[\'commit\']"', '"[\'rollback\']"')
source = source.replace("{\'commit\':\'committed\'}", "{\'rollback\':\'rolled_back\'}")
source = source.replace("OUT/'commit-results.png'", "OUT/'rollback-results.png'")
gui = {"__file__": str(base_path), "__name__": "normal_gui_rollback_lifecycle"}
exec(compile(source, str(base_path), "exec"), gui)
ns = gui["ns"]
ns["ARCHIVE"] = Path("/tmp/phase6-full-gui-opencode-1.18.25.tar.gz")
OUT, GUEST = gui["OUT"], gui["GUEST"]

FAULT_AND_OBSERVER = r'''
from dataclasses import replace
from llm_manager.application.ports import ValidationResult
from llm_manager.domain.enums import Severity,ValidationStatus
from llm_manager.domain.models import LocalizedMessage
from llm_manager.infrastructure.process import SubprocessRunner
from llm_manager.ui.composition import SshUserApplyTaskFactory

original_run=SubprocessRunner.run
transport_events=[]
def measured_run(self,request,cancellation):
 result=original_run(self,request,cancellation)
 if request.correlation_id in {'ssh.user_apply.invoke','ssh.user_rollback.invoke','ssh.staging.download'}:
  transport_events.append({'correlation_id':request.correlation_id,'exit_code':result.exit_code,
   'timed_out':result.timed_out,'duration_ms':result.duration_ms,'stderr':result.stderr_redacted})
  (OUT/'transport-events.json').write_text(json.dumps(transport_events,indent=2)+'\n')
 return result
SubprocessRunner.run=measured_run

class GateValidationFailure:
 def __init__(self,inner): self.inner=inner
 def validate(self,change_set,cancellation):
  results=self.inner.validate(change_set,cancellation)
  assert results and all(item.status is ValidationStatus.PASSED for item in results)
  observed=[{'check':item.check,'status':item.status.value,'actual':item.actual} for item in results]
  (OUT/'production-validation.json').write_text(json.dumps(observed,indent=2)+'\n')
  return (*results,ValidationResult(validation_id='gate.runtime.failure',scope='gate',
   check='gate.runtime.failure',status=ValidationStatus.FAILED,expected='passed',actual='injected_failed',
   severity=Severity.HIGH,message=LocalizedMessage('gate.runtime.failure')))

original_coordinator=SshUserApplyTaskFactory._coordinator
def gate_coordinator(self,*args,**kwargs):
 coordinator=original_coordinator(self,*args,**kwargs)
 coordinator.validator=GateValidationFailure(coordinator.validator)
 return coordinator
SshUserApplyTaskFactory._coordinator=gate_coordinator
'''

HARNESS = gui["HARNESS"]
HARNESS = HARNESS.replace("'evidence'/'commit'", "'evidence'/'rollback'")
HARNESS = HARNESS.replace("history=[]", "history=[]\n" + FAULT_AND_OBSERVER)
HARNESS = HARNESS.replace(
    "'plan_injected':False,'approval_injected':False,'transport_injected':False",
    "'plan_injected':False,'approval_injected':False,'transport_injected':False,'validation_fault_injected':True,'transport_events':transport_events",
)
HARNESS = HARNESS.replace(
    "QApplication.instance().exit(0 if outcome.status.value=='committed' else 1)",
    "QApplication.instance().exit(0 if outcome.status.value=='rolled_back' else 1)",
)
compile(HARNESS, "full-gui-rollback-observer.py", "exec")
gui["HARNESS"] = HARNESS


def setup():
    gui["setup"]()
    print("Normal GUI ready; production validation will be recorded before one explicit Gate failure.", flush=True)


def collect():
    ns["status"]("rollback")
    assert (OUT / "rollback-exit.json").exists()
    names = json.loads(ns["debian"].python(
        "from pathlib import Path; import json; print(json.dumps([f.name for f in Path("
        + repr(GUEST + "/evidence/rollback")
        + ").iterdir() if f.is_file()]))"
    ))
    for name in names:
        assert Path(name).name == name
        handle = ns["debian"].qga("guest-file-open", {
            "path": GUEST + "/evidence/rollback/" + name, "mode": "r",
        })
        data = bytearray()
        try:
            while True:
                block = ns["debian"].qga("guest-file-read", {"handle": handle, "count": 65536})
                data.extend(base64.b64decode(block.get("buf-b64", "")))
                if block.get("eof"):
                    break
        finally:
            ns["debian"].qga("guest-file-close", {"handle": handle})
        (OUT / ("rollback-" + name)).write_bytes(data)
    result = json.loads((OUT / "rollback-result.json").read_text())
    events = result["transport_events"]
    assert result["status"] == "rolled_back"
    assert not result["plan_injected"] and not result["approval_injected"]
    assert result["validation_fault_injected"]
    assert sum(e["correlation_id"] == "ssh.user_apply.invoke" for e in events) == 1
    assert sum(e["correlation_id"] == "ssh.user_rollback.invoke" for e in events) == 1
    production = json.loads((OUT / "rollback-production-validation.json").read_text())
    assert production and all(item["status"] == "passed" for item in production)
    value = ns["ubuntu"].python(
        "from pathlib import Path; import hashlib,json; "
        "p=Path('/home/yoshimi/.config/opencode/opencode.jsonc'); "
        "print(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'config':json.loads(p.read_text())}))"
    )
    ns["save"]("target-after.json", json.loads(value))
    code = "from pathlib import Path; import json; p=Path(" + repr(GUEST + "/state/llm-manager") + "); print(json.dumps({str(f.relative_to(p)):json.loads(f.read_text()) for pattern in ['journal/*.json','remote-recovery/receipts/*.json','backups/*/*/manifest.json'] for f in p.glob(pattern)}))"
    ns["save"]("operation-evidence.json", json.loads(ns["debian"].python(code)))
    print("Normal GUI planning/approval, one Apply, real validation, and one rollback verified.", flush=True)


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "setup":
        setup()
    elif action == "collect":
        collect()
    elif action in {"prepare", "inspect", "cleanup"}:
        ns[action]()
    elif action in {"launch", "status"}:
        ns[action]("rollback")
    else:
        raise ValueError(action)
