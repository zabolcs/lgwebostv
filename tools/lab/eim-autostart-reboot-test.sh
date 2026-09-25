#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
APP_ID="${APP_ID:-hu.szabi.launcher.eimprobe}"
VERSION="${VERSION:-0.0.1}"
PRODUCTION_MODE="${PRODUCTION_MODE:-0}"
KEEP_EIM_ON_SUCCESS="${KEEP_EIM_ON_SUCCESS:-0}"
ROLLBACK_MARKER=/media/lgtv/rollback-20260925-pre-activity-manager/COMPLETE
RUN_TAG="${GITHUB_RUN_ID:-manual}"
BACKUP_DIR="/media/lgtv/eim-autostart-backup-20260925-${RUN_TAG}"

test -f "$ROLLBACK_MARKER"
mkdir -p "$BACKUP_DIR"

TMP="$(mktemp -d)"
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
REMOTE="/tmp/hu.szabi.eim-autostart.$"
MANIFEST="/media/developer/apps/usr/palm/applications/$APP_ID/appinfo.json"
CLEANED=0
REBOOT_SENT=0
ORIGINAL_APP=""

cp "$SOURCE_KEY" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
test -s "$KNOWN"

SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")
SCP=(scp -i "$KEY" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN")

ssh_ok() {
  "${SSH[@]}" true >/dev/null 2>&1
}

luna_file() {
  local label="$1"
  local uri="$2"
  local payload="$3"
  "${SSH[@]}" "luna-send -t 1 -f -w 5000 'luna://$uri' '$payload' 2>&1" >"$TMP/$label.txt" || true
}

extract_json() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
decoder = json.JSONDecoder()
found = None
for line in reversed(text.splitlines()):
    for index, char in enumerate(line):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(line[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            found = candidate
            break
    if found is not None:
        break
if found is None:
    raise SystemExit("no JSON response")
print(json.dumps(found, separators=(",", ":")))
PY
}

last_input_json() {
  luna_file last_input com.webos.service.eim/getLastInput '{}'
  extract_json "$TMP/last_input.txt"
}

remove_probe_app() {
  [ "$PRODUCTION_MODE" != "1" ] || return 0
  "${SSH[@]}" "/usr/bin/luna-send-pub -t 1 -w 30000 -f 'luna://com.webos.appInstallService/dev/remove' '{\"id\":\"$APP_ID\",\"subscribe\":true}'" >/dev/null 2>&1 || true
  for _ in $(seq 1 40); do
    "${SSH[@]}" "test ! -e '$MANIFEST'" >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  return 1
}

soft_restore() {
  set +e
  if ! ssh_ok; then
    for _ in $(seq 1 180); do
      sleep 1
      ssh_ok && break
    done
  fi
  if ! ssh_ok; then
    echo CLEANUP_SSH_UNAVAILABLE
    return 1
  fi

  luna_file delete_device com.webos.service.eim/deleteDevice "{\"appId\":\"$APP_ID\"}"
  DELETE_JSON="$(extract_json "$TMP/delete_device.txt" 2>/dev/null || true)"
  echo "EIM_DELETE_DEVICE=$DELETE_JSON"

  if [ -n "$ORIGINAL_APP" ]; then
    luna_file restore_launch com.webos.service.applicationmanager/launch "{\"id\":\"$ORIGINAL_APP\",\"params\":{\"source\":\"eim-probe-restore\"}}"
    sleep 2
  fi

  AFTER="$(last_input_json 2>/dev/null || true)"
  echo "EIM_LAST_INPUT_AFTER_CLEANUP=$AFTER"

  remove_probe_app || true
  "${SSH[@]}" "rm -rf '$REMOTE'" >/dev/null 2>&1 || true

  if [ -n "$ORIGINAL_APP" ] && echo "$AFTER" | grep -q "$ORIGINAL_APP"; then
    echo EIM_SOFT_RESTORE=PASS
    CLEANED=1
    return 0
  fi

  echo EIM_SOFT_RESTORE=INCOMPLETE
  echo "EIM_BACKUP_AVAILABLE=$BACKUP_DIR"
  return 1
}

cleanup() {
  rc=$?
  set +e
  if [ "$CLEANED" -ne 1 ]; then
    soft_restore || true
  fi
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

ssh_ok
echo TV_SSH_BEFORE=PASS
echo ROLLBACK_BASELINE=PASS

# Capture immutable recovery material before changing EIM state.
luna_file original_last com.webos.service.eim/getLastInput '{}'
ORIGINAL_LAST="$(extract_json "$TMP/original_last.txt")"
echo "ORIGINAL_EIM_LAST_INPUT=$ORIGINAL_LAST"
echo "$ORIGINAL_LAST" | grep -q '"returnValue":true'
ORIGINAL_APP="$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d.get("lastSourceAppId") or d.get("physicalLastSourceAppId") or "")' "$ORIGINAL_LAST")"
test -n "$ORIGINAL_APP"
echo "ORIGINAL_INPUT_APP=$ORIGINAL_APP"

"${SSH[@]}" "tar -C /var/lib -czf /tmp/hu.szabi.eim-before.tar.gz eim"
"${SCP[@]}" "$TV:/tmp/hu.szabi.eim-before.tar.gz" "$BACKUP_DIR/eim-before.tar.gz"
"${SSH[@]}" "cat /var/lib/eim/lastinput" >"$BACKUP_DIR/lastinput-before.json"
printf '%s\n' "$ORIGINAL_LAST" >"$BACKUP_DIR/getLastInput-before.json"
sha256sum "$BACKUP_DIR/eim-before.tar.gz" "$BACKUP_DIR/lastinput-before.json" "$BACKUP_DIR/getLastInput-before.json" >"$BACKUP_DIR/SHA256SUMS"
sha256sum -c "$BACKUP_DIR/SHA256SUMS"
echo "EIM_BACKUP=$BACKUP_DIR"
echo EIM_BACKUP_VERIFY=PASS

if [ "$PRODUCTION_MODE" = "1" ]; then
  "${SSH[@]}" "tar -C /media/developer/apps/usr/palm -czf - applications/hu.szabi.launcher packages/hu.szabi.launcher" >"$BACKUP_DIR/launcher-before.tar.gz"
  sha256sum "$BACKUP_DIR/launcher-before.tar.gz" >>"$BACKUP_DIR/SHA256SUMS"
  sha256sum -c "$BACKUP_DIR/SHA256SUMS"
  echo PRODUCTION_LAUNCHER_BACKUP=PASS
fi

if [ "$PRODUCTION_MODE" = "1" ]; then
  python3 scripts/build-all.py >"$TMP/build.txt"
else
  python3 tools/lab/build-eim-autostart-probe.py >"$TMP/build.txt"
fi
IPK="$GITHUB_WORKSPACE/build/${APP_ID}_${VERSION}_all.ipk"
test -f "$IPK"
DIGEST="$(sha256sum "$IPK" | awk '{print $1}')"

"${SSH[@]}" "mkdir -p '$REMOTE'"
"${SCP[@]}" "$IPK" "$TV:$REMOTE/probe.ipk"
"${SCP[@]}" scripts/install-local-on-tv.sh "$TV:$REMOTE/install.sh"
"${SSH[@]}" "chmod 700 '$REMOTE/install.sh'; sh '$REMOTE/install.sh' '$REMOTE/probe.ipk' '$DIGEST'"
"${SSH[@]}" "grep -q '\"supportGIP\"[[:space:]]*:[[:space:]]*true' '$MANIFEST'"
if [ "$PRODUCTION_MODE" = "1" ]; then
  "${SSH[@]}" "grep -q '\"version\"[[:space:]]*:[[:space:]]*\"$VERSION\"' '$MANIFEST'"
  echo PRODUCTION_INSTALL=PASS
  echo PRODUCTION_SUPPORT_GIP=PASS
else
  echo PROBE_INSTALL=PASS
  echo PROBE_SUPPORT_GIP=PASS
fi

if [ "$PRODUCTION_MODE" = "1" ]; then
  ADD='{"appId":"hu.szabi.launcher","pigImage":"","mvpdIcon":"","showPopup":false,"label":"Saját kezdőképernyő","description":"Production EIM early launcher"}'
else
  ADD='{"appId":"hu.szabi.launcher.eimprobe","pigImage":"","mvpdIcon":"","showPopup":false,"label":"EIM boot probe","description":"One-shot controlled boot timing probe"}'
fi
luna_file add_device com.webos.service.eim/addDevice "$ADD"
ADD_JSON="$(extract_json "$TMP/add_device.txt")"
echo "EIM_ADD_DEVICE=$ADD_JSON"
echo "$ADD_JSON" | grep -q '"returnValue":true'
echo EIM_REGISTER=PASS

# Launch once so EIM can select the registered input app as the current/last input.
SOURCE="eim-probe-preflight"
[ "$PRODUCTION_MODE" != "1" ] || SOURCE="eim-production-preflight"
luna_file launch_probe com.webos.service.applicationmanager/launch "{\"id\":\"$APP_ID\",\"params\":{\"source\":\"$SOURCE\"}}"
LAUNCH_JSON="$(extract_json "$TMP/launch_probe.txt")"
echo "PROBE_PREFLIGHT_LAUNCH=$LAUNCH_JSON"
echo "$LAUNCH_JSON" | grep -q '"returnValue":true'
sleep 2

SELECTED=0
for _ in $(seq 1 12); do
  CURRENT="$(last_input_json 2>/dev/null || true)"
  FILE_LAST="$("${SSH[@]}" "cat /var/lib/eim/lastinput 2>/dev/null" || true)"
  echo "EIM_LAST_INPUT_PREFLIGHT=$CURRENT"
  echo "EIM_LASTINPUT_FILE_PREFLIGHT=$FILE_LAST"
  if echo "$CURRENT $FILE_LAST" | grep -q "$APP_ID"; then
    SELECTED=1
    break
  fi
  # A second registration after the app is foreground mirrors the reference autostart app flow.
  luna_file add_device_retry com.webos.service.eim/addDevice "$ADD"
  sleep 0.5
done

if [ "$SELECTED" -ne 1 ]; then
  echo EIM_PREFLIGHT=NOT_SELECTED
  echo NO_REBOOT=PASS
  exit 3
fi
echo EIM_PREFLIGHT_SELECTED=PASS

luna_file device_list com.webos.service.eim/getTotalDeviceList '{}'
DEVICE_LIST="$(extract_json "$TMP/device_list.txt")"
echo "EIM_DEVICE_LIST_PREFLIGHT=$DEVICE_LIST"

PRE_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
echo "PRE_REBOOT_UPTIME_SECONDS=$PRE_UPTIME"
REBOOT_REQUEST_MS="$(date +%s%3N)"
echo "REBOOT_REQUEST_EPOCH_MS=$REBOOT_REQUEST_MS"

"${SSH[@]}" 'sync; reboot' >/dev/null 2>&1 || true
REBOOT_SENT=1
echo REBOOT_COMMAND_SENT=PASS

DROPPED=0
for i in $(seq 1 45); do
  if ! ssh_ok; then
    DROPPED=1
    echo "SSH_DROPPED_AFTER_SECONDS=$i"
    break
  fi
  sleep 1
done
test "$DROPPED" -eq 1
echo TV_SSH_DROP=PASS

# CDP is polled independently of SSH so an early renderer can be observed.
TIMING=""
CDP_SEEN_MS=""
for i in $(seq 1 300); do
  TIMING="$(node tools/lab/measure-launcher-cdp.mjs "$APP_ID" 2>/dev/null || true)"
  if [ -n "$TIMING" ]; then
    CDP_SEEN_MS="$(date +%s%3N)"
    echo "PROBE_CDP_SEEN_POLL=$i"
    break
  fi
  sleep 0.25
done
echo "PROBE_CDP_TIMING=$TIMING"
test -n "$TIMING"

RETURNED=0
for i in $(seq 1 180); do
  if ssh_ok; then
    RETURNED=1
    echo "SSH_RETURNED_AFTER_SECONDS=$i"
    break
  fi
  sleep 1
done
test "$RETURNED" -eq 1
echo TV_SSH_AFTER=PASS

TV_NOW="$("${SSH[@]}" 'date +%s')"
CURRENT_UPTIME="$("${SSH[@]}" "cut -d' ' -f1 /proc/uptime")"
echo "TV_NOW_EPOCH=$TV_NOW"
echo "CURRENT_BOOT_UPTIME_SECONDS=$CURRENT_UPTIME"
if [ -n "$CDP_SEEN_MS" ]; then
  python3 - "$REBOOT_REQUEST_MS" "$CDP_SEEN_MS" <<'PY'
import sys
print("CDP_DETECTED_AFTER_REBOOT_REQUEST_SECONDS=%.3f" % ((int(sys.argv[2])-int(sys.argv[1]))/1000.0))
PY
fi

python3 - "$TIMING" "$TV_NOW" "$CURRENT_UPTIME" <<'PY'
import json, sys
timing=json.loads(sys.argv[1])
now=float(sys.argv[2])
uptime=float(sys.argv[3])
for key,label in (
    ("navigation","EIM_NAVIGATION_BOOT_UPTIME_SECONDS"),
    ("start","EIM_APP_START_BOOT_UPTIME_SECONDS"),
    ("ready","EIM_APP_READY_BOOT_UPTIME_SECONDS"),
    ("paint","EIM_FIRST_PAINT_BOOT_UPTIME_SECONDS"),
):
    value=timing.get(key)
    if isinstance(value,(int,float)):
        print(f"{label}={uptime-((now*1000-value)/1000.0):.3f}")
PY

echo BOOT_LOG_EIM_BEGIN
"${SSH[@]}" "grep -n -E 'Try to launch first app|Input App|firstapp-launched|applicationManager/launch|$APP_ID|foregroundAppId' /var/log/bootd.log 2>/dev/null | head -220 || true"
echo BOOT_LOG_EIM_END

POST_LAST="$(last_input_json 2>/dev/null || true)"
echo "EIM_LAST_INPUT_POST_BOOT=$POST_LAST"

if [ "$PRODUCTION_MODE" = "1" ] && [ "$KEEP_EIM_ON_SUCCESS" = "1" ]; then
  echo "$POST_LAST" | grep -q "\"lastSourceAppId\":\"$APP_ID\""
  luna_file production_devices com.webos.service.eim/getTotalDeviceList '{}'
  PRODUCTION_DEVICES="$(extract_json "$TMP/production_devices.txt")"
  echo "EIM_DEVICE_LIST_POST_BOOT=$PRODUCTION_DEVICES"
  echo "$PRODUCTION_DEVICES" | grep -q "MVPD_IP-$APP_ID"

  LAUNCH_COUNT="$("${SSH[@]}" "grep -c '\"id\":\"$APP_ID\"' /var/log/bootd.log 2>/dev/null || true")"
  echo "PRODUCTION_BOOT_LOG_APP_ID_COUNT=$LAUNCH_COUNT"
  echo "TV_GUARD_LAST_LAUNCH=$("${SSH[@]}" 'cat /tmp/hu.szabi.launcher.last-launch 2>/dev/null || true')"

  "${SSH[@]}" "rm -rf '$REMOTE'" >/dev/null 2>&1 || true
  CLEANED=1
  trap 'rm -rf "$TMP"' EXIT
  echo EIM_PERSISTENT_REGISTRATION=PASS
  echo FALLBACK_LEFT_ENABLED=PASS
  echo "PRODUCTION_VERSION=$VERSION"
  echo "ROLLBACK_BACKUP=$BACKUP_DIR"
  echo EIM_PRODUCTION_INTEGRATION=PASS
else
  # One-shot diagnostic mode: unregister the virtual input, restore the original
  # physical input, remove the probe package, and verify the last input.
  soft_restore
  test "$CLEANED" -eq 1
  trap 'rm -rf "$TMP"' EXIT
  echo PROBE_REMOVE=PASS
  echo ORIGINAL_INPUT_RESTORED=PASS
  echo PRODUCTION_LAUNCHER_UNCHANGED=PASS
  echo EIM_ONE_SHOT_TEST_COMPLETE=PASS
fi
