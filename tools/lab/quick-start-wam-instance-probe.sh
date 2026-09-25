#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
OVERLAY=hu.szabi.launcher.overlay

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "$SOURCE_KEY" "$TMP/id_rsa"
chmod 600 "$TMP/id_rsa"
ssh-keyscan -T 3 "$TV_HOST" >"$TMP/known_hosts" 2>/dev/null
SSH=(ssh -T -i "$TMP/id_rsa" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$TMP/known_hosts" "$TV")

"${SSH[@]}" true

query() {
  local uri="$1" payload="$2"
  "${SSH[@]}" "luna-send -t 1 -f -w 2500 '$uri' '$payload'" 2>&1 || true
}

MANAGER_INFO="$(query luna://com.webos.applicationManager/dev/managerInfo '{}')"
SAM_RUNNING="$(query luna://com.webos.applicationManager/running '{}')"
SAM_DEV_RUNNING="$(query luna://com.webos.applicationManager/dev/running '{}')"
WAM_RUNNING="$(query luna://com.webos.service.webappmanager/listRunningApps '{"includeSysApps":false}')"
WAM_PROCESSES="$(query luna://com.webos.service.webappmanager/getWebProcessSize '{}')"
FOREGROUND="$(query luna://com.webos.applicationManager/getForegroundAppInfo '{"extraInfo":true}')"

echo "MANAGER_INFO_RAW=$MANAGER_INFO"
echo "SAM_RUNNING_RAW=$SAM_RUNNING"
echo "SAM_DEV_RUNNING_RAW=$SAM_DEV_RUNNING"
echo "WAM_RUNNING_RAW=$WAM_RUNNING"
echo "WAM_PROCESSES_RAW=$WAM_PROCESSES"
echo "FOREGROUND_RAW=$FOREGROUND"

python3 - "$OVERLAY" "$MANAGER_INFO" "$SAM_RUNNING" "$SAM_DEV_RUNNING" "$WAM_RUNNING" "$WAM_PROCESSES" "$FOREGROUND" <<'PY'
import json
import sys

appid = sys.argv[1]
raws = {
    "managerInfo": sys.argv[2],
    "samRunning": sys.argv[3],
    "samDevRunning": sys.argv[4],
    "wamRunning": sys.argv[5],
    "wamProcesses": sys.argv[6],
    "foreground": sys.argv[7],
}

def payload(raw):
    marker = "payload "
    pos = raw.find(marker)
    if pos >= 0:
        raw = raw[pos + len(marker):]
    raw = raw.lstrip()
    value, _ = json.JSONDecoder().raw_decode(raw)
    return value

found = []
for name, raw in raws.items():
    try:
        obj = payload(raw)
    except Exception as exc:
        print(f"{name}: parse failed: {exc}")
        continue

    candidates = []
    if isinstance(obj, dict):
        candidates.extend(obj.get("running", []) if isinstance(obj.get("running"), list) else [])
        candidates.extend(obj.get("foregroundAppInfo", []) if isinstance(obj.get("foregroundAppInfo"), list) else [])
        for proc in obj.get("WebProcesses", []) if isinstance(obj.get("WebProcesses"), list) else []:
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
        if item.get("id") != appid and item.get("appId") != appid:
            continue
        iid = item.get("instanceId")
        wid = item.get("webprocessid") or item.get("processId") or item.get("processid")
        print(f"{name}: overlay instanceId={iid!r} webprocessid={wid!r}")
        if iid:
            found.append((name, str(iid), str(wid or "")))

if not found:
    print("OVERLAY_INSTANCE_ID=NOT_FOUND")
    raise SystemExit(3)

name, iid, wid = found[0]
print(f"OVERLAY_INSTANCE_SOURCE={name}")
print(f"OVERLAY_INSTANCE_ID={iid}")
print(f"OVERLAY_WEBPROCESS_ID={wid}")
print("OVERLAY_INSTANCE_PROBE=PASS")
PY
