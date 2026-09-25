set -eu
ROOT=/var/lib/webosbrew/remote-broker
broker=$(cat /tmp/hu.szabi.remote-broker.pid)
supervisor=$(cat /tmp/hu.szabi.remote-broker-supervisor.pid)
lg=$(pidof lginput2 | awk '{print $1}')
mic=$(pidof micomservice | awk '{print $1}')
printf 'start broker=%s supervisor=%s lginput2=%s micomservice=%s\n' "$broker" "$supervisor" "$lg" "$mic"
i=0
while [ "$i" -lt 9 ]; do
  sleep 5
  i=$((i + 1))
  [ -f "$ROOT/enabled" ]
  [ "$(cat /tmp/hu.szabi.remote-broker.pid)" = "$broker" ]
  [ "$(cat /tmp/hu.szabi.remote-broker-supervisor.pid)" = "$supervisor" ]
  [ "$(pidof lginput2 | awk '{print $1}')" = "$lg" ]
  [ "$(pidof micomservice | awk '{print $1}')" = "$mic" ]
  now=$(date +%s)
  heartbeat=$(cat /tmp/hu.szabi.remote-broker.heartbeat)
  age=$((now - heartbeat))
  [ "$age" -le 2 ]
  printf 'sample=%s heartbeat-age=%s\n' "$i" "$age"
done
for name in lginput2 micomservice; do
  pid=$(pidof "$name" | awk '{print $1}')
  if grep -q libphp "/proc/$pid/maps" 2>/dev/null; then echo "$name native-hook-loaded"; exit 1; fi
done
printf 'stability-window=PASS\n'
