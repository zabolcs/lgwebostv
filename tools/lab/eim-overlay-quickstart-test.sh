#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
NAS_API=http://192.168.0.223:8765
APP_ID=hu.szabi.launcher
HDMI_APP=com.webos.app.hdmi2
BASE=/var/lib/webosbrew/launcher-eim
FROZEN="$BASE/frozen-view"

TMP="$(mktemp -d)"
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
OFF_SENT=0
COMMITTED=0

cp "$SOURCE_KEY" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
test -s "$KNOWN"
SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")

ssh_ok() {
  "${SSH[@]}" true >/dev/null 2>&1
}

api_get() {
  python3 - "$NAS_API$1" <<'PY'
import json, sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=15) as r:
    print(json.dumps(json.load(r), separators=(",", ":")))
PY
}

api_post() {
  python3 - "$NAS_API$1" "$2" <<'PY'
import json, sys, urllib.request
url=sys.argv[1]
body=sys.argv[2].encode()
req=urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=20) as r:
    print(json.dumps(json.load(r), separators=(",", ":")))
PY
}

luna() {
  local uri="$1"
  local payload="$2"
  "${SSH[@]}" "luna-send -t 1 -f -w 5000 'luna://$uri' '$payload' 2>&1"
}

recover() {
  set +e
  if [ "$OFF_SENT" -eq 1 ] && [ "$COMMITTED" -ne 1 ]; then
    api_post /api/tv/power '{"state":"on"}' >/dev/null 2>&1 || true
    for _ in $(seq 1 90); do
      ssh_ok && break
      sleep 1
    done
    if ssh_ok; then
      luna com.webos.service.applicationmanager/launch '{"id":"hu.szabi.launcher","params":{"source":"quickstart-test-recovery"}}' >/dev/null 2>&1 || true
    fi
  fi
  rm -rf "$TMP"
}
trap recover EXIT

ssh_ok
echo TV_SSH_BEFORE=PASS
"${SSH[@]}" "test -f '$BASE/enabled' && test -f '$BASE/last-good' && test ! -e '$BASE/boot-pending' && test ! -e '$BASE/disabled-failsafe'"
"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$FROZEN'"
echo OVERLAY_PRECONDITION=PASS

FROZEN_BEFORE="$("${SSH[@]}" "cat '$FROZEN/lastinput'")"
echo "FROZEN_BEFORE=$FROZEN_BEFORE"
echo "$FROZEN_BEFORE" | grep -q '"appId":"hu.szabi.launcher"'

luna com.webos.service.applicationmanager/launch '{"id":"com.webos.app.hdmi2","params":{"source":"quickstart-overlay-test"}}' >"$TMP/hdmi.txt"
sleep 3
RUNTIME_BEFORE="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
FROZEN_AFTER_HDMI="$("${SSH[@]}" "cat '$FROZEN/lastinput'")"
echo "RUNTIME_BEFORE_STANDBY=$RUNTIME_BEFORE"
echo "FROZEN_BEFORE_STANDBY=$FROZEN_AFTER_HDMI"
echo "$RUNTIME_BEFORE" | grep -q '"appId":"com.webos.app.hdmi2"'
echo "$FROZEN_AFTER_HDMI" | grep -q '"appId":"hu.szabi.launcher"'
echo HDMI_RUNTIME_BASELINE=PASS

PRE_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
echo "PRE_STANDBY_UPTIME_SECONDS=$PRE_UPTIME"
PRE_CDP="$(node tools/lab/measure-launcher-cdp.mjs "$APP_ID" 2>/dev/null || true)"
echo "PRE_STANDBY_CDP=$PRE_CDP"

OFF_REPLY="$(api_post /api/tv/power '{"state":"off"}')"
OFF_SENT=1
echo "POWER_OFF_REPLY=$OFF_REPLY"
echo "$OFF_REPLY" | grep -q '"ok":true'

OFF_REACHED=0
for i in $(seq 1 50); do
  P="$(api_get /api/tv/power 2>/dev/null || true)"
  if echo "$P" | grep -q '"state":"off"'; then
    OFF_REACHED=1
    echo "POWER_OFF_CONFIRMED_AFTER_HALFSECONDS=$i"
    break
  fi
  sleep 0.5
done
test "$OFF_REACHED" -eq 1
echo QUICKSTART_STANDBY=PASS

sleep 15

WAKE_REQUEST_MS="$(date +%s%3N)"
ON_REPLY="$(api_post /api/tv/power '{"state":"on"}')"
echo "POWER_ON_REPLY=$ON_REPLY"
echo "$ON_REPLY" | grep -q '"ok":true'

VISIBLE=0
POST_CDP=""
for i in $(seq 1 200); do
  POST_CDP="$(node tools/lab/measure-launcher-cdp.mjs "$APP_ID" 2>/dev/null || true)"
  if [ -n "$POST_CDP" ]; then
    if python3 - "$POST_CDP" <<'PY'
import json,sys
d=json.loads(sys.argv[1])
raise SystemExit(0 if d.get("hidden") is False and d.get("activated") is True else 1)
PY
    then
      VISIBLE=1
      VISIBLE_MS="$(date +%s%3N)"
      echo "LAUNCHER_VISIBLE_POLL=$i"
      break
    fi
  fi
  sleep 0.25
done
test "$VISIBLE" -eq 1
echo "POST_WAKE_CDP=$POST_CDP"
python3 - "$WAKE_REQUEST_MS" "$VISIBLE_MS" <<'PY'
import sys
print("LAUNCHER_VISIBLE_AFTER_WAKE_SECONDS=%.3f" % ((int(sys.argv[2])-int(sys.argv[1]))/1000.0))
PY

SSH_RETURNED=0
for i in $(seq 1 90); do
  if ssh_ok; then
    SSH_RETURNED=1
    echo "SSH_AVAILABLE_AFTER_WAKE_SECONDS=$i"
    break
  fi
  sleep 1
done
test "$SSH_RETURNED" -eq 1

POST_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
echo "POST_WAKE_UPTIME_SECONDS=$POST_UPTIME"
python3 - "$PRE_UPTIME" "$POST_UPTIME" <<'PY'
import sys
before=float(sys.argv[1]); after=float(sys.argv[2])
if after <= before:
    raise SystemExit(f"uptime reset or moved backwards: before={before}, after={after}")
print("QUICKSTART_UPTIME_CONTINUITY=PASS")
PY

FG="$(luna com.webos.service.applicationmanager/getForegroundAppInfo '{}')"
echo "POST_WAKE_FOREGROUND=$FG"
echo "$FG" | grep -q '"appId"[[:space:]]*:[[:space:]]*"hu.szabi.launcher"'
echo QUICKSTART_LAUNCHER_FOREGROUND=PASS

"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$FROZEN'"
"${SSH[@]}" "test -f '$BASE/enabled' && test -f '$BASE/last-good' && test ! -e '$BASE/boot-pending' && test ! -e '$BASE/disabled-failsafe'"
RUNTIME_AFTER="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
FROZEN_AFTER="$("${SSH[@]}" "cat '$FROZEN/lastinput'")"
echo "RUNTIME_AFTER_WAKE=$RUNTIME_AFTER"
echo "FROZEN_AFTER_WAKE=$FROZEN_AFTER"
echo "$RUNTIME_AFTER" | grep -q '"appId":"com.webos.app.hdmi2"'
echo "$FROZEN_AFTER" | grep -q '"appId":"hu.szabi.launcher"'
echo QUICKSTART_OVERLAY_PERSISTED=PASS

OFF_SENT=0
COMMITTED=1
echo QUICKSTART_EVERY_PATH=PASS
trap 'rm -rf "$TMP"' EXIT
