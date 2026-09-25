#!/bin/sh
set -eu

SOURCE=/tmp/codex-lgtv-stage/lgtv-remote-broker
BACKUP=/root/lgtv-control-before-remote-broker-20260919-2218.tar.gz
SUCCESS=0

rollback() {
  [ "$SUCCESS" = 1 ] && return 0
  echo "CT frissítés sikertelen, automatikus visszaállítás." >&2
  if [ -f "$BACKUP" ]; then
    tar -xzf "$BACKUP" -C /
    systemctl daemon-reload || true
    systemctl restart lgtv-control.service || true
  fi
}
trap rollback EXIT HUP INT TERM

test -f "$SOURCE/remote-control/server.py"
test -f "$SOURCE/apps/remote-mapper/remote-ui.js"
test -f "$SOURCE/apps/launcher/launcher-ui.js"
test -f /etc/lgtv-control/config.json

tar -czf "$BACKUP" \
  /opt/lgtv-control \
  /etc/lgtv-control/config.json \
  /etc/systemd/system/lgtv-control.service \
  /var/lib/lgtv-control

systemctl stop lgtv-control.service
install -d -o root -g root -m 0755 /opt/lgtv-control /opt/lgtv-control/static
install -o root -g root -m 0755 "$SOURCE/remote-control/server.py" /opt/lgtv-control/server.py
install -o root -g root -m 0644 "$SOURCE/remote-control/static/index.html" /opt/lgtv-control/static/index.html
install -o root -g root -m 0644 "$SOURCE/apps/remote-mapper/remote-ui.js" /opt/lgtv-control/static/remote-ui.js
install -o root -g root -m 0644 "$SOURCE/apps/remote-mapper/remote-ui.css" /opt/lgtv-control/static/remote-ui.css
install -o root -g root -m 0644 "$SOURCE/remote-control/static/connections-ui.js" /opt/lgtv-control/static/connections-ui.js
install -o root -g root -m 0644 "$SOURCE/remote-control/static/launcher-admin.js" /opt/lgtv-control/static/launcher-admin.js
install -o root -g root -m 0644 "$SOURCE/apps/launcher/launcher-ui.js" /opt/lgtv-control/static/launcher-ui.js
install -o root -g root -m 0644 "$SOURCE/apps/launcher/launcher.css" /opt/lgtv-control/static/launcher.css
install -o root -g root -m 0644 "$SOURCE/remote-control/lgtv-control.service" /etc/systemd/system/lgtv-control.service

python3 - <<'PY'
import json, os
path='/etc/lgtv-control/config.json'
with open(path, encoding='utf-8') as handle:
    config=json.load(handle)
config['input_hook_watchdog_enabled']=False
config['remote_broker_enabled']=False
config['remote_broker_mode']='passive'
temporary=path+'.new'
with open(temporary, 'w', encoding='utf-8') as handle:
    json.dump(config, handle, ensure_ascii=False, indent=2, sort_keys=True)
    handle.write('\n')
os.chmod(temporary, 0o640)
os.replace(temporary, path)
PY

chown root:lgtv-control /etc/lgtv-control/config.json
chmod 0640 /etc/lgtv-control/config.json
python3 -m py_compile /opt/lgtv-control/server.py
systemctl daemon-reload
systemctl start lgtv-control.service
sleep 3
systemctl is-active --quiet lgtv-control.service
python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=5) as response:
    payload=json.load(response)
assert payload.get('ok') is True, payload
print(json.dumps(payload, separators=(',', ':')))
PY

SUCCESS=1
trap - EXIT HUP INT TERM
echo "CT update PASS; backup=$BACKUP"
