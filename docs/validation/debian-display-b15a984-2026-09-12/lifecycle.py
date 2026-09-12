"""Recorded Debian candidate gate. Run individual actions, not unattended UI."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path('/home/yoshimi/WorkSpace/LLM-Manager')
spec = importlib.util.spec_from_file_location('vm', ROOT / 'docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)
vm.VM = 'debian13'
OUT = Path(__file__).resolve().parent
SOURCE = Path('/tmp/llm-manager-candidate-b15a984-20260912/llm-manager_0.1.0_all.deb')
TARGET = '/tmp/llm-manager-b15a984-20260912.deb'
DIGEST = '292b831c5454e3a6d41b59a67145474a76b066146bebc4e7308b81a6e50ff7f8'


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


def inventory():
    return json.loads(vm.python('''import subprocess,json,hashlib,pwd
from pathlib import Path
assert pwd.getpwuid(1000).pw_name == 'user'
packages=sorted(subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\\t${Version}\\t${db:Status-Status}\\n'],text=True).splitlines())
manual=sorted(subprocess.check_output(['apt-mark','showmanual'],text=True).splitlines())
entries={}
for root in ['/home/user/.config/llm-manager','/home/user/.config/opencode','/home/user/.ssh','/var/lib/llm-manager','/usr/local/bin/opencode']:
 p=Path(root)
 for f in [p]+(sorted(p.rglob('*')) if p.is_dir() else []):
  if not f.exists() and not f.is_symlink(): entries[str(f)]=None; continue
  s=f.lstat()
  entries[str(f)]={'mode':s.st_mode,'uid':s.st_uid,'gid':s.st_gid,'hash':hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() and not f.is_symlink() else None}
print(json.dumps({'packages':packages,'manual':manual,'entries':entries}))
'''))


def apt(name, args):
    raw = vm.execute('/usr/bin/apt-get', args)
    (OUT / (name + '.txt.gz')).write_bytes(gzip.compress(raw.encode(), mtime=0))
    return raw


def selected(raw, kind):
    return sorted(row.split()[1] for row in raw.splitlines() if row.startswith(kind + ' '))


def absent():
    print(vm.python("import subprocess; p=subprocess.run(['pgrep','-a','-f','^/usr/bin/python3 -I /usr/bin/llm-manager'],capture_output=True,text=True); assert p.returncode==1,p.stdout; print('Application absent')"))


def main(action):
    if action == 'prepare':
        assert not (OUT / 'baseline.json').exists()
        assert vm.virsh('domstate', vm.VM).strip() == 'running'
        assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == DIGEST
        absent()
        baseline = inventory()
        assert not any(x.split('\t')[0].split(':')[0] == 'llm-manager' for x in baseline['packages'])
        save('baseline.json', baseline)
        (OUT / 'session.txt').write_text(vm.execute('/usr/bin/loginctl', ['show-session','2','-p','Name','-p','Type','-p','Active','-p','State','-p','LockedHint']))
        vm.python('from pathlib import Path; p=Path('+repr(TARGET)+'); assert not p.exists() and not p.is_symlink()')
        vm.transfer(str(SOURCE), TARGET)
        vm.python('import hashlib,os; assert hashlib.sha256(open('+repr(TARGET)+',"rb").read()).hexdigest()=='+repr(DIGEST)+'; os.chmod('+repr(TARGET)+',0o644)')
        sim = apt('apt-install-simulation', ['-s','--no-install-recommends','install',TARGET])
        added = selected(sim, 'Inst')
        prior = {x.split('\t')[0].split(':')[0] for x in baseline['packages']}
        assert 'llm-manager' in added and not selected(sim, 'Remv')
        assert not any(x.split(':')[0] in prior for x in added), sim
        save('added.json', added)
        print('Baseline saved; fixed added packages:', added)
    elif action == 'install':
        baseline=json.loads((OUT/'baseline.json').read_text())
        assert inventory()==baseline
        added=json.loads((OUT/'added.json').read_text())
        sim=apt('apt-install-recheck',['-s','--no-install-recommends','install',TARGET])
        assert selected(sim,'Inst')==added and not selected(sim,'Remv')
        apt('apt-install',['-y','--no-install-recommends','install',TARGET])
        installed=inventory()
        save('installed.json',installed)
        assert set(baseline['packages']).issubset(installed['packages'])
        assert sorted(x.split('\t')[0].split(':')[0] for x in set(installed['packages'])-set(baseline['packages']))==added
        assert installed['entries']==baseline['entries']
        assert vm.execute('/usr/bin/dpkg',['-V','llm-manager'])==''
        print('Candidate installed; prior packages/settings unchanged; dpkg -V clean.')
    elif action == 'verify':
        baseline=json.loads((OUT/'baseline.json').read_text())
        current=inventory()
        added=json.loads((OUT/'added.json').read_text())
        assert set(baseline['packages']).issubset(current['packages'])
        assert sorted(x.split('\t')[0].split(':')[0] for x in set(current['packages'])-set(baseline['packages']))==added
        assert current['entries']==baseline['entries']
        assert vm.execute('/usr/bin/dpkg',['-V','llm-manager'])==''
        info=json.loads(vm.execute('/usr/sbin/runuser',['-u','user','--','/usr/bin/python3','-I','-c','import os,json,llm_manager; from llm_manager.ui.i18n import Catalog; print(json.dumps({"uid":os.getuid(),"module":llm_manager.__file__,"en":Catalog("en").text("results.completed",status="committed"),"ja":Catalog("ja").text("results.completed",status="committed")}))']))
        assert info['uid']==1000 and 'sandbox' not in (info['en']+info['ja']).lower()
        save('installed-import.json',info)
        print('Installed package set, settings, dpkg verification and isolated user import passed.')
    elif action == 'process':
        result=vm.python('''import json,pathlib,subprocess
pids=subprocess.check_output(['pgrep','-f','^/usr/bin/python3 -I /usr/bin/llm-manager'],text=True).split()
assert len(pids)==1,pids
p=pathlib.Path('/proc')/pids[0]
argv=(p/'cmdline').read_bytes().split(b'\\0')[:-1]
assert argv==[b'/usr/bin/python3',b'-I',b'/usr/bin/llm-manager'],argv
uid=next(x for x in (p/'status').read_text().splitlines() if x.startswith('Uid:'))
assert uid.split()[1:]==['1000']*4,uid
print(json.dumps({'pid':int(pids[0]),'argv':[x.decode() for x in argv],'uid':uid}))
''')
        (OUT/'process.json').write_text(result)
        print(result)
    elif action == 'lifecycle':
        absent()
        save('normal-exit.json',{'pgrep_exit_code':1})
        original=inventory()
        assert original==json.loads((OUT/'installed.json').read_text())
        for name,args,installing in [
            ('reinstall',['--reinstall','--no-install-recommends','install',TARGET],True),
            ('remove',['remove','llm-manager'],False),
            ('fresh-install',['--no-install-recommends','install',TARGET],True),
        ]:
            sim=apt(name+'-simulation',['-s',*args])
            assert selected(sim,'Inst')==(['llm-manager'] if installing else [])
            assert sorted(set(selected(sim,'Remv')+selected(sim,'Purg')))==([] if installing else ['llm-manager'])
            apt(name,['-y',*args])
            after=inventory()
            save(name+'-inventory.json',after)
            assert after['entries']==original['entries']
            if installing:
                assert after['manual']==original['manual']
            else:
                assert set(after['manual'])==set(original['manual'])-{'llm-manager'}
            assert [x for x in after['packages'] if x.split('\t')[0]!='llm-manager']==[x for x in original['packages'] if x.split('\t')[0]!='llm-manager']
            if installing:
                assert after==original
                assert vm.execute('/usr/bin/dpkg',['-V','llm-manager'])==''
        print('Normal exit, reinstall, remove, fresh install passed; other packages/settings unchanged.')
    elif action == 'cleanup':
        absent()
        baseline=json.loads((OUT/'baseline.json').read_text())
        added=json.loads((OUT/'added.json').read_text())
        current=inventory()
        assert set(baseline['packages']).issubset(current['packages'])
        assert sorted(x.split('\t')[0].split(':')[0] for x in set(current['packages'])-set(baseline['packages']))==added
        sim=apt('apt-purge-simulation',['-s','purge',*added])
        removals=sorted(set(selected(sim,'Remv')+selected(sim,'Purg')))
        assert removals==added and not selected(sim,'Inst'),sim
        apt('apt-purge',['-y','purge',*added])
        cleaned=inventory()
        save('cleaned.json',cleaned)
        assert cleaned==baseline, 'Baseline mismatch: inspect saved inventories; do not delete user data.'
        assert vm.execute('/usr/bin/dpkg',['--audit'])==''
        apt('apt-check',['check'])
        vm.python('from pathlib import Path; p=Path('+repr(TARGET)+'); assert p.is_file() and not p.is_symlink(); p.unlink()')
        save('cleanup-result.json',{'baseline_exact_match':True,'dpkg_audit_empty':True,'apt_check':True,'vm_state':vm.virsh('domstate',vm.VM).strip(),'transferred_deb_removed':True})
        print('Exact baseline restored; transferred deb removed; VM remains running.')
    elif action == 'audit':
        assert inventory()==json.loads((OUT/'baseline.json').read_text())
        assert vm.python('from pathlib import Path; print(Path('+repr(TARGET)+').exists())').strip()=='False'
        states={name:vm.virsh('domstate',name).strip() for name in ['debian13','ubuntu26.04']}
        assert set(states.values())=={'running'}
        save('final-vm-state.json',states)
        (OUT/'final-session.txt').write_text(vm.execute('/usr/bin/loginctl',['show-session','2','-p','Name','-p','Type','-p','Active','-p','State','-p','LockedHint']))
        (OUT/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
        print('Final baseline/artifact/VM audit passed; evidence checksums generated.')
    else:
        raise ValueError(action)


if __name__ == '__main__':
    main(sys.argv[1])
