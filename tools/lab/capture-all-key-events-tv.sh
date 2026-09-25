#!/bin/sh
set -eu

ROOT=/var/lib/webosbrew/remote-broker
CONFIG=/tmp/hu.szabi.remote-broker-all-passive.conf
LOG=/tmp/hu.szabi.remote-broker-all-passive.log
HEARTBEAT=/tmp/hu.szabi.remote-broker-all-passive.heartbeat
PIDFILE=/tmp/hu.szabi.remote-broker-all-passive.pid
child=

cleanup() {
  trap - EXIT INT TERM HUP
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then kill "$child" 2>/dev/null || true; fi
  [ -z "$child" ] || wait "$child" 2>/dev/null || true
  rm -f "$CONFIG" "$HEARTBEAT" "$PIDFILE"
}
trap cleanup EXIT INT TERM HUP

cat >"$CONFIG" <<'EOF'
version=1
mode=passive
device=L
device=S
device=C
device=B
device=I
device=v
EOF
chown 0:0 "$CONFIG"
chmod 600 "$CONFIG"
rm -f "$LOG" "$HEARTBEAT" "$PIDFILE"
"$ROOT/remote-broker" --config "$CONFIG" --heartbeat "$HEARTBEAT" --pid-file "$PIDFILE" >"$LOG" 2>&1 &
child=$!
sleep 35
kill -0 "$child"
cleanup
cat "$LOG"
