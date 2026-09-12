"""Prepare, inspect, and clean up the Debian ff7913b desktop-menu gate."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO = Path('/home/yoshimi/WorkSpace/LLM-Manager')
OUT = REPO / 'docs/validation/debian-menu-ff7913b-2026-09-13'
DEB = Path('/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb')
DIGEST = '351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243'
TARGET = '/tmp/phase6-debian-menu-ff7913b-20260913.deb'

spec = importlib.util.spec_from_file_location(
    'debian_lifecycle',
    REPO / 'docs/validation/debian-display-b15a984-2026-09-12/lifecycle.py',
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


def apt(name, arguments):
    raw = gate.vm.execute('/usr/bin/apt-get', arguments)
    if '-s' in arguments:
        (OUT / (name + '.txt')).write_text(raw)
    else:
        (OUT / (name + '.txt.gz')).write_bytes(gzip.compress(raw.encode(), mtime=0))
    return raw


def selected(raw, prefixes):
    return sorted({
        line.split()[1]
        for line in raw.splitlines()
        if any(line.startswith(prefix + ' ') for prefix in prefixes)
    })


def names(inventory):
    return {row.split('\t')[0].split(':')[0] for row in inventory['packages']}


def delta(baseline, current):
    return sorted(
        row.split('\t')[0].split(':')[0]
        for row in set(current['packages']) - set(baseline['packages'])
        if row.split('\t')[-1] == 'installed'
    )


def session():
    return gate.vm.execute('/usr/bin/loginctl', [
        'show-session', '2', '-p', 'Name', '-p', 'Type', '-p', 'Active',
        '-p', 'State', '-p', 'LockedHint',
    ])


def absent():
    result = gate.vm.python(r'''
import subprocess
p=subprocess.run(['pgrep','-f','^/usr/bin/python3 -I /usr/bin/llm-manager$'],
                 capture_output=True,text=True)
print(p.returncode)
''').strip()
    assert result == '1', result


def prepare():
    assert gate.vm.virsh('domstate', gate.vm.VM).strip() == 'running'
    assert DEB.is_file() and hashlib.sha256(DEB.read_bytes()).hexdigest() == DIGEST
    assert not OUT.exists()
    absent()
    OUT.mkdir()
    baseline = gate.inventory()
    assert 'llm-manager' not in names(baseline)
    save('baseline.json', baseline)
    save('artifact-identity.json', {
        'source_commit': 'ff7913bb97e896f7992720b9a43c2382970a5fc8',
        'sha256': DIGEST,
        'package': 'llm-manager',
        'version': '0.1.0',
    })
    (OUT / 'session-before.txt').write_text(session())
    gate.vm.python(
        'from pathlib import Path; p=Path(' + repr(TARGET)
        + '); assert not p.exists() and not p.is_symlink()'
    )
    gate.vm.transfer(str(DEB), TARGET)
    gate.vm.execute('/bin/chmod', ['0644', TARGET])
    observed = gate.vm.python(
        f"import hashlib; print(hashlib.sha256(open({TARGET!r},'rb').read()).hexdigest())"
    ).strip()
    assert observed == DIGEST
    simulation = apt(
        'apt-install-simulation',
        ['-s', '--no-install-recommends', 'install', TARGET],
    )
    added = selected(simulation, ('Inst',))
    assert 'llm-manager' in added and not selected(simulation, ('Remv', 'Purg'))
    assert not (set(added) & names(baseline))
    save('added.json', added)
    apt('apt-install', ['-y', '--no-install-recommends', 'install', TARGET])
    installed = gate.inventory()
    save('installed.json', installed)
    assert delta(baseline, installed) == added
    assert installed['entries'] == baseline['entries']
    assert gate.vm.execute('/usr/bin/dpkg', ['-V', 'llm-manager']) == ''
    print('Candidate installed; ready for desktop menu input.', flush=True)


def process():
    value = gate.vm.python(r'''
import json
from pathlib import Path
import subprocess
pids=subprocess.check_output(
    ['pgrep','-f','^/usr/bin/python3 -I /usr/bin/llm-manager$'],text=True).split()
assert len(pids)==1,pids
root=Path('/proc')/pids[0]
argv=(root/'cmdline').read_bytes().split(b'\0')[:-1]
uid=next(row for row in (root/'status').read_text().splitlines() if row.startswith('Uid:'))
assert argv==[b'/usr/bin/python3',b'-I',b'/usr/bin/llm-manager'],argv
assert uid.split()[1:]==['1000']*4,uid
print(json.dumps({'pid':int(pids[0]),'argv':[x.decode() for x in argv],'uid':uid}))
''')
    save('process.json', json.loads(value))
    print(value, flush=True)


def finish():
    absent()
    save('normal-exit.json', {'pgrep_exit_code': 1})
    baseline = json.loads((OUT / 'baseline.json').read_text())
    added = json.loads((OUT / 'added.json').read_text())
    current = gate.inventory()
    assert delta(baseline, current) == added
    simulation = apt('apt-purge-simulation', ['-s', 'purge', *added])
    assert selected(simulation, ('Remv', 'Purg')) == added
    assert not selected(simulation, ('Inst',))
    apt('apt-purge', ['-y', 'purge', *added])
    gate.vm.python(
        'from pathlib import Path; p=Path(' + repr(TARGET)
        + '); assert p.is_file() and not p.is_symlink(); p.unlink()'
    )
    cleaned = gate.inventory()
    save('cleaned.json', cleaned)
    assert cleaned == baseline
    assert gate.vm.execute('/usr/bin/dpkg', ['--audit']) == ''
    apt('apt-check', ['check'])
    (OUT / 'session-after.txt').write_text(session())
    assert (OUT / 'session-after.txt').read_text() == (OUT / 'session-before.txt').read_text()
    save('cleanup-result.json', {
        'purged_packages': added,
        'baseline_exact_match': True,
        'dpkg_audit_empty': True,
        'apt_check': True,
        'transferred_deb_removed': True,
        'vm_state': gate.vm.virsh('domstate', gate.vm.VM).strip(),
    })
    (OUT / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
        for path in sorted(OUT.iterdir())
        if path.is_file() and path.name != 'SHA256SUMS'
    ))
    print('Normal exit and exact baseline cleanup passed.', flush=True)


if __name__ == '__main__':
    {'prepare': prepare, 'process': process, 'finish': finish}[sys.argv[1]]()
