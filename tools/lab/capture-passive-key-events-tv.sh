#!/bin/sh
set -eu

ROOT=/var/lib/webosbrew/remote-broker
CONFIG=/tmp/hu.szabi.remote-broker-passive.conf
LOG=/tmp/hu.szabi.remote-broker-passive-capture.log
HEARTBEAT=/tmp/hu.szabi.remote-broker-passive-capture.heartbeat
PIDFILE=/tmp/hu.szabi.remote-broker-passive-capture.pid
child=

cleanup() {
  trap - EXIT INT TERM HUP
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then kill "$child" 2>/dev/null || true; fi
  [ -z "$child" ] || wait "$child" 2>/dev/null || true
  rm -f "$CONFIG" "$HEARTBEAT" "$PIDFILE"
}
trap cleanup EXIT INT TERM HUP

sed 's/^mode=grab$/mode=passive/' "$ROOT/bindings.conf" >"$CONFIG"
chown 0:0 "$CONFIG"
chmod 600 "$CONFIG"
rm -f "$LOG" "$HEARTBEAT" "$PIDFILE"
"$ROOT/remote-broker" --config "$CONFIG" --heartbeat "$HEARTBEAT" --pid-file "$PIDFILE" >"$LOG" 2>&1 &
child=$!
sleep 60
kill -0 "$child"
cleanup
cat "$LOG"
