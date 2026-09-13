"""Capture Orca speech for the ff7913b candidate on Debian Wayland."""
import array
import base64
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import wave


REPO = Path('/home/yoshimi/WorkSpace/LLM-Manager')
OUT = REPO / 'docs/validation/debian-orca-ff7913b-2026-09-13'
GUEST_ROOT = '/tmp/phase6-debian-orca-ff7913b-20260913'
GUEST_WAV = GUEST_ROOT + '/orca-llm-manager.wav'
GUEST_DEBUG = GUEST_ROOT + '/orca-debug.out'

spec = importlib.util.spec_from_file_location(
    'menu_gate', REPO / 'docs/validation/debian-menu-ff7913b-2026-09-13.py'
)
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)
menu.OUT = OUT
menu.TARGET = '/tmp/phase6-debian-orca-ff7913b-20260913.deb'
vm = menu.gate.vm


ENVIRONMENT = [
    'XDG_RUNTIME_DIR=/run/user/1000',
    'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus',
    'DISPLAY=:0',
    'WAYLAND_DISPLAY=wayland-0',
    'XDG_SESSION_TYPE=wayland',
    'LANG=C.utf8',
    'LC_ALL=C.utf8',
]


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def start(path, arguments):
    result = vm.qga('guest-exec', {
        'path': path,
        'arg': arguments,
        'capture-output': True,
    })
    return result['pid']


def status(pid):
    result = vm.qga('guest-exec-status', {'pid': pid})
    if not result.get('exited'):
        return None
    return {
        'exit_code': result.get('exitcode'),
        'signal': result.get('signal'),
        'stdout': base64.b64decode(result.get('out-data', '')).decode(),
        'stderr': base64.b64decode(result.get('err-data', '')).decode(),
        'out_truncated': bool(result.get('out-truncated')),
        'err_truncated': bool(result.get('err-truncated')),
    }


def wait_status(pid, attempts=80):
    for _ in range(attempts):
        result = status(pid)
        if result is not None:
            return result
        time.sleep(0.25)
    raise RuntimeError(f'guest PID {pid} did not finish')


def receive(source, target, expected_size, expected_hash):
    handle = vm.qga('guest-file-open', {'path': source, 'mode': 'r'})
    data = bytearray()
    try:
        while True:
            block = vm.qga('guest-file-read', {'handle': handle, 'count': 65536})
            data.extend(base64.b64decode(block.get('buf-b64', '')))
            if block.get('eof'):
                break
    finally:
        vm.qga('guest-file-close', {'handle': handle})
    assert len(data) == expected_size
    assert hashlib.sha256(data).hexdigest() == expected_hash
    target.write_bytes(data)


def accessibility():
    return vm.execute('/usr/sbin/runuser', [
        '-u', 'user', '--', '/usr/bin/env', *ENVIRONMENT,
        '/usr/bin/gsettings', 'get', 'org.gnome.desktop.interface',
        'toolkit-accessibility',
    ]).strip()


def set_accessibility(value):
    vm.execute('/usr/sbin/runuser', [
        '-u', 'user', '--', '/usr/bin/env', *ENVIRONMENT,
        '/usr/bin/gsettings', 'set', 'org.gnome.desktop.interface',
        'toolkit-accessibility', value,
    ])


def prepare():
    assert accessibility() == 'false'
    menu.prepare()
    save('orca-environment.json', {
        'user': 'user',
        'uid': 1000,
        'display': ':0',
        'wayland_display': 'wayland-0',
        'pipewire_sink': 'alsa_output.pci-0000_00_1b.0.analog-stereo',
        'toolkit_accessibility_before': 'false',
        'temporary_orca_preferences': True,
    })


def audio_metrics(path):
    with wave.open(str(path), 'rb') as source:
        frames = source.getnframes()
        rate = source.getframerate()
        channels = source.getnchannels()
        width = source.getsampwidth()
        data = source.readframes(frames)
    assert width == 2 and frames > 0
    samples = array.array('h')
    samples.frombytes(data)
    if sys.byteorder == 'big':
        samples.byteswap()
    peak = max(abs(value) for value in samples)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    return {
        'frames': frames,
        'rate_hz': rate,
        'channels': channels,
        'sample_width_bytes': width,
        'duration_seconds': frames / rate,
        'peak_absolute': peak,
        'rms': rms,
        'non_silent': peak > 100 and rms > 10,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'bytes': path.stat().st_size,
    }


def capture():
    assert accessibility() == 'false'
    vm.python("""
import os
from pathlib import Path
root=Path('/tmp/phase6-debian-orca-ff7913b-20260913')
assert not root.exists() and not root.is_symlink()
root.mkdir(mode=0o700)
os.chown(root,1000,1000)
for name in ('prefs','config'):
    path=root/name
    path.mkdir(mode=0o700)
    os.chown(path,1000,1000)
""")
    common = ['-u', 'user', '--', '/usr/bin/env', *ENVIRONMENT]
    recorder_pid = start('/usr/sbin/runuser', [
        *common, '/usr/bin/pw-record',
        '--target', 'alsa_output.pci-0000_00_1b.0.analog-stereo',
        '--properties', 'stream.capture.sink=true', GUEST_WAV,
    ])
    orca_pid = None
    app_pid = None
    app_result = None
    orca_result = None
    recorder_result = None
    try:
        time.sleep(1)
        assert status(recorder_pid) is None
        orca_pid = start('/usr/sbin/runuser', [
            *common, '/usr/bin/orca', '-r',
            '-u', GUEST_ROOT + '/prefs', '--debug-file', GUEST_DEBUG,
        ])
        time.sleep(3)
        assert status(orca_pid) is None
        app_pid = start('/usr/sbin/runuser', [
            *common,
            'QT_QPA_PLATFORM=wayland',
            'QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1',
            'PYTHONDONTWRITEBYTECODE=1',
            'XDG_CONFIG_HOME=' + GUEST_ROOT + '/config',
            '/usr/bin/llm-manager',
        ])
        time.sleep(5)
        assert status(app_pid) is None
        vm.virsh('screenshot', vm.VM, str(OUT / 'orca-window.png'))
        for keys in (('KEY_TAB',), ('KEY_TAB',), ('KEY_LEFTSHIFT', 'KEY_TAB')):
            vm.virsh('send-key', vm.VM, *keys)
            time.sleep(1)
        time.sleep(5)
        vm.virsh('send-key', vm.VM, 'KEY_LEFTALT', 'KEY_F4')
        app_result = wait_status(app_pid)
        assert app_result['exit_code'] == 0, app_result
        assert not app_result['out_truncated'] and not app_result['err_truncated']
    finally:
        if app_pid is not None and app_result is None:
            vm.execute('/bin/kill', ['-TERM', str(app_pid)])
            app_result = wait_status(app_pid)
        if orca_pid is not None:
            vm.execute('/bin/kill', ['-TERM', str(orca_pid)])
            orca_result = wait_status(orca_pid)
        time.sleep(1)
        vm.execute('/bin/kill', ['-TERM', str(recorder_pid)])
        recorder_result = wait_status(recorder_pid)
        set_accessibility('false')
    assert accessibility() == 'false'
    save('process-results.json', {
        'app': app_result,
        'orca': orca_result,
        'recorder': recorder_result,
        'toolkit_accessibility_restored': True,
    })

    metadata = json.loads(vm.python(r'''
import hashlib,json
from pathlib import Path
root=Path('/tmp/phase6-debian-orca-ff7913b-20260913')
result={}
for name in ('orca-llm-manager.wav','orca-debug.out'):
    path=root/name
    assert path.is_file() and not path.is_symlink()
    result[name]={'bytes':path.stat().st_size,
                  'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
debug=(root/'orca-debug.out').read_text(errors='replace')
result['speech_output']=[line for line in debug.splitlines() if 'SPEECH OUTPUT:' in line]
print(json.dumps(result))
'''))
    receive(
        GUEST_WAV, OUT / 'orca-llm-manager.wav',
        metadata['orca-llm-manager.wav']['bytes'],
        metadata['orca-llm-manager.wav']['sha256'],
    )
    receive(
        GUEST_DEBUG, OUT / 'orca-debug.out',
        metadata['orca-debug.out']['bytes'],
        metadata['orca-debug.out']['sha256'],
    )
    debug_path = OUT / 'orca-debug.out'
    debug_path.write_text(
        '\n'.join(line.rstrip() for line in debug_path.read_text(errors='replace').splitlines())
        + '\n'
    )
    save('speech-output.json', metadata['speech_output'])
    joined = '\n'.join(metadata['speech_output'])
    assert 'Screen reader on.' in joined
    assert 'LLM Manager' in joined
    assert any(label in joined for label in ('Hosts', 'Language', 'Optimization profile'))
    metrics = audio_metrics(OUT / 'orca-llm-manager.wav')
    save('audio-metrics.json', metrics)
    assert metrics['non_silent'], metrics
    print(json.dumps({
        'speech_output_count': len(metadata['speech_output']),
        'audio': metrics,
    }), flush=True)


def finish():
    assert accessibility() == 'false'
    vm.python("""
import shutil
from pathlib import Path
root=Path('/tmp/phase6-debian-orca-ff7913b-20260913')
if root.exists():
    assert root.is_dir() and not root.is_symlink()
    shutil.rmtree(root)
""")
    menu.finish()


if __name__ == '__main__':
    {'prepare': prepare, 'capture': capture, 'finish': finish}[sys.argv[1]]()
