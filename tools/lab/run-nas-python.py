"""Upload a task-owned diagnostic and execute as the existing NAS service user."""
from pathlib import Path
import shlex,sys
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
import remote
script=Path(sys.argv[1]).resolve()
assert script.is_relative_to(ROOT.resolve()) and script.suffix=='.py'
c=remote.connect()
try:
    rc,out,err=remote.run(c,'pve','mktemp -d /tmp/lgtv-diagnostic.XXXXXX')
    assert rc==0
    stage=out.decode().strip()
    with c.open_sftp() as s:s.put(str(script),stage+'/diagnostic.py')
    destination='/tmp/'+stage.rsplit('/',1)[1]+'.py'
    rc,out,err=remote.run(c,'pve','pct push 125 '+shlex.quote(stage+'/diagnostic.py')+' '+shlex.quote(destination))
    assert rc==0
    rc,out,err=remote.run(c,'ct','chmod 644 '+shlex.quote(destination)+' && runuser -u lgtv-control -- python3 -u '+shlex.quote(destination)+' '+shlex.join(sys.argv[2:]),timeout=100)
    sys.stdout.buffer.write(out);sys.stderr.buffer.write(err)
    raise SystemExit(rc)
finally:c.close()
