"""Fresh final SSH rollback/disconnect Gate with human-turn auth allowance."""
from pathlib import Path
import sys


BASE = Path(__file__).with_name("final-ssh-gui-rollback-disconnect-2026-09-16.py")
source = BASE.read_text()
source = source.replace("phase6-final-ssh-rollback-net", "phase6-final-ssh-rollback-net2")
source = source.replace(
    "final-ssh-gui-rollback-disconnect-2026-09-16",
    "final-ssh-gui-rollback-disconnect-2026-09-17",
)
source = source.replace(
    'source = source.replace("20260915", "20260916")',
    'source = source.replace("20260915", "20260917")',
)
source = source.replace("deadline = time.monotonic() + 900", "deadline = time.monotonic() + 3600")
gate = {"__file__": str(BASE), "__name__": "final_ssh_rollback_disconnect_20260917"}
exec(compile(source, str(BASE), "exec"), gate)

HARNESS = gate["natural"]["gate"]["HARNESS"]
assert HARNESS.count("history=[]") == 1
injection = r'''history=[]
# Validation-only allowance for human input crossing a Codex task turn.
# The product accepts at most 600 seconds; plan, approval, and operation stay production-owned.
from llm_manager.ui import composition as _validation_composition
_validation_real_remote_sudo = _validation_composition.OpenSshRemoteSudoInvoker
def _validation_remote_sudo(runner, terminal, completion):
 return _validation_real_remote_sudo(runner, terminal, completion, timeout_seconds=600)
_validation_composition.OpenSshRemoteSudoInvoker = _validation_remote_sudo
'''
HARNESS = HARNESS.replace("history=[]", injection)
marker = "'transport_condition':'rollback stdout relay and short keepalive; actual NIC cut',"
assert HARNESS.count(marker) == 1
HARNESS = HARNESS.replace(
    marker,
    marker + "'remote_sudo_timeout_seconds':600,'remote_sudo_timeout_injected':True,",
)
compile(HARNESS, "final-ssh-gui-rollback-disconnect-2026-09-17-observer.py", "exec")
gate["natural"]["gate"]["HARNESS"] = HARNESS


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "prepare":
        gate["natural"]["prepare"]()
    elif action == "setup":
        gate["setup"]()
    elif action == "watch":
        gate["watch"]()
    elif action == "launch":
        gate["natural"]["launch"]()
    elif action == "status":
        gate["natural"]["status"]()
    elif action == "watcher-status":
        gate["natural"]["watcher_status"]()
    elif action == "collect":
        gate["collect"]()
    elif action == "inspect":
        gate["natural"]["inspect"]()
    elif action == "cleanup":
        gate["cleanup"]()
    else:
        raise ValueError(action)
