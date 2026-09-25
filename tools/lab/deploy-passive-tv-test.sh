set -eu
ROOT=/var/lib/webosbrew/remote-broker
LOG=/tmp/hu.szabi.remote-broker-passive-test.log
HEART=/tmp/hu.szabi.remote-broker-passive-test.heartbeat
PIDFILE=/tmp/hu.szabi.remote-broker-passive-test.pid
rm -f "$LOG" "$HEART" "$PIDFILE"
"$ROOT/remote-broker" --config "$ROOT/bindings.conf" --heartbeat "$HEART" --pid-file "$PIDFILE" >"$LOG" 2>&1 &
child=$!
sleep 8
kill -0 "$child"
heartbeat=$(cat "$HEART")
now=$(date +%s)
[ $((now - heartbeat)) -le 2 ]
kill "$child"
wait "$child"
[ ! -e "$PIDFILE" ]
printf 'passive-heartbeat-age=%s\n' "$((now - heartbeat))"
printf 'passive-process-after-stop='; kill -0 "$child" 2>/dev/null && echo alive || echo stopped
cat "$LOG"
printf 'native-hook-after-passive\n'
for name in lginput2 micomservice; do
  pid=$(pidof "$name" 2>/dev/null | awk '{print $1}')
  printf '%s=' "$name"
  if [ -n "$pid" ] && grep -q libphp "/proc/$pid/maps" 2>/dev/null; then echo loaded; else echo clean; fi
done
