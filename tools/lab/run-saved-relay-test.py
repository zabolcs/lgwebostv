from pathlib import Path
import json
import sys
import urllib.request
sys.path.insert(0, str(Path(__file__).parent / 'checkpoint-original' / 'LGTV-checkpoint-2026-09-19' / 'tools'))
import remote

def switch(enabled):
    request = urllib.request.Request('http://192.168.0.223:8765/api/remote-mapper/runtime',
        data=json.dumps({'enabled': enabled}).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
    print(json.dumps(result, ensure_ascii=True), flush=True)
    return result

pve = remote.connect()
tv = None
try:
    tv = remote.connect_tv(pve)
    script = Path(__file__).with_name('relay-saved-test-guard.sh').read_text(encoding='utf-8')
    inp, out, err = tv.exec_command(script, timeout=100)
    inp.channel.shutdown_write()
    assert out.readline().strip() == 'GUARD_ARMED'
    print('SAFETY_GUARD_ARMED', flush=True)
    active = switch(True)['runtime']
    assert active['active'] and active['enabled']
    print('SAVED_BINDINGS_ACTIVE_NOW: test Google Assistant -> camera PiP; timeout 60s', flush=True)
    for line in out: print(line.rstrip(), flush=True)
    print(err.read().decode(), file=sys.stderr, flush=True)
finally:
    try: switch(False)
    finally:
        if tv: tv.close()
        pve.close()
