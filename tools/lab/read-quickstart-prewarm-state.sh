#!/usr/bin/env bash
set -euo pipefail

TV=192.168.0.240
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp /media/lgtv/id_rsa "$TMP/id_rsa"
chmod 600 "$TMP/id_rsa"
ssh-keyscan -T 3 "$TV" >"$TMP/known_hosts" 2>/dev/null
SSH=(ssh -T -i "$TMP/id_rsa" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$TMP/known_hosts" root@"$TV")

"${SSH[@]}" '
  echo FLAGS_BEGIN
  for f in /tmp/hu.szabi.launcher.full-overlay-prewarm-ready /tmp/hu.szabi.launcher.quick-cover-prewarm-queued /tmp/hu.szabi.launcher.quick-wam-cover.json /tmp/hu.szabi.launcher.quick-wam-full.json /tmp/hu.szabi.launcher.quick-prewarm-attempt /tmp/hu.szabi.launcher.boot-ready /tmp/hu.szabi.launcher.power-state /tmp/hu.szabi.launcher.active-since; do
    if [ -e "$f" ]; then
      echo "PRESENT $f"
      wc -c "$f" 2>/dev/null || true
      case "$f" in *.json) head -c 800 "$f"; echo;; *) cat "$f" 2>/dev/null || true;; esac
    else
      echo "MISSING $f"
    fi
  done
  echo FLAGS_END
  echo RUNNING_BEGIN
  luna-send -t 1 -f -w 1800 luna://com.webos.service.webappmanager/listRunningApps "{\"includeSysApps\":false}" 2>&1 || true
  echo RUNNING_END
  echo PREWARM_LOG_BEGIN
  tail -n 160 /tmp/hu.szabi.launcher-prewarm.log 2>/dev/null || true
  echo PREWARM_LOG_END
  echo WAKE_LOG_BEGIN
  tail -n 100 /tmp/hu.szabi.launcher-wake.log 2>/dev/null || true
  echo WAKE_LOG_END
'
