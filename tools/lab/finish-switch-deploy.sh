#!/bin/sh
set -eu
pct push 125 /tmp/codex-relay-v3-server-final.py /tmp/codex-relay-v3-server-final.py
pct exec 125 -- sh -c '
set -eu
python3 -m py_compile /tmp/codex-relay-v3-server-final.py
cp -p /opt/lgtv-control/server.py /root/lgtv-relay-v3-backup.Azlrmu/server-before-off-save-finally.py
install -o root -g root -m 0755 /tmp/codex-relay-v3-server-final.py /opt/lgtv-control/server.py
systemctl restart lgtv-control.service
sleep 2
systemctl is-active --quiet lgtv-control.service
python3 - <<"PY"
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8765/api/remote-mapper/runtime", timeout=15) as response:
    value = json.load(response)
assert value["runtime"]["enabled"] is False
assert value["runtime"]["active"] is False
assert value["runtime"]["requestedEnabled"] is False
print("NAS_RESTART_PRESERVED_OFF=PASS")
print(json.dumps(value))
PY
'
