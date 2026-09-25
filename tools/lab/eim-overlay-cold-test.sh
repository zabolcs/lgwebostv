#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
KEY_SOURCE=/media/lgtv/id_rsa
BASE=/var/lib/webosbrew/launcher-eim
HOOK=/var/lib/webosbrew/init.d/launcher-eim-overlay
APP=hu.szabi.launcher
PHYSICAL_APP=com.webos.app.hdmi2

TMP="$(mktemp -d)"
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
cp "$KEY_SOURCE" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")
COMMITTED=0

ssh_ok() { "${SSH[@]}" true >/dev/null 2>&1; }
luna() { "${SSH[@]}" "luna-send -t 1 -f -w 5000 'luna://$1' '$2' 2>&1"; }

cleanup() {
  rc=$?
  set +e
  if [ "$COMMITTED" -ne 1 ]; then
    if ! ssh_ok; then
      for _ in $(seq 1 120); do sleep 1; ssh_ok && break; done
    fi
    if ssh_ok; then
      "${SSH[@]}" "rm -f '$BASE/enabled' '$HOOK'; mountpoint -q /var/lib/eim && umount /var/lib/eim || true; mountpoint -q '$BASE/frozen-view' && umount '$BASE/frozen-view' || true; rm -rf '$BASE'" >/dev/null 2>&1 || true
      luna com.webos.service.applicationmanager/launch '{"id":"hu.szabi.launcher","params":{"source":"overlay-cold-rollback"}}' >/dev/null 2>&1 || true
      echo OVERLAY_COLD_ROLLBACK=ATTEMPTED
    fi
  fi
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

ssh_ok
"${SSH[@]}" "test -f '$BASE/enabled' && test -x '$HOOK' && test -f '$BASE/runtime/lastinput'"
test -z "$("${SSH[@]}" "findmnt /var/lib/eim 2>/dev/null || true")"
PRE_FROZEN="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
PRE_RUNTIME="$("${SSH[@]}" "cat '$BASE/runtime/lastinput'")"
echo "PRE_FROZEN=$PRE_FROZEN"
echo "PRE_RUNTIME=$PRE_RUNTIME"
echo "$PRE_FROZEN" | grep -q '"appId":"hu.szabi.launcher"'
echo "$PRE_RUNTIME" | grep -q '"appId":"com.webos.app.hdmi2"'

BOOT_BEFORE="$("${SSH[@]}" 'cat /proc/sys/kernel/random/boot_id')"
"${SSH[@]}" 'sync; reboot' >/dev/null 2>&1 || true
echo COLD_REBOOT_SENT=PASS

for _ in $(seq 1 45); do ! ssh_ok && break; sleep 1; done
RETURNED=0
for i in $(seq 1 180); do
  if ssh_ok; then RETURNED=1; echo "SSH_RETURNED_AFTER_SECONDS=$i"; break; fi
  sleep 1
done
test "$RETURNED" -eq 1

BOOT_AFTER="$("${SSH[@]}" 'cat /proc/sys/kernel/random/boot_id')"
test "$BOOT_AFTER" != "$BOOT_BEFORE"
echo COLD_BOOT_ID_CHANGED=PASS

STATUS="$(luna com.webos.bootManager/getBootStatus '{}')"
echo "BOOT_STATUS=$STATUS"
echo "$STATUS" | grep -q '"firstAppId"[[:space:]]*:[[:space:]]*"hu.szabi.launcher"'
echo COLD_BOOT_FIRST_APP_LAUNCHER=PASS

"${SSH[@]}" "mountpoint -q /var/lib/eim && mountpoint -q '$BASE/frozen-view'"
echo "EIM_MOUNT=$("${SSH[@]}" 'findmnt /var/lib/eim')"
echo "FROZEN_MOUNT=$("${SSH[@]}" "findmnt '$BASE/frozen-view'")"

FROZEN="$("${SSH[@]}" "cat '$BASE/frozen-view/lastinput'")"
RUNTIME="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
echo "FROZEN_LASTINPUT=$FROZEN"
echo "RUNTIME_LASTINPUT=$RUNTIME"
echo "$FROZEN" | grep -q '"appId":"hu.szabi.launcher"'
echo "$RUNTIME" | grep -q '"appId":"com.webos.app.hdmi2"'
echo COLD_BOOT_EIM_ISOLATION=PASS

luna com.webos.service.eim/deleteDevice '{"appId":"hu.szabi.launcher"}' >/dev/null || true
luna com.webos.service.applicationmanager/launch '{"id":"com.webos.app.hdmi2","params":{"source":"overlay-cold-hdmi-check"}}' >/dev/null
sleep 3
RUNTIME_HDMI="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
FROZEN_HDMI="$("${SSH[@]}" "cat '$BASE/frozen-view/lastinput'")"
echo "RUNTIME_AFTER_HDMI=$RUNTIME_HDMI"
echo "FROZEN_AFTER_HDMI=$FROZEN_HDMI"
echo "$RUNTIME_HDMI" | grep -q '"appId":"com.webos.app.hdmi2"'
echo "$FROZEN_HDMI" | grep -q '"appId":"hu.szabi.launcher"'

luna com.webos.service.applicationmanager/launch '{"id":"hu.szabi.launcher","params":{"source":"overlay-cold-launcher-check"}}' >/dev/null
sleep 3
RUNTIME_LAUNCHER="$("${SSH[@]}" 'cat /var/lib/eim/lastinput')"
FG="$(luna com.webos.applicationManager/getForegroundAppInfo '{}')"
echo "RUNTIME_AFTER_LAUNCHER=$RUNTIME_LAUNCHER"
echo "FOREGROUND=$FG"
echo "$RUNTIME_LAUNCHER" | grep -q '"appId":"com.webos.app.hdmi2"'
echo "$FG" | grep -q '"appId"[[:space:]]*:[[:space:]]*"hu.szabi.launcher"'
echo RUNTIME_NOT_CLOBBERED_BY_LAUNCHER=PASS

COMMITTED=1
echo EIM_OVERLAY_COLD_BOOT=PASS
trap 'rm -rf "$TMP"' EXIT
