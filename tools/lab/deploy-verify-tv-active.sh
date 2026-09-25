set -eu
ROOT=/var/lib/webosbrew/remote-broker
now=$(date +%s)
heartbeat=$(cat /tmp/hu.szabi.remote-broker.heartbeat)
printf 'heartbeat-age=%s\n' "$((now - heartbeat))"
printf 'broker-pid='; cat /tmp/hu.szabi.remote-broker.pid
printf 'supervisor-pid='; cat /tmp/hu.szabi.remote-broker-supervisor.pid
printf 'enabled='; [ -f "$ROOT/enabled" ] && echo yes || echo no
printf 'config\n'; cat "$ROOT/bindings.conf"
printf 'actions\n'; ls -l "$ROOT/actions"
printf 'processes\n'; ps | grep -E '[r]emote-broker|[s]upervisor.sh'
printf 'runtime-log\n'; tail -n 80 /tmp/hu.szabi.remote-broker.log
printf 'app-version\n'; sed -n '/"version"/p' /media/developer/apps/usr/palm/applications/hu.szabi.remotemapper/appinfo.json
printf 'native-processes\n'
for name in lginput2 micomservice; do
  pid=$(pidof "$name" 2>/dev/null | awk '{print $1}')
  printf '%s pid=%s libphp=' "$name" "${pid:-none}"
  if [ -n "$pid" ] && grep -q libphp "/proc/$pid/maps" 2>/dev/null; then echo yes; else echo no; fi
done
