#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
CAMERA_ROOT=$(CDPATH= cd -- "$ROOT/../../apps/camera-viewer" && pwd)
CTID=${1:-120}
LIVE=/opt/go2rtc-tv-player
SERVICE=/etc/systemd/system/go2rtc-tv-player.service
LOCK=/run/lock/go2rtc-tv-player.deploy.lock
TXN="$$"
STAGE="/opt/.go2rtc-tv-player.stage-$TXN"
BACKUP="/opt/.go2rtc-tv-player.backup-$TXN"
SERVICE_NEW="/etc/systemd/system/.go2rtc-tv-player.service.new-$TXN"
SERVICE_BACKUP="/etc/systemd/system/.go2rtc-tv-player.service.backup-$TXN"
HAD_LIVE=0
HAD_SERVICE=0
WAS_ACTIVE=0
WAS_ENABLED=0
COMMITTED=0
STATE_CAPTURED=0
MUTATION_STARTED=0

case "$CTID" in
  ''|*[!0-9]*) echo "invalid container id: $CTID" >&2; exit 2 ;;
esac

for FILE in server.py go2rtc-tv-player.service; do
  test -f "$ROOT/$FILE" || { echo "missing gateway asset: $FILE" >&2; exit 2; }
done
for FILE in webos-player.html webos-player.js; do
  test -f "$CAMERA_ROOT/$FILE" || { echo "missing camera player asset: $FILE" >&2; exit 2; }
done

command -v pct >/dev/null 2>&1 || { echo "missing command: pct" >&2; exit 2; }
command -v sha256sum >/dev/null 2>&1 || { echo "missing command: sha256sum" >&2; exit 2; }
test "$(pct status "$CTID")" = "status: running" || {
  echo "container $CTID is not running" >&2
  exit 3
}

mkdir "$LOCK" 2>/dev/null || { echo "another gateway deployment is active" >&2; exit 4; }

cleanup() {
  RC=$?
  trap - EXIT INT TERM
  if test "$COMMITTED" -ne 1 && test "$STATE_CAPTURED" -eq 1 && test "$MUTATION_STARTED" -eq 1; then
    echo "deployment failed; restoring the previous gateway" >&2
    pct exec "$CTID" -- systemctl stop go2rtc-tv-player.service >/dev/null 2>&1 || true
    if test "$HAD_LIVE" -eq 1; then
      pct exec "$CTID" -- /bin/sh -c "test -d '$BACKUP' && { test ! -e '$LIVE' || mv '$LIVE' '$STAGE.failed'; mv '$BACKUP' '$LIVE'; }" || true
    else
      pct exec "$CTID" -- /bin/sh -c "test ! -e '$LIVE' || mv '$LIVE' '$STAGE.failed'" || true
    fi
    if test "$HAD_SERVICE" -eq 1; then
      pct exec "$CTID" -- /bin/sh -c "test -f '$SERVICE_BACKUP' && mv '$SERVICE_BACKUP' '$SERVICE'" || true
    else
      pct exec "$CTID" -- /bin/sh -c "test ! -f '$SERVICE' || mv '$SERVICE' '$SERVICE_NEW.failed'" || true
    fi
    pct exec "$CTID" -- systemctl daemon-reload >/dev/null 2>&1 || true
    if test "$WAS_ENABLED" -eq 1; then
      pct exec "$CTID" -- systemctl enable go2rtc-tv-player.service >/dev/null 2>&1 || true
    else
      pct exec "$CTID" -- systemctl disable go2rtc-tv-player.service >/dev/null 2>&1 || true
    fi
    if test "$WAS_ACTIVE" -eq 1; then
      pct exec "$CTID" -- systemctl start go2rtc-tv-player.service >/dev/null 2>&1 || true
    fi
  elif test "$COMMITTED" -ne 1 && test "$STATE_CAPTURED" -eq 1; then
    pct exec "$CTID" -- rm -rf "$STAGE" >/dev/null 2>&1 || true
    pct exec "$CTID" -- rm -f "$SERVICE_NEW" >/dev/null 2>&1 || true
  fi
  rmdir "$LOCK" 2>/dev/null || true
  exit "$RC"
}
trap cleanup EXIT INT TERM

pct exec "$CTID" -- /bin/sh -c 'command -v python3 >/dev/null && command -v systemctl >/dev/null && command -v sha256sum >/dev/null && command -v ffmpeg >/dev/null'

SNAPSHOT=$(pct exec "$CTID" -- /bin/sh -c '
  live=0; service=0; active=0; enabled=0
  test ! -d /opt/go2rtc-tv-player || live=1
  test ! -f /etc/systemd/system/go2rtc-tv-player.service || service=1
  systemctl is-active --quiet go2rtc-tv-player.service >/dev/null 2>&1 && active=1 || true
  systemctl is-enabled --quiet go2rtc-tv-player.service >/dev/null 2>&1 && enabled=1 || true
  printf "%s %s %s %s\n" "$live" "$service" "$active" "$enabled"
')
case "$SNAPSHOT" in
  '0 0 0 0'|'0 0 0 1'|'0 0 1 0'|'0 0 1 1'|'0 1 0 0'|'0 1 0 1'|'0 1 1 0'|'0 1 1 1'|\
  '1 0 0 0'|'1 0 0 1'|'1 0 1 0'|'1 0 1 1'|'1 1 0 0'|'1 1 0 1'|'1 1 1 0'|'1 1 1 1') ;;
  *) echo "invalid container state snapshot" >&2; exit 4 ;;
esac
set -- $SNAPSHOT
HAD_LIVE=$1
HAD_SERVICE=$2
WAS_ACTIVE=$3
WAS_ENABLED=$4
STATE_CAPTURED=1

pct exec "$CTID" -- mkdir -m 0755 "$STAGE"
pct push "$CTID" "$ROOT/server.py" "$STAGE/server.py" --perms 0755
pct push "$CTID" "$CAMERA_ROOT/webos-player.html" "$STAGE/webos-player.html" --perms 0644
pct push "$CTID" "$CAMERA_ROOT/webos-player.js" "$STAGE/webos-player.js" --perms 0644
pct push "$CTID" "$ROOT/go2rtc-tv-player.service" "$SERVICE_NEW" --perms 0644
pct exec "$CTID" -- ffmpeg -hide_banner -loglevel error -f lavfi -i color=c=black:s=16x16:r=1:d=2 \
  -an -c:v libx264 -profile:v baseline -level 3.0 -pix_fmt yuv420p -movflags +faststart \
  -y "$STAGE/screen-guard.mp4"
pct exec "$CTID" -- test -s "$STAGE/screen-guard.mp4"

EXPECTED_SERVER=$(sha256sum "$ROOT/server.py" | awk '{print $1}')
EXPECTED_HTML=$(sha256sum "$CAMERA_ROOT/webos-player.html" | awk '{print $1}')
EXPECTED_JS=$(sha256sum "$CAMERA_ROOT/webos-player.js" | awk '{print $1}')
EXPECTED_SERVICE=$(sha256sum "$ROOT/go2rtc-tv-player.service" | awk '{print $1}')
ACTUAL=$(pct exec "$CTID" -- sha256sum "$STAGE/server.py" "$STAGE/webos-player.html" "$STAGE/webos-player.js" "$SERVICE_NEW" | awk '{print $1}' | tr '\n' ' ')
EXPECTED="$EXPECTED_SERVER $EXPECTED_HTML $EXPECTED_JS $EXPECTED_SERVICE "
test "$ACTUAL" = "$EXPECTED" || { echo "container staging hash mismatch" >&2; exit 5; }

pct exec "$CTID" -- python3 -m py_compile "$STAGE/server.py"
pct exec "$CTID" -- chown -R 0:0 "$STAGE"
pct exec "$CTID" -- chmod 0755 "$STAGE" "$STAGE/server.py"
pct exec "$CTID" -- chmod 0644 "$STAGE/webos-player.html" "$STAGE/webos-player.js" "$STAGE/screen-guard.mp4" "$SERVICE_NEW"

MUTATION_STARTED=1
pct exec "$CTID" -- systemctl stop go2rtc-tv-player.service >/dev/null 2>&1 || true
if test "$HAD_LIVE" -eq 1; then pct exec "$CTID" -- mv "$LIVE" "$BACKUP"; fi
if test "$HAD_SERVICE" -eq 1; then pct exec "$CTID" -- cp -p "$SERVICE" "$SERVICE_BACKUP"; fi
pct exec "$CTID" -- mv "$STAGE" "$LIVE"
pct exec "$CTID" -- mv "$SERVICE_NEW" "$SERVICE"
pct exec "$CTID" -- systemctl daemon-reload
pct exec "$CTID" -- systemctl enable --now go2rtc-tv-player.service

READY=0
COUNT=0
while test "$COUNT" -lt 20; do
  if pct exec "$CTID" -- python3 -c "import urllib.request; assert urllib.request.urlopen('http://192.168.0.150:1985/healthz', timeout=1).read() == b'ok\\n'"; then
    READY=1
    break
  fi
  COUNT=$((COUNT + 1))
  sleep 1
done
test "$READY" -eq 1 || { echo "gateway health check failed" >&2; exit 6; }
pct exec "$CTID" -- systemctl is-active --quiet go2rtc-tv-player.service

COMMITTED=1
if test "$HAD_LIVE" -eq 1; then pct exec "$CTID" -- rm -rf "$BACKUP"; fi
if test "$HAD_SERVICE" -eq 1; then pct exec "$CTID" -- rm -f "$SERVICE_BACKUP"; fi
rmdir "$LOCK"
trap - EXIT INT TERM
echo "go2rtc TV-player gateway install: PASS"
