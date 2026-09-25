#!/bin/sh
set -eu

LUNA=/usr/bin/luna-send-pub
test -x "$LUNA" || { echo "missing TV Luna client: $LUNA" >&2; exit 2; }

if [ "$#" -ne 1 ]; then
  echo "usage: $0 APP_ID" >&2
  exit 2
fi

APP_ID=$1
case "$APP_ID" in
  hu.szabi.mediaoverlay|hu.szabi.cameraviewer|hu.szabi.remotemapper) ;;
  *) echo "refusing to remove an app outside the suite: $APP_ID" >&2; exit 2 ;;
esac

RESULT=$($LUNA -w 30000 -i -f \
  'luna://com.webos.appInstallService/dev/remove' \
  "{\"id\":\"$APP_ID\",\"subscribe\":true}")
printf '%s\n' "$RESULT"

TERMINAL_STATUS=$(printf '%s\n' "$RESULT" |
  sed -n 's/.*"statusValue"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' |
  tail -n 1)
[ "$TERMINAL_STATUS" = 31 ] || {
  echo "terminal remove success (statusValue 31) was not observed; last status: ${TERMINAL_STATUS:-none}" >&2
  exit 3
}
printf '%s\n' "$RESULT" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true' || {
  echo "remove response did not report returnValue true" >&2
  exit 4
}

echo "remove PASS"
