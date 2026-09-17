import hashlib,json,os,time
from pathlib import Path
config=Path('/home/yoshimi/.config/opencode/opencode.jsonc')
binary=Path('/usr/local/bin/opencode')
held=Path('/usr/local/bin/opencode.phase6-final-ssh-rollback-net2')
root=Path('/tmp/phase6-final-ssh-rollback-net2-20260917')
result=root/'runtime-watcher-result.json'
assert config.is_file() and not config.is_symlink()
assert binary.is_file() and not binary.is_symlink() and not held.exists()
before=hashlib.sha256(config.read_bytes()).hexdigest()
binary_hash=hashlib.sha256(binary.read_bytes()).hexdigest()
binary_mode=binary.stat().st_mode & 0o777
started=time.time_ns()
deadline=time.monotonic()+1800
detected=None
restored=None
try:
 while time.monotonic()<deadline:
  current=hashlib.sha256(config.read_bytes()).hexdigest()
  if current!=before:
   detected={'wall_time_ns':time.time_ns(),'after_sha256':current}
   os.rename(binary,held)
   break
  time.sleep(0.001)
 else: raise TimeoutError('approved config mutation not observed')
 while time.monotonic()<deadline:
  current=hashlib.sha256(config.read_bytes()).hexdigest()
  if current==before:
   assert held.is_file() and not held.is_symlink() and not binary.exists()
   os.rename(held,binary)
   assert hashlib.sha256(binary.read_bytes()).hexdigest()==binary_hash
   assert binary.stat().st_mode & 0o777==binary_mode
   restored={'wall_time_ns':time.time_ns(),'config_sha256':current}
   break
  time.sleep(0.001)
 else: raise TimeoutError('rollback restoration not observed')
 result.write_text(json.dumps({'status':'restored','started_wall_time_ns':started,
  'before_sha256':before,'binary_sha256':binary_hash,'binary_mode':oct(binary_mode),
  'mutation_detected':detected,'runtime_restored':restored},indent=2)+'\n')
except BaseException as error:
 if held.is_file() and not held.is_symlink() and not binary.exists(): os.rename(held,binary)
 result.write_text(json.dumps({'status':'failed','error':type(error).__name__,
  'before_sha256':before,'binary_sha256':binary_hash},indent=2)+'\n')
 raise
