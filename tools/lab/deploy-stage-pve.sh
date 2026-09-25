set -eu
ZIP=/tmp/codex-lgtv-remote-broker-0.2.0.zip
EXPECTED=594038590b3d32104bd65a16247467e7b35e003b0e4adef10e84fc47734044d7
STAGE=/tmp/codex-lgtv-deploy-20260919-2218
PAYLOAD=/tmp/codex-lgtv-payload-20260919-2218.tar.gz

printf '%s  %s\n' "$EXPECTED" "$ZIP" | sha256sum -c -
test ! -e "$STAGE"
mkdir -m 700 "$STAGE"
unzip -q "$ZIP" -d "$STAGE"
test -f "$STAGE/lgtv-remote-broker/remote-control/server.py"
tar -C "$STAGE" -czf "$PAYLOAD" lgtv-remote-broker

pct exec 125 -- test ! -e /tmp/codex-lgtv-stage
pct push 125 "$PAYLOAD" /tmp/codex-lgtv-payload-20260919-2218.tar.gz
pct push 125 /tmp/codex-deploy-ct-update.sh /tmp/codex-deploy-ct-update.sh
pct exec 125 -- mkdir -m 700 /tmp/codex-lgtv-stage
pct exec 125 -- tar -xzf /tmp/codex-lgtv-payload-20260919-2218.tar.gz -C /tmp/codex-lgtv-stage
pct exec 125 -- chmod 700 /tmp/codex-deploy-ct-update.sh
pct exec 125 -- /bin/sh /tmp/codex-deploy-ct-update.sh

echo "PVE/CT stage PASS: $STAGE"
