set -eu
HASH=fdef2b6ebc8e2b33ea52cb21f0fe7d35c55130b1e5fde527c0bec604d587701b
[ ! -e /var/lib/webosbrew/remote-broker/enabled ]
! pidof remote-broker >/dev/null 2>&1
printf '%s  %s\n' "$HASH" /tmp/codex-remote-broker-clone | sha256sum -c -
/bin/sh /tmp/codex-install-remote-broker-clone.sh /tmp/codex-remote-broker-clone "$HASH"
sha256sum /var/lib/webosbrew/remote-broker/remote-broker
[ ! -e /var/lib/webosbrew/remote-broker/enabled ]
! pidof remote-broker >/dev/null 2>&1
