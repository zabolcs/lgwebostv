#!/bin/sh
set -eu

ROOT=/var/lib/webosbrew/remote-broker
rm -f "$ROOT/enabled" /var/lib/webosbrew/init.d/remote-broker

if [ -s /tmp/hu.szabi.remote-broker-supervisor.pid ]; then
  supervisor=$(cat /tmp/hu.szabi.remote-broker-supervisor.pid 2>/dev/null || true)
  case "$supervisor" in ''|*[!0-9]*) ;; *) [ "$supervisor" -le 1 ] || kill "$supervisor" 2>/dev/null || true ;; esac
fi
if [ -s /tmp/hu.szabi.remote-broker.pid ]; then
  broker=$(cat /tmp/hu.szabi.remote-broker.pid 2>/dev/null || true)
  case "$broker" in ''|*[!0-9]*) ;; *) [ "$broker" -le 1 ] || kill "$broker" 2>/dev/null || true ;; esac
fi

sleep 2
rm -f /tmp/hu.szabi.remote-broker.pid \
  /tmp/hu.szabi.remote-broker-supervisor.pid \
  /tmp/hu.szabi.remote-broker.heartbeat

if ps | grep -E '[r]emote-broker|[s]upervisor.sh' >/dev/null 2>&1; then
  echo 'A Remote Broker egyik folyamata még fut.' >&2
  ps | grep -E '[r]emote-broker|[s]upervisor.sh' >&2 || true
  exit 1
fi
echo 'Remote Broker közvetlenül leállítva; input grab feloldva.'
