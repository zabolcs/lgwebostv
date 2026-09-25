#!/bin/sh
set -eu
pct push 125 /tmp/codex-relay-v3-switch.tar /tmp/codex-relay-v3-switch.tar
pct exec 125 -- sh -c '
set -eu
stage=$(mktemp -d /tmp/codex-relay-v3-stage.XXXXXX)
tar -xf /tmp/codex-relay-v3-switch.tar -C "$stage"
python3 "$stage/remote-control/tests/test_broker_switch.py" -v
python3 "$stage/remote-control/tests/test_broker_supervisor.py" -v
echo DEPLOY_DIFF_SUMMARY
diff -u /opt/lgtv-control/server.py "$stage/remote-control/server.py" | head -n 50 || true
backup=$(mktemp -d /root/lgtv-relay-v3-backup.XXXXXX)
cp -p /opt/lgtv-control/server.py "$backup/server.py"
cp -p /opt/lgtv-control/static/index.html "$backup/index.html"
cp -p /etc/lgtv-control/config.json "$backup/config.json"
echo "BACKUP=$backup"
scp -q -i /etc/lgtv-control/id_rsa -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/lgtv-control/known_hosts "$stage/remote-broker/remote-broker" root@192.168.0.240:/tmp/codex-relay-v3-install
ssh -T -i /etc/lgtv-control/id_rsa -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/lgtv-control/known_hosts root@192.168.0.240 sh -s -- /tmp/codex-relay-v3-install 118ed0689258db89f9fb2454fa1d8e3ba5873d22e2c0832655b790c6264b24aa <"$stage/remote-broker/install-on-tv.sh"
python3 -m py_compile "$stage/remote-control/server.py"
systemctl stop lgtv-control.service
install -o root -g root -m 0755 "$stage/remote-control/server.py" /opt/lgtv-control/server.py
install -o root -g root -m 0644 "$stage/remote-control/static/index.html" /opt/lgtv-control/static/index.html
install -o root -g root -m 0644 "$stage/remote-control/static/broker-control.js" /opt/lgtv-control/static/broker-control.js
if ! systemctl start lgtv-control.service; then
  cp -p "$backup/server.py" /opt/lgtv-control/server.py
  cp -p "$backup/index.html" /opt/lgtv-control/static/index.html
  systemctl start lgtv-control.service
  exit 1
fi
sleep 3
systemctl is-active --quiet lgtv-control.service
python3 -c "import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8765/api/remote-mapper/runtime\").read().decode())"
echo
echo SWITCH_INSTALLED_DISABLED
'
