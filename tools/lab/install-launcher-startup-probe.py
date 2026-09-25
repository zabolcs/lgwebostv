"""Install an isolated tiny diagnostic app; production packages untouched."""
import importlib.util
from pathlib import Path
import shlex
import sys
ROOT=Path(__file__).resolve().parent
SRC=ROOT/'lgtv-remote-broker'
PROBE=ROOT/'launcher-startup-probe'
sys.path.insert(0,str(ROOT/'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
import remote
spec=importlib.util.spec_from_file_location('builder',SRC/'scripts/build-all.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
package,digest=builder.build('launcher-startup-probe',{'id':'hu.szabi.launcher.startupprobe',
    'source':str(PROBE),'manifest':str(PROBE/'appinfo.json'),
    'files':('appinfo.json','index.html','icon.png','icon-large.png','splash-black.png')})
pve=remote.connect();tv=remote.connect_tv(pve)
def checked(command,timeout=45):
    rc,out,err=remote.run(tv,'pve',command,timeout=timeout)
    if rc:raise RuntimeError((out+err).decode(errors='replace'))
    return (out+err).decode(errors='replace')
try:
    stage=checked('mktemp -d /tmp/launcher-startup-probe.XXXXXX').strip()
    with tv.open_sftp() as s:
        s.put(str(package),stage+'/'+package.name)
        s.put(str(SRC/'scripts/install-local-on-tv.sh'),stage+'/install.sh')
    print(checked('sh '+shlex.quote(stage+'/install.sh')+' '+shlex.quote(stage+'/'+package.name)+' '+digest,60))
finally:tv.close();pve.close()
