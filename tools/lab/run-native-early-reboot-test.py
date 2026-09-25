"""One isolated, authorized reboot test with independent TV recovery hook."""
import json
from pathlib import Path
import shlex
import sys
import time
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
sys.path.insert(0,str(ROOT/'lgtv-remote-broker/remote-control'))
import remote
import server
DIR='/var/lib/webosbrew/launcher-home'
BACKUP=DIR+'/enabled.native-probe-backup'
RECOVER=DIR+'/native-probe-recover.sh'
UNTIL=DIR+'/native-probe-until'
HOOK='/var/lib/webosbrew/init.d/zz-launcher-native-probe-recovery'
pve=remote.connect();tv=remote.connect_tv(pve)
inhibited=False;nas_active=False;nas_stopped=False;probe_channel=None;unit=None
reboot_at=None;last_surface=None;next_sample=0;ssh_open=False
def checked(client,target,command,timeout=30):
    code,out,err=remote.run(client,target,command,timeout=timeout)
    if code:raise RuntimeError((out+err).decode(errors='replace'))
    return (out+err).decode(errors='replace').strip()
def luna(client,uri,payload):
    return server.parse_luna_response(checked(client,'pve','luna-send -t 1 -f -w 600 luna://'+uri+' '+shlex.quote(json.dumps(payload))+' 2>&1',3))
try:
    assert luna(tv,'com.webos.service.tvpower/power/getPowerState',{}).get('state')=='Active'
    checked(tv,'pve','test -f '+DIR+'/enabled && test ! -e '+BACKUP+' && test ! -e '+RECOVER+' && test ! -e '+HOOK)
    nas_active=checked(pve,'ct','systemctl is-active lgtv-launcher-early.service')=='active'
    # The TV's normal supported init directory restarts this recovery AFTER
    # reboot; an ordinary background sleep would be killed by reboot instead.
    with tv.open_sftp() as s:
        s.put(str(ROOT/'native-probe-tv-recover.sh'),RECOVER)
        s.put(str(ROOT/'native-probe-tv-recovery-init.sh'),HOOK)
        with s.open(UNTIL,'w') as f:f.write(str(int(time.time())+155))
        s.chmod(RECOVER,0o755);s.chmod(HOOK,0o755)
    checked(tv,'pve','sh -n '+RECOVER+' && sh -n '+HOOK+' && mv '+DIR+'/enabled '+BACKUP)
    inhibited=True
    checked(tv,'pve',server.LauncherHomeManager._stop_guard_command())
    checked(tv,'pve',HOOK)  # recover even if failure occurs before reboot
    checked(pve,'ct','systemctl stop lgtv-launcher-early.service');nas_stopped=True
    # Independent NAS resume as well; the TV recovery above does not depend on NAS.
    unit='lgtv-native-probe-resume-'+str(int(time.time()))
    checked(pve,'ct','systemd-run --quiet --unit='+unit+' --on-active=160s /bin/systemctl start lgtv-launcher-early.service')
    stage=checked(pve,'pve','mktemp -d /tmp/lgtv-early-probe.XXXXXX')
    with pve.open_sftp() as s:s.put(str(ROOT/'probe-native-early-once.py'),stage+'/probe.py')
    remote_script='/tmp/'+stage.rsplit('/',1)[-1]+'.py'
    checked(pve,'pve','pct push 125 '+shlex.quote(stage+'/probe.py')+' '+shlex.quote(remote_script))
    command='chmod 644 '+shlex.quote(remote_script)+' && runuser -u lgtv-control -- python3 -u '+shlex.quote(remote_script)
    stdin,stdout,stderr=pve.exec_command(remote.command('ct',command),timeout=120)
    stdin.channel.shutdown_write();probe_channel=stdout.channel
    buffer='';deadline=time.monotonic()+115
    while time.monotonic()<deadline:
        if probe_channel.recv_ready():
            buffer+=probe_channel.recv(65536).decode(errors='replace')
            while '\n' in buffer:
                line,buffer=buffer.split('\n',1)
                print(line,flush=True)
                try:event=json.loads(line)
                except ValueError:continue
                if event.get('event')=='ready' and reboot_at is None:
                    reboot_at=time.monotonic()
                    print(json.dumps({'event':'reboot-request','epoch':time.time()}),flush=True)
                    cmd='sleep 1; luna-send -t 1 -f -w 3000 luna://com.webos.service.sleep/shutdown/machineReboot '+shlex.quote('{"reason":"remoteKey"}')
                    checked(tv,'pve','nohup sh -c '+shlex.quote(cmd)+' </dev/null >/tmp/hu.szabi.native-probe-reboot.log 2>&1 &')
                    tv.close();tv=None
                if event.get('event')=='port' and event.get('port')==22:
                    ssh_open=event.get('opened') is True
        if probe_channel.recv_stderr_ready():
            # Probe emits no credentials; stderr is only a Python diagnostic.
            print(probe_channel.recv_stderr(16384).decode(errors='replace'),flush=True)
        if reboot_at and ssh_open and time.monotonic()>=next_sample:
            next_sample=time.monotonic()+1
            try:
                if tv is None:tv=remote.connect_tv(pve)
                surface=luna(tv,'com.webos.surfacemanager/getForegroundWindowInfo',{})
                if surface!=last_surface:
                    print(json.dumps({'event':'native-surface','afterRebootRequest':round(time.monotonic()-reboot_at,3),'surface':surface}),flush=True)
                    last_surface=surface
            except Exception as error:
                print(json.dumps({'event':'root-not-ready','error':type(error).__name__}),flush=True)
                if tv:tv.close();tv=None
                next_sample=time.monotonic()+1
        if probe_channel.exit_status_ready() and not probe_channel.recv_ready():
            print(json.dumps({'event':'probe-exit','code':probe_channel.recv_exit_status()}),flush=True)
            break
        time.sleep(.05)
finally:
    if probe_channel:probe_channel.close()
    if tv:tv.close()
    restored=False
    if inhibited:
        for attempt in range(6):
            try:
                checked(pve,'tv','sh '+RECOVER+' && test -f '+DIR+'/enabled',15)
                restored=True
                break
            except Exception:
                time.sleep(2)
        if restored:
            checked(pve,'tv','test ! -e '+BACKUP+' && rm -f '+HOOK+' '+RECOVER+' '+UNTIL)
            print(json.dumps({'event':'tv-fallback-restored'}),flush=True)
        else:print(json.dumps({'event':'restore-pending-independent-tv-recovery-active'}),flush=True)
    if nas_stopped and nas_active:
        checked(pve,'ct','systemctl start lgtv-launcher-early.service && systemctl is-active lgtv-launcher-early.service')
        print(json.dumps({'event':'nas-accelerator-restored'}),flush=True)
        if unit:checked(pve,'ct','systemctl stop '+unit+'.timer')
    pve.close()
