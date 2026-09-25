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
trap 'rm -rf "$TMP"' EXIT
cp "$SOURCE_KEY" "$TMP/id_rsa"
chmod 600 "$TMP/id_rsa"
ssh-keyscan -T 3 "$TV_HOST" >"$TMP/known_hosts" 2>/dev/null
SSH=(ssh -T -i "$TMP/id_rsa" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$TMP/known_hosts" "$TV")
GUARD_STOPPED=0
WAM_EVENT_FILE=/tmp/hu.szabi.launcher-wam-process-created.log
WAM_EVENT_PID=/tmp/hu.szabi.launcher-wam-process-created.pid

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
  "${SSH[@]}" '
    p=$(cat /tmp/hu.szabi.launcher-wam-process-created.pid 2>/dev/null || true)
    case "$p" in ""|*[!0-9]*) ;;
      *) kill "$p" 2>/dev/null || true ;;
    esac
    rm -f /tmp/hu.szabi.launcher-wam-process-created.pid
  ' >/dev/null 2>&1 || true
  "${SSH[@]}" "luna-send -n 1 -f -w 3000 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  if [ "$GUARD_STOPPED" -eq 1 ]; then start_guard >/dev/null 2>&1 || true; fi
  "${SSH[@]}" "luna-send -n 1 -f -w 5000 luna://com.webos.applicationManager/launch '{\"id\":\"$APP\",\"params\":{\"source\":\"wam-reactivate-probe-cleanup\"}}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

"${SSH[@]}" true
"${SSH[@]}" "luna-send -n 1 -f -w 3000 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true"
sleep 0.5
"${SSH[@]}" "rm -f '$WAM_EVENT_FILE' '$WAM_EVENT_PID'; nohup luna-send -i luna://com.webos.service.webappmanager/webProcessCreated '{\"subscribe\":true}' >'$WAM_EVENT_FILE' 2>&1 </dev/null & echo \$! >'$WAM_EVENT_PID'"
sleep 0.3
echo WAM_PROCESS_SUBSCRIPTION=PASS

origin="$("${SSH[@]}" "cat '$DIR/control-origin' 2>/dev/null")"
display="$("${SSH[@]}" "cat '$DIR/display-preferences.json' 2>/dev/null")"
[ -n "$display" ] || display='{}'
preload="$(printf '{"id":"%s","preload":"full","keepAlive":true,"noSplash":true,"params":{"source":"preload","launcherHost":"full-overlay","controlOrigin":"%s","displayPreferences":%s}}' "$OVERLAY" "$origin" "$display")"
PRELOAD_RESULT="$("${SSH[@]}" "luna-send-pub -t 1 -f -w 5000 luna://com.webos.applicationManager/launch '$preload' 2>&1")"
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
RUNNING="$("${SSH[@]}" "luna-send -t 1 -f -w 2000 luna://com.webos.service.webappmanager/listRunningApps '{\"includeSysApps\":false}'" 2>&1)"
PROCESSES="$("${SSH[@]}" "luna-send -t 1 -f -w 2000 luna://com.webos.service.webappmanager/getWebProcessSize '{}'" 2>&1)"
EVENTS="$("${SSH[@]}" "cat '$WAM_EVENT_FILE' 2>/dev/null || true")"
LOGS="$("${SSH[@]}" "grep -a -h -i '$OVERLAY' /var/log/messages* /var/log/legacy-log* 2>/dev/null | tail -200" || true)"
echo "APPINFO_RAW=$APPINFO"
echo "RUNNING_RAW=$RUNNING"
echo "PROCESSES_RAW=$PROCESSES"
echo "WAM_PROCESS_EVENTS_RAW=$EVENTS"
echo "OVERLAY_LOGS_RAW=$LOGS"
PAYLOAD="$(python3 - "$APPINFO" "$RUNNING" "$PROCESSES" "$EVENTS" "$LOGS" "$CDP" "$origin" "$display" "$OVERLAY" <<'PY'
import json,sys
def timed_payload(raw):
    marker="payload "
    pos=raw.find(marker)
    if pos >= 0:
        raw=raw[pos+len(marker):]
    raw=raw.lstrip()
    value,_=json.JSONDecoder().raw_decode(raw)
    return value
appinfo=timed_payload(sys.argv[1])
running=timed_payload(sys.argv[2])
processes=timed_payload(sys.argv[3])
events_raw=sys.argv[4]
logs_raw=sys.argv[5]
cdp=json.loads(sys.argv[6])
origin=sys.argv[7]; display=json.loads(sys.argv[8]); appid=sys.argv[9]
item=next((x for x in running.get("running",[]) if x.get("id")==appid),None)
instance_id=(item or {}).get("instanceId")
webprocess_id=(item or {}).get("webprocessid")
if not instance_id:
    raw=cdp.get("launchParams") or ""
    try:
        parsed=json.loads(raw) if isinstance(raw,str) else raw
    except Exception:
        parsed={}
    for _ in range(8):
        if not isinstance(parsed,dict):
            break
        if parsed.get("instanceId"):
            instance_id=str(parsed["instanceId"])
            break
        if "launchParams" in parsed:
            parsed=parsed["launchParams"]
        elif "parameters" in parsed:
            parsed=parsed["parameters"]
        elif isinstance(parsed.get("params"),dict):
            parsed=parsed["params"]
        elif isinstance(parsed.get("payload"),dict):
            parsed=parsed["payload"]
        else:
            break
        if isinstance(parsed,str):
            try: parsed=json.loads(parsed)
            except Exception: break
if not instance_id:
    decoder=json.JSONDecoder()
    pos=0
    while pos < len(events_raw):
        start=events_raw.find("{",pos)
        if start < 0: break
        try:
            event,end=decoder.raw_decode(events_raw[start:])
            pos=start+end
        except Exception:
            pos=start+1
            continue
        if event.get("id")==appid and event.get("instanceId"):
            instance_id=event["instanceId"]
            webprocess_id=event.get("webprocessid") or webprocess_id
if not instance_id:
    for proc in processes.get("WebProcesses",[]):
        for app in proc.get("runningApps",[]):
            if app.get("id")==appid and app.get("instanceId"):
                instance_id=app["instanceId"]
                webprocess_id=proc.get("pid") or webprocess_id
                break
        if instance_id:
            break
if not instance_id:
    import re
    patterns=[
        r'"instanceId"\s*:\s*"([^"]+)"',
        r'"INSTANCE_ID"\s*:\s*"([^"]+)"',
        r'INSTANCE_ID[^A-Za-z0-9._:-]+([A-Za-z0-9._:-]{8,})',
        r'instanceId[^A-Za-z0-9._:-]+([A-Za-z0-9._:-]{8,})'
    ]
    for line in reversed(logs_raw.splitlines()):
        if appid not in line:
            continue
        for pattern in patterns:
            m=re.search(pattern,line)
            if m:
                instance_id=m.group(1)
                break
        if instance_id:
            break
if not instance_id:
    raise SystemExit("overlay instanceId missing from launchParams/WAM events/running/process data/TV logs")
desc=appinfo.get("appInfo")
if not isinstance(desc,dict):
    raise SystemExit("overlay appInfo missing")
payload={
  "appDesc":desc,
  "appId":appid,
  "parameters":{
    "source":"wam-direct-reactivate",
    "launcherHost":"full-overlay",
    "controlOrigin":origin,
    "displayPreferences":display
  },
  "launchingAppId":"com.webos.app.home",
  "launchingProcId":"",
  "reason":"quick-start-probe",
  "instanceId":instance_id
}
print(json.dumps(payload,separators=(",",":")))
print("WAM_INSTANCE_ID="+str(instance_id),file=sys.stderr)
print("WAM_WEBPROCESS_ID="+str(webprocess_id or ""),file=sys.stderr)
PY
)"
echo "WAM_PAYLOAD_READY=PASS"


"${SSH[@]}" "luna-send -n 1 -f -w 4000 luna://com.webos.applicationManager/launch '{\"id\":\"com.webos.app.hdmi2\",\"params\":{\"source\":\"wam-reactivate-probe\"}}' >/dev/null"
sleep 1
stop_guard
echo GUARD_STOPPED=PASS
PRE_LINES="$("${SSH[@]}" "wc -l </var/log/messages 2>/dev/null || echo 0")"
START_MS="$(date +%s%3N)"
RESULT="$("${SSH[@]}" "luna-send-pub -t 1 -f -w 2500 luna://com.webos.service.webappmanager/launchApp '$PAYLOAD' 2>&1")"
END_MS="$(date +%s%3N)"
echo "WAM_LAUNCH_RESULT=$RESULT"
echo "WAM_LAUNCH_CALL_MS=$((END_MS-START_MS))"
echo "$RESULT" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'

VISIBLE=0
for i in $(seq 1 30); do
  CDP="$(node tools/lab/measure-launcher-cdp.mjs "$OVERLAY" 2>/dev/null || true)"
  if [ -n "$CDP" ] && python3 - "$CDP" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("hidden") is False and x.get("activated") is True else 1)
PY
  then VISIBLE=1; echo "WAM_VISIBLE_POLL=$i"; break; fi
  sleep 0.05
done
test "$VISIBLE" -eq 1

sleep 1
"${SSH[@]}" "tail -n +$((PRE_LINES+1)) /var/log/messages 2>/dev/null" >"$TMP/messages.delta"
python3 - "$TMP/messages.delta" "$START_MS" <<'PY'
import re,sys
from datetime import datetime,timezone
from pathlib import Path
wake=int(sys.argv[2])/1000.0
first=None
for line in Path(sys.argv[1]).read_text(errors="replace").splitlines():
    if 'NL_VSC' not in line or '"visible":true' not in line or '"app_id":"hu.szabi.launcher.overlay"' not in line:
        continue
    m=re.match(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z',line)
    if not m: continue
    ts=datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc).timestamp()
    if ts >= wake:
        first=ts-wake
        break
if first is None:
    raise SystemExit("no overlay visible surface after direct WAM call")
print(f"WAM_OVERLAY_VISIBLE_AFTER_SECONDS={first:.3f}")
PY

echo WAM_REACTIVATE_PROBE=PASS
