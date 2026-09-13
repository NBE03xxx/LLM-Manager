import json,subprocess,sys,time
from pathlib import Path
assert len(sys.argv)==5
assert sys.argv[1:3]==['/usr/bin/llm-manager-remote-helper','user-apply']
result=subprocess.run(sys.argv[1:],capture_output=True,timeout=30)
if result.returncode==0:
 p=Path(__file__).with_name('ready.json')
 with p.open('x') as f: json.dump({'verb':'user-apply','request_id':sys.argv[3],'request_hash':sys.argv[4],'helper_exit_code':result.returncode},f)
 time.sleep(10)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
