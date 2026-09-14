import hashlib,json,os
from datetime import timedelta
from pathlib import Path
from llm_manager.application.ports import CancellationToken
from llm_manager.domain.models import utc_now
from llm_manager.infrastructure.helper_protocol import HelperOperation,HelperOperationKind,HelperRequest
from llm_manager.infrastructure.root_apply_capture import capture_before_replace
from llm_manager.infrastructure.root_restore_execution import open_production_source_parent
from llm_manager.infrastructure.root_target_lock import locked_root_target
from llm_manager.planning.ollama import DROP_IN_PATH
root=Path('/tmp/phase6-local-root-restore-gui-20260914'); target=Path(DROP_IN_PATH); original=b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\nEnvironment="OLLAMA_FLASH_ATTENTION=0"\n'; changed=b'[Service]\nEnvironment="OLLAMA_HOST=127.0.0.1:11434"\nEnvironment="OLLAMA_FLASH_ATTENTION=1"\n'
assert os.geteuid()==0 and target.read_bytes()==original
now=utc_now(); digest=lambda value:hashlib.sha256(value).hexdigest()
request=HelperRequest(1,'rootapply-gui-20260914','local:'+os.uname().nodename,'plan-root-gui-20260914',digest(b'root-gui-change-set'),(
 HelperOperation('write-root-gui',HelperOperationKind.ATOMIC_REPLACE,target=DROP_IN_PATH,before_hash=digest(original),staged_content_hash=digest(changed),expected_mode=0o644,expected_uid=0,expected_gid=0),
 HelperOperation('reload-root-gui',HelperOperationKind.DAEMON_RELOAD),HelperOperation('restart-root-gui',HelperOperationKind.RESTART_UNIT,unit='ollama.service')),
 now,now+timedelta(minutes=5),approval_id='approval-root-gui-20260914',backup_id='root-gui-backup-20260914',manifest_hash=digest(b'root-gui-manifest')).with_hash()
fd=open_production_source_parent()
try:
 with locked_root_target(fd):
  evidence=capture_before_replace(request,fd); temporary=target.with_name('.90-llm-manager.conf.phase6-root-gui')
  with temporary.open('xb') as stream: stream.write(changed); stream.flush(); os.fsync(stream.fileno())
  temporary.chmod(0o644); os.replace(temporary,target); os.fsync(fd)
finally: os.close(fd)
(root/'fixture.json').write_text(json.dumps({'backup_id':evidence.backup_id,'record_hash':evidence.record_hash,'source_apply_request_hash':request.request_hash,'source_manifest_hash':request.manifest_hash,'original_sha256':digest(original),'changed_sha256':digest(changed),'target':DROP_IN_PATH},sort_keys=True)+'\n')
os.chown(root/'fixture.json',1000,1000); os.chmod(root/'fixture.json',0o600)
