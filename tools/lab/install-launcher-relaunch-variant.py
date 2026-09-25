"""Temporary full-card-only A/B variant, with original IPK saved on TV."""
import importlib.util
import json
from pathlib import Path
import shlex
import sys
ROOT=Path(__file__).resolve().parent;SRC=ROOT/'lgtv-remote-broker'
sys.path.insert(0,str(ROOT/'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
import remote
spec=importlib.util.spec_from_file_location('builder',SRC/'scripts/build-all.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
mode=sys.argv[1];assert mode in ('experiment','restore')
original=builder.build('launcher',builder.APPS['launcher'])
config=dict(builder.APPS['launcher'])
if mode=='experiment':config['manifest']=str(ROOT/'launcher-startup-probe/full-autoactivate.json')
package,digest=builder.build('launcher',config)
pve=remote.connect();tv=remote.connect_tv(pve)
def checked(command,timeout=45):
    rc,out,err=remote.run(tv,'pve',command,timeout=timeout)
    if rc:raise RuntimeError((out+err).decode(errors='replace'))
    return (out+err).decode(errors='replace')
try:
    backup=checked('mktemp -d /var/lib/webosbrew/launcher-relaunch-backup.XXXXXX').strip()
    checked('tar -czf '+shlex.quote(backup+'/full-app.tgz')+' -C /media/developer/apps/usr/palm/applications hu.szabi.launcher')
    print('rollback='+backup,flush=True)
    with tv.open_sftp() as s:
        s.put(str(original[0]),backup+'/'+original[0].name)
        s.put(str(package),backup+'/'+package.name)
        s.put(str(SRC/'scripts/install-local-on-tv.sh'),backup+'/install.sh')
    print(checked('sh '+shlex.quote(backup+'/install.sh')+' '+shlex.quote(backup+'/'+package.name)+' '+digest,60),flush=True)
    metadata=json.loads(checked('cat /media/developer/apps/usr/palm/applications/hu.szabi.launcher/appinfo.json'))
    assert metadata['handlesRelaunch'] is (mode=='restore')
    print(json.dumps({'version':metadata['version'],'handlesRelaunch':metadata['handlesRelaunch']}),flush=True)
finally:tv.close();pve.close()
