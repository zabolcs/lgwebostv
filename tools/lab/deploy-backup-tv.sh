set -eu
BACKUP=/media/developer/lgtv-remote-before-broker-20260919-2220.tar.gz
test ! -e "$BACKUP"
set --
for path in \
  /media/developer/apps/usr/palm/applications/hu.szabi.remotemapper \
  /media/developer/apps/usr/palm/packages/hu.szabi.remotemapper \
  /home/root/.config/lginputhook \
  /var/lib/webosbrew/remote-broker; do
  [ ! -e "$path" ] || set -- "$@" "$path"
done
[ "$#" -gt 0 ]
tar -czf "$BACKUP" "$@"
sha256sum "$BACKUP"
ls -lh "$BACKUP"
df -Pk /media/developer | tail -n 1
