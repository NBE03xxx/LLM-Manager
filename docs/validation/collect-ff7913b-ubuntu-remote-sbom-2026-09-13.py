"""Collect installed Ubuntu remote-helper candidate SBOM in a disposable snapshot."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


REPO = Path('/home/yoshimi/WorkSpace/LLM-Manager')
OUT = REPO / 'docs/validation/sbom-ff7913b-ubuntu-remote-2026-09-13'
DEB = Path(
    '/tmp/llm-manager-candidate-ff7913b-20260913/'
    'llm-manager-remote-helper_0.1.0_all.deb'
)
DIGEST = '830f50b2b22984bba9622d10cca81a54571e101655f0fbd53c7a7fe76b774d2d'
PACKAGE = 'llm-manager-remote-helper'
VERSION = '0.1.0'
SNAPSHOT = 'phase6-ff7913b-ubuntu-remote-sbom-20260913'
GUEST_DEB = '/tmp/phase6-ff7913b-remote-sbom.deb'
GUEST_COLLECTOR = '/tmp/phase6-ff7913b-remote-collector.py'
GUEST_ARCHIVE = '/tmp/phase6-ff7913b-remote-sbom.tar.xz'

spec = importlib.util.spec_from_file_location(
    'remote_lifecycle',
    REPO / 'docs/validation/remote-helper-b15a984-2026-09-12/lifecycle.py',
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
args=['/usr/sbin/runuser','-u','yoshimi','--','/usr/bin/python3','-I',
      '/tmp/phase6-ff7913b-remote-collector.py','--output',str(root/'environment/data')]
result=subprocess.run(args,capture_output=True,text=True)
assert result.returncode in (0,2),result.stderr
(root/'collector.exit').write_text(str(result.returncode)+'\n')
(root/'collector.log').write_text(result.stdout+result.stderr)
artifact=Path('/tmp/phase6-ff7913b-remote-sbom.deb')
digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
(root/'artifact.sha256').write_text(
    digest+'  llm-manager-remote-helper_0.1.0_all.deb\n')
version=subprocess.check_output(
    ['dpkg-query','-W','-f=${Version}','llm-manager-remote-helper'],text=True)
(root/'summary.json').write_text(json.dumps({
    'artifact_sha256':digest,
    'installed_package':'llm-manager-remote-helper',
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
archive=Path('/tmp/phase6-ff7913b-remote-sbom.tar.xz')
with tarfile.open(archive,'x:xz') as tar:
    tar.add(root,arcname=root.name)
print(json.dumps({
    'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
    'bytes':archive.stat().st_size,
}))
'''


def save_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


def receive(target, expected):
    handle = gate.qga('guest-file-open', {'path': target, 'mode': 'r'})
    data = bytearray()
    try:
        while True:
            block = gate.qga('guest-file-read', {'handle': handle, 'count': 65536})
            data.extend(base64.b64decode(block.get('buf-b64', '')))
            if block.get('eof'):
                break
    finally:
        gate.qga('guest-file-close', {'handle': handle})
    assert len(data) == expected['bytes']
    assert hashlib.sha256(data).hexdigest() == expected['sha256']
    return bytes(data)


def restore(baseline):
    print(gate.virsh('snapshot-revert', gate.VM, SNAPSHOT, '--running'), flush=True)
    restored = gate.inventory()
    save_json('restored.json', restored)
    assert restored == baseline
    print(gate.virsh('snapshot-delete', gate.VM, SNAPSHOT), flush=True)


def main():
    assert gate.virsh('domstate', gate.VM).strip() == 'running'
    assert SNAPSHOT not in gate.virsh('snapshot-list', gate.VM, '--name').splitlines()
    assert DEB.is_file() and hashlib.sha256(DEB.read_bytes()).hexdigest() == DIGEST
    assert not OUT.exists()
    OUT.mkdir()
    baseline = gate.inventory()
    assert gate.package_version() is None
    save_json('baseline.json', baseline)
    save_json('artifact-identity.json', {
        'source_commit': 'ff7913bb97e896f7992720b9a43c2382970a5fc8',
        'sha256': DIGEST,
        'package': PACKAGE,
        'version': VERSION,
    })
    print(gate.virsh(
        'snapshot-create-as', gate.VM, SNAPSHOT,
        'Disposable ff7913b Ubuntu remote-helper environment SBOM gate', '--atomic'
    ), flush=True)
    try:
        gate.transfer(DEB, GUEST_DEB)
        gate.execute('/bin/chmod', ['0644', GUEST_DEB])
        guest_hash = gate.python(
            f"import hashlib; print(hashlib.sha256(open({GUEST_DEB!r},'rb').read()).hexdigest())"
        ).strip()
        assert guest_hash == DIGEST

        simulation = gate.execute(
            '/usr/bin/apt-get', ['-s', '--no-install-recommends', 'install', GUEST_DEB]
        )
        (OUT / 'apt-install-simulation.txt').write_text(simulation)
        installs = {
            line.split()[1] for line in simulation.splitlines() if line.startswith('Inst ')
        }
        removals = {
            line.split()[1] for line in simulation.splitlines()
            if line.startswith(('Remv ', 'Purg '))
        }
        assert installs == {PACKAGE} and not removals, (installs, removals)
        install_log = gate.execute(
            '/usr/bin/apt-get', ['-y', '--no-install-recommends', 'install', GUEST_DEB]
        )
        (OUT / 'apt-install.txt.gz').write_bytes(
            gzip.compress(install_log.encode(), mtime=0)
        )
        assert gate.package_version() == VERSION
        assert gate.execute('/usr/bin/dpkg', ['-V', PACKAGE]) == ''
        installed = gate.inventory()
        save_json('installed-inventory.json', installed)
        assert installed['entries'] == baseline['entries']

        collector = REPO / 'packaging/collect-installed-sbom.py'
        gate.transfer(collector, GUEST_COLLECTOR)
        gate.execute('/bin/chmod', ['0644', GUEST_COLLECTOR])
        metadata = json.loads(gate.python(CAPTURE))
        archive = OUT / 'ubuntu-remote-evidence.tar.xz'
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
        if SNAPSHOT in gate.virsh('snapshot-list', gate.VM, '--name').splitlines():
            restore(baseline)

    (OUT / 'SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
        for path in sorted(OUT.iterdir())
        if path.is_file() and path.name != 'SHA256SUMS'
    ))


if __name__ == '__main__':
    main()
