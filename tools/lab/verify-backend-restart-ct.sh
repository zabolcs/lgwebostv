#!/bin/sh
set -eu

systemctl restart lgtv-control.service
ready=0
i=0
while [ "$i" -lt 15 ]; do
  i=$((i + 1))
  sleep 2
  if python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen('http://127.0.0.1:8765/api/remote-mapper/state', timeout=10) as response:
    data = json.load(response)
runtime = data.get('runtime') or {}
print(json.dumps(runtime, separators=(',', ':'), sort_keys=True))
assert runtime.get('enabled') is True
assert runtime.get('active') is True
assert runtime.get('mode') == 'grab'
assert runtime.get('nativeHookLoaded') is False
PY
  then
    ready=1
    break
  fi
done

[ "$ready" = 1 ]
systemctl is-active --quiet lgtv-control.service
python3 - <<'PY'
import json
path = '/etc/lgtv-control/config.json'
with open(path, encoding='utf-8') as handle:
    config = json.load(handle)
assert config['remote_broker_enabled'] is True
assert config['remote_broker_mode'] == 'grab'
assert config['input_hook_watchdog_enabled'] is False
print('persistent-config=PASS')
PY
