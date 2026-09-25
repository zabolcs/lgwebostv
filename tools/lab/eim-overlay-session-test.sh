#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
APP_ID=hu.szabi.launcher
HDMI_APP=com.webos.app.hdmi2
RUN_TAG="${GITHUB_RUN_ID:-manual}"
BACKUP="/media/lgtv/eim-overlay-session-backup-20260925-${RUN_TAG}"
BASE=/var/lib/webosbrew/launcher-eim
RUNTIME="$BASE/runtime"
FROZEN="$BASE/frozen-view"
REMOTE=/tmp/hu_szabi_eim_overlay_session

mkdir -p "$BACKUP"
TMP="$(mktemp -d)"
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
cp "$SOURCE_KEY" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
test -s "$KNOWN"
SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")
SCP=(scp -i "$KEY" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN")

luna() {
  local uri="$1"
  local payload="$2"
  "${SSH[@]}" "luna-send -t 1 -f -w 5000 'luna://$uri' '$payload' 2>&1"
}

cleanup() {
  set +e
  "${SSH[@]}" "mountpoint -q /var/lib/eim && umount /var/lib/eim || true; mountpoint -q '$FROZEN' && umount '$FROZEN' || true" >/dev/null 2>&1
  luna com.webos.service.applicationmanager/launch '{"id":"hu.szabi.launcher","params":{"source":"eim-overlay-session-restore"}}' >/dev/null 2>&1 || true
  sleep 2
  "${SSH[@]}" "rm -rf '$BASE' '$REMOTE'" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

"${SSH[@]}" true
echo TV_SSH=PASS
"${SSH[@]}" "test ! -e '$BASE'"
if "${SSH[@]}" "mountpoint -q /var/lib/eim"; then
  echo PREEXISTING_EIM_MOUNT
  exit 2
fi

BASELINE_LAST="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
echo "BASELINE_LASTINPUT=$BASELINE_LAST"
echo "$BASELINE_LAST" | grep -q '"appId":"hu.szabi.launcher"'

BASE_DB_SHA="$("${SSH[@]}" "sha256sum /var/lib/eim/eim_device_db.json | awk '{print \$1}'")"
BASE_LAST_SHA="$("${SSH[@]}" "sha256sum /var/lib/eim/lastinput | awk '{print \$1}'")"
echo "BASE_DB_SHA=$BASE_DB_SHA"
echo "BASE_LAST_SHA=$BASE_LAST_SHA"

"${SSH[@]}" "tar -C /var/lib -czf - eim" >"$BACKUP/eim-before.tar.gz"
printf '%s\n' "$BASE_DB_SHA" >"$BACKUP/eim-device-db.sha256"
printf '%s\n' "$BASE_LAST_SHA" >"$BACKUP/lastinput.sha256"
sha256sum "$BACKUP/eim-before.tar.gz" >"$BACKUP/SHA256SUMS"
sha256sum -c "$BACKUP/SHA256SUMS"
echo "BACKUP_DIR=$BACKUP"
echo BACKUP=PASS

"${SSH[@]}" "mkdir -p '$RUNTIME' '$FROZEN' '$REMOTE'; cp -a /var/lib/eim/. '$RUNTIME/'; touch '$BASE/enabled'"
"${SCP[@]}" tools/generated-tv-scripts/launcher-eim-overlay "$TV:$REMOTE/overlay.sh"
"${SSH[@]}" "chmod 700 '$REMOTE/overlay.sh'; sh -n '$REMOTE/overlay.sh'; '$REMOTE/overlay.sh'"
echo OVERLAY_SCRIPT=PASS

"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$FROZEN'"
MOUNT_INFO="$("${SSH[@]}" "findmnt /var/lib/eim; findmnt '$FROZEN'")"
echo "MOUNT_INFO=$MOUNT_INFO"

FROZEN_LAST="$("${SSH[@]}" "cat '$FROZEN/lastinput'")"
echo "FROZEN_LASTINPUT_BEFORE_HDMI=$FROZEN_LAST"
echo "$FROZEN_LAST" | grep -q '"appId":"hu.szabi.launcher"'

luna com.webos.service.applicationmanager/launch '{"id":"com.webos.app.hdmi2","params":{"source":"eim-overlay-session-test"}}' >"$TMP/hdmi.txt"
cat "$TMP/hdmi.txt"
sleep 3

LIVE_LAST="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
FROZEN_AFTER="$("${SSH[@]}" "cat '$FROZEN/lastinput'")"
echo "RUNTIME_LASTINPUT_AFTER_HDMI=$LIVE_LAST"
echo "FROZEN_LASTINPUT_AFTER_HDMI=$FROZEN_AFTER"
echo "$LIVE_LAST" | grep -q '"appId":"com.webos.app.hdmi2"'
echo "$FROZEN_AFTER" | grep -q '"appId":"hu.szabi.launcher"'

LIVE_API="$(luna com.webos.service.eim/getLastInput '{}')"
echo "RUNTIME_GET_LAST_INPUT=$LIVE_API"
echo "$LIVE_API" | grep -q '"lastSourceAppId"[[:space:]]*:[[:space:]]*"com.webos.app.hdmi2"'
echo RUNTIME_ISOLATION=PASS

echo FAILSAFE_SESSION_CONFIRM_WAIT=START
sleep 50
"${SSH[@]}" "test ! -e '$BASE/boot-pending'"
"${SSH[@]}" "test -f '$BASE/last-good'"
"${SSH[@]}" "test ! -e '$BASE/disabled-failsafe'"
echo "FAILSAFE_SESSION_LAST_GOOD=$("${SSH[@]}" "cat '$BASE/last-good'")"
echo "FAILSAFE_SESSION_LOG=$("${SSH[@]}" "tail -20 /tmp/hu.szabi.launcher-eim-overlay.log 2>/dev/null || true")"
echo FAILSAFE_SESSION_CONFIRM=PASS

"${SSH[@]}" "umount /var/lib/eim; umount '$FROZEN'"
echo UNMOUNT=PASS

RESTORED_LAST="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
RESTORED_DB_SHA="$("${SSH[@]}" "sha256sum /var/lib/eim/eim_device_db.json | awk '{print \$1}'")"
RESTORED_LAST_SHA="$("${SSH[@]}" "sha256sum /var/lib/eim/lastinput | awk '{print \$1}'")"
echo "RESTORED_LASTINPUT=$RESTORED_LAST"
echo "RESTORED_DB_SHA=$RESTORED_DB_SHA"
echo "RESTORED_LAST_SHA=$RESTORED_LAST_SHA"
test "$RESTORED_DB_SHA" = "$BASE_DB_SHA"
test "$RESTORED_LAST_SHA" = "$BASE_LAST_SHA"
echo UNDERLYING_EIM_HASH_RESTORE=PASS

luna com.webos.service.applicationmanager/launch '{"id":"hu.szabi.launcher","params":{"source":"eim-overlay-session-restore"}}' >"$TMP/launcher.txt"
sleep 2
FINAL_API="$(luna com.webos.service.eim/getLastInput '{}')"
FINAL_FILE="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
echo "FINAL_GET_LAST_INPUT=$FINAL_API"
echo "FINAL_LASTINPUT=$FINAL_FILE"
echo "$FINAL_API" | grep -q '"lastSourceAppId"[[:space:]]*:[[:space:]]*"hu.szabi.launcher"'
echo "$FINAL_FILE" | grep -q '"appId":"hu.szabi.launcher"'

"${SSH[@]}" "rm -rf '$BASE' '$REMOTE'"
trap 'rm -rf "$TMP"' EXIT

echo NO_REBOOT=PASS
echo TEMPORARY_OVERLAY_TEST=PASS
