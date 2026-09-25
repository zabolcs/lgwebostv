#!/bin/sh
# v0.4.7-probe guard: v0.4.0 behavior with low-overhead wake timing markers.
DIR=/var/lib/webosbrew/launcher-home
ENABLED="$DIR/enabled"
PIDFILE=/tmp/hu.szabi.launcher-home.pid
ALLOW=/tmp/hu.szabi.launcher.allow-home
FOREGROUND=/tmp/hu.szabi.launcher.foreground
LAST_LAUNCH=/tmp/hu.szabi.launcher.last-launch
POWER_STARTUP=/tmp/hu.szabi.launcher.power-startup
WAKE_WAIT_UNTIL=/tmp/hu.szabi.launcher.wake-wait-until
WAKE_RETRY_UNTIL=/tmp/hu.szabi.launcher.wake-retry-until
POWER_STATE=/tmp/hu.szabi.launcher.power-state
WAKE_SIGNAL=/tmp/hu.szabi.launcher.wake-signal
POWER_EVENT=/tmp/hu.szabi.launcher.power-event
FOREGROUND_EVENT=/tmp/hu.szabi.launcher.foreground-event
WAKE_HEARTBEAT=/tmp/hu.szabi.launcher.wake-heartbeat
BOOT_READY=/tmp/hu.szabi.launcher.boot-ready
ACTIVE_SINCE=/tmp/hu.szabi.launcher.active-since
PREWARM_AFTER=/tmp/hu.szabi.launcher.prewarm-after
QUICK_PREWARM_AFTER=/tmp/hu.szabi.launcher.quick-prewarm-after
QUICK_PREWARM_ATTEMPT=/tmp/hu.szabi.launcher.quick-prewarm-attempt
QUICK_WAKE_ARMED=/tmp/hu.szabi.launcher.quick-wake-armed
QUICK_FAST_ATTEMPT=/tmp/hu.szabi.launcher.quick-fast-attempt
QUICK_COVER_READY=/tmp/hu.szabi.launcher.full-overlay-prewarm-ready
QUICK_COVER_QUEUE=/tmp/hu.szabi.launcher.quick-cover-prewarm-queued
EIM_BASE=/var/lib/webosbrew/launcher-eim
WAKE_VISIBLE_APP=/tmp/hu.szabi.launcher.wake-visible-app
WAKE_VISIBLE_SINCE=/tmp/hu.szabi.launcher.wake-visible-since
FULL_VISIBLE=/tmp/hu.szabi.launcher.full-visible
QUICK_VISIBLE=/tmp/hu.szabi.launcher.quick-visible
OVERLAY_VISIBLE=/tmp/hu.szabi.launcher.full-overlay-visible
FULL_CLOSE_SUPPRESS=/tmp/hu.szabi.launcher.full-close-suppress
HOME_ACTIVE=/tmp/hu.szabi.launcher.home-active
RESUME_LAST="$DIR/resume-last-app"
LAST_APP="$DIR/last-app"
POWER_OFF_APP="$DIR/power-off-app"
ACTIVE_APP="$DIR/active-app-at-power-off"
APP=hu.szabi.launcher
OVERLAY_APP=hu.szabi.launcher.overlay
QUICK_APP=hu.szabi.launcher.quick
CONTROL_ORIGIN="$DIR/control-origin"
FACTORY_HOME=com.webos.app.home
DIAGNOSTIC=/tmp/hu.szabi.launcher-wake.log
TIMING_LOG=/tmp/hu.szabi.launcher-quick-timing.log

[ -f "$ENABLED" ] || exit 0
# Kernel locks cannot remain stale after a killed process or a PID reuse.
exec 9>/tmp/hu.szabi.launcher.guard-flock
flock -n 9 || exit 0
echo $$ >"$PIDFILE"
cleanup() {
  trap - EXIT INT TERM
  python -c 'import os, signal, sys

# Python 2/3 compatible; the TV has Python 2. Match exact owned scripts, then
# descendants captured before signalling. Never trust a stale PID file.
records = {}
for name in os.listdir('"'"'/proc'"'"'):
    if not name.isdigit():
        continue
    try:
        stat = open('"'"'/proc/'"'"' + name + '"'"'/stat'"'"').read()
        fields = stat[stat.rfind('"'"')'"'"') + 2:].split()
        cmd = open('"'"'/proc/'"'"' + name + '"'"'/cmdline'"'"', '"'"'rb'"'"').read().replace(b'"'"'\x00'"'"', b'"'"' '"'"').strip()
        records[int(name)] = (int(fields[1]), fields[19], cmd)
    except (IOError, ValueError, IndexError):
        pass
protected = int(sys.argv[1]) if len(sys.argv) > 1 else 0
commands = (b'"'"'/bin/sh /var/lib/webosbrew/launcher-home/guard.sh'"'"',
            b'"'"'/bin/sh /var/lib/webosbrew/launcher-home/prewarm.sh'"'"')
roots = set(pid for pid, row in records.items() if row[2] in commands)
if protected:
    roots = set([protected]) if protected in roots else set()
owned = set(roots)
ordered = list(roots)
while True:
    more = set(pid for pid, row in records.items() if row[0] in owned) - owned
    if not more:
        break
    ordered.extend(more)
    owned.update(more)
for pid in reversed(ordered):
    if pid <= 1 or pid in (os.getpid(), protected):
        continue
    try:
        stat = open('"'"'/proc/'"'"' + str(pid) + '"'"'/stat'"'"').read()
        fields = stat[stat.rfind('"'"')'"'"') + 2:].split()
        if fields[19] == records[pid][1]:
            os.kill(pid, signal.SIGTERM)
    except (IOError, OSError, IndexError):
        pass
' "$$"
  rm -f "$PIDFILE"
  exit 0
}
trap cleanup EXIT INT TERM

json_value() {
  echo "$1" | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p"
}

diagnostic() {
  # Bounded RAM log, only decisions/transitions; never persistent flash polling.
  size=$(wc -c "$DIAGNOSTIC" 2>/dev/null | awk '{print $1}'); size=${size:-0}
  [ "$size" -lt 32768 ] || mv -f "$DIAGNOSTIC" "$DIAGNOSTIC.1"
  printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >>"$DIAGNOSTIC"
}

timing_mark() {
  # /proc/uptime + shell builtins only, so the probe changes scheduling as
  # little as practical. /tmp is RAM-backed on this TV.
  read up _ < /proc/uptime
  printf '%s %s\n' "$up" "$*" >>"$TIMING_LOG"
}

fresh_power() {
  line=$(luna-send -n 1 -w 1500 luna://com.webos.service.tvpower/power/getPowerState '{}' 2>/dev/null)
  json_value "$line" state
}

arm_power_startup() {
  now=$(date +%s)
  touch "$POWER_STARTUP"
  echo "$now" >"$ACTIVE_SINCE"
  echo $((now + 180)) >"$WAKE_WAIT_UNTIL"
  echo $((now + 45)) >"$PREWARM_AFTER"
  echo $((now + 15)) >"$QUICK_PREWARM_AFTER"
  rm -f "$BOOT_READY" "$WAKE_RETRY_UNTIL" "$WAKE_VISIBLE_APP" "$WAKE_VISIBLE_SINCE" "$LAST_LAUNCH" "$ALLOW"
  diagnostic 'wake armed'
}

settle_wake() {
  diagnostic "wake $1 foreground=$current"
  rm -f "$POWER_STARTUP" "$WAKE_WAIT_UNTIL" "$WAKE_RETRY_UNTIL" "$POWER_OFF_APP" "$WAKE_VISIBLE_APP" "$WAKE_VISIBLE_SINCE" "$QUICK_WAKE_ARMED" "$QUICK_FAST_ATTEMPT"
}

wake_window_open() {
  # Only the worker owns these files. Neither polling nor failed requests
  # extends a deadline; missing state fails closed after a partial restart.
  now=$(date +%s)
  if [ -f "$WAKE_RETRY_UNTIL" ]; then
    deadline=$(cat "$WAKE_RETRY_UNTIL" 2>/dev/null)
    expiry=expired
  else
    deadline=$(cat "$WAKE_WAIT_UNTIL" 2>/dev/null)
    expiry=boot-wait-expired
  fi
  deadline=${deadline:-0}
  if [ "$now" -ge "$deadline" ]; then
    settle_wake "$expiry"
    return 1
  fi
  return 0
}

snapshot_power_off_app() {
  # No new Luna RPC while the firmware suspends. The foreground subscriber
  # already recorded the last stable real app while Active.
  app=$(cat "$ACTIVE_APP" 2>/dev/null)
  case "$app" in
    ''|*[!A-Za-z0-9._-]*) rm -f "$POWER_OFF_APP";;
    *) printf '%s\n' "$app" >"$POWER_OFF_APP";;
  esac
}

quick_fast_lane_safe() {
  [ -f "$EIM_BASE/enabled" ] || return 1
  [ -f "$EIM_BASE/last-good" ] || return 1
  [ ! -e "$EIM_BASE/boot-pending" ] || return 1
  [ ! -e "$EIM_BASE/disabled-failsafe" ] || return 1
  mountpoint -q /var/lib/eim || return 1
  mountpoint -q "$EIM_BASE/frozen-view" || return 1
  return 0
}

quick_start_fast_launch() {
  timing_mark quick-entry
  [ -f "$QUICK_WAKE_ARMED" ] || return 1
  [ ! -f "$QUICK_FAST_ATTEMPT" ] || return 1
  if [ -f "$HOME_ACTIVE" ]; then
    diagnostic 'quick fast lane blocked: explicit Home interaction active'
    return 1
  fi
  if ! quick_fast_lane_safe; then
    diagnostic 'quick fast lane blocked: EIM overlay not healthy'
    return 1
  fi
  # QUICK_WAKE_ARMED is created only by a real native standby state. A fresh
  # power RPC immediately before dispatch is therefore sufficient here; the
  # slower conservative path still handles every rejected/late launch.
  timing_mark fresh-power-begin
  fast_power=$(fresh_power)
  timing_mark "fresh-power-end state=$fast_power"
  if [ "$fast_power" != Active ]; then
    diagnostic 'quick fast lane blocked: power not Active'
    return 1
  fi
  touch "$QUICK_FAST_ATTEMPT"
  now=$(date +%s)
  echo "$now" >"$LAST_LAUNCH"
  origin=$(cat "$CONTROL_ORIGIN" 2>/dev/null)
  display=$(cat "$DIR/display-preferences.json" 2>/dev/null); [ -n "$display" ] || display='{}'

  if [ -f "$QUICK_COVER_READY" ]; then
    timing_mark list-running-begin
    running=$(luna-send -t 1 -f -w 900 luna://com.webos.service.webappmanager/listRunningApps '{"includeSysApps":false}' 2>&1)
    timing_mark list-running-end
    if echo "$running" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher[.]overlay"'; then
      cover_payload=$(printf '{"id":"%s","noSplash":true,"params":{"source":"quick-start-cover","launcherHost":"full-overlay","controlOrigin":"%s","displayPreferences":%s}}' "$OVERLAY_APP" "$origin" "$display")
      diagnostic 'quick cover dispatch'
      timing_mark cover-launch-begin
      cover_result=$(luna-send-pub -w 1200 -t 1 -f luna://com.webos.applicationManager/launch "$cover_payload" 2>&1)
      timing_mark cover-launch-end
      if echo "$cover_result" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
        diagnostic 'quick cover accepted'
      else
        rm -f "$QUICK_COVER_READY"
        diagnostic 'quick cover failed; continuing with full launcher'
      fi
    else
      rm -f "$QUICK_COVER_READY"
      diagnostic 'quick cover stale; full launcher only'
    fi
  fi

  payload=$(printf '{"id":"%s","noSplash":true,"params":{"source":"quick-start-fast-lane","controlOrigin":"%s","displayPreferences":%s}}' "$APP" "$origin" "$display")
  diagnostic 'quick fast lane dispatch'
  timing_mark full-launch-begin
  result=$(luna-send-pub -w 2500 -t 1 -f luna://com.webos.applicationManager/launch "$payload" 2>&1)
  timing_mark full-launch-end
  date +%s >"$LAST_LAUNCH"
  if echo "$result" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
    diagnostic 'quick fast lane accepted'
    return 0
  fi
  diagnostic 'quick fast lane failed; fallback remains armed'
  return 1
}

handle_power_state() {
  state=$1
  previous=$(cat "$POWER_STATE" 2>/dev/null)
  [ "$state" = "$previous" ] && return 0
  printf '%s\n' "$state" >"$POWER_STATE"
  diagnostic "power ${previous:-unknown} -> ${state:-unknown}"
  case "$state" in
    Active)
      # Screensaver dismissal is a user action, not a fresh TV power-on.
      if [ "$previous" != 'Screen Saver' ]; then
        arm_power_startup
        if [ -f "$QUICK_WAKE_ARMED" ]; then
          quick_start_fast_launch || true
          rm -f "$QUICK_WAKE_ARMED"
        fi
      fi
      ;;
    'Screen Saver')
      rm -f "$POWER_STARTUP" "$WAKE_WAIT_UNTIL" "$WAKE_RETRY_UNTIL" "$QUICK_WAKE_ARMED" "$QUICK_FAST_ATTEMPT"
      ;;
    'Active Standby'|Suspend|'Screen Off')
      [ "$previous" = Active ] && snapshot_power_off_app
      touch "$QUICK_WAKE_ARMED"
      rm -f "$QUICK_FAST_ATTEMPT" "$BOOT_READY" "$POWER_STARTUP" "$WAKE_WAIT_UNTIL" "$WAKE_RETRY_UNTIL"
      ;;
    *)
      [ "$previous" = Active ] && snapshot_power_off_app
      rm -f "$BOOT_READY" "$POWER_STARTUP" "$WAKE_WAIT_UNTIL" "$WAKE_RETRY_UNTIL"
      ;;
  esac
}

automatic_ready() {
  [ -f "$ENABLED" ] || return 1
  [ "$(cat "$POWER_STATE" 2>/dev/null)" = Active ] || return 1
  [ ! -f "$WAKE_SIGNAL" ] || return 1
  if [ ! -f "$BOOT_READY" ]; then
    since=$(cat "$ACTIVE_SINCE" 2>/dev/null); since=${since:-0}
    [ $(( $(date +%s) - since )) -ge 2 ] || return 1
    boot=$(luna-send -n 1 -w 1500 luna://com.webos.bootManager/getBootStatus '{}' 2>/dev/null)
    # These fields were verified on this TV. Fail closed if unavailable;
    # explicit remote-control Home still works independently of this guard.
    echo "$boot" | grep -Eq '"powerStatus"[[:space:]]*:[[:space:]]*"active"' || return 1
    # boot-done also waits for unrelated background services (observed 13-20s
    # after the TV already shows its first app). The initial app and minimal
    # boot ready flags suffice when the native foreground surface is visible.
    if ! echo "$boot" | grep -Eq '"boot-done"[[:space:]]*:[[:space:]]*true'; then
      echo "$boot" | grep -Eq '"minimal-boot-done"[[:space:]]*:[[:space:]]*true' || return 1
      echo "$boot" | grep -Eq '"firstAppLaunched"[[:space:]]*:[[:space:]]*true' || return 1
    fi
    touch "$BOOT_READY"
    diagnostic 'boot manager ready'
  fi
  return 0
}

foreground_app() {
  # Always ask Luna first; a frozen subscription is never proof of visibility.
  line=$(luna-send -n 1 -w 1500 luna://com.webos.applicationManager/getForegroundAppInfo '{}' 2>/dev/null)
  json_value "$line" appId
}

own_popup_visible() {
  line=$(luna-send -n 1 -w 1500 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>/dev/null)
  echo "$line" | grep -Eq '"appId"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher[.](quick|overlay)"'
}

foreground_surface_visible() {
  # Reuse only this attempt's compositor reply from own_popup_visible.
  # Do not launch over an as-yet invisible firmware app during resume.
  surface_pattern=$(printf '%s' "$current" | sed 's/\./[.]/g')
  echo "$foreground_window" | grep -Eq '"appId"[[:space:]]*:[[:space:]]*"'"$surface_pattern"'"'
}

foreground_decision() {
  current=$(foreground_app)
  case "$current" in
    "$FACTORY_HOME"|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*) return 0;;
    ''|com.webos.app.notification*|com.webos.app.volume*|com.webos.app.power*|com.webos.app.quicksettings*) return 2;;
    *) return 1;;
  esac
}

record_foreground() {
  [ -n "$current" ] || return 0
  old_app=$(cat "$FOREGROUND" 2>/dev/null)
  printf '%s\n' "$current" >"$FOREGROUND"
  [ "$current" != "$old_app" ] || return 0
  # A new Home visit after an actually observed app is not a duplicate of an
  # earlier launch. Keep the longer cooldown only inside the wake attempt.
  if [ "$current" = "$FACTORY_HOME" ] && [ -n "$old_app" ] && [ ! -f "$POWER_STARTUP" ]; then
    rm -f "$LAST_LAUNCH"
  fi
  case "$current" in
    "$APP"|"$OVERLAY_APP"|"$QUICK_APP"|"$FACTORY_HOME"|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*)
      rm -f "$ACTIVE_APP"
      [ "$current" != "$APP" ] || rm -f /tmp/hu.szabi.launcher.prewarm-attempt
      ;;
    com.webos.app.notification*|com.webos.app.volume*|com.webos.app.power*|com.webos.app.quicksettings*) ;;
    *[!A-Za-z0-9._-]*) ;;
    *) printf '%s\n' "$current" >"$LAST_APP"; printf '%s\n' "$current" >"$ACTIVE_APP";;
  esac
}

launch_id() {
  target=$1
  source=$2
  automatic_ready || return 1
  [ ! -f "$HOME_ACTIVE" ] || return 1
  now=$(date +%s)
  last=$(cat "$LAST_LAUNCH" 2>/dev/null); last=${last:-0}
  # Accepted and failed requests both cool down; never flood SAM with retries.
  cooldown=5
  [ ! -f "$POWER_STARTUP" ] || cooldown=8
  [ $((now - last)) -ge "$cooldown" ] || return 1
  # A power-off notification arriving during a foreground/boot RPC invalidates
  # the decision. Also ask tvpower immediately before the only dispatch site.
  [ "$(fresh_power)" = Active ] || return 1
  [ ! -f "$WAKE_SIGNAL" ] || return 1
  [ -f "$ENABLED" ] || return 1
  # A slow readiness/power RPC must not dispatch after the bounded window.
  if [ -f "$POWER_STARTUP" ]; then wake_window_open || return 1; fi
  echo "$now" >"$LAST_LAUNCH"
  origin=$(cat "$CONTROL_ORIGIN" 2>/dev/null)
  display=$(cat "$DIR/display-preferences.json" 2>/dev/null); [ -n "$display" ] || display='{}'
  payload=$(printf '{"id":"%s","noSplash":true,"params":{"source":"%s","controlOrigin":"%s","displayPreferences":%s}}' "$target" "$source" "$origin" "$display")
  result=$(luna-send-pub -w 4000 -n 1 luna://com.webos.applicationManager/launch "$payload" 2>&1)
  # Count from the response, so a slow launch acknowledgement cannot consume
  # its own cooldown and trigger an immediate duplicate request.
  date +%s >"$LAST_LAUNCH"
  if echo "$result" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
    diagnostic "launch accepted target=$target source=$source"
    return 0
  fi
  diagnostic "launch failed target=$target source=$source"
  return 1
}

launch_custom() {
  automatic_ready || return 1
  [ ! -f "$HOME_ACTIVE" ] || return 1
  if [ "$1" != foreground-checked ]; then
    own_popup_visible && return 1
    foreground_decision
    [ "$?" -eq 0 ] || return 1
  fi
  if [ "$current" = "$FACTORY_HOME" ]; then
    rm -f "$ALLOW" "$FULL_CLOSE_SUPPRESS"
  else
    [ ! -f "$ALLOW" ] || return 1
    suppress=$(cat "$FULL_CLOSE_SUPPRESS" 2>/dev/null); suppress=${suppress:-0}
    [ "$(date +%s)" -ge "$suppress" ] || return 1
  fi
  full_target=$APP
  [ "$(cat "$DIR/full-presentation" 2>/dev/null)" != overlay ] || full_target=$OVERLAY_APP
  launch_id "$full_target" default-home-guard
}

launch_last_or_custom() {
  if [ -f "$RESUME_LAST" ]; then
    last_app=$(cat "$POWER_OFF_APP" 2>/dev/null)
    case "$last_app" in
      ''|*[!A-Za-z0-9._-]*|hu.szabi.launcher*|"$FACTORY_HOME"|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*) ;;
      *)
        # Preserve the saved target until visible, but allow a failed/unavailable
        # last app to fall back after ten seconds of this wake attempt.
        retry_until=$(cat "$WAKE_RETRY_UNTIL" 2>/dev/null); retry_until=${retry_until:-40}
        since=$((retry_until - 40))
        if [ $(( $(date +%s) - since )) -lt 10 ]; then
          launch_id "$last_app" power-resume
          return $?
        fi
        ;;
    esac
  fi
  launch_custom foreground-checked
}

retry_power_startup() {
  [ -f "$POWER_STARTUP" ] || return 0
  wake_window_open || return 1
  [ -f "$ENABLED" ] || return 1
  [ "$(cat "$POWER_STATE" 2>/dev/null)" = Active ] || return 1
  [ ! -f "$WAKE_SIGNAL" ] || return 1
  since=$(cat "$ACTIVE_SINCE" 2>/dev/null); since=${since:-0}
  [ $((now - since)) -ge 2 ] || return 1
  [ ! -f "$HOME_ACTIVE" ] || return 1
  boot_ready=0
  automatic_ready && boot_ready=1
  # Never interrupt an already running app or a natively visible popup.
  # Observe these even before boot readiness: a user app seen during a slow
  # boot permanently ends this wake attempt, including a later HDMI switch.
  if own_popup_visible; then
    current=native-popup
    settle_wake popup-preserved
    return 0
  fi
  foreground_window=$line
  foreground_decision
  decision=$?
  record_foreground
  if [ "$decision" -eq 1 ]; then
    if [ "$current" != "$APP" ]; then
      settle_wake real-app-preserved
      return 0
    fi
    # An accepted launch may lose foreground to the firmware's restored input.
    # Require two seconds of actual visibility and at least six since Active.
    if ! foreground_surface_visible; then
      rm -f "$WAKE_VISIBLE_APP" "$WAKE_VISIBLE_SINCE"
      return 1
    fi
    now=$(date +%s)
    visible_app=$(cat "$WAKE_VISIBLE_APP" 2>/dev/null)
    if [ "$visible_app" != "$current" ]; then
      echo "$current" >"$WAKE_VISIBLE_APP"
      echo "$now" >"$WAKE_VISIBLE_SINCE"
    fi
    visible_since=$(cat "$WAKE_VISIBLE_SINCE")
    since=$(cat "$ACTIVE_SINCE")
    if [ $((now - visible_since)) -ge 2 ] && [ $((now - since)) -ge 6 ]; then
      settle_wake visible
    fi
    return 0
  fi
  rm -f "$WAKE_VISIBLE_APP" "$WAKE_VISIBLE_SINCE"
  [ "$decision" -eq 0 ] || return 1
  [ "$boot_ready" -eq 1 ] || return 1
  foreground_surface_visible || return 1
  # Boot and compositor RPCs may have crossed the wait/attempt deadline.
  wake_window_open || return 1
  if [ ! -f "$WAKE_RETRY_UNTIL" ]; then
    echo $((now + 40)) >"$WAKE_RETRY_UNTIL"
    rm -f "$WAKE_WAIT_UNTIL"
    diagnostic 'wake launch window ready'
  fi
  # HDMI/Live TV are eligible only inside this bounded wake window.
  launch_last_or_custom
}

replace_visible_factory_home() {
  automatic_ready || return 1
  [ ! -f "$HOME_ACTIVE" ] || return 1
  current=$(foreground_app)
  record_foreground
  [ "$current" = "$FACTORY_HOME" ] || return 0
  own_popup_visible && return 0
  # In an already settled session SAM reports Home before its surface arrives.
  # Dispatch now: waiting for that surface makes the LG animation visible.
  # The stronger native-surface gate remains in the power-on path above.
  launch_custom foreground-checked
}

queue_prewarm() {
  [ ! -f "$POWER_STARTUP" ] || return 0
  automatic_ready || return 0
  [ ! -f "$WAKE_SIGNAL" ] || return 0
  [ "$(cat "$POWER_STATE" 2>/dev/null)" = Active ] || return 0
  [ ! -f "$HOME_ACTIVE" ] || return 0
  epoch=$(cat "$ACTIVE_SINCE" 2>/dev/null)
  if [ -n "$epoch" ] && [ ! -f "$QUICK_COVER_READY" ]; then
    if [ "$(cat "$QUICK_COVER_QUEUE" 2>/dev/null)" = "$epoch" ]; then
      # The cover preload is still pending (or failed). Do not start another
      # renderer in parallel during this active epoch.
      return 0
    fi
    if [ -x "$DIR/prewarm.sh" ]; then
      echo "$epoch" >"$QUICK_COVER_QUEUE"
      "$DIR/prewarm.sh" cover </dev/null >>/tmp/hu.szabi.launcher-prewarm.log 2>&1 9>&-
      return 0
    fi
  fi
  quick_after=$(cat "$QUICK_PREWARM_AFTER" 2>/dev/null); quick_after=${quick_after:-0}
  if [ -n "$epoch" ] && [ "$(cat "$DIR/home-mode" 2>/dev/null)" != full ] &&
     [ "$(cat "$QUICK_PREWARM_ATTEMPT" 2>/dev/null)" != "$epoch" ] &&
     [ "$(date +%s)" -ge "$quick_after" ] && [ -x "$DIR/prewarm.sh" ]; then
    "$DIR/prewarm.sh" quick </dev/null >>/tmp/hu.szabi.launcher-prewarm.log 2>&1 9>&-
    return 0
  fi
  after=$(cat "$PREWARM_AFTER" 2>/dev/null); after=${after:-0}
  [ "$(date +%s)" -ge "$after" ] || return 0
  case "$current" in
    ''|hu.szabi.launcher*|com.webos.app.home|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*|com.webos.app.notification*|com.webos.app.volume*|com.webos.app.power*|com.webos.app.quicksettings*) return 0;;
  esac
  [ "$(cat /tmp/hu.szabi.launcher.prewarm-attempt 2>/dev/null)" != "$current" ] || return 0
  [ -x "$DIR/prewarm.sh" ] || return 0
  "$DIR/prewarm.sh" </dev/null >>/tmp/hu.szabi.launcher-prewarm.log 2>&1 9>&-
}

foreground_loop() {
  while [ -f "$ENABLED" ]; do
    luna-send -i luna://com.webos.applicationManager/getForegroundAppInfo '{"subscribe":true}' 2>/dev/null |
    while IFS= read -r line; do
      app=$(json_value "$line" appId)
      [ -n "$app" ] || continue
      # The event wakes the sole worker; its cached app never authorizes launch.
      printf '%s\n' "$app" >"$FOREGROUND_EVENT.new"
      mv -f "$FOREGROUND_EVENT.new" "$FOREGROUND_EVENT"
    done
    sleep 2
  done
}

power_loop() {
  while [ -f "$ENABLED" ]; do
    luna-send -i luna://com.webos.service.tvpower/power/getPowerState '{"subscribe":true}' 2>/dev/null |
    while IFS= read -r line; do
      state=$(json_value "$line" state)
      [ -n "$state" ] || continue
      [ "$state" != Active ] || timing_mark power-sub-active
      # Never wait on another Luna call here: Suspend must invalidate a launch
      # even while the single worker is blocked in a foreground/boot query.
      case "$state" in Active|'Screen Saver') ;; *) touch "$WAKE_SIGNAL";; esac
      printf '%s\n' "$state" >"$POWER_EVENT.new"
      mv -f "$POWER_EVENT.new" "$POWER_EVENT"
    done
    sleep 2
  done
}

wake_gap_loop() {
  while [ -f "$ENABLED" ]; do
    before=$(date +%s)
    sleep 1
    after=$(date +%s)
    # This loop does no RPC/work between its timestamps. A slow SAM answer
    # therefore cannot be mistaken for another suspend/resume cycle.
    if [ $((after - before)) -ge 7 ]; then
      touch "$WAKE_SIGNAL"
      echo "$after" >"$WAKE_HEARTBEAT"
    fi
  done
}

control_tick() {
  # Called exclusively by the main worker. No other loop launches or preloads.
  # During normal viewing, a Home event can skip the periodic power query;
  # the actual dispatch still rechecks power immediately before launching.
  if [ "$1" = foreground-event ] && [ -f "$BOOT_READY" ] &&
     [ "$(cat "$POWER_STATE" 2>/dev/null)" = Active ] &&
     [ ! -f "$POWER_STARTUP" ] && [ ! -f "$WAKE_SIGNAL" ] &&
     [ ! -f "$POWER_EVENT" ]; then
    replace_visible_factory_home
    return
  fi
  if [ -f "$WAKE_SIGNAL" ]; then
    rm -f "$WAKE_SIGNAL"
    snapshot_power_off_app
    handle_power_state unknown
  fi
  state=$(fresh_power)
  handle_power_state "$state"
  [ "$state" = Active ] || return 0
  if [ -f "$POWER_STARTUP" ]; then
    retry_power_startup
  else
    replace_visible_factory_home
    queue_prewarm
  fi
}

run_pending_tick() {
  now_tick=$(date +%s)
  if [ -f "$POWER_EVENT" ] || [ -f "$FOREGROUND_EVENT" ] ||
     [ -f "$WAKE_SIGNAL" ] || [ "$now_tick" -ge "$next_poll" ]; then
    tick_reason=poll
    [ ! -f "$FOREGROUND_EVENT" ] || tick_reason=foreground-event
    # Consume before the RPCs: an event delivered while they run must remain
    # pending for the next iteration. Cached event contents never allow launch.
    rm -f "$FOREGROUND_EVENT"
    # Move atomically so the exact event consumed determines the reason, even
    # if the subscriber publishes between the predicate and this handoff.
    if mv -f "$POWER_EVENT" "$POWER_EVENT.processing" 2>/dev/null; then
      tick_reason=power-event
      rm -f "$POWER_EVENT.processing"
    fi
    control_tick "$tick_reason"
    # Delay is measured after work. RPC latency never creates a retry burst.
    delay=2; [ ! -f "$POWER_STARTUP" ] || delay=1
    next_poll=$(( $(date +%s) + delay ))
  fi
}

# START WORKER (test fixtures source only the functions above).
rm -f "$ALLOW" "$POWER_STATE" "$POWER_EVENT" "$FOREGROUND_EVENT" "$BOOT_READY" "$LAST_LAUNCH" "$WAKE_SIGNAL" "$QUICK_WAKE_ARMED" "$QUICK_FAST_ATTEMPT" "$TIMING_LOG"
foreground_loop 9>&- &
power_loop 9>&- &
wake_gap_loop 9>&- &
diagnostic 'guard v0.4.7-probe started'
next_poll=0
while [ -f "$ENABLED" ]; do
  run_pending_tick
  /bin/usleep 250000
done
