#!/bin/sh
set -eu

ROOT=/var/lib/webosbrew/remote-broker
HASH=330fbd8909b0de67aaeb1f5715812570b6fdcc309df25589fb1b48b9b164f203
[ ! -e "$ROOT/enabled" ]
! pidof remote-broker >/dev/null 2>&1
printf '%s  %s\n' "$HASH" /tmp/codex-remote-broker-v2 | sha256sum -c -
/bin/sh /tmp/codex-install-remote-broker-v2.sh /tmp/codex-remote-broker-v2 "$HASH"
sha256sum "$ROOT/remote-broker"
[ ! -e "$ROOT/enabled" ]
! pidof remote-broker >/dev/null 2>&1
systemctl is-active --quiet micomservice.service
systemctl is-active --quiet lginput2.service
echo 'broker-v2-installed-disabled=PASS'
