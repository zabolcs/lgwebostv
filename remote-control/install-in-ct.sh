#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Ezt a telepítőt rootként kell futtatni a lgtv-control CT-ben." >&2
  exit 2
fi
if [ "$#" -ne 2 ]; then
  echo "Használat: $0 /abszolut/ut/id_rsa TV_PRIVAT_IPV4" >&2
  exit 2
fi

SOURCE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
TV_KEY=$1
TV_HOST=$2
case "$TV_KEY" in /*) ;; *) echo "A TV-kulcs útvonala abszolút legyen." >&2; exit 2 ;; esac
test -f "$TV_KEY" || { echo "A TV-kulcs nem található: $TV_KEY" >&2; exit 2; }
test -f "$SOURCE/server.py" || { echo "Hiányzó server.py" >&2; exit 2; }
test -f "$SOURCE/static/index.html" || { echo "Hiányzó static/index.html" >&2; exit 2; }
REMOTE_UI="$SOURCE/../apps/remote-mapper"
LAUNCHER_UI="$SOURCE/../apps/launcher"
test -f "$REMOTE_UI/remote-ui.js" || { echo "Hiányzó remote-ui.js" >&2; exit 2; }
test -f "$REMOTE_UI/remote-ui.css" || { echo "Hiányzó remote-ui.css" >&2; exit 2; }
test -f "$LAUNCHER_UI/launcher-ui.js" || { echo "Hiányzó launcher-ui.js" >&2; exit 2; }
test -f "$LAUNCHER_UI/launcher.css" || { echo "Hiányzó launcher.css" >&2; exit 2; }

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3 openssh-client ca-certificates

if ! getent passwd lgtv-control >/dev/null 2>&1; then
  useradd --system --home-dir /nonexistent --shell /usr/sbin/nologin lgtv-control
fi
install -d -o root -g root -m 0755 /opt/lgtv-control /opt/lgtv-control/static
install -d -o root -g lgtv-control -m 0750 /etc/lgtv-control
install -d -o lgtv-control -g lgtv-control -m 0750 /var/lib/lgtv-control
install -o root -g root -m 0755 "$SOURCE/server.py" /opt/lgtv-control/server.py
install -o root -g root -m 0644 "$SOURCE/static/index.html" /opt/lgtv-control/static/index.html
install -o root -g root -m 0644 "$SOURCE/static/broker-control.js" /opt/lgtv-control/static/broker-control.js
install -o root -g root -m 0644 "$REMOTE_UI/remote-ui.js" /opt/lgtv-control/static/remote-ui.js
install -o root -g root -m 0644 "$REMOTE_UI/remote-ui.css" /opt/lgtv-control/static/remote-ui.css
install -o root -g root -m 0644 "$SOURCE/static/connections-ui.js" /opt/lgtv-control/static/connections-ui.js
install -o root -g root -m 0644 "$SOURCE/static/launcher-admin.js" /opt/lgtv-control/static/launcher-admin.js
install -o root -g root -m 0644 "$LAUNCHER_UI/launcher-ui.js" /opt/lgtv-control/static/launcher-ui.js
install -o root -g root -m 0644 "$LAUNCHER_UI/launcher.css" /opt/lgtv-control/static/launcher.css
install -o lgtv-control -g lgtv-control -m 0600 "$TV_KEY" /etc/lgtv-control/id_rsa

KNOWN_TMP=/etc/lgtv-control/known_hosts.new
rm -f "$KNOWN_TMP"
ssh-keyscan -T 5 -H "$TV_HOST" >"$KNOWN_TMP" 2>/dev/null
test -s "$KNOWN_TMP" || { rm -f "$KNOWN_TMP"; echo "A TV SSH hostkulcsa nem kérhető le." >&2; exit 3; }
chown lgtv-control:lgtv-control "$KNOWN_TMP"
chmod 0600 "$KNOWN_TMP"
mv -f "$KNOWN_TMP" /etc/lgtv-control/known_hosts

umask 077
printf '%s\n' \
  '{' \
  '  "listen_host": "0.0.0.0",' \
  '  "listen_port": 8765,' \
  "  \"public_base_url\": \"http://$(hostname -I | awk '{print $1}'):8765\"," \
  '  "state_path": "/var/lib/lgtv-control/state.json",' \
  '  "connection_state_path": "/var/lib/lgtv-control/connections.json",' \
  '  "launcher_state_path": "/var/lib/lgtv-control/launcher.json",' \
  '  "launcher_apps_state_path": "/var/lib/lgtv-control/launcher-apps.json",' \
  '  "input_hook_watchdog_enabled": false,' \
  '  "remote_broker_enabled": false,' \
  '  "remote_broker_mode": "passive",' \
  '  "allowed_networks": ["127.0.0.0/8", "192.168.0.0/24"],' \
  "  \"tv_host\": \"$TV_HOST\"," \
  '  "tv_wifi_mac": "64:cb:e9:08:47:c6",' \
  '  "tv_wake_broadcasts": ["192.168.0.255"],' \
  '  "tv_user": "root",' \
  '  "ssh_key": "/etc/lgtv-control/id_rsa",' \
  '  "known_hosts": "/etc/lgtv-control/known_hosts",' \
  '  "ssh_timeout_seconds": 12' \
  '}' > /etc/lgtv-control/config.json
chown root:lgtv-control /etc/lgtv-control/config.json
chmod 0640 /etc/lgtv-control/config.json
rm -f /root/lgtv-control-access-token.txt

install -o root -g root -m 0644 "$SOURCE/lgtv-control.service" /etc/systemd/system/lgtv-control.service
python3 -m py_compile /opt/lgtv-control/server.py
systemctl daemon-reload
systemctl enable lgtv-control.service
systemctl restart lgtv-control.service
systemctl is-active --quiet lgtv-control.service

ADDRESS=$(hostname -I | awk '{print $1}')
echo "LG TV vezérlő: http://$ADDRESS:8765/"
