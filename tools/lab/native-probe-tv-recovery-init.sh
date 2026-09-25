#!/bin/sh
# This task-owned hook starts a bounded recovery after reboot; never blocks boot.
DIR=/var/lib/webosbrew/launcher-home
if [ -f "$DIR/enabled.native-probe-backup" ]; then
  nohup /bin/sh "$DIR/native-probe-recover.sh" delayed </dev/null >/tmp/hu.szabi.native-probe-recovery-wait.log 2>&1 &
fi
exit 0
