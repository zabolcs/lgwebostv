set -eu
ROOT=/tmp/codex-lgtv-deploy-20260919-2218/lgtv-remote-broker
IPK=$ROOT/build/hu.szabi.remotemapper_0.2.0_all.ipk
BROKER=$ROOT/remote-broker/remote-broker
APP_INSTALL=$ROOT/scripts/install-local-on-tv.sh
BROKER_INSTALL=$ROOT/remote-broker/install-on-tv.sh

printf '%s  %s\n' edceaee54d0225f264dc417ee397e94cc28754d5d8aef23e47024af7f14e0dfb "$IPK" | sha256sum -c -
printf '%s  %s\n' 2fbcecac545274d4a2b2ce6f30a8214713dce9ea41cfd91bf5f8ed74d7d04f15 "$BROKER" | sha256sum -c -

pct push 125 "$IPK" /tmp/hu.szabi.remotemapper_0.2.0_all.ipk
pct push 125 "$BROKER" /tmp/hu.szabi.remote-broker
pct push 125 "$APP_INSTALL" /tmp/install-local-on-tv.sh
pct push 125 "$BROKER_INSTALL" /tmp/install-remote-broker-on-tv.sh

pct exec 125 -- sh -c 'scp -q -i /etc/lgtv-control/id_rsa -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/lgtv-control/known_hosts /tmp/hu.szabi.remotemapper_0.2.0_all.ipk /tmp/hu.szabi.remote-broker /tmp/install-local-on-tv.sh /tmp/install-remote-broker-on-tv.sh root@192.168.0.240:/tmp/'
echo 'TV transfer PASS'
