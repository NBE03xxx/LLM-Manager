"""Five-sample normal-GUI SSH Apply operational performance Gate.

Each sample is a fresh GUI diagnosis/plan/approval/Apply operation.  A direct,
unprivileged reset of the disposable remote fixture happens only between
samples and outside every timed interval.  Never relaunch a sample with a saved
PID or reuse an operation after an ambiguous result.
"""
import base64
import hashlib
import json
from pathlib import Path
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
BASE = REPO / "docs/validation/full-gui-ssh-2026-09-13.py"
source = BASE.read_text()
source = source.replace("phase6-full-gui", "phase6-ssh-apply-performance")
source = source.replace(
    "full-gui-ssh-2026-09-13", "ssh-apply-performance-2026-09-14"
)
source = source.replace(
    "phase6-ssh-apply-performance-20260913",
    "phase6-ssh-apply-performance-20260914",
)
gui = {"__file__": str(BASE), "__name__": "ssh_apply_performance_lifecycle"}
exec(compile(source, str(BASE), "exec"), gui)
ns = gui["ns"]
old_guest = ns["GUEST"]
new_guest = "/tmp/phase6-ssh-apply-performance-20260914"
ns["GUEST"] = new_guest
ns["SNAP"] = "phase6-ssh-apply-performance-20260914"
ns["ENV"] = [value.replace(old_guest, new_guest) for value in ns["ENV"]]
ns["menu"].TARGET = new_guest + ".deb"
ns["ARCHIVE"] = Path("/tmp/phase6-full-gui-opencode-1.18.25.tar.gz")
gui["GUEST"] = new_guest
OUT, GUEST = gui["OUT"], gui["GUEST"]
SAMPLES = tuple(f"sample-{index:02d}" for index in range(1, 6))
ORIGINAL = '{"autoupdate": false, "compaction": {"auto": false, "prune": false}}\n'
ORIGINAL_HASH = hashlib.sha256(ORIGINAL.encode()).hexdigest()


OBSERVER = r'''import json,os,re,sys,time
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
'''


def _sample(value: str) -> str:
    if value not in SAMPLES:
        raise ValueError("sample must be sample-01 through sample-05")
    return value


def _save(name: str, value) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")


def setup() -> None:
    gui["HARNESS"] = OBSERVER
    gui["setup"]()
    assert (OUT / "gate.py").read_text() == OBSERVER
    print("Five-sample normal GUI Gate ready; no sample has been launched.", flush=True)


def launch(sample: str) -> None:
    sample = _sample(sample)
    assert not (OUT / f"{sample}-pid.json").exists(), "never resend a sample"
    index = SAMPLES.index(sample)
    if index:
        assert (OUT / f"{SAMPLES[index - 1]}-reset.json").exists()
    current = json.loads(ns["ubuntu"].python(
        "from pathlib import Path; import hashlib,json; "
        "p=Path('/home/yoshimi/.config/opencode/opencode.jsonc'); "
        "print(json.dumps({'exists':p.is_file() and not p.is_symlink(),"
        "'sha256':hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None}))"
    ))
    assert current == {"exists": True, "sha256": ORIGINAL_HASH}, current
    _save(f"{sample}-target-before.json", current)
    pid = ns["debian"].qga("guest-exec", {
        "path": "/usr/sbin/runuser",
        "arg": ["-u", "user", "--", "/usr/bin/env", *ns["ENV"],
                "LLM_MANAGER_PERF_SAMPLE=" + sample,
                "/usr/bin/python3", "-I", GUEST + "/gate.py"],
        "capture-output": True,
    })["pid"]
    _save(f"{sample}-pid.json", {"pid": pid})
    print(f"Started {sample} PID {pid}; perform this GUI workflow once.", flush=True)


def status(sample: str) -> None:
    sample = _sample(sample)
    path = OUT / f"{sample}-exit.json"
    if path.exists():
        saved = json.loads(path.read_text())
        print(json.dumps({"sample": sample, "exited": saved.get("exited"),
                          "exitcode": saved.get("exitcode")}))
        return
    pid = json.loads((OUT / f"{sample}-pid.json").read_text())["pid"]
    result = ns["debian"].qga("guest-exec-status", {"pid": pid})
    if result.get("exited"):
        _save(f"{sample}-exit.json", result)
        print(json.dumps({"sample": sample, "exited": True,
                          "exitcode": result.get("exitcode")}))
    else:
        print(f"{sample} running; do not relaunch.", flush=True)


def collect(sample: str) -> None:
    sample = _sample(sample)
    status(sample)
    exit_path = OUT / f"{sample}-exit.json"
    if not exit_path.exists():
        raise RuntimeError("sample still running; collect later without relaunch")
    exited = json.loads(exit_path.read_text())
    assert exited.get("exitcode") == 0
    assert not exited.get("out-truncated") and not exited.get("err-truncated")
    guest_out = GUEST + "/evidence/" + sample
    names = json.loads(ns["debian"].python(
        "from pathlib import Path; import json; print(json.dumps([f.name for f in Path("
        + repr(guest_out) + ").iterdir() if f.is_file()]))"
    ))
    selected = [name for name in names if not name.startswith("step-")]
    for name in selected:
        assert Path(name).name == name
        handle = ns["debian"].qga("guest-file-open", {
            "path": guest_out + "/" + name, "mode": "r",
        })
        data = bytearray()
        try:
            while True:
                block = ns["debian"].qga("guest-file-read", {
                    "handle": handle, "count": 65536,
                })
                data.extend(base64.b64decode(block.get("buf-b64", "")))
                if block.get("eof"):
                    break
        finally:
            ns["debian"].qga("guest-file-close", {"handle": handle})
        (OUT / f"{sample}-{name}").write_bytes(data)
    result = json.loads((OUT / f"{sample}-result.json").read_text())
    assert result["status"] == "committed"
    assert not result["plan_injected"] and not result["approval_injected"]
    assert not result["transport_injected"]
    assert result["timing"]["apply_elapsed_including_authorization_ms"] > 0
    assert sum(e["correlation_id"] == "ssh.user_apply.invoke" for e in result["transport"]) == 1
    after = json.loads(ns["ubuntu"].python(
        "from pathlib import Path; import hashlib,json; "
        "p=Path('/home/yoshimi/.config/opencode/opencode.jsonc'); "
        "print(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),"
        "'config':json.loads(p.read_text())}))"
    ))
    _save(f"{sample}-target-after.json", after)
    assert after["config"]["compaction"] == {"auto": True, "prune": True}
    print(f"Collected committed {sample}; no operation was resent.", flush=True)


def reset(sample: str) -> None:
    sample = _sample(sample)
    assert sample != SAMPLES[-1], "the final sample is restored by snapshot cleanup"
    assert (OUT / f"{sample}-result.json").exists()
    path = OUT / f"{sample}-reset.json"
    assert not path.exists()
    code = (
        "from pathlib import Path\n"
        "p=Path('/home/yoshimi/.config/opencode/opencode.jsonc')\n"
        "assert p.is_file() and not p.is_symlink()\n"
        f"with p.open('w') as f: f.write({ORIGINAL!r})\n"
        "p.chmod(0o600)\n"
    )
    ns["user"](ns["ubuntu"], "yoshimi", code)
    current = json.loads(ns["ubuntu"].python(
        "from pathlib import Path; import hashlib,json; "
        "p=Path('/home/yoshimi/.config/opencode/opencode.jsonc'); "
        "print(json.dumps({'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))"
    ))
    assert current["sha256"] == ORIGINAL_HASH
    _save(path.name, {
        "scope": "disposable fixture reset outside timed interval",
        "sample": sample,
        "restored_sha256": ORIGINAL_HASH,
    })
    (OUT / "gate.py").write_text(OBSERVER)
    ns["debian"].transfer(str(OUT / "gate.py"), GUEST + "/gate.py")
    print(f"Reset disposable target after {sample}; next sample may start.", flush=True)


def summarize() -> None:
    rows = []
    for sample in SAMPLES:
        result = json.loads((OUT / f"{sample}-result.json").read_text())
        apply_events = [e for e in result["transport"]
                        if e["correlation_id"] == "ssh.user_apply.invoke"]
        rows.append({
            "sample": sample,
            "status": result["status"],
            "apply_elapsed_including_authorization_ms":
                result["timing"]["apply_elapsed_including_authorization_ms"],
            "ssh_apply_invoke_ms": apply_events[0]["elapsed_ms"],
            "ssh_event_count": len(result["transport"]),
        })
    _save("summary.json", {
        "schema_version": 1,
        "scope": "normal GUI production SSH user Apply; five sequential samples",
        "limitations": "single VM pair; interactive authorization is included only in end-to-end Apply elapsed time; between-sample fixture resets are excluded",
        "samples": rows,
    })
    print((OUT / "summary.json").read_text(), end="")


def cleanup() -> None:
    summarize()
    for sample in SAMPLES:
        exited = json.loads((OUT / f"{sample}-exit.json").read_text())
        assert exited.get("exited") and exited.get("exitcode") == 0
        assert (OUT / f"{sample}-results.png").exists()
    shutil.copy2(OUT / f"{SAMPLES[-1]}-exit.json", OUT / "commit-exit.json")
    shutil.copy2(OUT / f"{SAMPLES[-1]}-results.png", OUT / "commit-results.png")
    ns["cleanup"]()
    print("Five samples preserved and both VM baselines restored.", flush=True)


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "prepare":
        ns["prepare"]()
    elif action == "setup":
        setup()
    elif action in {"launch", "status", "collect", "reset"}:
        globals()[action](_sample(sys.argv[2]))
    elif action == "summarize":
        summarize()
    elif action == "inspect":
        ns["inspect"]()
    elif action == "cleanup":
        cleanup()
    else:
        raise ValueError(action)
