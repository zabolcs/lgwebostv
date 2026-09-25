#!/bin/sh
set -eu

ROOT=/var/lib/webosbrew/remote-broker
CONFIG=/tmp/hu.szabi.remote-broker-v2-test.conf
LOG=/tmp/hu.szabi.remote-broker-v2-test.log
HEARTBEAT=/tmp/hu.szabi.remote-broker-v2-test.heartbeat
PIDFILE=/tmp/hu.szabi.remote-broker-v2-test.pid
ACK=/tmp/hu.szabi.remote-broker.reload
COUNTER=/tmp/hu.szabi.remote-broker-v2-red-counter
ACTION=$ROOT/actions/398
BACKUP=$ROOT/actions/398.v2-test-backup
child=

restore_factory_input() {
  systemctl restart micomservice.service >/dev/null 2>&1 || true
  sleep 1
  systemctl restart lginput2.service >/dev/null 2>&1 || true
  sleep 2
}

cleanup() {
  trap - EXIT INT TERM HUP
  if [ -n "$child" ] && kill -0 "$child" 2>/dev/null; then kill "$child" 2>/dev/null || true; fi
  [ -z "$child" ] || wait "$child" 2>/dev/null || true
  if [ -f "$BACKUP" ]; then mv "$BACKUP" "$ACTION"; fi
  rm -f "$CONFIG" "$HEARTBEAT" "$PIDFILE" "$ACK"
  restore_factory_input
}
trap cleanup EXIT INT TERM HUP

[ ! -e "$ROOT/enabled" ]
[ ! -e "$BACKUP" ]
cp -p "$ACTION" "$BACKUP"
cat >"$ACTION" <<'EOF'
#!/bin/sh
set -eu
counter=/tmp/hu.szabi.remote-broker-v2-red-counter
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
rm -f "$LOG" "$HEARTBEAT" "$PIDFILE" "$ACK" "$COUNTER"

"$ROOT/remote-broker" --config "$CONFIG" --heartbeat "$HEARTBEAT" --pid-file "$PIDFILE" >"$LOG" 2>&1 &
child=$!
sleep 10
kill -0 "$child"
printf '399=ignore\n' >>"$CONFIG"
kill -HUP "$child"
i=0
while [ "$i" -lt 30 ]; do
  i=$((i + 1))
  ack=$(cat "$ACK" 2>/dev/null || true)
  [ "$ack" = "$child" ] && break
  /bin/usleep 100000
done
[ "${ack:-}" = "$child" ]
sleep 18
kill -0 "$child"
count=$(cat "$COUNTER" 2>/dev/null || printf '0')
pid_before_cleanup=$child
cleanup
mic=$(pidof micomservice | awk '{print $1}')
lg=$(pidof lginput2 | awk '{print $1}')
[ -n "$mic" ]
[ -n "$lg" ]
printf 'same-broker-pid=%s red-action-count=%s micomservice=%s lginput2=%s\n' "$pid_before_cleanup" "$count" "$mic" "$lg"
cat "$LOG"
