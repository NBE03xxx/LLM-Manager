import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

REPO=Path('/home/yoshimi/WorkSpace/LLM-Manager')
spec=importlib.util.spec_from_file_location('vm_gate',REPO/'docs/validation/ssh-gui-2026-09-11/vm-lifecycle.py')
vm=importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)
SNAP='phase6-ubuntu-display-b15a984-20260912'
OUT=REPO/'docs/validation/ubuntu-display-b15a984-2026-09-12'
DEB=Path('/tmp/llm-manager-candidate-b15a984-20260912/llm-manager_0.1.0_all.deb')
HASH='292b831c5454e3a6d41b59a67145474a76b066146bebc4e7308b81a6e50ff7f8'
GUEST='/tmp/phase6-ubuntu-display-b15a984.deb'

def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2)+'\n')

def baseline(): return json.loads((OUT/'baseline.json').read_text())

def apt(name,args,removing=False):
    assert SNAP in vm.virsh('snapshot-list',vm.VM,'--name').splitlines()
    simulation=vm.execute('/usr/bin/apt-get',['-s',*args])
    (OUT/(name+'-simulation.txt')).write_text(simulation)
    installs=[line.split()[1] for line in simulation.splitlines() if line.startswith('Inst ')]
    removes=[line.split()[1] for line in simulation.splitlines() if line.startswith('Remv ') or line.startswith('Purg ')]
    assert set(installs)<= {'llm-manager'} and set(removes)<= {'llm-manager'}
    assert not (installs if removing else removes)
    raw=vm.execute('/usr/bin/apt-get',['-y',*args])
    (OUT/(name+'.txt.gz')).write_bytes(gzip.compress(raw.encode(),mtime=0))
    after=vm.inventory()
    save(name+'-inventory.json',after)
    assert after['entries']==baseline()['entries'], 'existing configuration/backup changed'

def main(action):
    if action=='prepare':
        assert vm.virsh('domstate',vm.VM).strip()=='running'
        assert SNAP not in vm.virsh('snapshot-list',vm.VM,'--name').splitlines()
        assert hashlib.sha256(DEB.read_bytes()).hexdigest()==HASH
        OUT.mkdir(exist_ok=False)
        save('baseline.json',vm.inventory())
        print(vm.virsh('snapshot-create-as',vm.VM,SNAP,'Updated candidate desktop lifecycle; restore running', '--atomic'),flush=True)
        assert vm.python('from pathlib import Path; print(Path('+repr(GUEST)+').exists())').strip()=='False'
        vm.transfer(DEB,GUEST)
        vm.execute('/bin/chmod',['0644',GUEST])
        assert vm.python('import hashlib; print(hashlib.sha256(open('+repr(GUEST)+',"rb").read()).hexdigest())').strip()==HASH
        apt('upgrade',['--no-install-recommends','install',GUEST])
        apt('reinstall',['--reinstall','--no-install-recommends','install',GUEST])
        assert vm.execute('/usr/bin/dpkg',['-V','llm-manager']).strip()==''
        info=vm.execute('/usr/sbin/runuser',['-u','yoshimi','--','/usr/bin/python3','-I','-c',
            'import os,json,llm_manager; from llm_manager.ui.i18n import Catalog; print(json.dumps({"uid":os.getuid(),"module":llm_manager.__file__,"en":Catalog("en").text("results.completed",status="committed"),"ja":Catalog("ja").text("results.completed",status="committed")}))'])
        data=json.loads(info)
        assert data['uid']==1000 and 'sandbox' not in (data['en']+data['ja']).lower()
        save('installed-import.json',data)
        print('Candidate upgraded/reinstalled and installed labels verified. Ready for menu launch.')
    elif action=='process':
        value=vm.python('''import subprocess,json,os
from pathlib import Path
p=subprocess.run(['pgrep','-f','^/usr/bin/python3 -I /usr/bin/llm-manager$'],capture_output=True,text=True)
rows=[]
for value in p.stdout.split():
 root=Path('/proc')/value
 rows.append({'pid':int(value),'uid':root.stat().st_uid,'argv':(root/'cmdline').read_bytes().decode().split('\\0')[:-1]})
print(json.dumps(rows))
''')
        data=json.loads(value)
        assert len(data)==1 and data[0]['uid']==1000
        save('menu-process.json',data)
        print(value)
    elif action=='finish':
        absent=vm.python('import subprocess; print(subprocess.run(["pgrep","-f","^/usr/bin/python3 -I /usr/bin/llm-manager$"],capture_output=True).returncode)')
        assert absent.strip()=='1'
        save('normal-exit.json',{'pgrep_exit_code':1})
        apt('remove',['remove','llm-manager'],True)
        apt('fresh-install',['--no-install-recommends','install',GUEST])
        assert vm.execute('/usr/bin/dpkg',['-V','llm-manager']).strip()==''
        apt('purge',['purge','llm-manager'],True)
        assert vm.execute('/usr/bin/dpkg',['--audit']).strip()==''
        vm.execute('/usr/bin/apt-get',['check'])
        print('Remove/fresh install/purge succeeded; existing config/backup hashes unchanged.')
    elif action=='restore':
        assert SNAP in vm.virsh('snapshot-list',vm.VM,'--name').splitlines()
        print(vm.virsh('snapshot-revert',vm.VM,SNAP,'--running'),flush=True)
        after=vm.inventory()
        save('restored.json',after)
        assert after==baseline()
        print(vm.virsh('snapshot-delete',vm.VM,SNAP),flush=True)
        print('Restored baseline exactly; temporary snapshot deleted; running.')
    elif action=='audit':
        before=baseline()
        others=lambda rows: {row for row in rows if row.split('\t')[0].split(':')[0]!='llm-manager'}
        summary={}
        for name in ('upgrade','reinstall','remove','fresh-install','purge'):
            current=json.loads((OUT/(name+'-inventory.json')).read_text())
            assert others(current['packages'])==others(before['packages'])
            assert set(current['manual'])-{'llm-manager'}==set(before['manual'])-{'llm-manager'}
            rows=[row.split('\t') for row in current['packages'] if row.split('\t')[0]=='llm-manager']
            installed=[row for row in rows if row[-1]=='installed']
            if name in ('upgrade','reinstall','fresh-install'):
                assert len(installed)==1 and installed[0][1]=='0.1.0'
            else: assert not installed
            assert current['entries']==before['entries']
            summary[name]={'package_rows':rows,'other_packages_unchanged':True,'existing_paths_unchanged':True}
        save('lifecycle-audit.json',summary)
        print('All five lifecycle inventories audited against baseline.')

if __name__=='__main__': main(sys.argv[1])
