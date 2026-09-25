#!/bin/sh
set -eu
CONFIG=/etc/lgtv-control/config.json
BACKUP=/etc/lgtv-control/config.before-remote-broker-20260920-0035.json
test ! -e "$BACKUP"
cp -p "$CONFIG" "$BACKUP"

rollback() {
  echo 'Broker aktiválása sikertelen; CT konfiguráció visszaállítása.' >&2
  cp -p "$BACKUP" "$CONFIG"
  systemctl restart lgtv-control.service || true
}

python3 - <<'PY'
import json, os
path='/etc/lgtv-control/config.json'
with open(path, encoding='utf-8') as handle:
    config=json.load(handle)
config['input_hook_watchdog_enabled']=False
config['remote_broker_enabled']=True
config['remote_broker_mode']='grab'
temporary=path+'.new'
with open(temporary, 'w', encoding='utf-8') as handle:
    json.dump(config, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write('\n')
os.chmod(temporary, 0o640)
os.replace(temporary, path)
PY
chown root:lgtv-control "$CONFIG"
chmod 0640 "$CONFIG"

if ! systemctl restart lgtv-control.service; then rollback; exit 1; fi
ready=0
attempt=0
while [ "$attempt" -lt 12 ]; do
  attempt=$((attempt + 1))
  sleep 3
  if python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8765/api/remote-mapper/state', timeout=15) as response:
    data=json.load(response)
runtime=data.get('runtime') or {}
print(json.dumps(runtime, separators=(',',':')))
assert runtime.get('active') is True
assert runtime.get('enabled') is True
assert runtime.get('mode') == 'grab'
assert runtime.get('nativeHookLoaded') is False
PY
  then ready=1; break; fi
done

if [ "$ready" != 1 ]; then
  rollback
  exit 1
fi

systemctl is-active --quiet lgtv-control.service
echo "Remote Broker activation PASS; config backup=$BACKUP"
