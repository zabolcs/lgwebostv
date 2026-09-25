#!/bin/sh
# Reattach the already installed Input Hook to a replaced lginput2 process only.
# Never inject into micomservice, restart an LG process, or inject twice.
ROOT=/var/lib/webosbrew/inputhook-watchdog
ASSETS=/media/developer/apps/usr/palm/services/org.webosbrew.inputhook.service/inputhook
LOCK=/tmp/hu.szabi.inputhook-repair.lock
ATTEMPT=/tmp/hu.szabi.inputhook-repair-attempt
RELOADED=/tmp/hu.szabi.inputhook-reloaded
[ -f "$ROOT/enabled" ] || exit 0
[ -f /var/lib/webosbrew/launcher-home/enabled ] || exit 0
[ -f /tmp/hu.szabi.launcher.boot-ready ] || exit 0
[ ! -f /tmp/hu.szabi.launcher.power-startup ] || exit 0
[ ! -f /tmp/hu.szabi.launcher.wake-signal ] || exit 0
[ "$(cat /tmp/hu.szabi.launcher.power-state 2>/dev/null)" = Active ] || exit 0
exec 8>"$LOCK"
flock -n 8 || exit 0
pid=$(pidof lginput2)
case "$pid" in ''|*[!0-9]*) exit 0;; esac
[ "$(cat /proc/$pid/comm 2>/dev/null)" = lginput2 ] || exit 0
start=$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)
[ -n "$start" ] || exit 0
identity="$pid:$start"
epoch=$(cat /tmp/hu.szabi.launcher.active-since 2>/dev/null)
case "$epoch" in ''|*[!0-9]*) exit 0;; esac
reload_identity="$identity:$epoch"
reload_bindings() {
  [ "$(cat "$RELOADED" 2>/dev/null)" != "$reload_identity" ] || return 0
  # Quick Start retains native code but its PHP key map can be stale. Reload
  # once per Active epoch, without attaching another hook or starting a service.
  touch /home/root/.config/lginputhook/keybinds.json || return 1
  echo "$reload_identity" >"$RELOADED"
  printf '%s keybind reload pid=%s wake=%s\n' "$(date -Iseconds)" "$pid" "$epoch"
}
if grep -q 'libphp' /proc/$pid/maps; then
  [ "$(cat "$RELOADED" 2>/dev/null)" != "$reload_identity" ] || exit 0
else
  [ "$(cat "$ATTEMPT" 2>/dev/null)" != "$identity" ] || exit 0
fi
lib="$ASSETS/libcrypt1/libphp.so"
[ ! -f /usr/lib/libcrypt.so.2 ] || lib="$ASSETS/libcrypt2/libphp.so"
[ -x "$ASSETS/ezinject" ] && [ -r "$lib" ] && [ -r "$ASSETS/lginput-hook.php" ] || exit 0
power=$(luna-send -n 1 -w 1500 luna://com.webos.service.tvpower/power/getPowerState '{}' 2>/dev/null)
echo "$power" | grep -Eq '"state"[[:space:]]*:[[:space:]]*"Active"' || exit 0
# Firmware can still report Active while processing a suspend request.
# If supplied, processing must be the empty string; unknown forms fail closed.
if echo "$power" | grep -Eq '"processing"[[:space:]]*:'; then
  echo "$power" | grep -Eq '"processing"[[:space:]]*:[[:space:]]*""' || exit 0
fi
echo "$power" | grep -Eq '"onOff"[[:space:]]*:[[:space:]]*"off"' && exit 0
[ ! -f /tmp/hu.szabi.launcher.wake-signal ] || exit 0
[ "$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)" = "$start" ] || exit 0
[ -f "$ROOT/enabled" ] && [ -f /var/lib/webosbrew/launcher-home/enabled ] || exit 0
[ ! -f /tmp/hu.szabi.launcher.power-startup ] || exit 0
# The installed service might have attached while the power RPC was pending.
if grep -q 'libphp' /proc/$pid/maps; then reload_bindings; exit $?; fi
# One attempt per process identity, even after failure; no repeated native attach.
echo "$identity" >"$ATTEMPT"
printf '%s repair lginput2 pid=%s start=%s\n' "$(date -Iseconds)" "$pid" "$start"
"$ASSETS/ezinject" "$pid" "$lib" "$ASSETS/lginput-hook.php" lginput2 >/tmp/hu.szabi.inputhook-repair-detail.log 2>&1
sleep 1
if grep -q 'libphp' /proc/$pid/maps; then
  reload_bindings
  printf '%s repair attached pid=%s\n' "$(date -Iseconds)" "$pid"
else
  printf '%s repair not-attached pid=%s\n' "$(date -Iseconds)" "$pid"
fi
