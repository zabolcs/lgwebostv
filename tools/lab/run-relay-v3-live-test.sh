#!/bin/sh
set -eu
BIN=/tmp/codex-remote-relay-v3
CFG=/tmp/codex-remote-relay-v3.conf
HB=/tmp/codex-remote-relay-v3.test.heartbeat
PID=/tmp/codex-remote-relay-v3.test.pid
LOG=/tmp/codex-remote-relay-v3.test.log
test ! -e /var/lib/webosbrew/remote-broker/enabled
printf '%s  %s\n' 118ed0689258db89f9fb2454fa1d8e3ba5873d22e2c0832655b790c6264b24aa "$BIN" | sha256sum -c -
"$BIN" --config "$CFG" --check-config
"$BIN" --config "$CFG" --check-devices
child=
guard=
status=0
cleanup() {
  trap - EXIT HUP INT TERM
  if [ -n "$child" ]; then
    kill "$child" 2>/dev/null || true
    i=0
    while kill -0 "$child" 2>/dev/null && [ "$i" -lt 20 ]; do
      /bin/usleep 100000
      i=$((i + 1))
    done
    if kill -0 "$child" 2>/dev/null; then kill -9 "$child" 2>/dev/null || true; status=137; fi
    wait "$child" 2>/dev/null || status=$?
  fi
  if [ -n "$guard" ]; then kill "$guard" 2>/dev/null || true; wait "$guard" 2>/dev/null || true; fi
  if [ "$status" != 0 ]; then "$BIN" --config "$CFG" --recover-output || true; fi
  printf 'TEST_ENDED status=%s time=%s\n' "$status" "$(date -Iseconds)"
  cat "$LOG"
  test ! -e /var/lib/webosbrew/remote-broker/enabled && echo AUTOSTART_REMAINS_DISABLED
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
"$BIN" --config "$CFG" --heartbeat "$HB" --pid-file "$PID" --run-seconds 60 >"$LOG" 2>&1 &
child=$!
(
  elapsed=0
  while kill -0 "$child" 2>/dev/null; do
    sleep 1
    elapsed=$((elapsed + 1))
    read up rest </proc/uptime
    now=${up%%.*}
    beat=$(cat "$HB" 2>/dev/null || echo 0)
    case "$beat" in ''|*[!0-9]*) beat=0;; esac
    if [ "$elapsed" -ge 60 ] || { [ "$elapsed" -gt 5 ] && [ $((now - beat)) -gt 5 ]; }; then
      kill "$child" 2>/dev/null || true
      sleep 2
      kill -9 "$child" 2>/dev/null || true
      exit 0
    fi
  done
) &
guard=$!
i=0
while [ "$i" -lt 20 ] && kill -0 "$child" 2>/dev/null && [ ! -s "$PID" ]; do
  /bin/usleep 100000
  i=$((i + 1))
done
if [ -s "$PID" ] && kill -0 "$child" 2>/dev/null; then
  printf 'TEST_ACTIVE pid=%s time=%s duration=60s red=disabled other=passthrough\n' "$child" "$(date -Iseconds)"
else
  echo TEST_FAILED_TO_START
fi
wait "$child" || status=$?
child=
exit "$status"
