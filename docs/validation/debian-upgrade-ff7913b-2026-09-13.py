"""Validate Debian upgrade from a historical dev package to the ff7913b candidate."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


REPO = Path('/home/yoshimi/WorkSpace/LLM-Manager')
OUT = REPO / 'docs/validation/debian-upgrade-ff7913b-2026-09-13'
OLD = Path(
    '/tmp/llm-manager-debian-upgrade-8854232-5mkwqv17/'
    'llm-manager_0.1.0~dev0_all.deb'
)
OLD_HASH = 'e302d19d6d68c32cc1de777ad766361c1afcf68b7430f7418f1f3095c546737d'
NEW = Path('/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb')
NEW_HASH = '351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243'
GUEST_ROOT = '/tmp/phase6-debian-upgrade-ff7913b-20260913'
GUEST_OLD = GUEST_ROOT + '/old.deb'
GUEST_NEW = GUEST_ROOT + '/new.deb'
PACKAGE = 'llm-manager'

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
    suffix = '.txt.gz' if '-s' not in arguments else '.txt'
    path = OUT / (name + suffix)
    if suffix.endswith('.gz'):
        path.write_bytes(gzip.compress(raw.encode(), mtime=0))
    else:
        path.write_text(raw)
    return raw


def selected(raw, prefixes):
    return sorted({
        line.split()[1]
        for line in raw.splitlines()
        if any(line.startswith(prefix + ' ') for prefix in prefixes)
    })


def package_names(inventory):
    return {row.split('\t')[0].split(':')[0] for row in inventory['packages']}


def installed_delta(baseline, current):
    before = set(baseline['packages'])
    return sorted(
        row.split('\t')[0].split(':')[0]
        for row in set(current['packages']) - before
        if row.split('\t')[-1] == 'installed'
    )


def version():
    return gate.vm.python(r'''
import subprocess
p=subprocess.run(['dpkg-query','-W','-f=${db:Status-Status}\t${Version}','llm-manager'],
                 capture_output=True,text=True)
print(p.stdout if p.returncode == 0 else '')
''').strip()


def cleanup(baseline, added):
    current = gate.inventory()
    assert set(baseline['packages']).issubset(current['packages'])
    current_added = installed_delta(baseline, current)
    assert set(current_added).issubset(added), (current_added, added)
    if current_added:
        simulation = apt('apt-purge-simulation', ['-s', 'purge', *current_added])
        assert selected(simulation, ('Remv', 'Purg')) == current_added
        assert not selected(simulation, ('Inst',))
        apt('apt-purge', ['-y', 'purge', *current_added])
    gate.vm.python(r'''
import shutil
from pathlib import Path
root=Path('/tmp/phase6-debian-upgrade-ff7913b-20260913')
if root.exists():
    assert root.is_dir() and not root.is_symlink()
    shutil.rmtree(root)
''')
    cleaned = gate.inventory()
    save('cleaned.json', cleaned)
    assert cleaned == baseline
    assert gate.vm.execute('/usr/bin/dpkg', ['--audit']) == ''
    apt('apt-check', ['check'])
    save('cleanup-result.json', {
        'purged_packages': current_added,
        'baseline_exact_match': True,
        'dpkg_audit_empty': True,
        'apt_check': True,
        'temporary_files_removed': True,
        'vm_state': gate.vm.virsh('domstate', gate.vm.VM).strip(),
    })


def main():
    assert gate.vm.virsh('domstate', gate.vm.VM).strip() == 'running'
    for artifact, digest in ((OLD, OLD_HASH), (NEW, NEW_HASH)):
        assert artifact.is_file() and hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
    assert not OUT.exists()
    OUT.mkdir()
    baseline = gate.inventory()
    assert PACKAGE not in package_names(baseline)
    save('baseline.json', baseline)
    save('artifact-identity.json', {
        'upgrade_predecessor': {
            'source_commit': '88542323d250e8e9e18bc11e3ed0e093ade3f396',
            'sha256': OLD_HASH,
            'version': '0.1.0~dev0',
            'historical_verifier': 'pass',
        },
        'candidate': {
            'source_commit': 'ff7913bb97e896f7992720b9a43c2382970a5fc8',
            'sha256': NEW_HASH,
            'version': '0.1.0',
        },
    })
    (OUT / 'session-before.txt').write_text(
        gate.vm.execute('/usr/bin/loginctl', [
            'show-session', '2', '-p', 'Name', '-p', 'Type', '-p', 'Active',
            '-p', 'State', '-p', 'LockedHint',
        ])
    )
    gate.vm.python(
        "from pathlib import Path; p=Path(" + repr(GUEST_ROOT)
        + "); assert not p.exists() and not p.is_symlink(); p.mkdir(mode=0o700)"
    )
    gate.vm.transfer(str(OLD), GUEST_OLD)
    gate.vm.transfer(str(NEW), GUEST_NEW)
    gate.vm.execute('/bin/chmod', ['0644', GUEST_OLD, GUEST_NEW])
    for target, digest in ((GUEST_OLD, OLD_HASH), (GUEST_NEW, NEW_HASH)):
        observed = gate.vm.python(
            f"import hashlib; print(hashlib.sha256(open({target!r},'rb').read()).hexdigest())"
        ).strip()
        assert observed == digest

    old_simulation = apt(
        'apt-old-install-simulation',
        ['-s', '--no-install-recommends', 'install', GUEST_OLD],
    )
    added = selected(old_simulation, ('Inst',))
    assert PACKAGE in added and not selected(old_simulation, ('Remv', 'Purg'))
    assert not (set(added) & package_names(baseline)), added
    save('added.json', added)

    try:
        apt('apt-old-install', ['-y', '--no-install-recommends', 'install', GUEST_OLD])
        old_installed = gate.inventory()
        save('old-installed-inventory.json', old_installed)
        assert installed_delta(baseline, old_installed) == added
        assert old_installed['entries'] == baseline['entries']
        assert version() == 'installed\t0.1.0~dev0'
        assert gate.vm.execute('/usr/bin/dpkg', ['-V', PACKAGE]) == ''

        upgrade_simulation = apt(
            'apt-upgrade-simulation',
            ['-s', '--no-install-recommends', 'install', GUEST_NEW],
        )
        assert selected(upgrade_simulation, ('Inst',)) == [PACKAGE]
        assert not selected(upgrade_simulation, ('Remv', 'Purg'))
        assert '0.1.0~dev0' in upgrade_simulation and '0.1.0' in upgrade_simulation
        apt('apt-upgrade', ['-y', '--no-install-recommends', 'install', GUEST_NEW])
        upgraded = gate.inventory()
        save('upgraded-inventory.json', upgraded)
        assert installed_delta(baseline, upgraded) == added
        assert upgraded['entries'] == baseline['entries']
        assert upgraded['manual'] == old_installed['manual']
        old_other = [row for row in old_installed['packages'] if not row.startswith(PACKAGE + '\t')]
        new_other = [row for row in upgraded['packages'] if not row.startswith(PACKAGE + '\t')]
        assert new_other == old_other
        assert version() == 'installed\t0.1.0'
        assert gate.vm.execute('/usr/bin/dpkg', ['-V', PACKAGE]) == ''

        smoke = gate.vm.execute('/usr/sbin/runuser', [
            '-u', 'user', '--', '/usr/bin/env', 'QT_QPA_PLATFORM=offscreen',
            'PYTHONDONTWRITEBYTECODE=1', '/usr/bin/python3', '-I', '-c',
            'import json,os,llm_manager; from PySide6.QtWidgets import QApplication; '
            'from llm_manager.ui.qt_window import MainWindow; app=QApplication([]); '
            'w=MainWindow(lambda _: lambda token: None); w.show(); app.processEvents(); '
            'assert w.isVisible(); w.close(); app.processEvents(); assert not w.isVisible(); '
            'print(json.dumps({"uid":os.getuid(),"module":llm_manager.__file__,"qt":"pass"}))',
        ])
        smoke_result = json.loads(smoke)
        assert smoke_result['uid'] == 1000 and smoke_result['qt'] == 'pass'
        save('upgraded-smoke.json', smoke_result)
    finally:
        cleanup(baseline, added)

    (OUT / 'session-after.txt').write_text(
        gate.vm.execute('/usr/bin/loginctl', [
            'show-session', '2', '-p', 'Name', '-p', 'Type', '-p', 'Active',
            '-p', 'State', '-p', 'LockedHint',
        ])
    )
    assert (OUT / 'session-after.txt').read_text() == (OUT / 'session-before.txt').read_text()
    (OUT / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
        for path in sorted(OUT.iterdir())
        if path.is_file() and path.name != 'SHA256SUMS'
    ))


if __name__ == '__main__':
    main()
