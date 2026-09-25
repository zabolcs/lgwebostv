set -eu
IPK=/tmp/hu.szabi.remotemapper_0.2.0_all.ipk
BROKER=/tmp/hu.szabi.remote-broker
IPK_HASH=edceaee54d0225f264dc417ee397e94cc28754d5d8aef23e47024af7f14e0dfb
BROKER_HASH=2fbcecac545274d4a2b2ce6f30a8214713dce9ea41cfd91bf5f8ed74d7d04f15

printf '%s  %s\n' "$IPK_HASH" "$IPK" | sha256sum -c -
printf '%s  %s\n' "$BROKER_HASH" "$BROKER" | sha256sum -c -
/bin/sh /tmp/install-local-on-tv.sh "$IPK" "$IPK_HASH"
grep -E '"(id|version)"' /media/developer/apps/usr/palm/applications/hu.szabi.remotemapper/appinfo.json

/bin/sh /tmp/install-remote-broker-on-tv.sh "$BROKER" "$BROKER_HASH"
/var/lib/webosbrew/remote-broker/remote-broker \
  --config /var/lib/webosbrew/remote-broker/bindings.conf --check-config

printf 'broker-enabled-marker='; [ -e /var/lib/webosbrew/remote-broker/enabled ] && echo present || echo absent
printf 'broker-process='; pidof remote-broker 2>/dev/null || echo none
sha256sum /var/lib/webosbrew/remote-broker/remote-broker
