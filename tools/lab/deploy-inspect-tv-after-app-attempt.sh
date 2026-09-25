set -eu
MANIFEST=/media/developer/apps/usr/palm/applications/hu.szabi.remotemapper/appinfo.json
printf 'remote-mapper-manifest\n'
if [ -r "$MANIFEST" ]; then
  sed -n '/"id"/p; /"version"/p' "$MANIFEST"
else
  echo missing
fi
printf 'broker-process='; pidof remote-broker 2>/dev/null || echo none
printf 'broker-files\n'; ls -la /var/lib/webosbrew/remote-broker 2>/dev/null || true
