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

SNAPSHOT = "phase6-accessibility-fix-20260912"
OUT = REPO / "docs/validation/accessibility-fix-2026-09-12"
DEB = Path(
    "/tmp/llm-manager-accessibility-fix-20260912/llm-manager_0.1.0_all.deb"
)
DEB_SHA256 = "351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243"
GUEST_DEB = "/tmp/phase6-accessibility-fix.deb"
TESTS_ARCHIVE = Path("/tmp/llm-manager-accessibility-fix-tests-20260912.tar.gz")
TESTS_SHA256 = "7ad657b42e51619224fb672a07a6122e574b48cf7715e9e32a450420f054b33d"
GUEST_TESTS_ARCHIVE = "/tmp/phase6-accessibility-fix-tests.tar.gz"
GUEST_TESTS_ROOT = "/tmp/phase6-accessibility-fix-tests"
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
        f"XDG_CONFIG_HOME=/tmp/phase6-accessibility-fix-config-{locale}",
        f"LANG={locale}",
        f"LC_ALL={locale}",
    ]


def guest_exec(path, arguments):
    result = vm.qga(
        "guest-exec", {"path": path, "arg": arguments, "capture-output": True}
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

def safe_name(node):
    try: return node.get_name() or ''
    except Exception: return ''

def relation_value(relation):
    relation_type = relation.get_relation_type()
    relation_name = relation_type.value_name.removeprefix('ATSPI_RELATION_').lower()
    targets = []
    for index in range(relation.get_n_targets()):
        target = relation.get_target(index)
        if target is not None: targets.append(safe_name(target))
    return {'type': relation_name, 'targets': targets}

def node_value(node, depth=0):
    value={
        'name':safe_name(node), 'description':'', 'role':'unknown',
        'states':{}, 'relations':[], 'children':[]
    }
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
    try: value['relations']=[relation_value(item) for item in node.get_relation_set()]
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


def matching(nodes, *, name, role=None):
    return [
        node for node in nodes
        if node["name"] == name and (role is None or node["role"] == role)
    ]


def inspect(locale, expected):
    config = f"/tmp/phase6-accessibility-fix-config-{locale}"
    vm.execute("/usr/bin/mkdir", ["-m", "0700", config])
    vm.execute("/usr/bin/chown", ["1000:1000", config])
    environment = session_environment(locale)
    app_pid = guest_exec(
        "/usr/sbin/runuser",
        ["-u", USER, "--", "/usr/bin/env", *environment, "/usr/bin/llm-manager"],
    )
    try:
        inspector = vm.execute(
            "/usr/sbin/runuser",
            [
                "-u", USER, "--", "/usr/bin/env", *environment,
                "/usr/bin/python3", "-I", "-c", INSPECTOR,
            ],
        )
        tree = json.loads(inspector)
        save(f"{locale}-tree.json", tree)
        nodes = list(flatten(tree))
        names = [node["name"] for node in nodes]

        assert "LLM Manager" in names
        for name in expected["all_names"]:
            assert name in names, (name, names)
        for spec in expected["controls"]:
            found = matching(nodes, name=spec["name"], role=spec["role"])
            assert len(found) == 1, (spec, found)
            node = found[0]
            assert node["description"] == spec["description"], (spec, node)
            assert node["states"].get("focusable"), node
            assert node["states"].get("enabled"), node
        for label, target in expected["label_for"]:
            found = matching(nodes, name=label, role="label")
            assert len(found) == 1, (label, found)
            relations = found[0]["relations"]
            assert any(
                relation["type"] == "label_for" and target in relation["targets"]
                for relation in relations
            ), (label, target, relations)
        internal_prefixes = ("page-", "scroll-", "placeholder-")
        assert not any(name.startswith(internal_prefixes) for name in names), names
        internal_names = {
            "start-diagnosis", "cancel-operation", "host-selector",
            "language-selector", "profile-selector", "workflow-status",
        }
        assert not internal_names.intersection(names), names
        save(
            f"{locale}-summary.json",
            {
                "expected": expected,
                "observed_names": names,
                "node_count": len(nodes),
                "result": "pass",
            },
        )
    finally:
        vm.virsh("send-key", vm.VM, "KEY_LEFTALT", "KEY_F4")
        status = None
        for _ in range(80):
            status = guest_status(app_pid)
            if status is not None:
                break
            time.sleep(0.25)
        save(f"{locale}-exit.json", status)
        vm.execute("/usr/bin/rm", ["-rf", config])
    assert status is not None, app_pid
    assert not status["out_truncated"] and not status["err_truncated"], status
    assert status["exit_code"] == 0, status


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
            "-u", USER, "--", "/usr/bin/env",
            f"XDG_RUNTIME_DIR={RUNTIME}",
            f"DBUS_SESSION_BUS_ADDRESS=unix:path={RUNTIME}/bus",
            "/usr/bin/gsettings", "get", "org.gnome.desktop.interface",
            "toolkit-accessibility",
        ],
    ).strip()
    assert original_accessibility == "false"
    save("baseline.json", vm.inventory())
    save(
        "environment.json",
        {
            "candidate_sha256": DEB_SHA256,
            "candidate_basis_commit": "8056850bf6c2747ca25dd26d006a003066ed9f3d",
            "candidate_overlay": [
                "src/llm_manager/ui/i18n.py",
                "src/llm_manager/ui/qt_window.py",
                "tests/test_ui_qt_runtime.py",
                "tests/test_ui_qt_window.py",
            ],
            "wayland_display": "wayland-0",
            "toolkit_accessibility": original_accessibility,
            "atspi": "available",
            "orca": "installed",
        },
    )
    print(
        vm.virsh(
            "snapshot-create-as", vm.VM, SNAPSHOT,
            "Accessibility-fix AT-SPI gate; restore running", "--atomic",
        ),
        flush=True,
    )
    vm.transfer(DEB, GUEST_DEB)
    vm.execute("/bin/chmod", ["0644", GUEST_DEB])
    assert vm.python(
        f"import hashlib; print(hashlib.sha256(open({GUEST_DEB!r},'rb').read()).hexdigest())"
    ).strip() == DEB_SHA256
    simulation = vm.execute(
        "/usr/bin/apt-get", ["-s", "--no-install-recommends", "install", GUEST_DEB]
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
        "/usr/bin/apt-get", ["-y", "--no-install-recommends", "install", GUEST_DEB]
    )
    (OUT / "apt-install.txt.gz").write_bytes(gzip.compress(install.encode(), mtime=0))
    assert vm.execute("/usr/bin/dpkg", ["-V", "llm-manager"]) == ""
    print("Fix candidate installed inside snapshot; ready for inspection.", flush=True)


def run():
    assert SNAPSHOT in vm.virsh("snapshot-list", vm.VM, "--name").splitlines()
    inspect(
        "C.utf8",
        {
            "all_names": [
                "LLM Manager", "Hosts", "Language", "Optimization profile",
                "Local", "English", "Balanced", "Ready", "Diagnose", "Cancel",
            ],
            "controls": [
                {"name": "Local", "role": "combo box", "description": "Hosts"},
                {"name": "English", "role": "combo box", "description": "Language"},
                {
                    "name": "Balanced", "role": "combo box",
                    "description": "Optimization profile",
                },
                {"name": "Diagnose", "role": "button", "description": ""},
            ],
            "label_for": [
                ["Hosts", "Local"], ["Language", "English"],
                ["Optimization profile", "Balanced"],
            ],
        },
    )
    inspect(
        "ja_JP.utf8",
        {
            "all_names": [
                "LLM Manager", "ホスト", "言語", "最適化プロファイル",
                "Local", "日本語", "バランス", "準備完了", "診断する", "キャンセル",
            ],
            "controls": [
                {"name": "Local", "role": "combo box", "description": "ホスト"},
                {"name": "日本語", "role": "combo box", "description": "言語"},
                {
                    "name": "バランス", "role": "combo box",
                    "description": "最適化プロファイル",
                },
                {"name": "診断する", "role": "button", "description": ""},
            ],
            "label_for": [
                ["ホスト", "Local"], ["言語", "日本語"],
                ["最適化プロファイル", "バランス"],
            ],
        },
    )
    print("English and Japanese AT-SPI trees passed.", flush=True)


def tests():
    assert SNAPSHOT in vm.virsh("snapshot-list", vm.VM, "--name").splitlines()
    assert hashlib.sha256(TESTS_ARCHIVE.read_bytes()).hexdigest() == TESTS_SHA256
    vm.transfer(TESTS_ARCHIVE, GUEST_TESTS_ARCHIVE)
    assert vm.python(
        f"import hashlib; print(hashlib.sha256(open({GUEST_TESTS_ARCHIVE!r},'rb').read()).hexdigest())"
    ).strip() == TESTS_SHA256
    vm.execute("/usr/bin/rm", ["-rf", GUEST_TESTS_ROOT])
    vm.execute("/usr/bin/mkdir", ["-m", "0755", GUEST_TESTS_ROOT])
    vm.execute(
        "/usr/bin/tar",
        ["-xzf", GUEST_TESTS_ARCHIVE, "-C", GUEST_TESTS_ROOT, "--no-same-owner"],
    )
    runner = f'''import os, subprocess, sys
environment = os.environ.copy()
environment.update({{
    "QT_QPA_PLATFORM": "offscreen",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONPATH": {str(GUEST_TESTS_ROOT + ":" + GUEST_TESTS_ROOT + "/src")!r},
}})
result = subprocess.run(
    [
        "/usr/bin/python3", "-m", "unittest",
        "tests.test_ui_i18n", "tests.test_ui_qt_window",
        "tests.test_ui_qt_runtime", "-v",
    ],
    cwd={GUEST_TESTS_ROOT!r}, env=environment,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)
print(result.stdout, end="")
raise SystemExit(result.returncode)
'''
    output = vm.execute(
        "/usr/sbin/runuser",
        [
            "-u", USER, "--", "/usr/bin/python3", "-I", "-c", runner,
        ],
    )
    (OUT / "ubuntu-qt-tests.txt").write_text(output)
    vm.execute("/usr/bin/rm", ["-rf", GUEST_TESTS_ROOT, GUEST_TESTS_ARCHIVE])
    print("Ubuntu system-PySide focused tests passed.", flush=True)


def restore():
    assert SNAPSHOT in vm.virsh("snapshot-list", vm.VM, "--name").splitlines()
    print(vm.virsh("snapshot-revert", vm.VM, SNAPSHOT, "--running"), flush=True)
    restored = vm.inventory()
    save("restored.json", restored)
    assert restored == baseline()
    print(vm.virsh("snapshot-delete", vm.VM, SNAPSHOT), flush=True)
    print("Baseline exact match; temporary snapshot deleted; VM running.", flush=True)


if __name__ == "__main__":
    {"prepare": prepare, "run": run, "tests": tests, "restore": restore}[sys.argv[1]]()
