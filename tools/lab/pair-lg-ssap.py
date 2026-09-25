"""Explicitly authorized, attended-by-remote-screen LG pairing on NAS."""
from pathlib import Path
import sys
import shlex
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
import remote
client=remote.connect()
try:
    rc,out,err=remote.run(client,'pve','mktemp -d /tmp/lgtv-ssap-pair.XXXXXX')
    if rc: raise RuntimeError('Could not stage module')
    stage=out.decode().strip()
    with client.open_sftp() as sftp:
        sftp.put(str(ROOT/'lgtv-remote-broker/remote-control/lg_ssap.py'),stage+'/lg_ssap.py')
    rc,out,err=remote.run(client,'pve','pct push 125 '+shlex.quote(stage+'/lg_ssap.py')+' /tmp/lg_ssap.py')
    if rc: raise RuntimeError('Could not upload module')
    rc,out,err=remote.run(client,'ct','install -o root -g root -m 644 /tmp/lg_ssap.py /opt/lgtv-control/lg_ssap.py && runuser -u lgtv-control -- python3 -u /opt/lgtv-control/lg_ssap.py pair --host 192.168.0.240 --credentials /var/lib/lgtv-control/lg-ssap.json --timeout 90',timeout=100)
    sys.stdout.buffer.write(out);sys.stderr.buffer.write(err)
    raise SystemExit(rc)
finally:client.close()
