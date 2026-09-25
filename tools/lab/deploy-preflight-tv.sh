set -eu
date -Iseconds
uname -a
printf 'uinput='; [ -c /dev/uinput ] && echo yes || echo no
printf 'broker-dir\n'; ls -la /var/lib/webosbrew/remote-broker 2>/dev/null || true
printf 'input-markers\n'; ls -l /var/lib/webosbrew/init.d/inputhook /var/lib/webosbrew/inputhook-watchdog/enabled /var/lib/webosbrew/init.d/inputhook-watchdog 2>/dev/null || true
printf 'native-maps\n'
for name in lginput2 micomservice; do
  pid=$(pidof "$name" 2>/dev/null | awk '{print $1}')
  printf '%s pid=%s libphp=' "$name" "${pid:-none}"
  if [ -n "$pid" ] && grep -q libphp "/proc/$pid/maps" 2>/dev/null; then echo yes; else echo no; fi
done
printf 'app-versions\n'
for app in hu.szabi.remotemapper hu.szabi.mediaoverlay hu.szabi.cameraviewer hu.szabi.launcher hu.szabi.launcher.overlay hu.szabi.launcher.quick; do
  manifest="/media/developer/apps/usr/palm/applications/$app/appinfo.json"
  if [ -r "$manifest" ]; then grep -E '"(id|version)"' "$manifest" | tr '\n' ' '; echo; else echo "$app missing"; fi
done
