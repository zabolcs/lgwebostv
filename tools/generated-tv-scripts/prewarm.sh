#!/bin/sh
# Native hidden preload. The sole guard worker calls this after wake settles.
DIR=/var/lib/webosbrew/launcher-home
HOST=${1:-full}
REQUESTED_HOST="$HOST"
TARGET=hu.szabi.launcher
ATTEMPT=/tmp/hu.szabi.launcher.prewarm-attempt
QUICK_ATTEMPT=/tmp/hu.szabi.launcher.quick-prewarm-attempt
COVER_ATTEMPT=/tmp/hu.szabi.launcher.quick-cover-prewarm-attempt
COVER_READY=/tmp/hu.szabi.launcher.full-overlay-prewarm-ready
[ -f "$DIR/enabled" ] || exit 0
case "$HOST" in
  cover)
    TARGET=hu.szabi.launcher.overlay
    HOST=full-overlay
    epoch=$(cat /tmp/hu.szabi.launcher.active-since 2>/dev/null)
    case "$epoch" in ''|*[!0-9]*) exit 0;; esac
    [ "$(cat "$COVER_ATTEMPT" 2>/dev/null)" != "$epoch" ] || exit 0
    [ -f /tmp/hu.szabi.launcher.boot-ready ] || exit 0
    after=0
    ;;
  quick)
    [ "$(cat "$DIR/home-mode" 2>/dev/null)" != full ] || exit 0
    TARGET=hu.szabi.launcher.quick
    epoch=$(cat /tmp/hu.szabi.launcher.active-since 2>/dev/null)
    case "$epoch" in ''|*[!0-9]*) exit 0;; esac
    [ "$(cat "$QUICK_ATTEMPT" 2>/dev/null)" != "$epoch" ] || exit 0
    [ -f /tmp/hu.szabi.launcher.boot-ready ] || exit 0
    after=$(cat /tmp/hu.szabi.launcher.quick-prewarm-after 2>/dev/null)
    ;;
  full)
    [ "$(cat "$DIR/home-mode" 2>/dev/null)" != overlay ] || exit 0
    [ "$(cat "$DIR/full-presentation" 2>/dev/null)" != overlay ] || exit 0
    after=$(cat /tmp/hu.szabi.launcher.prewarm-after 2>/dev/null)
    ;;
  *) exit 0;;
esac
exec 8>/tmp/hu.szabi.launcher.prewarm-flock
flock -n 8 || exit 0
power_safe() {
  [ -f "$DIR/enabled" ] || return 1
  [ ! -f /tmp/hu.szabi.launcher.power-startup ] || return 1
  [ ! -f /tmp/hu.szabi.launcher.wake-signal ] || return 1
  [ ! -f /tmp/hu.szabi.launcher.home-active ] || return 1
  power=$(luna-send -n 1 -w 1500 luna://com.webos.service.tvpower/power/getPowerState '{}' 2>/dev/null)
  echo "$power" | grep -Eq '"state"[[:space:]]*:[[:space:]]*"Active"' || return 1
  [ ! -f /tmp/hu.szabi.launcher.wake-signal ]
}
after=${after:-0}
[ "$(date +%s)" -ge "$after" ] || exit 0
last=$(cat /tmp/hu.szabi.launcher.last-launch 2>/dev/null); last=${last:-0}
[ $(( $(date +%s) - last )) -ge 6 ] || exit 0
sleep 1
power_safe || exit 0
line=$(luna-send -n 1 -w 1500 luna://com.webos.applicationManager/getForegroundAppInfo '{}' 2>/dev/null)
app=$(echo "$line" | sed -n 's/.*"appId"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
case "$app" in
  ''|*[!A-Za-z0-9._-]*|com.webos.app.home|com.webos.app.notification*|com.webos.app.volume*|com.webos.app.power*|com.webos.app.quicksettings*) exit 0;;
esac
if [ "$REQUESTED_HOST" = cover ]; then
  echo "$epoch" >"$COVER_ATTEMPT"
  available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  case "$available" in ''|*[!0-9]*) exit 0;; esac
  [ "$available" -ge 131072 ] || exit 0
elif [ "$HOST" = quick ]; then
  # At most one attempt per real wake, including memory rejection/reclamation.
  # Never repopulate a reclaimed popup in a loop during video playback.
  echo "$epoch" >"$QUICK_ATTEMPT"
  available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  case "$available" in ''|*[!0-9]*) exit 0;; esac
  [ "$available" -ge 131072 ] || exit 0
else
  case "$app" in hu.szabi.launcher*|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*) exit 0;; esac
  [ "$(cat "$ATTEMPT" 2>/dev/null)" != "$app" ] || exit 0
  echo "$app" >"$ATTEMPT"
fi
line=$(luna-send -n 1 -w 1500 luna://com.webos.service.webappmanager/listRunningApps '{"includeSysApps":false}' 2>/dev/null)
pattern=$(echo "$TARGET" | sed 's/\./[.]/g')
if echo "$line" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"'"$pattern"'"'; then
  [ "$REQUESTED_HOST" != cover ] || [ -f "$COVER_READY" ]
  exit 0
fi
origin=$(cat "$DIR/control-origin" 2>/dev/null)
display=$(cat "$DIR/display-preferences.json" 2>/dev/null); [ -n "$display" ] || display='{}'
# WAM's preload flag prevents surface activation before the app's JS runs.
# source=preload also initializes our shared UI parked, ready for Home relaunch.
payload=$(printf '{"id":"%s","preload":"full","keepAlive":true,"noSplash":true,"params":{"source":"preload","launcherHost":"%s","controlOrigin":"%s","displayPreferences":%s}}' "$TARGET" "$HOST" "$origin" "$display")
power_safe || exit 0
luna-send-pub -n 1 -w 4000 luna://com.webos.applicationManager/launch "$payload"
