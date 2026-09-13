"""Fresh rollback network-cut operation after explicit guest clock sync.

The prior operation is retained as non-qualifying evidence.  This wrapper uses
new guest paths, alias, snapshot, Secret Service reference, operation identity,
and output directory.  It also preserves the helper's bounded JSON response so
an early helper failure has a precise error code without reinvocation.
"""
from pathlib import Path
import sys

source = Path(__file__).with_name('cross-vm-network-rollback-2026-09-13.py').read_text()
source = source.replace('network-rollback', 'network-rollback2')
namespace = {'__file__': __file__, '__name__': 'network_rollback2_lifecycle'}
exec(compile(source, __file__, 'exec'), namespace)

namespace['RELAY'] = namespace['RELAY'].replace(
    "result=subprocess.run(sys.argv[1:],capture_output=True,timeout=30)\nif result.returncode==0:",
    "result=subprocess.run(sys.argv[1:],capture_output=True,timeout=30)\n"
    "p=Path(__file__).with_name('helper-observation.json')\n"
    "with p.open('x') as f: json.dump({'exit_code':result.returncode,'stdout':result.stdout.decode('utf-8','replace'),'stderr':result.stderr.decode('utf-8','replace')},f)\n"
    "if result.returncode==0:",
)

def collect_helper_observation():
    import json
    base = namespace['namespace']['namespace']
    path = namespace['GUEST']+'/hold/helper-observation.json'
    value = namespace['ubuntu'].python(
        'from pathlib import Path; print(Path('+repr(path)+').read_text())'
    )
    observation = json.loads(value)
    assert observation['exit_code'] == 0
    result = json.loads(observation['stdout'])
    marker = json.loads((namespace['OUT']/'rollback-helper-completion.json').read_text())
    assert result['request_id'] == marker['request_id']
    assert result['request_hash'] == marker['request_hash']
    assert result['restored_hash'] == 'b30b14759c0fd796fc8e6a744ccd19caf081d874d51ff1dfebb1c1938ae29088'
    base['save']('helper-observation.json', observation)


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'collect-helper':
        collect_helper_observation()
    elif action in {'setup', 'watch', 'collect', 'cleanup'}:
        namespace[action]()
    elif action == 'collect-failed':
        namespace['collect_failed']()
    elif action == 'launch':
        namespace['namespace']['namespace']['launch']('rollback')
    elif action == 'status':
        namespace['namespace']['namespace']['status']('rollback')
    elif action in {'prepare', 'inspect'}:
        namespace['namespace']['namespace'][action]()
    elif action == 'diagnose':
        namespace['namespace']['diagnose']()
    elif action == 'clocks':
        namespace['namespace']['clocks']()
    else:
        raise ValueError(action)
