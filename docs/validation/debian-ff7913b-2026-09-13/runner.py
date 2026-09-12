"""Debian ff7913b lifecycle and English/Japanese AT-SPI gate."""
import importlib.util
import json
from pathlib import Path
import sys

BASE = Path('/home/yoshimi/WorkSpace/LLM-Manager/docs/validation')

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, BASE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

gate = load('debian_lifecycle', 'debian-display-b15a984-2026-09-12/lifecycle.py')
gate.OUT = BASE / 'debian-ff7913b-2026-09-13'
gate.SOURCE = Path('/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb')
gate.TARGET = '/tmp/llm-manager-ff7913b-20260913.deb'
gate.DIGEST = '351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243'

def prepare():
    # Read-only prerequisites before installing any packages.
    print(gate.vm.execute('/usr/bin/loginctl', ['list-sessions', '--no-legend']))
    print(gate.vm.execute('/usr/bin/locale', ['-a']))
    print(gate.vm.python("from pathlib import Path; assert Path('/run/user/1000/wayland-0').is_socket(); import gi; gi.require_version('Atspi','2.0'); from gi.repository import Atspi; print('Wayland and AT-SPI available')"))
    gate.OUT.mkdir(exist_ok=False)
    (gate.OUT / 'runner.py').write_bytes(Path(__file__).read_bytes())
    gate.save('artifact-identity.json', {'source_commit': 'ff7913bb97e896f7992720b9a43c2382970a5fc8', 'sha256': gate.DIGEST})
    gate.main('prepare')

def display():
    a = load('debian_accessibility', 'accessibility-fix-2026-09-12/gate.py')
    a.vm.VM = 'debian13'
    a.USER = 'user'
    a.OUT = gate.OUT
    for locale, labels, values, button in (
        ('C.utf8', ['Hosts', 'Language', 'Optimization profile'], ['Local', 'English', 'Balanced'], 'Diagnose'),
        ('ja_JP.utf8', ['ホスト', '言語', '最適化プロファイル'], ['Local', '日本語', 'バランス'], '診断する'),
    ):
        a.inspect(locale, {
            'all_names': labels + values + [button],
            'controls': [
                {'name': value, 'role': 'combo box', 'description': label}
                for label, value in zip(labels, values)
            ] + [{'name': button, 'role': 'button', 'description': ''}],
            'label_for': list(zip(labels, values)),
        })
    gate.absent()
    print('Debian stock Qt English/Japanese Wayland AT-SPI and normal exit passed.')

if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'prepare':
        prepare()
    elif action == 'display':
        display()
    else:
        gate.main(action)
