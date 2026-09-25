#!/bin/sh
set -u
ROOT=/var/lib/webosbrew/remote-broker
echo CLOCKS
date -Iseconds
cat /proc/uptime
echo FILES
ls -la "$ROOT" /var/lib/webosbrew/init.d/remote-broker 2>&1 || true
echo VERSION
"$ROOT/remote-broker" --version 2>&1 || true
echo CONFIG
sed -n '1,120p' "$ROOT/bindings.conf" 2>&1 || true
echo INIT
sed -n '1,160p' /var/lib/webosbrew/init.d/remote-broker 2>&1 || true
echo SUPERVISOR
sed -n '1,220p' "$ROOT/supervisor.sh" 2>&1 || true
echo PIDS
for file in /tmp/hu.szabi.remote-broker.pid /tmp/hu.szabi.remote-broker-supervisor.pid /tmp/hu.szabi.remote-broker.heartbeat; do
  printf '%s=' "$file"
  cat "$file" 2>/dev/null || echo MISSING
done
pidof remote-broker 2>/dev/null || true
echo REASON
cat "$ROOT/disabled-reason" 2>/dev/null || true
echo LOG
tail -n 200 /tmp/hu.szabi.remote-broker.log 2>/dev/null || true
echo INIT_DIRECTORY
find /var/lib/webosbrew/init.d -maxdepth 1 -type f -printf '%f %m\n' 2>/dev/null | sort || true
