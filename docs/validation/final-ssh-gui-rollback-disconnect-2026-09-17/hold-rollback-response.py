import json,subprocess,sys,time
from pathlib import Path
assert len(sys.argv)==5
assert sys.argv[1:3]==['/usr/bin/llm-manager-remote-helper','user-rollback']
result=subprocess.run(sys.argv[1:],capture_output=True,timeout=30)
observation={'exit_code':result.returncode,'stdout':result.stdout.decode('utf-8','replace'),'stderr':result.stderr.decode('utf-8','replace')}
with Path(__file__).with_name('helper-observation.json').open('x') as f: json.dump(observation,f)
if result.returncode==0:
 decoded=json.loads(observation['stdout'])
 marker={'verb':'user-rollback','request_id':sys.argv[3],'request_hash':sys.argv[4],
  'helper_exit_code':result.returncode,'restored_hash':decoded.get('restored_hash')}
 with Path(__file__).with_name('rollback-ready.json').open('x') as f: json.dump(marker,f)
 time.sleep(10)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
