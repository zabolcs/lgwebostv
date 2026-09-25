set -eu
printf 'native-hook-init='; [ -e /var/lib/webosbrew/init.d/inputhook ] && echo present || echo absent
printf 'watchdog-init='; [ -e /var/lib/webosbrew/init.d/inputhook-watchdog ] && echo present || echo absent
printf 'watchdog-enabled='; [ -e /var/lib/webosbrew/inputhook-watchdog/enabled ] && echo present || echo absent
printf 'broker-init='; [ -e /var/lib/webosbrew/init.d/remote-broker ] && echo present || echo absent
for name in lginput2 micomservice; do
  pid=$(pidof "$name" 2>/dev/null | awk '{print $1}')
  printf '%s-libphp=' "$name"
  if [ -n "$pid" ] && grep -q libphp "/proc/$pid/maps" 2>/dev/null; then echo yes; else echo no; fi
done
