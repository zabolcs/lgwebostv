#!/bin/sh
set -eu

ROOT=/var/lib/webosbrew/remote-broker
INIT=/var/lib/webosbrew/init.d/remote-broker
PIDFILE=/tmp/hu.szabi.remote-broker.pid
SUPERVISOR_PIDFILE=/tmp/hu.szabi.remote-broker-supervisor.pid

[ -f "$ROOT/enabled" ]
[ -x "$INIT" ]
[ -x "$ROOT/supervisor.sh" ]

old_broker=$(cat "$PIDFILE")
old_supervisor=$(cat "$SUPERVISOR_PIDFILE")
kill "$old_broker"

new_broker=
i=0
while [ "$i" -lt 15 ]; do
  i=$((i + 1))
  sleep 1
  if [ -s "$PIDFILE" ]; then
    candidate=$(cat "$PIDFILE")
    if [ "$candidate" != "$old_broker" ] && kill -0 "$candidate" 2>/dev/null; then
      new_broker=$candidate
      break
    fi
  fi
done

[ -n "$new_broker" ]
[ "$(cat "$SUPERVISOR_PIDFILE")" = "$old_supervisor" ]
kill -0 "$old_supervisor"

now=$(date +%s)
heartbeat=$(cat /tmp/hu.szabi.remote-broker.heartbeat)
age=$((now - heartbeat))
[ "$age" -le 2 ]

printf 'recovery=PASS old-broker=%s new-broker=%s supervisor=%s heartbeat-age=%s\n' \
  "$old_broker" "$new_broker" "$old_supervisor" "$age"
printf 'init='; ls -l "$INIT"
