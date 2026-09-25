#!/bin/sh
set -eu

LUNA=/usr/bin/luna-send-pub
test -x "$LUNA" || { echo "missing TV Luna client: $LUNA" >&2; exit 2; }

if [ "$#" -ne 2 ]; then
  echo "usage: $0 /absolute/path/app.ipk EXPECTED_SHA256" >&2
  exit 2
fi

IPK=$1
EXPECTED=$2
case "$IPK" in
  /*) ;;
  *) echo "IPK path must be absolute" >&2; exit 2 ;;
esac
case "$IPK" in *[!A-Za-z0-9_./-]*) echo "unsupported character in IPK path" >&2; exit 2 ;; esac
test -f "$IPK" || { echo "IPK not found: $IPK" >&2; exit 2; }
case "$EXPECTED" in *[!0-9a-fA-F]*|'') echo "invalid SHA-256" >&2; exit 2 ;; esac
[ "${#EXPECTED}" -eq 64 ] || { echo "invalid SHA-256 length" >&2; exit 2; }

ACTUAL=$(sha256sum "$IPK" | awk '{print $1}')
EXPECTED_LOWER=$(printf '%s' "$EXPECTED" | tr 'A-F' 'a-f')
[ "$EXPECTED_LOWER" = "$ACTUAL" ] || { echo "SHA-256 mismatch: $ACTUAL" >&2; exit 3; }

PAYLOAD=$(printf '{"id":"com.ares.defaultName","ipkUrl":"%s","subscribe":true}' "$IPK")
CONTROL=$(ar p "$IPK" control.tar.gz | gzip -dc | tar -xOf - control)
PACKAGE=$(printf '%s\n' "$CONTROL" | sed -n 's/^Package: //p' | head -n 1)
VERSION=$(printf '%s\n' "$CONTROL" | sed -n 's/^Version: //p' | head -n 1)
case "$PACKAGE" in ''|*[!A-Za-z0-9._-]*) echo "invalid package id" >&2; exit 3;; esac
case "$VERSION" in ''|*[!A-Za-z0-9._+-]*) echo "invalid package version" >&2; exit 3;; esac

RESULT=$($LUNA -t 1 -w 30000 -f \
  'luna://com.webos.appInstallService/dev/install' "$PAYLOAD" 2>&1)
printf '%s\n' "$RESULT"
printf '%s\n' "$RESULT" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true' || {
  echo "install response did not report returnValue true" >&2
  exit 4
}

# Newer webOS builds return only the initial subscribed acknowledgement for a
# one-shot client. Verify the installed manifest instead of waiting for the
# old statusValue:30 subscription event, which is no longer delivered here.
MANIFEST=/media/developer/apps/usr/palm/applications/$PACKAGE/appinfo.json
i=0
while [ "$i" -lt 60 ]; do
  if [ -f "$MANIFEST" ] &&
     grep -Eq '"id"[[:space:]]*:[[:space:]]*"'"$PACKAGE"'"' "$MANIFEST" &&
     grep -Eq '"version"[[:space:]]*:[[:space:]]*"'"$VERSION"'"' "$MANIFEST"; then
    echo "install PASS; verified $PACKAGE $VERSION; the application was not launched"
    exit 0
  fi
  /bin/usleep 500000
  i=$((i + 1))
done

echo "installed manifest did not reach $PACKAGE $VERSION" >&2
exit 5
