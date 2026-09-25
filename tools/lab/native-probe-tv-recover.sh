#!/bin/sh
# Temporary experiment recovery, also started by init after the tested reboot.
DIR=/var/lib/webosbrew/launcher-home
BACKUP=$DIR/enabled.native-probe-backup
if [ "$1" = delayed ]; then
  deadline=$(cat "$DIR/native-probe-until" 2>/dev/null)
  case "$deadline" in ''|*[!0-9]*) deadline=0;; esac
  remaining=150
  while [ -f "$BACKUP" ] && [ "$(date +%s)" -lt "$deadline" ] && [ "$remaining" -gt 0 ]; do
    sleep 1
    remaining=$((remaining - 1))
  done
fi
if [ -f "$BACKUP" ]; then
  mv "$BACKUP" "$DIR/enabled" || exit 1
  /var/lib/webosbrew/init.d/launcher-home </dev/null >/tmp/hu.szabi.native-probe-recovery.log 2>&1
fi
test -f "$DIR/enabled"
