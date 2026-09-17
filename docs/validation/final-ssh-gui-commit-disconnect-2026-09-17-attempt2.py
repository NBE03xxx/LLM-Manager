"""Final SSH commit/disconnect Gate with a human-turn auth allowance."""
from pathlib import Path
import sys


BASE = Path(__file__).with_name("final-ssh-gui-commit-disconnect-2026-09-17.py")
source = BASE.read_text()
source = source.replace("phase6-final-ssh-commit-net3", "phase6-final-ssh-commit-net4")
source = source.replace(
    "final-ssh-gui-commit-disconnect-2026-09-17",
    "final-ssh-gui-commit-disconnect-2026-09-17-attempt2",
)
gate = {"__file__": str(BASE), "__name__": "final_ssh_commit_disconnect_20260917_attempt2"}
exec(compile(source, str(BASE), "exec"), gate)


def setup_with_human_turn_allowance() -> None:
    gate["gate"]["scope"]["setup"]()
    ns = gate["ns"]
    guest = gate["GUEST"]
    local_gate = gate["gate"]["OUT"] / "gate.py"
    text = local_gate.read_text()
    assert text.count("history=[]") == 1
    injection = r'''history=[]
# Validation-only allowance for human input crossing a Codex task turn.
# The product accepts at most 600 seconds; plan, approval, and operation stay production-owned.
from llm_manager.ui import composition as _validation_composition
_validation_real_remote_sudo = _validation_composition.OpenSshRemoteSudoInvoker
def _validation_remote_sudo(runner, terminal, completion):
 return _validation_real_remote_sudo(runner, terminal, completion, timeout_seconds=600)
_validation_composition.OpenSshRemoteSudoInvoker = _validation_remote_sudo
'''
    text = text.replace("history=[]", injection)
    marker = "'transport_condition':'stdout relay and short keepalive; actual NIC cut'"
    assert text.count(marker) == 1
    text = text.replace(
        marker,
        marker + ", 'remote_sudo_timeout_seconds':600, 'remote_sudo_timeout_injected':True",
    )
    compile(text, "final-ssh-gui-commit-disconnect-attempt2.py", "exec")
    local_gate.write_text(text)
    ns["debian"].transfer(str(local_gate), guest + "/gate.py")
    ns["debian"].execute("/bin/chown", ["1000:1000", guest + "/gate.py"])
    print("GUI harness ready with a documented 600-second remote sudo allowance.", flush=True)


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "prepare":
        gate["gate"]["prepare"]()
    elif action == "setup":
        setup_with_human_turn_allowance()
    elif action == "watch":
        gate["watch_long"]()
    elif action == "collect":
        gate["gate"]["scope"]["collect"]()
    elif action == "cleanup":
        gate["network"].cleanup()
    elif action in {"launch", "status"}:
        gate["ns"][action]("commit")
    elif action == "inspect":
        gate["ns"]["inspect"]()
    elif action == "mark-pre-mutation-failure":
        gate["mark_pre_mutation_failure"]()
    else:
        raise ValueError(action)
