#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
OVERLAY=hu.szabi.launcher.overlay
DIR=/var/lib/webosbrew/launcher-home
EVENTS=/tmp/hu.szabi.launcher-app-life-events.log
STATUS=/tmp/hu.szabi.launcher-app-life-status.log
EVENTS_PID=/tmp/hu.szabi.launcher-app-life-events.pid
STATUS_PID=/tmp/hu.szabi.launcher-app-life-status.pid

TMP="$(mktemp -d)"
cp "$SOURCE_KEY" "$TMP/id_rsa"
chmod 600 "$TMP/id_rsa"
ssh-keyscan -T 3 "$TV_HOST" >"$TMP/known_hosts" 2>/dev/null
SSH=(ssh -T -i "$TMP/id_rsa" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$TMP/known_hosts" "$TV")

cleanup() {
  set +e
  "${SSH[@]}" '
    for f in /tmp/hu.szabi.launcher-app-life-events.pid /tmp/hu.szabi.launcher-app-life-status.pid; do
      p=$(cat "$f" 2>/dev/null || true)
      case "$p" in ""|*[!0-9]*) ;; *) kill "$p" 2>/dev/null || true ;; esac
      rm -f "$f"
    done
  ' >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

"${SSH[@]}" true
"${SSH[@]}" "rm -f '$EVENTS' '$STATUS' '$EVENTS_PID' '$STATUS_PID';
  nohup luna-send -i -f luna://com.webos.applicationManager/getAppLifeEvents '{\"subscribe\":true}' >'$EVENTS' 2>&1 </dev/null & echo \$! >'$EVENTS_PID';
  nohup luna-send -i -f luna://com.webos.applicationManager/getAppLifeStatus '{\"subscribe\":true}' >'$STATUS' 2>&1 </dev/null & echo \$! >'$STATUS_PID'"
sleep 0.4

origin="$("${SSH[@]}" "cat '$DIR/control-origin' 2>/dev/null")"
display="$("${SSH[@]}" "cat '$DIR/display-preferences.json' 2>/dev/null")"
[ -n "$display" ] || display='{}'
preload="$(printf '{"id":"%s","preload":"full","keepAlive":true,"noSplash":true,"params":{"source":"instance-probe","launcherHost":"full-overlay","controlOrigin":"%s","displayPreferences":%s}}' "$OVERLAY" "$origin" "$display")"
PRELOAD_RESULT="$("${SSH[@]}" "luna-send-pub -t 1 -f -w 5000 luna://com.webos.applicationManager/launch '$preload'" 2>&1 || true)"
echo "PRELOAD_RESULT=$PRELOAD_RESULT"
sleep 0.8

EVENTS_RAW="$("${SSH[@]}" "cat '$EVENTS' 2>/dev/null || true")"
STATUS_RAW="$("${SSH[@]}" "cat '$STATUS' 2>/dev/null || true")"
WAM_RUNNING="$("${SSH[@]}" "luna-send -t 1 -f -w 2500 luna://com.webos.service.webappmanager/listRunningApps '{\"includeSysApps\":false}'" 2>&1 || true)"
WAM_PROCESSES="$("${SSH[@]}" "luna-send -t 1 -f -w 2500 luna://com.webos.service.webappmanager/getWebProcessSize '{}'" 2>&1 || true)"

echo "APP_LIFE_EVENTS_RAW=$EVENTS_RAW"
echo "APP_LIFE_STATUS_RAW=$STATUS_RAW"
echo "WAM_RUNNING_RAW=$WAM_RUNNING"
echo "WAM_PROCESSES_RAW=$WAM_PROCESSES"

python3 - "$OVERLAY" "$EVENTS_RAW" "$STATUS_RAW" "$WAM_RUNNING" "$WAM_PROCESSES" <<'PY'
import json
import sys

appid = sys.argv[1]
sources = {
    "lifeEvents": sys.argv[2],
    "lifeStatus": sys.argv[3],
    "wamRunning": sys.argv[4],
    "wamProcesses": sys.argv[5],
}

def decode_objects(raw):
    marker = "payload "
    if marker in raw:
        raw = raw.replace(marker, "")
    out = []
    dec = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
        start = raw.find("{", pos)
        if start < 0:
            break
        try:
            obj, used = dec.raw_decode(raw[start:])
            out.append(obj)
            pos = start + used
        except Exception:
            pos = start + 1
    return out

found = []
for name, raw in sources.items():
    for obj in decode_objects(raw):
        candidates = []
        if isinstance(obj, dict):
            candidates.append(obj)
            if isinstance(obj.get("running"), list):
                candidates.extend(obj["running"])
            if isinstance(obj.get("WebProcesses"), list):
                for proc in obj["WebProcesses"]:
                    if not isinstance(proc, dict):
                        continue
                    for app in proc.get("runningApps", []) if isinstance(proc.get("runningApps"), list) else []:
                        if isinstance(app, dict):
                            app = dict(app)
                            app.setdefault("webprocessid", proc.get("pid"))
                            candidates.append(app)
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if item.get("appId") != appid and item.get("id") != appid:
                continue
            iid = item.get("instanceId")
            wid = item.get("webprocessid") or item.get("processId") or item.get("processid")
            event = item.get("event") or item.get("status")
            print(f"{name}: overlay event={event!r} instanceId={iid!r} webprocessid={wid!r}")
            if iid:
                found.append((name, str(iid), str(wid or "")))

if not found:
    print("OVERLAY_INSTANCE_ID=NOT_FOUND")
    raise SystemExit(3)

name, iid, wid = found[-1]
print(f"OVERLAY_INSTANCE_SOURCE={name}")
print(f"OVERLAY_INSTANCE_ID={iid}")
print(f"OVERLAY_WEBPROCESS_ID={wid}")
print("OVERLAY_INSTANCE_PROBE=PASS")
PY
