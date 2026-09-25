"""Deploy the verified wake lifecycle fix, preserving rollback files on both hosts."""
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'lgtv-remote-broker/remote-control'
sys.path.insert(0, str(ROOT / 'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
sys.path.insert(0, str(SOURCE))
import remote
import server

def checked(client, target, command, timeout=30):
    code, out, err = remote.run(client, target, command, timeout=timeout)
    if code: raise RuntimeError('Remote operation failed: ' + out.decode(errors='replace') + err.decode(errors='replace'))
    return out.decode()

pve = remote.connect()
try:
    tv = remote.connect_tv(pve)
    try:
        backup = checked(pve, 'ct', 'mkdir -p /var/backups/lgtv-control; mktemp -d /var/backups/lgtv-control/wake-20260921.XXXXXX').strip()
        checked(pve, 'ct', 'cp -p /opt/lgtv-control/server.py ' + backup + '/server.py; cp -p /opt/lgtv-control/static/broker-control.js ' + backup + '/broker-control.js')
        tv_backup = checked(tv, 'pve', 'mktemp -d /var/lib/webosbrew/wake-backup-20260921.XXXXXX').strip()
        checked(tv, 'pve', 'cp -p /var/lib/webosbrew/launcher-home/guard.sh /var/lib/webosbrew/launcher-home/prewarm.sh /var/lib/webosbrew/remote-broker/supervisor.sh ' + tv_backup + '; if [ -f /var/lib/webosbrew/remote-broker/disabled-reason ]; then cp -p /var/lib/webosbrew/remote-broker/disabled-reason ' + tv_backup + '; fi')
        print('CT backup=' + backup, flush=True)
        print('TV backup=' + tv_backup, flush=True)
        stage = checked(pve, 'pve', 'mktemp -d /tmp/lgtv-wake-deploy-20260921.XXXXXX').strip()
        with pve.open_sftp() as sftp:
            sftp.put(str(SOURCE / 'server.py'), stage + '/server.py')
            sftp.put(str(SOURCE / 'static/broker-control.js'), stage + '/broker-control.js')
        for filename in ('server.py', 'broker-control.js'):
            checked(pve, 'pve', 'pct push 125 ' + stage + '/' + filename + ' /tmp/wake-20260921-' + filename)
        checked(pve, 'ct', 'python3 -m py_compile /tmp/wake-20260921-server.py')
        checked(pve, 'ct', 'install -o root -g root -m 644 /tmp/wake-20260921-server.py /opt/lgtv-control/server.py && install -o root -g root -m 644 /tmp/wake-20260921-broker-control.js /opt/lgtv-control/static/broker-control.js && systemctl restart lgtv-control.service')
        expected = hashlib.sha256(server.LauncherHomeManager.GUARD_SCRIPT.encode()).hexdigest()
        for attempt in range(30):
            digest = checked(tv, 'pve', 'sha256sum /var/lib/webosbrew/launcher-home/guard.sh').split()[0]
            if digest == expected: break
            time.sleep(1)
        else: raise RuntimeError('The NAS did not synchronize the new guard')
        expected = hashlib.sha256(server.LauncherHomeManager.PREWARM_SCRIPT.encode()).hexdigest()
        for attempt in range(30):
            digest = checked(tv, 'pve', 'sha256sum /var/lib/webosbrew/launcher-home/prewarm.sh').split()[0]
            if digest == expected: break
            time.sleep(1)
        else: raise RuntimeError('The NAS did not synchronize the new preload script')
        # The old fault is preserved above. Explicitly re-enable the user's
        # saved binding map once the power-aware supervisor is installed.
        request = urllib.request.Request('http://192.168.0.223:8765/api/remote-mapper/runtime',
            data=b'{"enabled":true}', headers={'Content-Type':'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=45) as response:
            runtime = json.load(response)
        assert runtime['runtime']['active'] is True, runtime
        print(json.dumps(runtime, ensure_ascii=False), flush=True)
        checked(tv, 'pve', server.LauncherHomeManager._stop_guard_command())
        time.sleep(1)
        checked(tv, 'pve', '/var/lib/webosbrew/init.d/launcher-home </dev/null >/dev/null 2>&1')
        checked(pve, 'ct', 'systemctl is-active lgtv-control.service')
        print('DEPLOYED', flush=True)
    finally:
        tv.close()
finally:
    pve.close()
