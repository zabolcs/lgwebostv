#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
KEY_SOURCE=/media/lgtv/id_rsa
BASE=/var/lib/webosbrew/launcher-eim
APP=hu.szabi.launcher
NAS_API=http://192.168.0.223:8765

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
cp "$KEY_SOURCE" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")

api() {
  local path="$1"
  local body="${2-}"
  python3 - "$NAS_API$path" "$body" <<'PY'
import json, sys, urllib.request
url=sys.argv[1]
body=sys.argv[2]
data=None if body=="" else body.encode()
req=urllib.request.Request(url,data=data,headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=15) as r:
    print(r.read().decode())
PY
}

power_state() {
  api /api/tv/power | python3 -c 'import json,sys; d=json.load(sys.stdin); print(((d.get("power") or {}).get("state")) or d.get("state") or "")'
}

foreground() {
  "${SSH[@]}" "luna-send -t 1 -f -w 1200 'luna://com.webos.applicationManager/getForegroundAppInfo' '{}' 2>&1" || true
}

"${SSH[@]}" true
"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$BASE/frozen-view'"
"${SSH[@]}" "test -f '$BASE/last-good' && test ! -e '$BASE/boot-pending' && test ! -e '$BASE/disabled-failsafe'"
echo OVERLAY_PREFLIGHT=PASS

PRE_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
PRE_BOOT_ID="$("${SSH[@]}" 'cat /proc/sys/kernel/random/boot_id 2>/dev/null || true')"
PRE_FROZEN="$("${SSH[@]}" "cat '$BASE/frozen-view/lastinput'")"
PRE_RUNTIME="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
echo "PRE_UPTIME=$PRE_UPTIME"
echo "PRE_BOOT_ID=$PRE_BOOT_ID"
echo "PRE_FROZEN=$PRE_FROZEN"
echo "PRE_RUNTIME=$PRE_RUNTIME"
echo "$PRE_FROZEN" | grep -q '"appId":"hu.szabi.launcher"'

echo "POWER_OFF_RESPONSE=$(api /api/tv/power '{"state":"off"}')"
OFF=0
for i in $(seq 1 30); do
  STATE="$(power_state || true)"
  echo "POWER_OFF_POLL_$i=$STATE"
  if [ "$STATE" = "off" ]; then OFF=1; break; fi
  sleep 0.5
done
test "$OFF" -eq 1
echo QUICK_START_STANDBY=PASS

sleep 8
WAKE_EPOCH="$(date +%s%3N)"
echo "POWER_ON_RESPONSE=$(api /api/tv/power '{"state":"on"}')"
echo "WAKE_REQUEST_EPOCH_MS=$WAKE_EPOCH"

LAUNCHER_SEEN=0
SEEN_MS=""
FG=""
for i in $(seq 1 100); do
  FG="$(foreground)"
  if echo "$FG" | grep -Eq '"appId"[[:space:]]*:[[:space:]]*"hu.szabi.launcher"'; then
    LAUNCHER_SEEN=1
    SEEN_MS="$(date +%s%3N)"
    echo "LAUNCHER_FOREGROUND_POLL=$i"
    break
  fi
  sleep 0.25
done

echo "FOREGROUND_AFTER_WAKE=$FG"
test "$LAUNCHER_SEEN" -eq 1
python3 - "$WAKE_EPOCH" "$SEEN_MS" <<'PY'
import sys
print("QUICK_START_LAUNCHER_FOREGROUND_AFTER_SECONDS=%.3f" % ((int(sys.argv[2])-int(sys.argv[1]))/1000.0))
PY

POST_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
POST_BOOT_ID="$("${SSH[@]}" 'cat /proc/sys/kernel/random/boot_id 2>/dev/null || true')"
echo "POST_UPTIME=$POST_UPTIME"
echo "POST_BOOT_ID=$POST_BOOT_ID"
python3 - "$PRE_UPTIME" "$POST_UPTIME" <<'PY'
import sys
before=float(sys.argv[1]); after=float(sys.argv[2])
if after <= before:
    raise SystemExit(f"uptime reset or regressed: before={before} after={after}")
print("QUICK_START_NO_UPTIME_RESET=PASS")
PY

"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$BASE/frozen-view'"
"${SSH[@]}" "test -f '$BASE/last-good' && test ! -e '$BASE/boot-pending' && test ! -e '$BASE/disabled-failsafe'"
POST_FROZEN="$("${SSH[@]}" "cat '$BASE/frozen-view/lastinput'")"
POST_RUNTIME="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
echo "POST_FROZEN=$POST_FROZEN"
echo "POST_RUNTIME=$POST_RUNTIME"
echo "$POST_FROZEN" | grep -q '"appId":"hu.szabi.launcher"'
echo QUICK_START_OVERLAY_PERSISTED=PASS

echo GUARD_LOG_BEGIN
"${SSH[@]}" "tail -120 /tmp/hu.szabi.launcher-wake.log 2>/dev/null || true"
echo GUARD_LOG_END

echo QUICK_START_LAUNCHER_WAKE=PASS
