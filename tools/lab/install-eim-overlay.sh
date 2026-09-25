#!/usr/bin/env bash
set -euo pipefail

TV_HOST=192.168.0.240
TV=root@"$TV_HOST"
SOURCE_KEY=/media/lgtv/id_rsa
BASE=/var/lib/webosbrew/launcher-eim
HOOK=/var/lib/webosbrew/init.d/launcher-eim-overlay
RUN_TAG="${GITHUB_RUN_ID:-manual}"
BACKUP="/media/lgtv/eim-overlay-backup-20260925-${RUN_TAG}"

mkdir -p "$BACKUP"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
KEY="$TMP/id_rsa"
KNOWN="$TMP/known_hosts"
cp "$SOURCE_KEY" "$KEY"
chmod 600 "$KEY"
ssh-keyscan -T 3 "$TV_HOST" >"$KNOWN" 2>/dev/null
SSH=(ssh -T -i "$KEY" -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" "$TV")
SCP=(scp -i "$KEY" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN")

"${SSH[@]}" true
test -z "$("${SSH[@]}" "findmnt /var/lib/eim 2>/dev/null || true")"
"${SSH[@]}" "test ! -e '$BASE/enabled'"

RAW="$("${SSH[@]}" "luna-send -t 1 -f -w 4000 'luna://com.webos.service.eim/getLastInput' '{}' 2>&1")"
CURRENT="$(python3 -c 'import json,sys
for line in reversed(sys.stdin.read().splitlines()):
 p=line.find("{")
 if p>=0:
  try:
   d=json.loads(line[p:])
   if isinstance(d,dict):
    print(json.dumps(d,separators=(",",":"))); break
  except Exception: pass' <<<"$RAW")"
echo "CURRENT_EIM=$CURRENT"
echo "$CURRENT" | grep -q '"lastSourceAppId":"hu.szabi.launcher"'

PHYSICAL_ID="$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d.get("physicalLastSourceId",""))' "$CURRENT")"
PHYSICAL_APP="$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(d.get("physicalLastSourceAppId",""))' "$CURRENT")"
case "$PHYSICAL_ID" in HDMI_*|LIVE_TV) ;; *) exit 3;; esac
case "$PHYSICAL_APP" in com.webos.app.hdmi*|com.webos.app.livetv) ;; *) exit 3;; esac
echo "PHYSICAL_BASELINE=$PHYSICAL_ID/$PHYSICAL_APP"

"${SSH[@]}" "tar -C /var/lib -czf - eim" >"$BACKUP/eim-frozen-before.tar.gz"
sha256sum "$BACKUP/eim-frozen-before.tar.gz" >"$BACKUP/SHA256SUMS"
sha256sum -c "$BACKUP/SHA256SUMS"

printf '{"type":"%s","appId":"%s","physicalLastSourceId":"%s","physicalLastSourceAppId":"%s"}\n'   "$PHYSICAL_ID" "$PHYSICAL_APP" "$PHYSICAL_ID" "$PHYSICAL_APP" >"$TMP/lastinput"

"${SSH[@]}" "rm -rf '$BASE/runtime.new'; mkdir -p '$BASE/runtime.new' '$BASE/frozen-view'; cp -a /var/lib/eim/. '$BASE/runtime.new/'"
"${SCP[@]}" "$TMP/lastinput" "$TV:$BASE/runtime.new/lastinput"
"${SSH[@]}" "chmod 644 '$BASE/runtime.new/lastinput'; rm -rf '$BASE/runtime'; mv '$BASE/runtime.new' '$BASE/runtime'"
"${SCP[@]}" tools/generated-tv-scripts/launcher-eim-overlay "$TV:$HOOK"
"${SSH[@]}" "chmod 755 '$HOOK'; sh -n '$HOOK'; touch '$BASE/enabled'; sync"

echo "OVERLAY_BACKUP=$BACKUP"
echo EIM_OVERLAY_INSTALLED_NO_REBOOT=PASS
