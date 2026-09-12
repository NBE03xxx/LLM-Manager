"""Run the reviewed Ubuntu lifecycle gates with the ff7913b artifact pair.

Historical scripts supply the unchanged lifecycle assertions; all mutable paths
and artifact identities are replaced before invoking them. No menu gate is claimed.
"""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

REPO = Path('/home/yoshimi/WorkSpace/LLM-Manager')
BASE = REPO / 'docs/validation'
ARTIFACTS = Path('/tmp/llm-manager-candidate-ff7913b-20260913')
COMMIT = 'ff7913bb97e896f7992720b9a43c2382970a5fc8'

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, BASE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def seal(out):
    (out / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
        for p in sorted(out.iterdir()) if p.is_file() and p.name != 'SHA256SUMS'
    ))

def remote():
    gate = load('remote_lifecycle', 'remote-helper-b15a984-2026-09-12/lifecycle.py')
    gate.OUT = BASE / 'remote-helper-ff7913b-2026-09-13'
    gate.SNAPSHOT = 'phase6-remote-helper-ff7913b-20260913'
    gate.NEW_SOURCE_COMMIT = COMMIT
    # Rebuilt historical source for this run; identity differs from prior build.
    gate.OLD_SHA256 = '3fe79afe4e1d72ca8e9dfea94cd514154a2fdb099d79671174a7601e44adf52f'
    gate.NEW_ARTIFACT = ARTIFACTS / 'llm-manager-remote-helper_0.1.0_all.deb'
    gate.NEW_SHA256 = '830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d'
    gate.GUEST_ROOT = '/tmp/phase6-remote-helper-ff7913b-20260913'
    gate.GUEST_OLD = gate.GUEST_ROOT + '/old.deb'
    gate.GUEST_NEW = gate.GUEST_ROOT + '/new.deb'
    gate.OUT.mkdir(exist_ok=False)
    (gate.OUT / 'lifecycle.py').write_bytes(Path(__file__).read_bytes())
    original_write = gate.write
    def write(name, content):
        if name.startswith('apt-') and 'simulation' not in name:
            (gate.OUT / (name + '.gz')).write_bytes(gzip.compress(content.encode(), mtime=0))
        else:
            original_write(name, content)
    gate.write = write
    try:
        gate.prepare()
        gate.gate()
    finally:
        if gate.SNAPSHOT in gate.virsh('snapshot-list', gate.VM, '--name').splitlines():
            gate.restore()
    seal(gate.OUT)

def local():
    gate = load('local_lifecycle', 'ubuntu-display-b15a984-2026-09-12/lifecycle.py')
    gate.OUT = BASE / 'ubuntu-lifecycle-ff7913b-2026-09-13'
    gate.SNAP = 'phase6-ubuntu-lifecycle-ff7913b-20260913'
    gate.DEB = ARTIFACTS / 'llm-manager_0.1.0_all.deb'
    gate.HASH = '351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243'
    gate.GUEST = '/tmp/phase6-ubuntu-lifecycle-ff7913b.deb'
    assert not gate.OUT.exists()
    try:
        gate.main('prepare')
        (gate.OUT / 'lifecycle.py').write_bytes(Path(__file__).read_bytes())
        gate.save('artifact-identity.json', {'source_commit': COMMIT, 'sha256': gate.HASH})
        # UID 1000 installed Qt startup and clean exit, with no user settings.
        result = gate.vm.execute('/usr/sbin/runuser', [
            '-u', 'yoshimi', '--', '/usr/bin/env', 'QT_QPA_PLATFORM=offscreen',
            'PYTHONDONTWRITEBYTECODE=1', '/usr/bin/python3', '-I', '-c',
            'from PySide6.QtWidgets import QApplication; '
            'from llm_manager.ui.qt_window import MainWindow; '
            'app=QApplication([]); w=MainWindow(lambda _: lambda token: None); '
            'w.show(); app.processEvents(); assert w.isVisible(); '
            'w.close(); app.processEvents(); assert not w.isVisible(); print("PASS")'
        ])
        assert result.strip() == 'PASS', result
        gate.save('installed-qt-smoke.json', {'result': 'pass', 'platform': 'offscreen', 'uid': 1000})
        gate.main('finish')
        gate.main('audit')
    finally:
        if gate.SNAP in gate.vm.virsh('snapshot-list', gate.vm.VM, '--name').splitlines():
            gate.main('restore')
    seal(gate.OUT)

if __name__ == '__main__':
    {'remote': remote, 'local': local}[sys.argv[1]]()
