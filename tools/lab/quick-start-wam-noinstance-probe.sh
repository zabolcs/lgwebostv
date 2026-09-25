#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
APP=hu.szabi.launcher
OVERLAY=hu.szabi.launcher.overlay
INIT=/var/lib/webosbrew/init.d/launcher-home
PIDFILE=/tmp/hu.szabi.launcher-home.pid
DIR=/var/lib/webosbrew/launcher-home

TMP="$(mktemp -d)"
cp "$SOURCE_KEY" "$TMP/id_rsa"
chmod 600 "$TMP/id_rsa"
ssh-keyscan -T 3 "$TV_HOST" >"$TMP/known_hosts" 2>/dev/null
SSH=(ssh -T -i "$TMP/id_rsa" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$TMP/known_hosts" "$TV")
GUARD_STOPPED=0

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
  "${SSH[@]}" "luna-send -n 1 -f -w 3000 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  if [ "$GUARD_STOPPED" -eq 1 ]; then start_guard >/dev/null 2>&1 || true; fi
  "${SSH[@]}" "luna-send -n 1 -f -w 5000 luna://com.webos.applicationManager/launch '{\"id\":\"$APP\",\"params\":{\"source\":\"wam-noinstance-probe-cleanup\"}}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

"${SSH[@]}" true
stop_guard
echo GUARD_STOPPED=PASS

origin="$("${SSH[@]}" "cat '$DIR/control-origin' 2>/dev/null")"
display="$("${SSH[@]}" "cat '$DIR/display-preferences.json' 2>/dev/null")"
[ -n "$display" ] || display='{}'

preload="$(printf '{"id":"%s","preload":"full","keepAlive":true,"noSplash":true,"params":{"source":"wam-noinstance-preload","launcherHost":"full-overlay","controlOrigin":"%s","displayPreferences":%s}}' "$OVERLAY" "$origin" "$display")"
PRELOAD_RESULT="$("${SSH[@]}" "luna-send -t 1 -f -w 5000 luna://com.webos.applicationManager/launch '$preload'" 2>&1)"
echo "PRELOAD_RESULT=$PRELOAD_RESULT"
echo "$PRELOAD_RESULT" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'

READY=0
CDP=""
for i in $(seq 1 40); do
  CDP="$(node tools/lab/measure-launcher-cdp.mjs "$OVERLAY" 2>/dev/null || true)"
  if [ -n "$CDP" ] && python3 - "$CDP" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("ready") and x.get("hidden") is True else 1)
PY
  then READY=1; echo "PREWARM_READY_POLL=$i"; break; fi
  sleep 0.2
done
echo "PREWARM_CDP=$CDP"
test "$READY" -eq 1
echo PREWARM_READY=PASS

APPINFO="$("${SSH[@]}" "luna-send -t 1 -f -w 2000 luna://com.webos.applicationManager/getAppInfo '{\"id\":\"$OVERLAY\"}'" 2>&1)"
PAYLOAD="$(python3 - "$APPINFO" "$origin" "$display" "$OVERLAY" <<'PY'
import json,sys
def timed(raw):
    marker="payload "
    p=raw.find(marker)
    if p>=0: raw=raw[p+len(marker):]
    return json.JSONDecoder().raw_decode(raw.lstrip())[0]
appinfo=timed(sys.argv[1])
desc=appinfo.get("appInfo")
if not isinstance(desc,dict):
    raise SystemExit("overlay appInfo missing")
payload={
  "appDesc":desc,
  "appId":sys.argv[4],
  "parameters":{
    "source":"wam-direct-noinstance",
    "launcherHost":"full-overlay",
    "controlOrigin":sys.argv[2],
    "displayPreferences":json.loads(sys.argv[3])
  },
  "launchingAppId":"com.webos.app.home",
  "launchingProcId":"",
  "reason":"quick-start-probe"
}
print(json.dumps(payload,separators=(",",":")))
PY
)"
echo WAM_PAYLOAD_READY=PASS

"${SSH[@]}" "luna-send -n 1 -f -w 4000 luna://com.webos.applicationManager/launch '{\"id\":\"com.webos.app.hdmi2\",\"params\":{\"source\":\"wam-noinstance-probe\"}}' >/dev/null"
sleep 0.8

START_MS="$(date +%s%3N)"
RESULT="$("${SSH[@]}" "luna-send -t 1 -f -w 2500 luna://com.webos.service.webappmanager/launchApp '$PAYLOAD'" 2>&1 || true)"
END_MS="$(date +%s%3N)"
echo "WAM_PRIVATE_LAUNCH_RESULT=$RESULT"
echo "WAM_PRIVATE_LAUNCH_CALL_MS=$((END_MS-START_MS))"

if ! echo "$RESULT" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
  echo WAM_PRIVATE_LAUNCH=FAILED
  exit 41
fi

VISIBLE=0
for i in $(seq 1 40); do
  CDP="$(node tools/lab/measure-launcher-cdp.mjs "$OVERLAY" 2>/dev/null || true)"
  if [ -n "$CDP" ] && python3 - "$CDP" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("hidden") is False and x.get("activated") is True else 1)
PY
  then VISIBLE=1; echo "WAM_VISIBLE_POLL=$i"; break; fi
  sleep 0.05
done
echo "WAM_VISIBLE_CDP=$CDP"
test "$VISIBLE" -eq 1
echo WAM_DIRECT_NOINSTANCE_PROBE=PASS
