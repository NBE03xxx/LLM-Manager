"""Collect installed Ubuntu local candidate SBOM inside a disposable snapshot."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path('/home/yoshimi/WorkSpace/LLM-Manager')
OUT = REPO / 'docs/validation/sbom-ff7913b-ubuntu-local-2026-09-13'
DEB = Path('/tmp/llm-manager-candidate-ff7913b-20260913/llm-manager_0.1.0_all.deb')
DIGEST = '351edec886ff06f7e72979e7e6022abac45354871dbd412cab724d01f9518243'
spec = importlib.util.spec_from_file_location('lifecycle', REPO / 'docs/validation/ubuntu-display-b15a984-2026-09-12/lifecycle.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
gate.OUT = OUT
gate.SNAP = 'phase6-ff7913b-ubuntu-local-sbom-20260913'
gate.DEB = DEB
gate.HASH = DIGEST
gate.GUEST = '/tmp/phase6-ff7913b-sbom.deb'
vm = gate.vm

CAPTURE = r'''
import hashlib,json,os,subprocess,tarfile
from pathlib import Path
root=Path('/tmp/llm-manager-phase6-sbom-gate')
root.mkdir(mode=0o755)
(root/'environment').mkdir()
os.chown(root/'environment',1000,1000)
args=['/usr/sbin/runuser','-u','yoshimi','--','/usr/bin/python3','-I',
      '/tmp/phase6-ff7913b-collector.py','--output',str(root/'environment/data')]
result=subprocess.run(args,capture_output=True,text=True)
assert result.returncode in (0,2),result.stderr
(root/'collector.exit').write_text(str(result.returncode)+'\n')
(root/'collector.log').write_text(result.stdout+result.stderr)
digest=hashlib.sha256(Path('/tmp/phase6-ff7913b-sbom.deb').read_bytes()).hexdigest()
(root/'artifact.sha256').write_text(digest+'  llm-manager_0.1.0_all.deb\n')
version=subprocess.check_output(['dpkg-query','-W','-f=${Version}','llm-manager'],text=True)
(root/'summary.json').write_text(json.dumps({'artifact_sha256':digest,'installed_package':'llm-manager',
    'installed_version':version,'collector_exit':result.returncode,'source_commit':'ff7913bb97e896f7992720b9a43c2382970a5fc8'})+'\n')
(root/'packages-installed.tsv').write_bytes(subprocess.check_output([
    'dpkg-query','-W','-f=${binary:Package}\t${Version}\t${Architecture}\t${db:Status-Status}\n']))
audit=subprocess.check_output(['dpkg','--audit'])
assert not audit.strip()
(root/'dpkg-audit.log').write_bytes(audit)
files=sorted(p for p in root.rglob('*') if p.is_file())
(root/'EVIDENCE-SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
archive=Path('/tmp/phase6-ff7913b-sbom.tar.xz')
with tarfile.open(archive,'x:xz') as tar: tar.add(root,arcname=root.name)
print(json.dumps({'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size}))
'''

assert not OUT.exists()
try:
    gate.main('prepare')
    collector = REPO / 'packaging/collect-installed-sbom.py'
    vm.transfer(collector, '/tmp/phase6-ff7913b-collector.py')
    vm.execute('/bin/chmod', ['0644', '/tmp/phase6-ff7913b-collector.py'])
    metadata = json.loads(vm.python(CAPTURE))
    handle = vm.qga('guest-file-open', {'path':'/tmp/phase6-ff7913b-sbom.tar.xz','mode':'r'})
    data = bytearray()
    try:
        while True:
            block = vm.qga('guest-file-read', {'handle':handle,'count':65536})
            data.extend(base64.b64decode(block.get('buf-b64','')))
            if block.get('eof'): break
    finally:
        vm.qga('guest-file-close', {'handle':handle})
    assert len(data)==metadata['bytes'] and hashlib.sha256(data).hexdigest()==metadata['sha256']
    archive = OUT / 'ubuntu-local-evidence.tar.xz'
    archive.write_bytes(data)
    verify_spec=importlib.util.spec_from_file_location('verify',REPO/'packaging/verify-environment-evidence.py')
    verifier=importlib.util.module_from_spec(verify_spec)
    verify_spec.loader.exec_module(verifier)
    result=verifier.verify(archive,DEB,'llm-manager','0.1.0')
    (OUT/'verified.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
finally:
    if gate.SNAP in vm.virsh('snapshot-list',vm.VM,'--name').splitlines():
        gate.main('restore')
(OUT/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n'
    for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
