#!/bin/sh
echo BINDINGS
cat /var/lib/webosbrew/remote-broker/bindings.conf
echo GOOGLE_ASSISTANT_ACTION
cat /var/lib/webosbrew/remote-broker/actions/1117
echo RECENT_BROKER_LOG
tail -n 20 /tmp/hu.szabi.remote-broker.log
echo LIVE_PIDS
cat /tmp/hu.szabi.remote-broker.pid /tmp/hu.szabi.remote-broker-supervisor.pid 2>/dev/null || true
