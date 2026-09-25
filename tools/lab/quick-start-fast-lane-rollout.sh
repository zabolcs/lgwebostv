#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
NAS_API=http://192.168.0.223:8765
GUARD=/var/lib/webosbrew/launcher-home/guard.sh
INIT=/var/lib/webosbrew/init.d/launcher-home
PIDFILE=/tmp/hu.szabi.launcher-home.pid
APP=hu.szabi.launcher
BASE=/var/lib/webosbrew/launcher-eim
RUN_TAG="${GITHUB_RUN_ID:-manual}"
BACKUP="/media/lgtv/quick-fast-lane-backup-20260925-${RUN_TAG}"

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
      while [ "$i" -lt 30 ] && kill -0 "$p" 2>/dev/null; do sleep 0.1; i=$((i+1)); done
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

restore_old_guard() {
  set +e
  if [ "$DEPLOYED" -eq 1 ] && [ "$COMMITTED" -ne 1 ]; then
    echo ROLLBACK_OLD_GUARD=START
    stop_guard || true
    "${SCP[@]}" "$BACKUP/guard.sh" "$TV:$GUARD.rollback" >/dev/null 2>&1 || true
    "${SSH[@]}" "sh -n '$GUARD.rollback' && chmod 755 '$GUARD.rollback' && mv -f '$GUARD.rollback' '$GUARD'" >/dev/null 2>&1 || true
    start_guard || true
    echo ROLLBACK_OLD_GUARD=ATTEMPTED
  fi
}

cleanup() {
  rc=$?
  set +e
  if [ "$OFF_SENT" -eq 1 ]; then
    api /api/tv/power '{"state":"on"}' >/dev/null 2>&1 || true
  fi
  restore_old_guard
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

"${SSH[@]}" true
"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$BASE/frozen-view'"
"${SSH[@]}" "test -f '$BASE/last-good' && test ! -e '$BASE/boot-pending' && test ! -e '$BASE/disabled-failsafe'"
echo PRECONDITION=PASS

"${SCP[@]}" "$TV:$GUARD" "$BACKUP/guard.sh"
sha256sum "$BACKUP/guard.sh" >"$BACKUP/SHA256SUMS"
sha256sum -c "$BACKUP/SHA256SUMS"
OLD_SHA="$(sha256sum "$BACKUP/guard.sh" | awk '{print $1}')"
NEW_SHA="$(sha256sum tools/generated-tv-scripts/guard.sh | awk '{print $1}')"
echo "OLD_GUARD_SHA=$OLD_SHA"
echo "NEW_GUARD_SHA=$NEW_SHA"
grep -q "guard v0.3.8" tools/generated-tv-scripts/guard.sh
echo BACKUP=PASS

"${SCP[@]}" tools/generated-tv-scripts/guard.sh "$TV:$GUARD.new"
"${SSH[@]}" "sh -n '$GUARD.new'; chmod 755 '$GUARD.new'; mv -f '$GUARD.new' '$GUARD'"
DEPLOYED=1
ACTUAL_SHA="$("${SSH[@]}" "sha256sum '$GUARD' | awk '{print \$1}'")"
echo "TV_GUARD_SHA=$ACTUAL_SHA"
test "$ACTUAL_SHA" = "$NEW_SHA"

stop_guard
start_guard
sleep 1
"${SSH[@]}" "tail -40 /tmp/hu.szabi.launcher-wake.log 2>/dev/null | grep -q 'guard v0.3.8 started'"
echo FAST_GUARD_DEPLOY=PASS

# Worst-case user state: HDMI2 is foreground before Quick Start standby.
"${SSH[@]}" "luna-send -t 1 -f -w 5000 'luna://com.webos.service.applicationmanager/launch' '{\"id\":\"com.webos.app.hdmi2\",\"params\":{\"source\":\"quick-fast-lane-baseline\"}}' >/dev/null 2>&1 || luna-send -t 1 -f -w 5000 'luna://com.webos.applicationManager/launch' '{\"id\":\"com.webos.app.hdmi2\",\"params\":{\"source\":\"quick-fast-lane-baseline\"}}' >/dev/null 2>&1"
sleep 2
PRE_LINES="$("${SSH[@]}" "wc -l </var/log/messages 2>/dev/null || echo 0")"
PRE_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
echo "PRE_STANDBY_UPTIME=$PRE_UPTIME"

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
VISIBLE=0
FG=""
for i in $(seq 1 120); do
  FG="$("${SSH[@]}" "luna-send -t 1 -f -w 800 'luna://com.webos.applicationManager/getForegroundAppInfo' '{}' 2>&1" 2>/dev/null || true)"
  if echo "$FG" | grep -Eq '"appId"[[:space:]]*:[[:space:]]*"hu.szabi.launcher"'; then
    VISIBLE=1
    SEEN_MS="$(date +%s%3N)"
    echo "LAUNCHER_FOREGROUND_POLL=$i"
    break
  fi
  sleep 0.2
done
test "$VISIBLE" -eq 1
OFF_SENT=0
python3 - "$WAKE_MS" "$SEEN_MS" <<'PY'
import sys
print("FAST_LANE_LAUNCHER_FOREGROUND_AFTER_SECONDS=%.3f" % ((int(sys.argv[2])-int(sys.argv[1]))/1000.0))
PY
echo "FOREGROUND=$FG"

POST_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
python3 - "$PRE_UPTIME" "$POST_UPTIME" <<'PY'
import sys
before=float(sys.argv[1]); after=float(sys.argv[2])
if after <= before: raise SystemExit("Quick Start unexpectedly reset uptime")
print("QUICK_START_UPTIME_CONTINUITY=PASS")
PY

"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$BASE/frozen-view'"
"${SSH[@]}" "test -f '$BASE/last-good' && test ! -e '$BASE/boot-pending' && test ! -e '$BASE/disabled-failsafe'"
echo OVERLAY_PERSISTED=PASS

echo FAST_LANE_GUARD_LOG_BEGIN
"${SSH[@]}" "tail -100 /tmp/hu.szabi.launcher-wake.log 2>/dev/null"
echo FAST_LANE_GUARD_LOG_END
"${SSH[@]}" "tail -n +$((PRE_LINES+1)) /var/log/messages 2>/dev/null | grep -E 'NL_APP_LAUNCH_BEGIN|NL_VSC' | grep -E 'hu.szabi.launcher|com.webos.app.home|com.webos.app.hdmi2' || true"

"${SSH[@]}" "tail -100 /tmp/hu.szabi.launcher-wake.log 2>/dev/null | grep -q 'quick fast lane accepted'"
echo QUICK_START_FAST_LANE=PASS

COMMITTED=1
echo "ROLLBACK_BACKUP=$BACKUP"
echo FAST_LANE_ROLLOUT=PASS
trap 'rm -rf "$TMP"' EXIT
