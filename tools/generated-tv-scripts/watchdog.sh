#!/bin/sh
# v0.3.7: opt-in lginput2 repair only; never start the broad injector service.
DIR=/var/lib/webosbrew/inputhook-watchdog
ENABLED="$DIR/enabled"
PIDFILE=/tmp/hu.szabi.inputhook-watchdog.pid
[ -f "$ENABLED" ] || exit 0
exec 9>/tmp/hu.szabi.inputhook-watchdog.flock
flock -n 9 || exit 0
echo $$ >"$PIDFILE"
cleanup() { trap - EXIT INT TERM; rm -f "$PIDFILE"; exit 0; }
trap cleanup EXIT INT TERM
while [ -f "$ENABLED" ]; do
  # The helper owns power/boot/wake gates, its lock and PID/start identity.
  # Starting the original Node service would inject into other LG services.
  [ ! -x "$DIR/repair-home-hook.sh" ] || "$DIR/repair-home-hook.sh" 9>&-
  sleep 2
done
