#!/bin/sh
set -eu

ROOT=/var/lib/webosbrew/remote-broker
CONFIG=/tmp/hu.szabi.remote-broker-single-source.conf
LOG=/tmp/hu.szabi.remote-broker-single-source.log
HEARTBEAT=/tmp/hu.szabi.remote-broker-single-source.heartbeat
PIDFILE=/tmp/hu.szabi.remote-broker-single-source.pid
COUNTER=/tmp/hu.szabi.remote-broker-red-counter
ACTION=$ROOT/actions/398
BACKUP=$ROOT/actions/398.single-source-test-backup
child=

cleanup() {
  trap - EXIT INT TERM HUP
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then kill "$child" 2>/dev/null || true; fi
  [ -z "$child" ] || wait "$child" 2>/dev/null || true
  if [ -f "$BACKUP" ]; then mv "$BACKUP" "$ACTION"; fi
  rm -f "$CONFIG" "$HEARTBEAT" "$PIDFILE"
}
trap cleanup EXIT INT TERM HUP

[ ! -e "$ROOT/enabled" ]
[ ! -e "$BACKUP" ]
cp -p "$ACTION" "$BACKUP"
cat >"$ACTION" <<'EOF'
#!/bin/sh
set -eu
counter=/tmp/hu.szabi.remote-broker-red-counter
value=$(cat "$counter" 2>/dev/null || printf '0')
case "$value" in ''|*[!0-9]*) value=0;; esac
printf '%s\n' "$((value + 1))" >"$counter"
EOF
chown 0:0 "$ACTION"
chmod 700 "$ACTION"

cat >"$CONFIG" <<'EOF'
version=1
mode=grab
device=LGE M-RCU - Builtin [0]
398=action
EOF
chown 0:0 "$CONFIG"
chmod 600 "$CONFIG"
rm -f "$LOG" "$HEARTBEAT" "$PIDFILE" "$COUNTER"

"$ROOT/remote-broker" --config "$CONFIG" --heartbeat "$HEARTBEAT" --pid-file "$PIDFILE" >"$LOG" 2>&1 &
child=$!
sleep 35
kill -0 "$child"
now=$(date +%s)
heartbeat=$(cat "$HEARTBEAT")
[ $((now - heartbeat)) -le 2 ]
count=$(cat "$COUNTER" 2>/dev/null || printf '0')
cleanup
printf 'red-action-count=%s\n' "$count"
cat "$LOG"
