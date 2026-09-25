#!/bin/sh
set -eu

HASH=330fbd8909b0de67aaeb1f5715812570b6fdcc309df25589fb1b48b9b164f203
printf '%s  %s\n' "$HASH" /tmp/codex-remote-broker-v2 | sha256sum -c -

pct push 125 /tmp/codex-lgtv-server-v2.py /tmp/codex-lgtv-server-v2.py
pct push 125 /tmp/codex-remote-broker-v2 /tmp/codex-remote-broker-v2
pct push 125 /tmp/codex-install-remote-broker-v2.sh /tmp/codex-install-remote-broker-v2.sh

pct exec 125 -- sh -c '
set -eu
BACKUP=/opt/lgtv-control/server.py.before-single-source-broker-20260920
test ! -e "$BACKUP"
cp -p /opt/lgtv-control/server.py "$BACKUP"
python3 -m py_compile /tmp/codex-lgtv-server-v2.py
systemctl stop lgtv-control.service
install -o root -g root -m 0755 /tmp/codex-lgtv-server-v2.py /opt/lgtv-control/server.py
if ! systemctl start lgtv-control.service; then
  cp -p "$BACKUP" /opt/lgtv-control/server.py
  systemctl start lgtv-control.service
  exit 1
fi
sleep 3
systemctl is-active --quiet lgtv-control.service
python3 - <<"PY"
import json, urllib.request
with open("/etc/lgtv-control/config.json", encoding="utf-8") as handle:
    config = json.load(handle)
assert config["remote_broker_enabled"] is False
assert config["remote_broker_mode"] == "passive"
with urllib.request.urlopen("http://127.0.0.1:8765/api/health", timeout=5) as response:
    assert json.load(response).get("ok") is True
print("backend-disabled-health=PASS")
PY
scp -q -i /etc/lgtv-control/id_rsa -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/lgtv-control/known_hosts /tmp/codex-remote-broker-v2 /tmp/codex-install-remote-broker-v2.sh root@192.168.0.240:/tmp/
'
echo 'backend-and-transfer=PASS'
