set -eu
HASH=fdef2b6ebc8e2b33ea52cb21f0fe7d35c55130b1e5fde527c0bec604d587701b
printf '%s  %s\n' "$HASH" /tmp/codex-remote-broker-clone | sha256sum -c -
pct push 125 /tmp/codex-remote-broker-clone /tmp/codex-remote-broker-clone
pct push 125 /tmp/codex-install-remote-broker-clone.sh /tmp/codex-install-remote-broker-clone.sh
pct exec 125 -- sh -c 'scp -q -i /etc/lgtv-control/id_rsa -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/etc/lgtv-control/known_hosts /tmp/codex-remote-broker-clone /tmp/codex-install-remote-broker-clone.sh root@192.168.0.240:/tmp/'
echo transfer-PASS
