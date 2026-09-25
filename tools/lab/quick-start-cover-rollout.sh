#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
NAS_API=http://192.168.0.223:8765
GUARD=/var/lib/webosbrew/launcher-home/guard.sh
PREWARM=/var/lib/webosbrew/launcher-home/prewarm.sh
INIT=/var/lib/webosbrew/init.d/launcher-home
PIDFILE=/tmp/hu.szabi.launcher-home.pid
DIR=/var/lib/webosbrew/launcher-home
APP=hu.szabi.launcher
OVERLAY=hu.szabi.launcher.overlay
COVER_READY=/tmp/hu.szabi.launcher.full-overlay-prewarm-ready
BASE=/var/lib/webosbrew/launcher-eim
RUN_TAG="${GITHUB_RUN_ID:-manual}"
BACKUP="/media/lgtv/quick-cover-backup-20260925-${RUN_TAG}"

TMP="$(mktemp -d)"
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
mkdir -p "$BACKUP"
cp "$SOURCE_KEY" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")
SCP=(scp -i "$KEY" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN")

DEPLOYED=0
COMMITTED=0
OFF_SENT=0

api() {
  local path="$1"
  local body="${2-}"
  python3 - "$NAS_API$path" "$body" <<'PY'
import json,sys,urllib.request
url=sys.argv[1]; body=sys.argv[2]
data=None if body=="" else body.encode()
req=urllib.request.Request(url,data=data,headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=20) as r:
    print(r.read().decode())
PY
}

power_state() {
  api /api/tv/power | python3 -c 'import json,sys; d=json.load(sys.stdin); print(((d.get("power") or {}).get("state")) or d.get("state") or "")'
}

stop_guard() {
  "${SSH[@]}" '
    p=$(cat /tmp/hu.szabi.launcher-home.pid 2>/dev/null || true)
    case "$p" in ""|*[!0-9]*) exit 0;; esac
    if [ "$p" -gt 1 ] && [ -r "/proc/$p/cmdline" ] &&
       tr "\000" " " <"/proc/$p/cmdline" | grep -F "/var/lib/webosbrew/launcher-home/guard.sh" >/dev/null; then
      kill "$p" 2>/dev/null || true
      i=0
      while [ "$i" -lt 30 ] && kill -0 "$p" 2>/dev/null; do /bin/usleep 100000; i=$((i+1)); done
      ! kill -0 "$p" 2>/dev/null
    fi
  '
}

start_guard() {
  "${SSH[@]}" "'$INIT' </dev/null >/dev/null 2>&1"
  for _ in $(seq 1 40); do
    if "${SSH[@]}" "p=\$(cat '$PIDFILE' 2>/dev/null || true); case \"\$p\" in ''|*[!0-9]*) exit 1;; esac; kill -0 \"\$p\" 2>/dev/null"; then
      return 0
    fi
    sleep 0.25
  done
  return 1
}

close_overlay() {
  "${SSH[@]}" "luna-send -t 1 -f -w 5000 'luna://com.webos.applicationManager/closeByAppId' '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true"
  "${SSH[@]}" "rm -f '$COVER_READY' /tmp/hu.szabi.launcher.full-overlay-prewarm-ready /tmp/hu.szabi.launcher.full-overlay-visible" >/dev/null 2>&1 || true
}

restore_old_guard() {
  set +e
  if [ "$DEPLOYED" -eq 1 ] && [ "$COMMITTED" -ne 1 ]; then
    echo ROLLBACK_OLD_GUARD=START
    close_overlay || true
    stop_guard || true
    "${SCP[@]}" "$BACKUP/guard.sh" "$TV:$GUARD.rollback" >/dev/null 2>&1 || true
    "${SSH[@]}" "sh -n '$GUARD.rollback' && chmod 755 '$GUARD.rollback' && mv -f '$GUARD.rollback' '$GUARD'" >/dev/null 2>&1 || true
    start_guard || true
    "${SSH[@]}" "luna-send -t 1 -f -w 5000 'luna://com.webos.applicationManager/launch' '{\"id\":\"$APP\",\"params\":{\"source\":\"quick-cover-rollback\"}}' >/dev/null 2>&1 || true"
    echo ROLLBACK_OLD_GUARD=ATTEMPTED
  fi
}

cleanup() {
  rc=$?
  set +e
  if [ "$OFF_SENT" -eq 1 ]; then api /api/tv/power '{"state":"on"}' >/dev/null 2>&1 || true; fi
  restore_old_guard
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

"${SSH[@]}" true
"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$BASE/frozen-view'"
"${SSH[@]}" "test -f '$BASE/last-good' && test ! -e '$BASE/boot-pending' && test ! -e '$BASE/disabled-failsafe'"
"${SSH[@]}" "test -f /media/developer/apps/usr/palm/applications/$OVERLAY/appinfo.json"
echo PRECONDITION=PASS

"${SCP[@]}" "$TV:$GUARD" "$BACKUP/guard.sh"
sha256sum "$BACKUP/guard.sh" >"$BACKUP/SHA256SUMS"
sha256sum -c "$BACKUP/SHA256SUMS"
OLD_SHA="$(sha256sum "$BACKUP/guard.sh" | awk '{print $1}')"
NEW_SHA="$(sha256sum tools/generated-tv-scripts/guard.sh | awk '{print $1}')"
echo "OLD_GUARD_SHA=$OLD_SHA"
echo "NEW_GUARD_SHA=$NEW_SHA"
grep -q "guard v0.4.1" tools/generated-tv-scripts/guard.sh

"${SCP[@]}" tools/generated-tv-scripts/guard.sh "$TV:$GUARD.new"
"${SSH[@]}" "sh -n '$GUARD.new'; chmod 755 '$GUARD.new'; mv -f '$GUARD.new' '$GUARD'"
DEPLOYED=1
ACTUAL_SHA="$("${SSH[@]}" "sha256sum '$GUARD' | awk '{print \$1}'")"
test "$ACTUAL_SHA" = "$NEW_SHA"
stop_guard
start_guard
sleep 1
"${SSH[@]}" "tail -30 /tmp/hu.szabi.launcher-wake.log 2>/dev/null | grep -q 'guard v0.4.1 started'"
echo COVER_GUARD_DEPLOY=PASS

origin="$("${SSH[@]}" "cat '$DIR/control-origin' 2>/dev/null")"
display="$("${SSH[@]}" "cat '$DIR/display-preferences.json' 2>/dev/null")"
[ -n "$display" ] || display='{}'
preload_payload="$(printf '{"id":"%s","preload":"full","keepAlive":true,"noSplash":true,"params":{"source":"preload","launcherHost":"full-overlay","controlOrigin":"%s","displayPreferences":%s}}' "$OVERLAY" "$origin" "$display")"
PRELOAD="$("${SSH[@]}" "luna-send-pub -t 1 -f -w 6000 'luna://com.webos.applicationManager/launch' '$preload_payload' 2>&1")"
echo "COVER_PRELOAD=$PRELOAD"
echo "$PRELOAD" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'

READY=0
COVER_CDP=""
for i in $(seq 1 50); do
  COVER_CDP="$(node tools/lab/measure-launcher-cdp.mjs "$OVERLAY" 2>/dev/null || true)"
  if [ -n "$COVER_CDP" ]; then
    if python3 - "$COVER_CDP" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("ready") and x.get("hidden") is True else 1)
PY
    then
      READY=1
      echo "COVER_PREWARM_READY_POLL=$i"
      break
    fi
  fi
  sleep 0.2
done
echo "COVER_PREWARM_CDP=$COVER_CDP"
test "$READY" -eq 1
"${SSH[@]}" "touch '$COVER_READY'"
echo COVER_PREWARM=PASS

# Establish a worst-case visible input while keeping the prewarmed popup hidden.
"${SSH[@]}" "luna-send -t 1 -f -w 5000 'luna://com.webos.applicationManager/launch' '{\"id\":\"com.webos.app.hdmi2\",\"params\":{\"source\":\"quick-cover-baseline\"}}' >/dev/null 2>&1"
sleep 2
WINDOW="$("${SSH[@]}" "luna-send -t 1 -f -w 1500 'luna://com.webos.surfacemanager/getForegroundWindowInfo' '{}' 2>&1" || true)"
echo "PRE_STANDBY_WINDOW=$WINDOW"
echo "$WINDOW" | grep -vq "$OVERLAY"
PRE_LINES="$("${SSH[@]}" "wc -l </var/log/messages 2>/dev/null || echo 0")"
PRE_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"

echo "POWER_OFF_RESPONSE=$(api /api/tv/power '{"state":"off"}')"
OFF_SENT=1
OFF=0
for i in $(seq 1 30); do
  STATE="$(power_state || true)"
  if [ "$STATE" = off ]; then OFF=1; echo "STANDBY_AFTER_HALFSECONDS=$i"; break; fi
  sleep 0.5
done
test "$OFF" -eq 1
sleep 8

WAKE_MS="$(date +%s%3N)"
echo "POWER_ON_RESPONSE=$(api /api/tv/power '{"state":"on"}')"

FULL_VISIBLE=0
FG=""
for i in $(seq 1 140); do
  FG="$("${SSH[@]}" "luna-send -t 1 -f -w 800 'luna://com.webos.applicationManager/getForegroundAppInfo' '{}' 2>&1" 2>/dev/null || true)"
  if echo "$FG" | grep -Eq '"appId"[[:space:]]*:[[:space:]]*"hu.szabi.launcher"'; then
    FULL_VISIBLE=1
    FULL_SEEN_MS="$(date +%s%3N)"
    break
  fi
  sleep 0.2
done
test "$FULL_VISIBLE" -eq 1
OFF_SENT=0

sleep 2
LOG_DELTA="$TMP/messages.delta"
"${SSH[@]}" "tail -n +$((PRE_LINES+1)) /var/log/messages 2>/dev/null" >"$LOG_DELTA"

python3 - "$LOG_DELTA" "$WAKE_MS" <<'PY'
import re,sys
from datetime import datetime,timezone
from pathlib import Path
text=Path(sys.argv[1]).read_text(errors="replace")
wake=int(sys.argv[2])/1000.0
wanted={
 "overlay":"hu.szabi.launcher.overlay",
 "full":"hu.szabi.launcher",
 "home":"com.webos.app.home",
 "hdmi":"com.webos.app.hdmi2",
}
first={}
for line in text.splitlines():
    if 'NL_VSC' not in line or '"visible":true' not in line:
        continue
    m=re.match(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z',line)
    if not m: continue
    ts=datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc).timestamp()
    for key,app in wanted.items():
        if f'"app_id":"{app}"' in line and key not in first:
            first[key]=ts-wake
for key in ('home','hdmi','overlay','full'):
    if key in first: print(f"{key.upper()}_VISIBLE_AFTER_SECONDS={first[key]:.3f}")
cover=first.get('overlay')
full=first.get('full')
if cover is None or full is None:
    raise SystemExit("cover/full surface timestamp missing")
if not (0 <= cover < full):
    raise SystemExit(f"cover was not earlier than full: cover={cover}, full={full}")
if cover >= 2.20:
    raise SystemExit(f"resume-edge cover did not beat the protected 2.368s baseline enough: {cover:.3f}s")
if full-cover < 1.0:
    raise SystemExit(f"cover lead too small: {full-cover:.3f}s")
print(f"COVER_LEAD_SECONDS={full-cover:.3f}")
print("QUICK_COVER_TIMING=PASS")
PY

echo COVER_GUARD_LOG_BEGIN
"${SSH[@]}" "tail -100 /tmp/hu.szabi.launcher-wake.log 2>/dev/null"
echo COVER_GUARD_LOG_END
"${SSH[@]}" "tail -100 /tmp/hu.szabi.launcher-wake.log 2>/dev/null | grep -q 'resume edge cover accepted'"
"${SSH[@]}" "tail -100 /tmp/hu.szabi.launcher-wake.log 2>/dev/null | grep -q 'quick fast lane accepted'"

POST_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
python3 - "$PRE_UPTIME" "$POST_UPTIME" <<'PY'
import sys
if float(sys.argv[2]) <= float(sys.argv[1]): raise SystemExit("uptime reset")
print("QUICK_START_UPTIME_CONTINUITY=PASS")
PY
"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$BASE/frozen-view'"
echo OVERLAY_PERSISTED=PASS

COMMITTED=1
echo "ROLLBACK_BACKUP=$BACKUP"
echo QUICK_COVER_ROLLOUT=PASS
trap 'rm -rf "$TMP"' EXIT
