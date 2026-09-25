"""Install only launcher packages with rollback; do not touch the input broker."""
import importlib.util
import json
from pathlib import Path
import shlex
import sys
import time

ROOT = Path(__file__).parent
SRC = ROOT / 'lgtv-remote-broker'
sys.path.insert(0, str(ROOT / 'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
import remote
spec = importlib.util.spec_from_file_location('builder', SRC / 'scripts/build-all.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

def checked(tv, cmd, timeout=45):
    rc,out,err=remote.run(tv,'pve',cmd,timeout=timeout)
    if rc: raise RuntimeError((out+err).decode(errors='replace'))
    return (out+err).decode(errors='replace')

slugs = sys.argv[1:] or ['launcher','launcher-quick','launcher-overlay']
assert all(slug in ('launcher','launcher-quick','launcher-overlay') for slug in slugs)
packages = [builder.build(slug, builder.APPS[slug]) for slug in slugs]
pve=remote.connect()
tv=remote.connect_tv(pve)
try:
    backup=checked(tv,'mktemp -d /var/lib/webosbrew/launcher-v039-backup.XXXXXX').strip()
    print('rollback=' + backup,flush=True)
    checked(tv,'tar -czf ' + shlex.quote(backup+'/apps.tgz') + ' -C /media/developer/apps/usr/palm/applications hu.szabi.launcher hu.szabi.launcher.quick hu.szabi.launcher.overlay')
    stage=checked(tv,'mktemp -d /tmp/launcher-v039.XXXXXX').strip()
    old_versions = {}
    for slug in slugs:
        app = builder.APPS[slug]['id']
        old_versions[app] = json.loads(checked(tv,'cat /media/developer/apps/usr/palm/applications/'+app+'/appinfo.json'))['version']
    with tv.open_sftp() as sftp:
        sftp.put(str(SRC/'scripts/install-local-on-tv.sh'),stage+'/install.sh')
        for pkg,digest in packages:
            sftp.put(str(pkg),stage+'/'+pkg.name)
            app = pkg.name.split('_')[0]
            old=SRC/'build'/(app+'_'+old_versions[app]+'_all.ipk')
            if old.is_file(): sftp.put(str(old),backup+'/'+old.name)
    for pkg,digest in packages:
        print(checked(tv,'sh '+shlex.quote(stage+'/install.sh')+' '+shlex.quote(stage+'/'+pkg.name)+' '+digest,timeout=60),flush=True)
    # Verify actual bundle, not only asynchronous install acknowledgement.
    expected=b';\n'.join((SRC/'apps/launcher'/name).read_bytes() for name in ('launcher-cache.js','launcher-quick-core.js','launcher-popup-lifecycle.js','launcher-ui.js','app.js'))
    import hashlib
    digest=hashlib.sha256(expected).hexdigest()
    for app in (builder.APPS[slug]['id'] for slug in slugs):
        path='/media/developer/apps/usr/palm/applications/'+app+'/launcher-runtime.js'
        actual=checked(tv,'sha256sum '+path).split()[0]
        assert actual == digest, (app,actual,digest)
    print('Selected launcher bundles verified; broker untouched.',flush=True)
finally:
    tv.close()
    pve.close()
