"""Deploy NAS pairing/accelerator with rollback copy; leave TV fallback intact."""
from pathlib import Path
import hashlib
import shlex
import sys
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent.parent/'remote-control'
sys.path.insert(0,str(ROOT/'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
import remote

FILES=('server.py','lg_ssap.py','ssap_pairing.py','launcher_early.py',
       'static/index.html','static/ssap-control.js','static/power-control.js','static/launcher-admin.js','static/connections-ui.js','static/dashboard-control.js','lgtv-launcher-early.service')
selected=tuple(sys.argv[1:]) or FILES
assert set(selected) <= set(FILES)
def checked(client,target,command,timeout=45):
    code,out,err=remote.run(client,target,command,timeout=timeout)
    if code: raise RuntimeError(out.decode(errors='replace')+err.decode(errors='replace'))
    return out.decode().strip()

c=remote.connect()
try:
    stage=checked(c,'pve','mktemp -d /tmp/lgtv-native-deploy.XXXXXX')
    backup=checked(c,'ct','mkdir -p /var/backups/lgtv-control && mktemp -d /var/backups/lgtv-control/native-launcher.XXXXXX')
    print('Rollback: '+backup,flush=True)
    with c.open_sftp() as sftp:
        for relative in selected:
            name=relative.replace('/','_')
            sftp.put(str(SOURCE/relative),stage+'/'+name)
    for relative in selected:
        name=relative.replace('/','_')
        temporary='/tmp/'+stage.rsplit('/',1)[-1]+'-'+name
        checked(c,'pve','pct push 125 '+shlex.quote(stage+'/'+name)+' '+shlex.quote(temporary))
        destination='/etc/systemd/system/'+relative if relative.endswith('.service') else '/opt/lgtv-control/'+relative
        checked(c,'ct','if [ -f '+shlex.quote(destination)+' ]; then cp -p '+shlex.quote(destination)+' '+shlex.quote(backup+'/'+name)+'; fi')
        if relative.endswith('.py'): checked(c,'ct','python3 -m py_compile '+shlex.quote(temporary))
        checked(c,'ct','install -o root -g root -m 644 '+shlex.quote(temporary)+' '+shlex.quote(destination))
        digest=checked(c,'ct','sha256sum '+shlex.quote(destination)).split()[0]
        assert digest==hashlib.sha256((SOURCE/relative).read_bytes()).hexdigest()
    checked(c,'ct','systemctl daemon-reload')
    if 'server.py' in selected:
        checked(c,'ct','systemctl restart lgtv-control.service && systemctl is-active lgtv-control.service')
    if 'launcher_early.py' in selected:
        checked(c,'ct','if systemctl is-active --quiet lgtv-launcher-early.service; then systemctl restart lgtv-launcher-early.service; fi')
    print('NAS files deployed; existing service activation preserved.',flush=True)
finally:c.close()
