set -eu
pct push 125 /tmp/codex-lgtv-server-hotfix.py /tmp/codex-lgtv-server-hotfix.py
pct exec 125 -- sh -c '
set -eu
cp -p /opt/lgtv-control/server.py /opt/lgtv-control/server.py.before-broker-active-wait-20260920
python3 -m py_compile /tmp/codex-lgtv-server-hotfix.py
systemctl stop lgtv-control.service
install -o root -g root -m 0755 /tmp/codex-lgtv-server-hotfix.py /opt/lgtv-control/server.py
if ! systemctl start lgtv-control.service; then
  cp -p /opt/lgtv-control/server.py.before-broker-active-wait-20260920 /opt/lgtv-control/server.py
  systemctl start lgtv-control.service
  exit 1
fi
sleep 3
systemctl is-active --quiet lgtv-control.service
python3 -c "import json,urllib.request; d=json.load(urllib.request.urlopen(\"http://127.0.0.1:8765/api/health\",timeout=5)); assert d.get(\"ok\") is True; print(d)"
'
echo 'server hotfix PASS'
