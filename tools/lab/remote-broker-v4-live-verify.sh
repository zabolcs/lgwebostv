#!/bin/sh
set -eu
ROOT=/var/lib/webosbrew/remote-broker
echo VERSION=$($ROOT/remote-broker --version)
echo ENABLED=$([ -f "$ROOT/enabled" ] && echo 1 || echo 0)
first=$(cat /tmp/hu.szabi.remote-broker.heartbeat)
echo HEARTBEAT_FIRST=$first
sleep 8
second=$(cat /tmp/hu.szabi.remote-broker.heartbeat)
echo HEARTBEAT_SECOND=$second
test "$second" -gt "$first"
broker=$(cat /tmp/hu.szabi.remote-broker.pid)
supervisor=$(cat /tmp/hu.szabi.remote-broker-supervisor.pid)
kill -0 "$broker"
kill -0 "$supervisor"
echo BROKER_PID=$broker
echo SUPERVISOR_PID=$supervisor
grep -q 'stale_samples' "$ROOT/supervisor.sh"
grep -q 'hu.szabi.remote-broker.key-773.state' "$ROOT/actions/773"
grep -q 'LAUNCHER_HOME_KEY_CODE=773' "$ROOT/actions/773"
grep -q '\-t 1' /var/lib/webosbrew/launcher-home/home-key.sh
test -x /var/lib/webosbrew/init.d/remote-broker
echo AUTOSTART_AND_HOME_WIRING_VERIFIED
