"""Collect the Debian local candidate SBOM and explicitly restore its baseline."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


REPO = Path('/home/yoshimi/WorkSpace/LLM-Manager')
OUT = REPO / 'docs/validation/sbom-ff7913b-debian-local-2026-09-13'
DEB = Path('/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb')
DIGEST = '351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243'
PACKAGE = 'llm-manager'
VERSION = '0.1.0'
GUEST_DEB = '/tmp/phase6-ff7913b-debian-sbom.deb'
GUEST_COLLECTOR = '/tmp/phase6-ff7913b-debian-collector.py'
GUEST_ROOT = '/tmp/llm-manager-phase6-sbom-gate'
GUEST_ARCHIVE = '/tmp/phase6-ff7913b-debian-sbom.tar.xz'

spec = importlib.util.spec_from_file_location(
    'debian_lifecycle',
    REPO / 'docs/validation/debian-display-b15a984-2026-09-12/lifecycle.py',
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


CAPTURE = r'''
import hashlib,json,os,subprocess,tarfile
from pathlib import Path
root=Path('/tmp/llm-manager-phase6-sbom-gate')
root.mkdir(mode=0o755)
(root/'environment').mkdir()
os.chown(root/'environment',1000,1000)
args=['/usr/sbin/runuser','-u','user','--','/usr/bin/python3','-I',
      '/tmp/phase6-ff7913b-debian-collector.py','--output',str(root/'environment/data')]
result=subprocess.run(args,capture_output=True,text=True)
assert result.returncode in (0,2),result.stderr
(root/'collector.exit').write_text(str(result.returncode)+'\n')
(root/'collector.log').write_text(result.stdout+result.stderr)
artifact=Path('/tmp/phase6-ff7913b-debian-sbom.deb')
digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
(root/'artifact.sha256').write_text(digest+'  llm-manager_0.1.0_all.deb\n')
version=subprocess.check_output(['dpkg-query','-W','-f=${Version}','llm-manager'],text=True)
(root/'summary.json').write_text(json.dumps({
    'artifact_sha256':digest,
    'installed_package':'llm-manager',
    'installed_version':version,
    'collector_exit':result.returncode,
    'source_commit':'ff7913bb97e896f7992720b9a43c2382970a5fc8',
})+'\n')
(root/'packages-installed.tsv').write_bytes(subprocess.check_output([
    'dpkg-query','-W',
    '-f=${binary:Package}\t${Version}\t${Architecture}\t${db:Status-Status}\n']))
audit=subprocess.check_output(['dpkg','--audit'])
assert not audit.strip()
(root/'dpkg-audit.log').write_bytes(audit)
files=sorted(p for p in root.rglob('*') if p.is_file())
(root/'EVIDENCE-SHA256SUMS').write_text(''.join(
    hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n'
    for p in files))
archive=Path('/tmp/phase6-ff7913b-debian-sbom.tar.xz')
with tarfile.open(archive,'x:xz') as tar:
    tar.add(root,arcname=root.name)
print(json.dumps({
    'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'bytes':archive.stat().st_size,
}))
'''


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


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


def receive(target, expected):
    handle = gate.vm.qga('guest-file-open', {'path': target, 'mode': 'r'})
    data = bytearray()
    try:
        while True:
            block = gate.vm.qga('guest-file-read', {'handle': handle, 'count': 65536})
            data.extend(base64.b64decode(block.get('buf-b64', '')))
            if block.get('eof'):
                break
    finally:
        gate.vm.qga('guest-file-close', {'handle': handle})
    assert len(data) == expected['bytes']
    assert hashlib.sha256(data).hexdigest() == expected['sha256']
    return bytes(data)


def remove_guest_temporary_files():
    gate.vm.python(r'''
import shutil
from pathlib import Path
files=[
    Path('/tmp/phase6-ff7913b-debian-sbom.deb'),
    Path('/tmp/phase6-ff7913b-debian-collector.py'),
    Path('/tmp/phase6-ff7913b-debian-sbom.tar.xz'),
]
root=Path('/tmp/llm-manager-phase6-sbom-gate')
for path in files:
    if path.exists() or path.is_symlink():
        assert path.is_file() and not path.is_symlink()
        path.unlink()
if root.exists():
    assert root.is_dir() and not root.is_symlink()
    shutil.rmtree(root)
''')


def cleanup(baseline, added):
    current = gate.inventory()
    assert set(baseline['packages']).issubset(current['packages'])
    current_added = installed_delta(baseline, current)
    assert set(current_added).issubset(added), (current_added, added)
    if current_added:
        simulation = gate.vm.execute('/usr/bin/apt-get', ['-s', 'purge', *current_added])
        (OUT / 'apt-purge-simulation.txt').write_text(simulation)
        assert selected(simulation, ('Remv', 'Purg')) == current_added
        assert not selected(simulation, ('Inst',))
        purge_log = gate.vm.execute('/usr/bin/apt-get', ['-y', 'purge', *current_added])
        (OUT / 'apt-purge.txt.gz').write_bytes(gzip.compress(purge_log.encode(), mtime=0))
    remove_guest_temporary_files()
    cleaned = gate.inventory()
    save_json('cleaned.json', cleaned)
    assert cleaned == baseline
    assert gate.vm.execute('/usr/bin/dpkg', ['--audit']) == ''
    check = gate.vm.execute('/usr/bin/apt-get', ['check'])
    (OUT / 'apt-check.txt.gz').write_bytes(gzip.compress(check.encode(), mtime=0))
    save_json('cleanup-result.json', {
        'purged_packages': current_added,
        'baseline_exact_match': True,
        'dpkg_audit_empty': True,
        'apt_check': True,
        'temporary_files_removed': True,
        'vm_state': gate.vm.virsh('domstate', gate.vm.VM).strip(),
    })


def main():
    assert gate.vm.virsh('domstate', gate.vm.VM).strip() == 'running'
    assert DEB.is_file() and hashlib.sha256(DEB.read_bytes()).hexdigest() == DIGEST
    assert not OUT.exists()
    OUT.mkdir()
    baseline = gate.inventory()
    assert PACKAGE not in package_names(baseline)
    save_json('baseline.json', baseline)
    save_json('artifact-identity.json', {
        'source_commit': 'ff7913bb97e896f7992720b9a43c2382970a5fc8',
        'sha256': DIGEST,
        'package': PACKAGE,
        'version': VERSION,
    })
    (OUT / 'session.txt').write_text(
        gate.vm.execute('/usr/bin/loginctl', ['list-sessions', '--no-legend'])
    )
    absent = gate.vm.python(
        "from pathlib import Path; print([Path(p).exists() for p in "
        + repr([GUEST_DEB, GUEST_COLLECTOR, GUEST_ROOT, GUEST_ARCHIVE]) + '])'
    ).strip()
    assert absent == '[False, False, False, False]', absent

    gate.vm.transfer(str(DEB), GUEST_DEB)
    gate.vm.execute('/bin/chmod', ['0644', GUEST_DEB])
    guest_hash = gate.vm.python(
        f"import hashlib; print(hashlib.sha256(open({GUEST_DEB!r},'rb').read()).hexdigest())"
    ).strip()
    assert guest_hash == DIGEST

    simulation = gate.vm.execute(
        '/usr/bin/apt-get', ['-s', '--no-install-recommends', 'install', GUEST_DEB]
    )
    (OUT / 'apt-install-simulation.txt').write_text(simulation)
    added = selected(simulation, ('Inst',))
    removals = selected(simulation, ('Remv', 'Purg'))
    assert PACKAGE in added and not removals
    assert not (set(added) & package_names(baseline)), added
    save_json('added.json', added)

    try:
        install_log = gate.vm.execute(
            '/usr/bin/apt-get', ['-y', '--no-install-recommends', 'install', GUEST_DEB]
        )
        (OUT / 'apt-install.txt.gz').write_bytes(gzip.compress(install_log.encode(), mtime=0))
        installed = gate.inventory()
        save_json('installed-inventory.json', installed)
        assert installed_delta(baseline, installed) == added
        assert installed['entries'] == baseline['entries']
        assert gate.vm.execute('/usr/bin/dpkg', ['-V', PACKAGE]) == ''

        collector = REPO / 'packaging/collect-installed-sbom.py'
        gate.vm.transfer(str(collector), GUEST_COLLECTOR)
        gate.vm.execute('/bin/chmod', ['0644', GUEST_COLLECTOR])
        metadata = json.loads(gate.vm.python(CAPTURE))
        archive = OUT / 'debian-local-evidence.tar.xz'
        archive.write_bytes(receive(GUEST_ARCHIVE, metadata))

        verify_spec = importlib.util.spec_from_file_location(
            'verify', REPO / 'packaging/verify-environment-evidence.py'
        )
        verifier = importlib.util.module_from_spec(verify_spec)
        verify_spec.loader.exec_module(verifier)
        result = verifier.verify(archive, DEB, PACKAGE, VERSION)
        save_json('verified.json', result)
        print(json.dumps(result), flush=True)
    finally:
        cleanup(baseline, added)

    (OUT / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
        for path in sorted(OUT.iterdir())
        if path.is_file() and path.name != 'SHA256SUMS'
    ))


if __name__ == '__main__':
    main()
