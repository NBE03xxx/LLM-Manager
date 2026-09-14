import hashlib,json,os
from pathlib import Path
from llm_manager.application.ports import CancellationToken
from llm_manager.infrastructure.backup_crypto import AesGcmBackupCipher
from llm_manager.infrastructure.local_root_key_provisioning import open_production_key_directory
from llm_manager.infrastructure.root_backup_capture import LocalRootBackupKeys,decrypt_root_backup
from llm_manager.infrastructure.root_backup_evidence import RootBackupEvidenceReader,open_production_directory
root=Path('/tmp/phase6-local-root-restore-gui-20260914'); original=b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'; changed=b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\nEnvironment="OLLAMA_FLASH_ATTENTION=1"\n'; digest=lambda value:hashlib.sha256(value).hexdigest()
backups=Path('/var/lib/llm-manager/local-root-restore/backups'); executions=Path('/var/lib/llm-manager/local-root-restore/executions'); audit=Path('/var/lib/llm-manager/local-root-restore/audit')
assert sorted(p.name for p in backups.iterdir())==['root-gui-backup-20260914.bin','root-gui-backup-20260914.json']
assert list(executions.iterdir())==[] and list(audit.iterdir())==[] and Path('/etc/systemd/system/ollama.service.d/90-llm-manager.conf').read_bytes()==changed
origin_fd=open_production_directory(); key_fd=open_production_key_directory()
try:
 evidence,envelope=RootBackupEvidenceReader(origin_fd).inspect('root-gui-backup-20260914',CancellationToken())
 plaintext=decrypt_root_backup(evidence,envelope,AesGcmBackupCipher(LocalRootBackupKeys(key_fd)))
finally: os.close(origin_fd); os.close(key_fd)
assert plaintext==original
(root/'fixture.json').write_text(json.dumps({'backup_id':evidence.backup_id,'record_hash':evidence.record_hash,'source_apply_request_hash':evidence.source_apply_request_hash,'source_manifest_hash':evidence.source_manifest_hash,'original_sha256':digest(original),'changed_sha256':digest(changed),'target':evidence.target},sort_keys=True)+'\n')
os.chown(root/'fixture.json',1000,1000); os.chmod(root/'fixture.json',0o600)
