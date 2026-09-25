"""One authorized power cycle; sample actual surfaces, not launch acknowledgements."""
import concurrent.futures
import json
from pathlib import Path
import shlex
import socket
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
sys.path.insert(0, str(ROOT / 'lgtv-remote-broker/remote-control'))
import remote
import server

def api(path, body=None):
    req = urllib.request.Request('http://192.168.0.223:8765' + path,
        data=None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response: return json.load(response)

SAMPLE = """date +%s; cat /proc/uptime
luna-send -t 1 -f -w 600 luna://com.webos.service.tvpower/power/getPowerState '{}' 2>&1
luna-send -t 1 -f -w 600 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>&1
"""

def call(tv, cmd):
    rc, out, err = remote.run(tv, 'pve', cmd, timeout=5)
    if rc: raise RuntimeError(rc)
    return (out + err).decode(errors='replace')

def sample(tv):
    lines = call(tv, SAMPLE).splitlines()
    raw = '\n'.join(lines)
    payloads = [json.JSONDecoder().raw_decode(part.lstrip())[0] for part in raw.split('payload ')[1:]]
    power = next((p['state'] for p in payloads if 'state' in p), None)
    windows = next((p for p in payloads if 'foreground' in p or 'windows' in p), {})
    return {'tvEpoch':lines[0], 'uptime':float(lines[1].split()[0]), 'power':power, 'windows':windows}

def pages():
    try:
        with urllib.request.urlopen('http://192.168.0.240:9998/json', timeout=.4) as r:
            return [{'id':p['id'], 'url':p['url']} for p in json.load(r) if '/hu.szabi.launcher/' in p.get('url','')]
    except Exception: return []

mode = sys.argv[1]
assert mode in {'standby', 'reboot', 'observe'}
pve = remote.connect()
tv = remote.connect_tv(pve)
records = []
started = time.monotonic()
stop_ports = threading.Event()
def observe_ports():
    previous = {}
    while not stop_ports.is_set():
        for port in (3000, 22):
            try:
                with socket.create_connection(('192.168.0.240',port), timeout=.25): pass
                state = True
            except OSError: state = False
            if previous.get(port) != state:
                print(json.dumps({'port':port,'open':state,'seconds':round(time.monotonic()-started,3)}),flush=True)
                previous[port]=state
        stop_ports.wait(.3)
port_thread = None
try:
    before = sample(tv)
    print(json.dumps({'before':before, 'broker':api('/api/remote-mapper/runtime')['runtime']}), flush=True)
    if mode == 'standby':
        print(json.dumps(api('/api/tv/power', {'state':'off'})), flush=True)
        for _ in range(20):
            time.sleep(.5)
            if api('/api/tv/power')['power']['state'] == 'off': break
        else: raise RuntimeError('Did not reach standby')
        time.sleep(float(sys.argv[2]) if len(sys.argv)>2 else 5)
        started = time.monotonic()
        print(json.dumps(api('/api/tv/power', {'state':'on'})), flush=True)
    elif mode == 'reboot':
        reboot = 'sleep 1; luna-send -t 1 -f -w 3000 luna://com.webos.service.sleep/shutdown/machineReboot ' + shlex.quote('{"reason":"remoteKey"}')
        call(tv, 'nohup sh -c ' + shlex.quote(reboot) + ' </dev/null >/tmp/hu.szabi.launcher-measure-reboot.log 2>&1 &')
        started = time.monotonic()
        port_thread=threading.Thread(target=observe_ports,daemon=True)
        port_thread.start()
    deadline = started + (100 if mode == 'reboot' else 50)
    last_key = None
    last_output = 0
    while time.monotonic() < deadline:
        try:
            if tv is None: tv = remote.connect_tv(pve)
            row = sample(tv)
            row.update(seconds=round(time.monotonic()-started,3), pages=pages())
            records.append(row)
            key = (row['power'], row['windows'], row['pages'])
            if key != last_key or time.monotonic() - last_output > 5:
                print(json.dumps(row), flush=True)
                last_key, last_output = key, time.monotonic()
        except Exception as exc:
            if tv: tv.close()
            tv = None
            print(json.dumps({'seconds':round(time.monotonic()-started,3),'unreachable':type(exc).__name__}),flush=True)
            time.sleep(.5)
        time.sleep(.35)
    if tv:
        print(call(tv, 'tail -n 60 /tmp/hu.szabi.launcher-wake.log; grep -E "foregroundAppId|SIGNAL_minimal|SIGNAL_boot-done" /var/log/bootd.log | tail -n 15'),flush=True)
    print(json.dumps({'brokerAfter':api('/api/remote-mapper/runtime')['runtime']}),flush=True)
finally:
    stop_ports.set()
    if port_thread: port_thread.join(timeout=2)
    if tv: tv.close()
    pve.close()
