import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time


REPO = Path("/home/yoshimi/WorkSpace/LLM-Manager")
spec = importlib.util.spec_from_file_location(
    "vm_gate", REPO / "docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py"
)
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

SNAPSHOT = "phase6-accessibility-b15a984-20260912"
OUT = REPO / "docs/validation/accessibility-b15a984-2026-09-12"
DEB = Path(
    "/tmp/llm-manager-candidate-b15a984-20260912/llm-manager_0.1.0_all.deb"
)
DEB_SHA256 = "292b831c5454e3a6d41b59a67145474a76b066146bebc4e7308b81a6e50ff7f8"
GUEST_DEB = "/tmp/phase6-accessibility-b15a984.deb"
USER = "yoshimi"
RUNTIME = "/run/user/1000"


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def baseline():
    return json.loads((OUT / "baseline.json").read_text())


def session_environment(locale):
    return [
        f"XDG_RUNTIME_DIR={RUNTIME}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path={RUNTIME}/bus",
        "XDG_SESSION_TYPE=wayland",
        "WAYLAND_DISPLAY=wayland-0",
        "QT_QPA_PLATFORM=wayland",
        "QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1",
        "PYTHONDONTWRITEBYTECODE=1",
        f"XDG_CONFIG_HOME=/tmp/phase6-accessibility-config-{locale}",
        f"LANG={locale}",
        f"LC_ALL={locale}",
    ]


def guest_exec(path, arguments):
    result = vm.qga(
        "guest-exec",
        {"path": path, "arg": arguments, "capture-output": True},
    )
    return result["pid"]


def guest_status(pid):
    result = vm.qga("guest-exec-status", {"pid": pid})
    if not result.get("exited"):
        return None
    return {
        "exit_code": result.get("exitcode"),
        "stdout": base64.b64decode(result.get("out-data", "")).decode(),
        "stderr": base64.b64decode(result.get("err-data", "")).decode(),
        "out_truncated": bool(result.get("out-truncated")),
        "err_truncated": bool(result.get("err-truncated")),
    }


INSPECTOR = r'''
import json
import time
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi

Atspi.init()

def node_value(node, depth=0):
    value={'name':'','description':'','role':'unknown','states':{},'children':[]}
    try: value['name']=node.get_name() or ''
    except Exception: pass
    try: value['description']=node.get_description() or ''
    except Exception: pass
    try: value['role']=node.get_role_name() or 'unknown'
    except Exception: pass
    try:
        states=node.get_state_set()
        value['states']={
            name:bool(states.contains(item)) for name,item in (
                ('enabled',Atspi.StateType.ENABLED),
                ('focusable',Atspi.StateType.FOCUSABLE),
                ('focused',Atspi.StateType.FOCUSED),
                ('sensitive',Atspi.StateType.SENSITIVE),
                ('showing',Atspi.StateType.SHOWING),
                ('visible',Atspi.StateType.VISIBLE),
            )
        }
    except Exception: pass
    if depth < 8:
        try: count=min(node.get_child_count(),256)
        except Exception: count=0
        for index in range(count):
            try: child=node.get_child_at_index(index)
            except Exception: continue
            if child is not None: value['children'].append(node_value(child,depth+1))
    return value

def flatten(value):
    yield value
    for child in value['children']: yield from flatten(child)

deadline=time.monotonic()+15
selected=None
while time.monotonic()<deadline:
    desktop=Atspi.get_desktop(0)
    for index in range(desktop.get_child_count()):
        application=desktop.get_child_at_index(index)
        value=node_value(application)
        if any(item['name']=='LLM Manager' for item in flatten(value)):
            selected=value
            break
    if selected is not None: break
    time.sleep(.25)
if selected is None: raise SystemExit('LLM Manager accessibility tree not found')
print(json.dumps(selected,ensure_ascii=False,sort_keys=True))
'''


def flatten(value):
    yield value
    for child in value["children"]:
        yield from flatten(child)


def inspect(locale, expected):
    config = f"/tmp/phase6-accessibility-config-{locale}"
    vm.execute("/usr/bin/mkdir", ["-m", "0700", config])
    vm.execute("/usr/bin/chown", ["1000:1000", config])
    environment = session_environment(locale)
    app_pid = guest_exec(
        "/usr/sbin/runuser",
        [
            "-u",
            USER,
            "--",
            "/usr/bin/env",
            *environment,
            "/usr/bin/llm-manager",
        ],
    )
    inspector = vm.execute(
        "/usr/sbin/runuser",
        [
            "-u",
            USER,
            "--",
            "/usr/bin/env",
            *environment,
            "/usr/bin/python3",
            "-I",
            "-c",
            INSPECTOR,
        ],
    )
    tree = json.loads(inspector)
    nodes = list(flatten(tree))
    names = [node["name"] for node in nodes]
    roles = {node["name"]: node["role"] for node in nodes if node["name"]}
    assert "LLM Manager" in names
    for name in expected["all"]:
        assert name in names, (name, names)
    for name in expected["focusable"]:
        matching = [node for node in nodes if node["name"] == name]
        assert len(matching) == 1, (name, matching)
        assert matching[0]["states"].get("focusable"), matching[0]
        assert matching[0]["states"].get("enabled"), matching[0]
    assert not any(
        name in names
        for name in (
            "start-diagnosis",
            "cancel-operation",
            "host-selector",
            "language-selector",
            "workflow-status",
        )
    )
    save(
        f"{locale}-summary.json",
        {
            "expected_names": expected,
            "observed_names": names,
            "observed_roles": roles,
            "node_count": len(nodes),
        },
    )
    save(f"{locale}-tree.json", tree)
    vm.virsh("send-key", vm.VM, "KEY_LEFTALT", "KEY_F4")
    status = None
    for _ in range(80):
        status = guest_status(app_pid)
        if status is not None:
            break
        time.sleep(0.25)
    assert status is not None, app_pid
    assert not status["out_truncated"] and not status["err_truncated"], status
    assert status["exit_code"] == 0, status
    save(f"{locale}-exit.json", status)
    vm.execute("/usr/bin/rm", ["-rf", config])


def prepare():
    assert vm.virsh("domstate", vm.VM).strip() == "running"
    assert SNAPSHOT not in vm.virsh("snapshot-list", vm.VM, "--name").splitlines()
    assert hashlib.sha256(DEB.read_bytes()).hexdigest() == DEB_SHA256
    assert OUT.is_dir() and {path.name for path in OUT.iterdir()} == {"gate.py"}
    assert vm.python(
        "from pathlib import Path; print(Path('/run/user/1000/wayland-0').is_socket())"
    ).strip() == "True"
    locales = vm.execute("/usr/bin/locale", ["-a"])
    assert "C.utf8" in locales and "ja_JP.utf8" in locales
    original_accessibility = vm.execute(
        "/usr/sbin/runuser",
        [
            "-u",
            USER,
            "--",
            "/usr/bin/env",
            f"XDG_RUNTIME_DIR={RUNTIME}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path={RUNTIME}/bus",
            "/usr/bin/gsettings",
            "get",
            "org.gnome.desktop.interface",
            "toolkit-accessibility",
        ],
    ).strip()
    assert original_accessibility == "false"
    save("baseline.json", vm.inventory())
    save(
        "environment.json",
        {
            "candidate_sha256": DEB_SHA256,
            "source_commit": "b15a98454ddf9e397333350d371b35cc2ed8fdd8",
            "wayland_display": "wayland-0",
            "toolkit_accessibility": original_accessibility,
            "atspi": "available",
            "orca": "installed",
        },
    )
    print(
        vm.virsh(
            "snapshot-create-as",
            vm.VM,
            SNAPSHOT,
            "Updated candidate AT-SPI accessibility gate; restore running",
            "--atomic",
        ),
        flush=True,
    )
    vm.transfer(DEB, GUEST_DEB)
    vm.execute("/bin/chmod", ["0644", GUEST_DEB])
    assert vm.python(
        f"import hashlib; print(hashlib.sha256(open({GUEST_DEB!r},'rb').read()).hexdigest())"
    ).strip() == DEB_SHA256
    simulation = vm.execute(
        "/usr/bin/apt-get",
        ["-s", "--no-install-recommends", "install", GUEST_DEB],
    )
    (OUT / "apt-simulation.txt").write_text(simulation)
    installs = {
        line.split()[1] for line in simulation.splitlines() if line.startswith("Inst ")
    }
    removes = {
        line.split()[1] for line in simulation.splitlines() if line.startswith("Remv ")
    }
    assert installs <= {"llm-manager"} and not removes, simulation
    install = vm.execute(
        "/usr/bin/apt-get",
        ["-y", "--no-install-recommends", "install", GUEST_DEB],
    )
    (OUT / "apt-install.txt.gz").write_bytes(gzip.compress(install.encode(), mtime=0))
    assert vm.execute("/usr/bin/dpkg", ["-V", "llm-manager"]) == ""
    print("Candidate installed inside snapshot; ready for AT-SPI inspection.", flush=True)


def run():
    assert SNAPSHOT in vm.virsh("snapshot-list", vm.VM, "--name").splitlines()
    inspect(
        "C.utf8",
        {
            "all": ["LLM Manager", "Hosts", "English / 日本語", "Ready", "Diagnose", "Cancel"],
            "focusable": ["Hosts", "English / 日本語", "Diagnose"],
        },
    )
    inspect(
        "ja_JP.utf8",
        {
            "all": ["LLM Manager", "ホスト", "English / 日本語", "準備完了", "診断する", "取消"],
            "focusable": ["ホスト", "English / 日本語", "診断する"],
        },
    )
    print("English and Japanese AT-SPI trees passed.", flush=True)


def restore():
    assert SNAPSHOT in vm.virsh("snapshot-list", vm.VM, "--name").splitlines()
    print(vm.virsh("snapshot-revert", vm.VM, SNAPSHOT, "--running"), flush=True)
    restored = vm.inventory()
    save("restored.json", restored)
    assert restored == baseline()
    print(vm.virsh("snapshot-delete", vm.VM, SNAPSHOT), flush=True)
    print("Baseline exact match; temporary snapshot deleted; VM running.", flush=True)


if __name__ == "__main__":
    {"prepare": prepare, "run": run, "restore": restore}[sys.argv[1]]()
