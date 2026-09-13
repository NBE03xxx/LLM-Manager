"""Explicit one-shot guest clock synchronization; no NTP configuration changes."""
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import time

REPO=Path(__file__).resolve().parents[2]
OUT=Path(__file__).with_suffix('.json')
spec=importlib.util.spec_from_file_location('clock_vm',REPO/'docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py')
vm=importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)


def measure():
    start=time.time()
    guest=float(vm.python('import time; print(time.time())').strip())
    end=time.time()
    return {'host_start':start,'guest':guest,'host_end':end,
            'offset_lower_seconds':guest-end,'offset_upper_seconds':guest-start}


def main():
    assert sys.argv[1:] == ['--synchronize']
    records=[]
    for name in ['ubuntu26.04','debian13']:
        vm.VM=name
        assert vm.virsh('domstate',name).strip()=='running'
        before=measure()
        method='guest-set-time'
        error=None
        try:
            if vm.python("from pathlib import Path; print(Path('/sbin/hwclock').is_file())").strip()!='True':
                raise FileNotFoundError('hwclock unavailable; skip guest-set-time RTC update')
            vm.qga('guest-set-time',{'time':time.time_ns()})
        except (subprocess.CalledProcessError,FileNotFoundError) as exc:
            # Ubuntu may lack hwclock: guest-set-time can set system time then
            # fail its RTC update. Explicit date updates only the system clock.
            error=str(exc)
            method='guest-exec date --set (system clock only)'
            vm.execute('/usr/bin/date',['--set','@'+str(time.time()),'--utc'])
        after=measure()
        assert abs(after['offset_lower_seconds'])<1 and abs(after['offset_upper_seconds'])<1,after
        records.append({'vm':name,'before':before,'after':after,'method':method,'qga_error':error})
    previous=json.loads(OUT.read_text()) if OUT.exists() else []
    previous.append({'scope':'guest clocks only; host clock and NTP settings unchanged','measurements':records})
    OUT.write_text(json.dumps(previous,indent=2)+'\n')
    print(json.dumps(records,indent=2))


if __name__=='__main__': main()
