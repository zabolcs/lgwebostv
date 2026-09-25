#!/bin/sh
date -Iseconds
pidof remote-broker || true
test ! -e /var/lib/webosbrew/remote-broker/enabled && echo broker-disabled
systemctl cat lginput2.service micomservice.service
for name in lginput2 micomservice; do
  p=$(pidof "$name" | awk '{print $1}')
  echo "$name pid=$p"
  [ -n "$p" ] || continue
  ls -l "/proc/$p/fd" | grep -E 'input|uinput|socket' || true
done
journalctl -u lginput2.service -u micomservice.service -n 100 --no-pager
tail -n 100 /tmp/hu.szabi.remote-broker.log
cat /proc/bus/input/devices
