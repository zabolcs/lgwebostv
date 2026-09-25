#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
APP=hu.szabi.launcher
DIR=/var/lib/webosbrew/launcher-home

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "$SOURCE_KEY" "$TMP/id_rsa"
chmod 600 "$TMP/id_rsa"
ssh-keyscan -T 3 "$TV_HOST" >"$TMP/known_hosts" 2>/dev/null
SSH=(ssh -T -i "$TMP/id_rsa" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$TMP/known_hosts" "$TV")

"${SSH[@]}" true
READY=0
POWER=""
RUNNING=""
for i in $(seq 1 24); do
  POWER="$("${SSH[@]}" "luna-send -n 1 -f -w 1200 luna://com.webos.service.tvpower/power/getPowerState '{}'" 2>&1 || true)"
  RUNNING="$("${SSH[@]}" "luna-send -n 1 -f -w 1500 luna://com.webos.service.webappmanager/listRunningApps '{\"includeSysApps\":false}'" 2>&1 || true)"
  if echo "$POWER" | grep -Eq '"state"[[:space:]]*:[[:space:]]*"Active"' &&
     echo "$RUNNING" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
    READY=1
    echo "TV_WAM_READY_POLL=$i"
    break
  fi
  sleep 0.5
done
echo "POWER_BEFORE=$POWER"
echo "RUNNING_BEFORE=$RUNNING"
test "$READY" -eq 1
echo "$RUNNING" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher"'

CDP="$(node tools/lab/measure-launcher-cdp.mjs "$APP" 2>/dev/null || true)"
echo "FULL_PRE_CDP=$CDP"
test -n "$CDP"

origin="$("${SSH[@]}" "cat '$DIR/control-origin' 2>/dev/null")"
display="$("${SSH[@]}" "cat '$DIR/display-preferences.json' 2>/dev/null")"
[ -n "$display" ] || display='{}'
APPINFO="$("${SSH[@]}" "luna-send -t 1 -f -w 2000 luna://com.webos.applicationManager/getAppInfo '{\"id\":\"$APP\"}'" 2>&1)"
PAYLOAD="$(python3 - "$APPINFO" "$origin" "$display" "$APP" <<'PY'
import json,sys
raw=sys.argv[1]
marker="payload "
p=raw.find(marker)
if p>=0: raw=raw[p+len(marker):]
desc=json.JSONDecoder().raw_decode(raw.lstrip())[0].get("appInfo")
if not isinstance(desc,dict): raise SystemExit("full appInfo missing")
print(json.dumps({
  "appDesc":desc,
  "appId":sys.argv[4],
  "parameters":{
    "source":"wam-direct-full",
    "controlOrigin":sys.argv[2],
    "displayPreferences":json.loads(sys.argv[3])
  },
  "launchingAppId":"com.webos.app.home",
  "launchingProcId":"",
  "reason":"quick-start-full-probe"
},separators=(",",":")))
PY
)"
echo WAM_FULL_PAYLOAD_READY=PASS

"${SSH[@]}" "luna-send -n 1 -f -w 4000 luna://com.webos.applicationManager/launch '{\"id\":\"com.webos.app.hdmi2\",\"params\":{\"source\":\"wam-full-probe\"}}' >/dev/null"
sleep 1
PRE_LINES="$("${SSH[@]}" "wc -l </var/log/messages 2>/dev/null || echo 0")"
START_MS="$(date +%s%3N)"
RESULT="$("${SSH[@]}" "luna-send -t 1 -f -w 2500 luna://com.webos.service.webappmanager/launchApp '$PAYLOAD'" 2>&1 || true)"
END_MS="$(date +%s%3N)"
echo "WAM_FULL_RESULT=$RESULT"
echo "WAM_FULL_CALL_MS=$((END_MS-START_MS))"
echo "$RESULT" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'

VISIBLE=0
FINAL_CDP=""
for i in $(seq 1 50); do
  FINAL_CDP="$(node tools/lab/measure-launcher-cdp.mjs "$APP" 2>/dev/null || true)"
  if [ -n "$FINAL_CDP" ] && python3 - "$FINAL_CDP" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("hidden") is False and x.get("activated") is True else 1)
PY
  then
    VISIBLE=1
    echo "FULL_VISIBLE_POLL=$i"
    break
  fi
  sleep 0.05
done
echo "FULL_FINAL_CDP=$FINAL_CDP"
test "$VISIBLE" -eq 1

sleep 0.5
"${SSH[@]}" "tail -n +$((PRE_LINES+1)) /var/log/messages 2>/dev/null" >"$TMP/messages.delta"
python3 - "$TMP/messages.delta" "$START_MS" <<'PY'
import re,sys
from datetime import datetime,timezone
from pathlib import Path
start=int(sys.argv[2])/1000.0
first=None
for line in Path(sys.argv[1]).read_text(errors="replace").splitlines():
    if 'NL_VSC' not in line or '"visible":true' not in line or '"app_id":"hu.szabi.launcher"' not in line:
        continue
    m=re.match(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z',line)
    if not m: continue
    ts=datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc).timestamp()
    if ts>=start:
        first=ts-start
        break
if first is None: raise SystemExit("full launcher surface timestamp missing")
print(f"WAM_FULL_VISIBLE_AFTER_SECONDS={first:.3f}")
PY

echo WAM_DIRECT_FULL_PROBE=PASS
