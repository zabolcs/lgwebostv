#!/bin/sh
set -eu
ROOT=/var/lib/webosbrew/remote-broker
INIT=/var/lib/webosbrew/init.d/remote-broker
test -f "$ROOT/enabled"
old_supervisor=$(cat /tmp/hu.szabi.remote-broker-supervisor.pid)
old_broker=$(cat /tmp/hu.szabi.remote-broker.pid)
kill "$old_supervisor"
i=0
while kill -0 "$old_supervisor" 2>/dev/null && [ "$i" -lt 50 ]; do
  /bin/usleep 100000
  i=$((i + 1))
done
test ! -e /proc/$old_supervisor
test ! -e /proc/$old_broker
test -f "$ROOT/enabled"
"$INIT"
i=0
while [ "$i" -lt 50 ]; do
  new_broker=$(cat /tmp/hu.szabi.remote-broker.pid 2>/dev/null || true)
  new_supervisor=$(cat /tmp/hu.szabi.remote-broker-supervisor.pid 2>/dev/null || true)
  if [ -n "$new_broker" ] && [ -n "$new_supervisor" ] && kill -0 "$new_broker" 2>/dev/null && kill -0 "$new_supervisor" 2>/dev/null; then
    break
  fi
  /bin/usleep 100000
  i=$((i + 1))
done
test -n "${new_broker:-}"
test -n "${new_supervisor:-}"
test "$new_broker" != "$old_broker"
test "$new_supervisor" != "$old_supervisor"
first=$(cat /tmp/hu.szabi.remote-broker.heartbeat)
sleep 7
second=$(cat /tmp/hu.szabi.remote-broker.heartbeat)
test "$second" -gt "$first"
test -f "$ROOT/enabled"
kill -0 "$new_broker"
kill -0 "$new_supervisor"
echo INIT_RESTART_PASS old=$old_supervisor/$old_broker new=$new_supervisor/$new_broker heartbeat=$first-$second
