#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
NAS_API=http://192.168.0.223:8765
APP=hu.szabi.launcher
OVERLAY=hu.szabi.launcher.overlay
GUARD=/var/lib/webosbrew/launcher-home/guard.sh
INIT=/var/lib/webosbrew/init.d/launcher-home
PIDFILE=/tmp/hu.szabi.launcher-home.pid
DIR=/var/lib/webosbrew/launcher-home
EXPECTED_GUARD_SHA=52cb0ec94e475d3478916d4af781566e31636bb91042dac1a4218efc043f7e97

TMP="$(mktemp -d)"
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
cp "$SOURCE_KEY" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")

OFF_SENT=0
GUARD_STOPPED=0

api() {
  local path="$1"
  local body="${2-}"
  python3 - "$NAS_API$path" "$body" <<'PY'
import sys,urllib.request
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
  GUARD_STOPPED=1
}

start_guard() {
  "${SSH[@]}" "'$INIT' </dev/null >/dev/null 2>&1"
  for _ in $(seq 1 40); do
    if "${SSH[@]}" "p=\$(cat '$PIDFILE' 2>/dev/null || true); case \"\$p\" in ''|*[!0-9]*) exit 1;; esac; kill -0 \"\$p\" 2>/dev/null"; then
      GUARD_STOPPED=0
      return 0
    fi
    sleep 0.25
  done
  return 1
}

cleanup() {
  rc=$?
  set +e
  if [ "$OFF_SENT" -eq 1 ]; then
    api /api/tv/power '{"state":"on"}' >/dev/null 2>&1 || true
    sleep 3
  fi
  "${SSH[@]}" "luna-send -t 1 -f -w 4000 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  if [ "$GUARD_STOPPED" -eq 1 ]; then start_guard >/dev/null 2>&1 || true; fi
  "${SSH[@]}" "luna-send -t 1 -f -w 5000 luna://com.webos.applicationManager/launch '{\"id\":\"$APP\",\"params\":{\"source\":\"selfwake-probe-cleanup\"}}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

"${SSH[@]}" true
SHA_LINE="$("${SSH[@]}" "sha256sum '$GUARD'")"
ACTUAL_SHA="${SHA_LINE%% *}"
echo "TV_GUARD_SHA=$ACTUAL_SHA"
test "$ACTUAL_SHA" = "$EXPECTED_GUARD_SHA"
"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q /var/lib/webosbrew/launcher-eim/frozen-view"
"${SSH[@]}" "test -f /var/lib/webosbrew/launcher-eim/last-good && test ! -e /var/lib/webosbrew/launcher-eim/boot-pending && test ! -e /var/lib/webosbrew/launcher-eim/disabled-failsafe"
echo PRECONDITION=PASS

"${SSH[@]}" "luna-send -t 1 -f -w 4000 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true"
sleep 1
origin="$("${SSH[@]}" "cat '$DIR/control-origin' 2>/dev/null")"
display="$("${SSH[@]}" "cat '$DIR/display-preferences.json' 2>/dev/null")"
[ -n "$display" ] || display='{}'
payload="$(printf '{"id":"%s","preload":"full","keepAlive":true,"noSplash":true,"params":{"source":"preload","launcherHost":"full-overlay","controlOrigin":"%s","displayPreferences":%s}}' "$OVERLAY" "$origin" "$display")"
PRELOAD="$("${SSH[@]}" "luna-send-pub -t 1 -f -w 6000 luna://com.webos.applicationManager/launch '$payload' 2>&1")"
echo "PRELOAD=$PRELOAD"
echo "$PRELOAD" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'

READY=0
for i in $(seq 1 50); do
  CDP="$(node tools/lab/measure-launcher-cdp.mjs "$OVERLAY" 2>/dev/null || true)"
  if [ -n "$CDP" ] && python3 - "$CDP" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("ready") and x.get("hidden") is True else 1)
PY
  then
    READY=1
    echo "PREWARM_READY_POLL=$i"
    break
  fi
  sleep 0.2
done
test "$READY" -eq 1
echo PREWARM_READY=PASS

INJECT="$(node tools/lab/inject-launcher-selfwake-cdp.mjs "$OVERLAY" install)"
echo "SELFWAKE_INJECT=$INJECT"
python3 - "$INJECT" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("ok") else 1)
PY

"${SSH[@]}" "luna-send -t 1 -f -w 5000 luna://com.webos.applicationManager/launch '{\"id\":\"com.webos.app.hdmi2\",\"params\":{\"source\":\"selfwake-probe\"}}' >/dev/null 2>&1"
sleep 2
stop_guard
echo GUARD_STOPPED_FOR_ISOLATED_TEST=PASS

PRE_LINES="$("${SSH[@]}" "wc -l </var/log/messages 2>/dev/null || echo 0")"
PRE_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"

echo "POWER_OFF_RESPONSE=$(api /api/tv/power '{"state":"off"}')"
OFF_SENT=1
for i in $(seq 1 30); do
  STATE="$(power_state || true)"
  if [ "$STATE" = off ]; then echo "STANDBY_AFTER_HALFSECONDS=$i"; break; fi
  sleep 0.5
done
sleep 8

WAKE_MS="$(date +%s%3N)"
echo "POWER_ON_RESPONSE=$(api /api/tv/power '{"state":"on"}')"

for _ in $(seq 1 50); do
  if "${SSH[@]}" true >/dev/null 2>&1; then break; fi
  sleep 0.2
done
OFF_SENT=0
sleep 2

STATUS="$(node tools/lab/inject-launcher-selfwake-cdp.mjs "$OVERLAY" status 2>/dev/null || true)"
echo "SELFWAKE_STATUS=$STATUS"

LOG_DELTA="$TMP/messages.delta"
"${SSH[@]}" "tail -n +$((PRE_LINES+1)) /var/log/messages 2>/dev/null" >"$LOG_DELTA"
python3 - "$LOG_DELTA" "$WAKE_MS" <<'PY'
import re,sys
from datetime import datetime,timezone
from pathlib import Path
text=Path(sys.argv[1]).read_text(errors="replace")
wake=int(sys.argv[2])/1000.0
first=None
for line in text.splitlines():
    if 'NL_VSC' not in line or '"visible":true' not in line or '"app_id":"hu.szabi.launcher.overlay"' not in line:
        continue
    m=re.match(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z',line)
    if not m: continue
    ts=datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc).timestamp()
    if ts >= wake:
        first=ts-wake
        break
if first is None:
    raise SystemExit("self-wake overlay surface never became visible")
print(f"SELFWAKE_OVERLAY_VISIBLE_AFTER_SECONDS={first:.3f}")
print("SELFWAKE_SURFACE=PASS")
PY

POST_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
python3 - "$PRE_UPTIME" "$POST_UPTIME" <<'PY'
import sys
if float(sys.argv[2]) <= float(sys.argv[1]): raise SystemExit("uptime reset")
print("QUICK_START_UPTIME_CONTINUITY=PASS")
PY

echo SELFWAKE_PROBE_COMPLETE=PASS
