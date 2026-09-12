import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


VM = "ubuntu26.04"
SNAPSHOT = "phase6-remote-helper-b15a984-20260912"
OUT = Path(
    "/home/yoshimi/WorkSpace/LLM-Manager/"
    "docs/validation/remote-helper-b15a984-2026-09-12"
)
OLD_SOURCE_COMMIT = "88542323d250e8e9e18bc11e3ed0e093ade3f396"
OLD_ARTIFACT = Path("/tmp/llm-manager-remote-upgrade-predecessor-8854232.deb")
OLD_SHA256 = "c80493117be42491921b726b05140ac606af5a806a80b75945f45a26807db882"
NEW_SOURCE_COMMIT = "b15a98454ddf9e397333350d371b35cc2ed8fdd8"
NEW_ARTIFACT = Path(
    "/tmp/llm-manager-candidate-b15a984-20260912/"
    "llm-manager-remote-helper_0.1.0_all.deb"
)
NEW_SHA256 = "ee4930896f02e72d7097c58878e8900bdb0c11a495b90fd3c7b6e14b0af034bc"
GUEST_ROOT = "/tmp/phase6-remote-helper-b15a984-20260912"
GUEST_OLD = f"{GUEST_ROOT}/old.deb"
GUEST_NEW = f"{GUEST_ROOT}/new.deb"
PACKAGE = "llm-manager-remote-helper"


def virsh(*args: str) -> str:
    return subprocess.check_output(["virsh", *args], text=True)


def qga(command: str, arguments: dict[str, object]) -> object:
    response = virsh(
        "qemu-agent-command",
        VM,
        json.dumps({"execute": command, "arguments": arguments}),
    )
    return json.loads(response)["return"]


def execute(path: str, arguments: list[str], *, expected: int = 0) -> str:
    started = qga(
        "guest-exec",
        {"path": path, "arg": arguments, "capture-output": True},
    )
    assert isinstance(started, dict)
    pid = started["pid"]
    for _ in range(240):
        result = qga("guest-exec-status", {"pid": pid})
        assert isinstance(result, dict)
        if result.get("exited"):
            assert not result.get("out-truncated") and not result.get("err-truncated"), result
            stdout = base64.b64decode(result.get("out-data", "")).decode()
            stderr = base64.b64decode(result.get("err-data", "")).decode()
            assert result.get("exitcode") == expected, (result, stdout, stderr)
            return stdout + stderr
        time.sleep(0.25)
    raise RuntimeError(f"guest PID {pid} did not finish; inspect it before retrying")


def python(code: str) -> str:
    return execute("/usr/bin/python3", ["-I", "-c", code])


def transfer(source: Path, target: str) -> None:
    handle = qga("guest-file-open", {"path": target, "mode": "w"})
    assert isinstance(handle, int)
    try:
        data = source.read_bytes()
        for position in range(0, len(data), 32768):
            chunk = data[position : position + 32768]
            result = qga(
                "guest-file-write",
                {"handle": handle, "buf-b64": base64.b64encode(chunk).decode()},
            )
            assert isinstance(result, dict) and result["count"] == len(chunk)
    finally:
        qga("guest-file-close", {"handle": handle})


def inventory() -> dict[str, object]:
    return json.loads(
        python(
            r'''import hashlib,json,subprocess
from pathlib import Path
packages=sorted(subprocess.check_output([
    'dpkg-query','-W','-f=${binary:Package}\t${Version}\t${db:Status-Status}\n'
],text=True).splitlines())
manual=sorted(subprocess.check_output(['apt-mark','showmanual'],text=True).splitlines())
roots=[
    '/home/yoshimi/.config/llm-manager',
    '/home/yoshimi/.config/opencode',
    '/home/yoshimi/.ssh',
    '/var/lib/llm-manager',
    '/usr/local/bin/opencode',
]
entries={}
for root in roots:
    path=Path(root)
    paths=[path]+(sorted(path.rglob('*')) if path.is_dir() and not path.is_symlink() else [])
    for item in paths:
        if not item.exists() and not item.is_symlink():
            entries[str(item)]=None
            continue
        metadata=item.lstat()
        entries[str(item)]={
            'mode':metadata.st_mode,
            'uid':metadata.st_uid,
            'gid':metadata.st_gid,
            'hash':hashlib.sha256(item.read_bytes()).hexdigest()
                   if item.is_file() and not item.is_symlink() else None,
        }
print(json.dumps({'packages':packages,'manual':manual,'entries':entries}))
'''
        )
    )


def package_version() -> str | None:
    output = python(
        "import subprocess\n"
        "p=subprocess.run(['dpkg-query','-W','-f=${db:Status-Status}\\t${Version}',"
        f"'{PACKAGE}'],text=True,capture_output=True)\n"
        "print(p.stdout if p.returncode == 0 else '')\n"
    ).strip()
    if not output:
        return None
    status, version = output.split("\t", 1)
    assert status == "installed"
    return version


def protected_entries() -> dict[str, object]:
    return inventory()["entries"]  # type: ignore[return-value]


def write(name: str, content: str) -> None:
    (OUT / name).write_text(content)


def apt_simulation(
    name: str, *arguments: str, allowed_removals: frozenset[str] = frozenset()
) -> str:
    output = execute("/usr/bin/apt-get", ["-s", *arguments])
    write(name, output)
    removals = {
        line.split()[1] for line in output.splitlines() if line.startswith("Remv ")
    }
    assert removals <= allowed_removals, (removals, output)
    changed = {
        line.split()[1]
        for line in output.splitlines()
        if line.startswith(("Inst ", "Conf "))
    }
    assert changed <= {PACKAGE}, changed
    return output


def validate_installed(expected_version: str, evidence_name: str) -> None:
    assert package_version() == expected_version
    assert execute("/usr/bin/dpkg", ["-V", PACKAGE]) == ""
    evidence = python(
        r'''import hashlib,json,os,stat
from pathlib import Path
helper=Path('/usr/bin/llm-manager-remote-helper')
metadata=Path('/usr/share/llm-manager-remote-helper/helper-metadata.json')
runtime=Path('/usr/lib/llm-manager-remote-helper/llm_manager')
assert helper.is_file() and not helper.is_symlink()
assert metadata.is_file() and not metadata.is_symlink()
assert runtime.is_dir() and not runtime.is_symlink()
for path,mode in ((helper,0o755),(metadata,0o644)):
    value=path.stat(follow_symlinks=False)
    assert (value.st_uid,value.st_gid,stat.S_IMODE(value.st_mode)) == (0,0,mode)
document=json.loads(metadata.read_text())
assert set(document) == {'package','package_version','protocol_version','schema_version'}
assert document['package'] == 'llm-manager-remote-helper'
assert document['protocol_version'] == 1 and document['schema_version'] == '1.0'
canonical=json.dumps(document,sort_keys=True,separators=(',',':'))+'\n'
assert metadata.read_text() == canonical
assert not list(runtime.rglob('__pycache__')) and not list(runtime.rglob('*.pyc'))
print(json.dumps({
    'metadata':document,
    'helper_sha256':hashlib.sha256(helper.read_bytes()).hexdigest(),
    'metadata_sha256':hashlib.sha256(metadata.read_bytes()).hexdigest(),
    'helper_mode':'0755','metadata_mode':'0644','owner':'root:root',
},sort_keys=True))
'''
    )
    document = json.loads(evidence)
    assert document["metadata"]["package_version"] == expected_version
    write(evidence_name, json.dumps(document, indent=2, sort_keys=True) + "\n")
    listing = execute("/usr/bin/dpkg", ["-L", PACKAGE])
    write(evidence_name.replace(".json", "-files.txt"), listing)
    forbidden = (
        "/usr/bin/llm-manager\n",
        "/usr/bin/llm-manager-helper\n",
        "/usr/share/applications/",
        "/usr/share/icons/",
        "/usr/share/polkit-1/",
        "/usr/lib/python3/dist-packages/llm_manager",
    )
    assert not any(value in listing for value in forbidden), listing


def assert_removed() -> None:
    assert package_version() is None
    result = python(
        "from pathlib import Path\n"
        "paths=['/usr/bin/llm-manager-remote-helper',"
        "'/usr/lib/llm-manager-remote-helper',"
        "'/usr/share/llm-manager-remote-helper',"
        "'/usr/share/doc/llm-manager-remote-helper']\n"
        "print(int(any(Path(p).exists() or Path(p).is_symlink() for p in paths)))\n"
    )
    assert result.strip() == "0"


def prepare() -> None:
    assert virsh("domstate", VM).strip() == "running"
    assert SNAPSHOT not in virsh("snapshot-list", VM, "--name").splitlines()
    assert OUT.is_dir()
    assert {path.name for path in OUT.iterdir()} == {"lifecycle.py"}
    for path, expected in ((OLD_ARTIFACT, OLD_SHA256), (NEW_ARTIFACT, NEW_SHA256)):
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    baseline = inventory()
    assert package_version() is None
    (OUT / "baseline.json").write_text(json.dumps(baseline, indent=2) + "\n")
    write(
        "artifact-identity.json",
        json.dumps(
            {
                "upgrade_predecessor": {
                    "source_commit": OLD_SOURCE_COMMIT,
                    "sha256": OLD_SHA256,
                    "version": "0.1.0~dev0",
                },
                "candidate": {
                    "source_commit": NEW_SOURCE_COMMIT,
                    "sha256": NEW_SHA256,
                    "version": "0.1.0",
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    print(
        virsh(
            "snapshot-create-as",
            VM,
            SNAPSHOT,
            "Disposable updated remote-helper lifecycle gate; restore running desktop",
            "--atomic",
        ),
        flush=True,
    )
    execute("/usr/bin/mkdir", ["-m", "0700", GUEST_ROOT])
    print("Baseline saved and disposable snapshot created.", flush=True)


def gate() -> None:
    assert SNAPSHOT in virsh("snapshot-list", VM, "--name").splitlines()
    baseline = json.loads((OUT / "baseline.json").read_text())
    baseline_entries = baseline["entries"]
    assert inventory() == baseline
    transfer(OLD_ARTIFACT, GUEST_OLD)
    transfer(NEW_ARTIFACT, GUEST_NEW)
    for guest, expected in ((GUEST_OLD, OLD_SHA256), (GUEST_NEW, NEW_SHA256)):
        actual = python(
            f"import hashlib; print(hashlib.sha256(open({guest!r},'rb').read()).hexdigest())"
        ).strip()
        assert actual == expected

    apt_simulation("apt-old-fresh-simulation.txt", "--no-install-recommends", "install", GUEST_OLD)
    write(
        "apt-old-fresh-install.txt",
        execute(
            "/usr/bin/apt-get",
            ["-y", "--no-install-recommends", "install", GUEST_OLD],
        ),
    )
    validate_installed("0.1.0~dev0", "old-installed.json")
    assert protected_entries() == baseline_entries

    simulation = apt_simulation(
        "apt-upgrade-simulation.txt", "--no-install-recommends", "install", GUEST_NEW
    )
    assert "0.1.0~dev0" in simulation and "0.1.0" in simulation, simulation
    write(
        "apt-upgrade.txt",
        execute(
            "/usr/bin/apt-get",
            ["-y", "--no-install-recommends", "install", GUEST_NEW],
        ),
    )
    validate_installed("0.1.0", "upgraded-installed.json")
    assert protected_entries() == baseline_entries

    apt_simulation(
        "apt-reinstall-simulation.txt",
        "--reinstall",
        "--no-install-recommends",
        "install",
        GUEST_NEW,
    )
    write(
        "apt-reinstall.txt",
        execute(
            "/usr/bin/apt-get",
            ["-y", "--reinstall", "--no-install-recommends", "install", GUEST_NEW],
        ),
    )
    validate_installed("0.1.0", "reinstalled.json")
    assert protected_entries() == baseline_entries

    finish_gate(baseline_entries)


def finish_gate(baseline_entries: dict[str, object] | None = None) -> None:
    assert SNAPSHOT in virsh("snapshot-list", VM, "--name").splitlines()
    baseline = json.loads((OUT / "baseline.json").read_text())
    if baseline_entries is None:
        baseline_entries = baseline["entries"]
        validate_installed("0.1.0", "resume-after-reinstall.json")
        assert protected_entries() == baseline_entries

    apt_simulation(
        "apt-remove-simulation.txt",
        "remove",
        PACKAGE,
        allowed_removals=frozenset({PACKAGE}),
    )
    write("apt-remove.txt", execute("/usr/bin/apt-get", ["-y", "remove", PACKAGE]))
    assert_removed()
    assert protected_entries() == baseline_entries

    apt_simulation("apt-new-fresh-simulation.txt", "--no-install-recommends", "install", GUEST_NEW)
    write(
        "apt-new-fresh-install.txt",
        execute(
            "/usr/bin/apt-get",
            ["-y", "--no-install-recommends", "install", GUEST_NEW],
        ),
    )
    validate_installed("0.1.0", "fresh-installed.json")
    assert protected_entries() == baseline_entries

    apt_simulation(
        "apt-purge-simulation.txt",
        "purge",
        PACKAGE,
        allowed_removals=frozenset({PACKAGE}),
    )
    write("apt-purge.txt", execute("/usr/bin/apt-get", ["-y", "purge", PACKAGE]))
    assert_removed()
    assert protected_entries() == baseline_entries
    execute("/usr/bin/apt-get", ["check"])
    assert execute("/usr/bin/dpkg", ["--audit"]) == ""
    execute("/usr/bin/rm", [GUEST_OLD, GUEST_NEW])
    execute("/usr/bin/rmdir", [GUEST_ROOT])
    cleaned = inventory()
    (OUT / "cleaned-before-revert.json").write_text(json.dumps(cleaned, indent=2) + "\n")
    assert cleaned == baseline
    print("Upgrade/reinstall/remove/fresh install/purge and exact cleanup passed.", flush=True)


def restore() -> None:
    assert SNAPSHOT in virsh("snapshot-list", VM, "--name").splitlines()
    print(virsh("snapshot-revert", VM, SNAPSHOT, "--running"), flush=True)
    restored = inventory()
    (OUT / "restored.json").write_text(json.dumps(restored, indent=2) + "\n")
    assert restored == json.loads((OUT / "baseline.json").read_text())
    print(virsh("snapshot-delete", VM, SNAPSHOT), flush=True)
    print("Snapshot restored; baseline exact match; VM running.", flush=True)


if __name__ == "__main__":
    {
        "prepare": prepare,
        "gate": gate,
        "finish-gate": finish_gate,
        "restore": restore,
    }[sys.argv[1]]()
