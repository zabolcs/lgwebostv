#!/bin/sh
set -eu

if [ "$(id -u)" != 0 ]; then
  echo "Ezt a telepítőt rootként kell futtatni a TV-n." >&2
  exit 2
fi
if [ "$#" != 2 ]; then
  echo "Használat: $0 /tmp/remote-broker ELVART_SHA256" >&2
  exit 2
fi

SOURCE=$1
EXPECTED=$2
ROOT=/var/lib/webosbrew/remote-broker
TARGET=$ROOT/remote-broker
CONFIG=$ROOT/bindings.conf

case "$(uname -m)" in armv7l|armv8l) ;; *) echo "Nem támogatott TV architektúra." >&2; exit 2;; esac
case "$EXPECTED" in *[!0-9a-f]*|'') echo "Az elvárt SHA-256 érvénytelen." >&2; exit 2;; esac
[ "${#EXPECTED}" = 64 ] || { echo "Az elvárt SHA-256 nem 64 karakteres." >&2; exit 2; }
[ -f "$SOURCE" ] || { echo "A broker bináris nem található." >&2; exit 2; }
[ ! -f "$ROOT/enabled" ] || { echo "A broker jelenleg engedélyezett; előbb szabályosan állítsd le." >&2; exit 2; }
! pidof remote-broker >/dev/null 2>&1 || { echo "A broker még fut; előbb állítsd le." >&2; exit 2; }

ACTUAL=$(sha256sum "$SOURCE" | awk '{print $1}')
[ "$ACTUAL" = "$EXPECTED" ] || { echo "A broker SHA-256 ellenőrzése sikertelen." >&2; exit 2; }

mkdir -p "$ROOT"
cp "$SOURCE" "$TARGET.new"
chown 0:0 "$TARGET.new"
chmod 700 "$TARGET.new"

if [ ! -f "$CONFIG" ] || ! grep -q '^version=2$' "$CONFIG"; then
  if [ -f "$CONFIG" ]; then cp -p "$CONFIG" "$CONFIG.before-relay-v4-$(date +%s)"; fi
  cat >"$CONFIG.new" <<'EOF'
version=2
mode=passive
device=LGE M-RCU - Builtin [0]
output=LGE M-RCU - Builtin [2]
EOF
  chown 0:0 "$CONFIG.new"
  chmod 600 "$CONFIG.new"
  mv "$CONFIG.new" "$CONFIG"
fi

"$TARGET.new" --config "$CONFIG" --check-config
if [ -f "$TARGET" ]; then
  cp -p "$TARGET" "$TARGET.previous"
fi
mv "$TARGET.new" "$TARGET"

echo "Remote Broker telepítve, de nincs engedélyezve és nem indult el."
