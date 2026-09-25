#!/bin/sh
DIR=/var/lib/webosbrew/launcher-home
LOG=${LAUNCHER_HOME_KEY_LOG:-/tmp/lginput-hook-lginput2.log}
HOME_KEY_CODE=${LAUNCHER_HOME_KEY_CODE:-773}
case "$HOME_KEY_CODE" in ''|*[!0-9]*) HOME_KEY_CODE=773;; esac
FULL_APP=hu.szabi.launcher
if [ "$(cat "$DIR/full-presentation" 2>/dev/null)" = overlay ]; then FULL_APP=hu.szabi.launcher.overlay; fi
QUICK_APP=hu.szabi.launcher.quick
HOME_ACTIVE=/tmp/hu.szabi.launcher.home-active
FULL_VISIBLE=/tmp/hu.szabi.launcher.full-visible
QUICK_VISIBLE=/tmp/hu.szabi.launcher.quick-visible
QUICK_CLOSE_SUPPRESS=/tmp/hu.szabi.launcher.quick-close-suppress
ALLOW=/tmp/hu.szabi.launcher.allow-home
HOME_MODE="$DIR/home-mode"
CONTROL_ORIGIN="$DIR/control-origin"

mkdir -p "$DIR"
exec 7>/tmp/hu.szabi.launcher-home-key.flock
flock -n 7 || exit 0
touch "$HOME_ACTIVE"
cleanup() { rm -f "$HOME_ACTIVE"; }
trap cleanup EXIT INT TERM

quick_running() {
  line=$(luna-send -t 1 -w 1000 luna://com.webos.service.webappmanager/listRunningApps '{"includeSysApps":false}' 2>/dev/null)
  echo "$line" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher[.]quick"'
}

recent_quick_close() {
  suppress_until=$(cat "$QUICK_CLOSE_SUPPRESS" 2>/dev/null)
  case "$suppress_until" in ''|*[!0-9]*) return 1;; esac
  now=$(date +%s)
  [ "$now" -lt "$suppress_until" ]
}

close_quick() {
  rm -f "$QUICK_VISIBLE"
  close_attempt=0
  while [ "$close_attempt" -lt 3 ]; do
    quick_running || return 0
    /usr/bin/luna-send -t 1 -w 2000 -f luna://com.webos.service.applicationmanager/closeByAppId       '{"id":"hu.szabi.launcher.quick"}' >/dev/null 2>&1 || true
    close_attempt=$((close_attempt + 1))
    /bin/usleep 300000
  done
  ! quick_running
}

launch_mode() {
  mode=$1
  source=$2
  configured_mode=$(cat "$HOME_MODE" 2>/dev/null)
  case "$configured_mode" in
    full) mode=full;;
    overlay) mode=overlay;;
  esac
  if [ "$mode" = "overlay" ]; then
    app=$QUICK_APP
    host=quick
    visible=$QUICK_VISIBLE
  else
    app=$FULL_APP
    host=full
    visible=$FULL_VISIBLE
    if [ "$app" = hu.szabi.launcher.overlay ]; then host=full-overlay; visible=/tmp/hu.szabi.launcher.full-overlay-visible; fi
  fi

  # The retained popup knows whether it is open or natively hidden. A unique
  # request id also prevents initial/duplicate relaunch events closing it.
  [ "$source" = home-short ] && [ "$host" = quick ] && source=home-short-toggle
  request_id="$$-$(date +%s)"

  # Never leave an old full popup above a newly selected host.
  if [ "$host" != "full-overlay" ] && [ -f /tmp/hu.szabi.launcher.full-overlay-visible ]; then
    /usr/bin/luna-send -t 1 -w 2000 luna://com.webos.service.applicationmanager/closeByAppId '{"id":"hu.szabi.launcher.overlay"}' >/dev/null 2>&1 || true
    rm -f /tmp/hu.szabi.launcher.full-overlay-visible
  fi
  source=${source%-open}
  if [ "$host" != "quick" ] && [ -f "$QUICK_VISIBLE" ]; then
    close_quick || true
  fi
  origin=$(cat "$CONTROL_ORIGIN" 2>/dev/null)
  display=$(cat "$DIR/display-preferences.json" 2>/dev/null); [ -n "$display" ] || display='{}'
  payload=$(printf '{"id":"%s","noSplash":true,"params":{"mode":"%s","source":"%s","launcherHost":"%s","controlOrigin":"%s","displayPreferences":%s,"homeRequestId":"%s"}}'     "$app" "$mode" "$source" "$host" "$origin" "$display" "$request_id")
  attempt=0
  while [ "$attempt" -lt 4 ]; do
    result=$(/usr/bin/luna-send-pub -t 1 -w 5000 -f luna://com.webos.applicationManager/launch "$payload" 2>&1)
    if echo "$result" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
      rm -f "$ALLOW"
      touch "$visible"
      [ "$host" != "quick" ] && rm -f "$QUICK_VISIBLE"
      [ "$host" = "quick" ] && rm -f "$FULL_VISIBLE"
      return 0
    fi
    attempt=$((attempt + 1))
  done
  /usr/bin/luna-send-pub -t 1 -w 10000 -f luna://com.webos.applicationManager/launch "$payload" >/dev/null 2>&1
}

# Both press lengths have the same destination in full mode. Dispatch on the
# key-down hook without waiting for release/long-press detection in the log.
case "$(cat "$HOME_MODE" 2>/dev/null)" in
  full) launch_mode full home-short; exit $?;;
  overlay) launch_mode overlay home-short; exit $?;;
esac

if [ ! -r "$LOG" ]; then
  launch_mode overlay home-short
  exit 0
fi

mode=overlay
source=home-short
count=0
while [ "$count" -lt 16 ]; do
  state=$(grep "^$HOME_KEY_CODE => [012]$" "$LOG" 2>/dev/null | tail -n 1 | sed 's/.* => //')
  case "$state" in
    0) break ;;
    2) mode=full; source=home-long; break ;;
  esac
  count=$((count + 1))
  if [ "$count" -ge 16 ]; then
    mode=full
    source=home-long
    break
  fi
  /bin/usleep 50000
done
launch_mode "$mode" "$source"
