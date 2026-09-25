#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
NAS_API=http://192.168.0.223:8765
APP=hu.szabi.launcher
OVERLAY=hu.szabi.launcher.overlay
INIT=/var/lib/webosbrew/init.d/launcher-home
PIDFILE=/tmp/hu.szabi.launcher-home.pid
DIR=/var/lib/webosbrew/launcher-home
REMOTE_PAYLOAD=/tmp/hu.szabi.launcher-wam-active-payload.json
REMOTE_SIDECAR=/tmp/hu.szabi.launcher-wam-active-sidecar.py
REMOTE_LOG=/tmp/hu.szabi.launcher-wam-active-sidecar.log
REMOTE_PID=/tmp/hu.szabi.launcher-wam-active-sidecar.pid

TMP="$(mktemp -d)"
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
cp "$SOURCE_KEY" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")
SCP=(scp -i "$KEY" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN")

GUARD_STOPPED=0
OFF_SENT=0

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

stop_sidecar() {
  "${SSH[@]}" '
    p=$(cat /tmp/hu.szabi.launcher-wam-active-sidecar.pid 2>/dev/null || true)
    case "$p" in ""|*[!0-9]*) ;; *) kill "$p" 2>/dev/null || true ;; esac
    rm -f /tmp/hu.szabi.launcher-wam-active-sidecar.pid
  ' >/dev/null 2>&1 || true
}

cleanup() {
  rc=$?
  set +e
  if [ "$OFF_SENT" -eq 1 ]; then
    api /api/tv/power '{"state":"on"}' >/dev/null 2>&1 || true
    sleep 2
  fi
  stop_sidecar
  "${SSH[@]}" "rm -f '$REMOTE_PAYLOAD' '$REMOTE_SIDECAR'; luna-send -n 1 -f -w 3000 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  if [ "$GUARD_STOPPED" -eq 1 ]; then start_guard >/dev/null 2>&1 || true; fi
  "${SSH[@]}" "luna-send -n 1 -f -w 5000 luna://com.webos.applicationManager/launch '{\"id\":\"$APP\",\"params\":{\"source\":\"wam-active-probe-cleanup\"}}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

"${SSH[@]}" true
echo "TV_GUARD_SHA=$("${SSH[@]}" "sha256sum '$DIR/guard.sh' 2>/dev/null | awk '{print \$1}'")"
echo "TV_GUARD_VERSION=$("${SSH[@]}" "sed -n '2p' '$DIR/guard.sh' 2>/dev/null")"

stop_guard
echo GUARD_STOPPED=PASS
stop_sidecar
"${SSH[@]}" "luna-send -n 1 -f -w 3000 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true"
sleep 0.4

origin="$("${SSH[@]}" "cat '$DIR/control-origin' 2>/dev/null")"
display="$("${SSH[@]}" "cat '$DIR/display-preferences.json' 2>/dev/null")"
[ -n "$display" ] || display='{}'
preload="$(printf '{"id":"%s","preload":"full","keepAlive":true,"noSplash":true,"params":{"source":"wam-active-preload","launcherHost":"full-overlay","controlOrigin":"%s","displayPreferences":%s}}' "$OVERLAY" "$origin" "$display")"
PRELOAD_RESULT="$("${SSH[@]}" "luna-send -t 1 -f -w 5000 luna://com.webos.applicationManager/launch '$preload'" 2>&1)"
echo "PRELOAD_RESULT=$PRELOAD_RESULT"
echo "$PRELOAD_RESULT" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'

READY=0
CDP=""
for i in $(seq 1 50); do
  CDP="$(node tools/lab/measure-launcher-cdp.mjs "$OVERLAY" 2>/dev/null || true)"
  if [ -n "$CDP" ] && python3 - "$CDP" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("ready") and x.get("hidden") is True else 1)
PY
  then READY=1; echo "PREWARM_READY_POLL=$i"; break; fi
  sleep 0.15
done
echo "PREWARM_CDP=$CDP"
test "$READY" -eq 1

APPINFO="$("${SSH[@]}" "luna-send -t 1 -f -w 2000 luna://com.webos.applicationManager/getAppInfo '{\"id\":\"$OVERLAY\"}'" 2>&1)"
python3 - "$APPINFO" "$origin" "$display" "$OVERLAY" >"$TMP/payload.json" <<'PY'
import json,sys
raw=sys.argv[1]
marker="payload "
p=raw.find(marker)
if p>=0: raw=raw[p+len(marker):]
obj=json.JSONDecoder().raw_decode(raw.lstrip())[0]
desc=obj.get("appInfo")
if not isinstance(desc,dict): raise SystemExit("overlay appInfo missing")
print(json.dumps({
  "appDesc":desc,
  "appId":sys.argv[4],
  "parameters":{
    "source":"wam-active-sidecar",
    "launcherHost":"full-overlay",
    "controlOrigin":sys.argv[2],
    "displayPreferences":json.loads(sys.argv[3])
  },
  "launchingAppId":"com.webos.app.home",
  "launchingProcId":"",
  "reason":"quick-start-active-probe"
},separators=(",",":")))
PY

cat >"$TMP/sidecar.py" <<'PY'
#!/usr/bin/python
from __future__ import print_function
import json, os, subprocess, sys, time

PAYLOAD="/tmp/hu.szabi.launcher-wam-active-payload.json"
LOG="/tmp/hu.szabi.launcher-wam-active-sidecar.log"

def ms():
    return int(time.time()*1000)

def log(msg):
    f=open(LOG,"a")
    f.write("%d %s\n" % (ms(),msg))
    f.flush()
    os.fsync(f.fileno())
    f.close()

payload=open(PAYLOAD).read().strip()
open(LOG,"w").close()
p=subprocess.Popen([
    "luna-send","-i",
    "luna://com.webos.service.tvpower/power/getPowerState",
    '{"subscribe":true}'
],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=1,universal_newlines=True)
armed=False
log("SIDECAR_READY")
try:
    while True:
        line=p.stdout.readline()
        if not line:
            if p.poll() is not None:
                raise SystemExit("power subscription ended")
            time.sleep(0.01)
            continue
        if '"state"' not in line:
            continue
        try:
            state=line.split('"state"',1)[1].split('"',2)[1]
        except Exception:
            continue
        log("POWER_STATE="+state)
        if state not in ("Active","Screen Saver"):
            armed=True
        if state=="Active" and armed:
            active=ms()
            log("ACTIVE_TRIGGER")
            start=ms()
            q=subprocess.Popen([
                "luna-send","-n","1","-f","-w","800",
                "luna://com.webos.service.webappmanager/launchApp",
                payload
            ],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            out=q.communicate()[0]
            end=ms()
            if not isinstance(out,str):
                out=out.decode("utf-8","replace")
            log("WAM_START_MS=%d" % start)
            log("WAM_END_MS=%d" % end)
            log("WAM_RESULT="+out.replace("\n"," "))
            break
finally:
    try: p.terminate()
    except Exception: pass
PY

"${SCP[@]}" "$TMP/payload.json" "$TV:$REMOTE_PAYLOAD" >/dev/null
"${SCP[@]}" "$TMP/sidecar.py" "$TV:$REMOTE_SIDECAR" >/dev/null
"${SSH[@]}" "chmod 700 '$REMOTE_SIDECAR'; rm -f '$REMOTE_LOG' '$REMOTE_PID'; nohup python '$REMOTE_SIDECAR' > /tmp/hu.szabi.launcher-wam-active-sidecar.stdout 2>&1 </dev/null & echo \$! >'$REMOTE_PID'"
for _ in $(seq 1 30); do
  "${SSH[@]}" "grep -q SIDECAR_READY '$REMOTE_LOG' 2>/dev/null" && break
  sleep 0.1
done
"${SSH[@]}" "grep -q SIDECAR_READY '$REMOTE_LOG'"
echo SIDECAR_READY=PASS

"${SSH[@]}" "luna-send -n 1 -f -w 4000 luna://com.webos.applicationManager/launch '{\"id\":\"com.webos.app.hdmi2\",\"params\":{\"source\":\"wam-active-sidecar-baseline\"}}' >/dev/null"
sleep 1.5
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
echo "RUNNER_WAKE_MS=$WAKE_MS"
echo "POWER_ON_RESPONSE=$(api /api/tv/power '{"state":"on"}')"

VISIBLE=0
FINAL_CDP=""
for i in $(seq 1 100); do
  FINAL_CDP="$(node tools/lab/measure-launcher-cdp.mjs "$OVERLAY" 2>/dev/null || true)"
  if [ -n "$FINAL_CDP" ] && python3 - "$FINAL_CDP" <<'PY'
import json,sys
x=json.loads(sys.argv[1])
raise SystemExit(0 if x.get("hidden") is False and x.get("activated") is True and x.get("resume") else 1)
PY
  then
    VISIBLE=1
    echo "VISIBLE_POLL=$i"
    break
  fi
  sleep 0.03
done
test "$VISIBLE" -eq 1
OFF_SENT=0
echo "FINAL_CDP=$FINAL_CDP"

sleep 0.3
SIDECAR_LOG="$("${SSH[@]}" "cat '$REMOTE_LOG' 2>/dev/null")"
echo SIDECAR_LOG_BEGIN
echo "$SIDECAR_LOG"
echo SIDECAR_LOG_END

python3 - "$SIDECAR_LOG" "$FINAL_CDP" "$WAKE_MS" <<'PY'
import json,re,sys
log=sys.argv[1]
cdp=json.loads(sys.argv[2])
wake=int(sys.argv[3])
rows=[]
for line in log.splitlines():
    m=re.match(r'([0-9]+) (.*)',line)
    if m: rows.append((int(m.group(1)),m.group(2)))
active=next((t for t,s in rows if s=="ACTIVE_TRIGGER"),None)
start=next((int(s.split("=",1)[1]) for t,s in rows if s.startswith("WAM_START_MS=")),None)
end=next((int(s.split("=",1)[1]) for t,s in rows if s.startswith("WAM_END_MS=")),None)
if active is None or start is None or end is None:
    raise SystemExit("sidecar timing missing")
resume=int(cdp["resume"])
paint=int(cdp.get("resumePaint") or 0)
print("ACTIVE_TO_WAM_START_MS=%d" % (start-active))
print("WAM_CALL_MS=%d" % (end-start))
print("ACTIVE_TO_RESUME_MS=%d" % (resume-active))
if paint:
    print("ACTIVE_TO_RESUME_PAINT_MS=%d" % (paint-active))
print("RUNNER_WAKE_TO_ACTIVE_MS=%d" % (active-wake))
print("RUNNER_WAKE_TO_RESUME_MS=%d" % (resume-wake))
if paint:
    print("RUNNER_WAKE_TO_RESUME_PAINT_MS=%d" % (paint-wake))
if resume-active < 0 or resume-active > 1200:
    raise SystemExit("direct WAM Active path outside expected bound")
print("WAM_ACTIVE_SIDECAR_TIMING=PASS")
PY

POST_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
python3 - "$PRE_UPTIME" "$POST_UPTIME" <<'PY'
import sys
if float(sys.argv[2]) <= float(sys.argv[1]): raise SystemExit("uptime reset")
print("QUICK_START_UPTIME_CONTINUITY=PASS")
PY

echo WAM_ACTIVE_SIDECAR_PROBE=PASS
