#!/bin/sh
set -u
ROOT=/var/lib/webosbrew/remote-broker
PID=/tmp/hu.szabi.remote-broker.pid
SUP=/tmp/hu.szabi.remote-broker-supervisor.pid
cleanup() {
  trap - EXIT HUP INT TERM
  rm -f "$ROOT/enabled" /var/lib/webosbrew/init.d/remote-broker
  for file in "$SUP" "$PID"; do
    p=$(cat "$file" 2>/dev/null || true)
    case "$p" in ''|*[!0-9]*) continue;; esac
    if [ "$p" -gt 1 ] && [ -r "/proc/$p/cmdline" ] && tr '\000' ' ' <"/proc/$p/cmdline" | grep -F "$ROOT/" >/dev/null; then
      kill "$p" 2>/dev/null || true
    fi
  done
  echo GUARD_STOPPED_TEST
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
echo GUARD_ARMED
i=0
while [ "$i" -lt 30 ]; do
  if [ -s "$PID" ]; then break; fi
  sleep 1
  i=$((i+1))
done
if [ ! -s "$PID" ]; then echo TEST_DID_NOT_START; exit 1; fi
echo GUARD_DETECTED_ACTIVE
i=0
while [ "$i" -lt 60 ] && [ -s "$PID" ]; do
  sleep 1
  i=$((i+1))
done
echo TEST_WINDOW_ENDED
