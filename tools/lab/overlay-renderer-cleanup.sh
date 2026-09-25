#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
OVERLAY=hu.szabi.launcher.overlay
APP=hu.szabi.launcher
INIT=/var/lib/webosbrew/init.d/launcher-home
PIDFILE=/tmp/hu.szabi.launcher-home.pid

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "$SOURCE_KEY" "$TMP/id_rsa"
chmod 600 "$TMP/id_rsa"
ssh-keyscan -T 3 "$TV_HOST" >"$TMP/known_hosts" 2>/dev/null
SSH=(ssh -T -i "$TMP/id_rsa" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$TMP/known_hosts" "$TV")

GUARD_STOPPED=0
stop_guard() {
  "${SSH[@]}" '
    p=$(cat /tmp/hu.szabi.launcher-home.pid 2>/dev/null || true)
    case "$p" in ""|*[!0-9]*) exit 0;; esac
    if [ "$p" -gt 1 ] && [ -r "/proc/$p/cmdline" ] &&
       tr "\000" " " <"/proc/$p/cmdline" | grep -F "/var/lib/webosbrew/launcher-home/guard.sh" >/dev/null; then
      kill "$p" 2>/dev/null || true
      i=0
      while [ "$i" -lt 30 ] && kill -0 "$p" 2>/dev/null; do /bin/usleep 100000; i=$((i+1)); done
      ! kill -0 "$p" 2>/dev/null
    fi
  '
  GUARD_STOPPED=1
}
start_guard() {
  "${SSH[@]}" "'$INIT' </dev/null >/dev/null 2>&1"
  for _ in $(seq 1 40); do
    if "${SSH[@]}" "p=\$(cat '$PIDFILE' 2>/dev/null || true); case \"\$p\" in ''|*[!0-9]*) exit 1;; esac; kill -0 \"\$p\" 2>/dev/null"; then
      GUARD_STOPPED=0
      return 0
    fi
    sleep 0.25
  done
  return 1
}
cleanup() {
  rc=$?
  set +e
  if [ "$GUARD_STOPPED" -eq 1 ]; then start_guard >/dev/null 2>&1 || true; fi
  "${SSH[@]}" "luna-send -n 1 -f -w 5000 luna://com.webos.applicationManager/launch '{\"id\":\"$APP\",\"params\":{\"source\":\"overlay-renderer-cleanup\"}}' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
  rm -rf "$TMP"
  exit "$rc"
}
trap cleanup EXIT

"${SSH[@]}" true
stop_guard
echo GUARD_STOPPED=PASS

"${SSH[@]}" "luna-send -n 1 -f -w 3000 luna://com.webos.applicationManager/closeByAppId '{\"id\":\"$OVERLAY\"}' >/dev/null 2>&1 || true"
sleep 0.4

RUNNING="$("${SSH[@]}" "luna-send -t 1 -f -w 2000 luna://com.webos.service.webappmanager/listRunningApps '{\"includeSysApps\":false}'" 2>&1 || true)"
echo "RUNNING_BEFORE=$RUNNING"
WEBPID="$(python3 - "$RUNNING" "$OVERLAY" <<'PY'
import json,sys
raw=sys.argv[1]; appid=sys.argv[2]
p=raw.find("payload ")
if p>=0: raw=raw[p+8:]
obj=json.JSONDecoder().raw_decode(raw.lstrip())[0]
item=next((x for x in obj.get("running",[]) if x.get("id")==appid),None)
print((item or {}).get("webprocessid") or "")
PY
)"

if [ -z "$WEBPID" ]; then
  echo OVERLAY_RENDERER_ALREADY_GONE=PASS
  exit 0
fi
case "$WEBPID" in *[!0-9]*|'') echo "invalid webprocessid: $WEBPID"; exit 20;; esac
[ "$WEBPID" -gt 100 ] || { echo "unsafe webprocessid: $WEBPID"; exit 21; }

PROC_INFO="$("${SSH[@]}" "if [ -r /proc/$WEBPID/cmdline ]; then tr '\\000' ' ' </proc/$WEBPID/cmdline; echo; fi; if [ -r /proc/$WEBPID/environ ]; then tr '\\000' '\\n' </proc/$WEBPID/environ | grep -F '$OVERLAY' || true; fi" 2>&1 || true)"
echo "OVERLAY_WEBPROCESS_ID=$WEBPID"
echo "OVERLAY_PROC_INFO=$PROC_INFO"
if ! echo "$PROC_INFO" | grep -F "$OVERLAY" >/dev/null; then
  echo "renderer ownership could not be proven; refusing TERM"
  exit 22
fi

"${SSH[@]}" "kill -TERM '$WEBPID'"
for _ in $(seq 1 30); do
  if ! "${SSH[@]}" "kill -0 '$WEBPID' 2>/dev/null"; then
    echo OVERLAY_RENDERER_TERM=PASS
    break
  fi
  sleep 0.1
done
if "${SSH[@]}" "kill -0 '$WEBPID' 2>/dev/null"; then
  echo "renderer survived TERM; refusing stronger signal"
  exit 23
fi

sleep 0.5
AFTER="$("${SSH[@]}" "luna-send -t 1 -f -w 2000 luna://com.webos.service.webappmanager/listRunningApps '{\"includeSysApps\":false}'" 2>&1 || true)"
echo "RUNNING_AFTER=$AFTER"
if echo "$AFTER" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher[.]overlay"'; then
  echo "overlay renderer respawned or remained registered"
  exit 24
fi

echo STALE_OVERLAY_RENDERER_CLEANUP=PASS
