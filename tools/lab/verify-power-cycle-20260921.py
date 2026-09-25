"""One explicitly authorized standby or OS reboot cycle, with bounded observations."""
import json
from pathlib import Path
import shlex
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
sys.path.insert(0, str(ROOT / 'lgtv-remote-broker/remote-control'))
import remote
import server

mode = sys.argv[1]
if mode not in {'standby', 'reboot'}: raise ValueError(mode)

def api(path, body=None):
    request = urllib.request.Request('http://192.168.0.223:8765' + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response: return json.load(response)

def call(client, command, timeout=10):
    code, out, err = remote.run(client, 'tv', command, timeout=timeout)
    if code: raise RuntimeError('TV unreachable or command failed: ' + str(code))
    return (out + err).decode(errors='replace')

def luna(client, method):
    return server.parse_luna_response(call(client, 'luna-send -t 1 -f -w 1500 luna://' + method + " '{}'"))

client = remote.connect()
try:
    before_boot = call(client, 'cat /proc/sys/kernel/random/boot_id').strip()
    assert api('/api/remote-mapper/runtime')['runtime']['active']
    print(json.dumps({'mode':mode,'beforeBoot':before_boot}), flush=True)
    if mode == 'standby':
        print(json.dumps(api('/api/tv/power', {'state':'off'})), flush=True)
        for _ in range(20):
            time.sleep(1)
            if api('/api/tv/power')['power']['state'] == 'off': break
        else: raise RuntimeError('TV did not reach standby; no repeated off request was sent')
        try:
            print('standby_runtime=' + json.dumps(api('/api/remote-mapper/runtime')), flush=True)
        except Exception as error:
            print('standby_runtime_unreachable=' + type(error).__name__, flush=True)
        time.sleep(8)
        started = time.monotonic()
        print(json.dumps(api('/api/tv/power', {'state':'on'})), flush=True)
    else:
        started = time.monotonic()
        try:
            command = 'nohup sh -c ' + shlex.quote('sleep 1; luna-send -t 1 -f -w 3000 luna://com.webos.service.sleep/shutdown/machineReboot \'{"reason":"remoteKey"}\'') + ' </dev/null >/tmp/hu.szabi.reboot-test.log 2>&1 &'
            call(client, command)
        except Exception as error:
            print('reboot_transport=' + type(error).__name__, flush=True)
        print('One OS reboot requested', flush=True)
        time.sleep(5)

    deadline = started + 150
    first_active = first_broker = first_launcher = None
    stable_since = None
    after_boot = None
    last = None
    while time.monotonic() < deadline:
        elapsed = round(time.monotonic() - started, 2)
        sample = {'seconds': elapsed}
        try:
            after_boot = call(client, 'cat /proc/sys/kernel/random/boot_id', timeout=8).strip()
            power = luna(client, 'com.webos.service.tvpower/power/getPowerState').get('state')
            runtime = api('/api/remote-mapper/runtime')['runtime']
            windows = luna(client, 'com.webos.surfacemanager/getForegroundWindowInfo')
            visible = [row.get('appId') for row in windows.get('foreground', windows.get('windows', [])) if isinstance(row, dict)]
            if not visible:
                def ids(value):
                    if isinstance(value, dict):
                        if 'appId' in value: yield value['appId']
                        for item in value.values(): yield from ids(item)
                    elif isinstance(value, list):
                        for item in value: yield from ids(item)
                visible = list(ids(windows))
            elapsed = round(time.monotonic() - started, 2)
            sample.update(seconds=elapsed, power=power, broker=runtime['active'], enabled=runtime['enabled'], lifecycle=runtime.get('lifecycle'), windows=visible, bootChanged=after_boot != before_boot)
            valid_boot = mode == 'standby' or after_boot != before_boot
            if power == 'Active' and valid_boot:
                if first_active is None: first_active = elapsed
                if runtime['active']:
                    if first_broker is None: first_broker = elapsed
                if any(str(item).startswith('hu.szabi.launcher') for item in visible):
                    if first_launcher is None: first_launcher = elapsed
                if runtime['active'] and runtime['enabled']:
                    if stable_since is None: stable_since = time.monotonic()
                else: stable_since = None
            if sample != last:
                print(json.dumps(sample), flush=True)
                last = sample
            if stable_since is not None and time.monotonic() - stable_since >= 20 and first_launcher is not None: break
            if stable_since is not None and time.monotonic() - stable_since >= 40: break
        except Exception as error:
            sample['unreachable'] = type(error).__name__
            stable_since = None
            print(json.dumps(sample), flush=True)
        time.sleep(1)
    print('result=' + json.dumps({'mode':mode,'activeObservedSeconds':first_active,'brokerObservedSeconds':first_broker,'launcherObservedSeconds':first_launcher,'bootChanged':after_boot != before_boot,'brokerStable':stable_since is not None and time.monotonic()-stable_since>=20}), flush=True)
    print(call(client, 'tail -n 40 /tmp/hu.szabi.remote-broker.log; tail -n 35 /tmp/hu.szabi.launcher-wake.log; cat /var/lib/webosbrew/remote-broker/disabled-reason 2>/dev/null || true'), flush=True)
    assert first_broker is not None and stable_since is not None
    if mode == 'reboot': assert after_boot != before_boot
finally:
    client.close()
