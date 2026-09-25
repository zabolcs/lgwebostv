#!/bin/sh
set -u
echo INSTALLED_MANIFEST
for manifest in \
  /media/developer/apps/usr/palm/applications/hu.szabi.cameraviewer/appinfo.json \
  /usr/palm/applications/hu.szabi.cameraviewer/appinfo.json; do
  if [ -f "$manifest" ]; then echo "$manifest"; cat "$manifest"; fi
done
echo FOREGROUND_APP
luna-send -n 1 -w 2000 luna://com.webos.applicationManager/getForegroundAppInfo '{}' 2>/dev/null || true
echo FOREGROUND_WINDOW
luna-send -n 1 -w 2000 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>/dev/null || true
echo CAMERA_RUNNING
luna-send -n 1 -w 2000 luna://com.webos.service.webappmanager/listRunningApps '{"includeSysApps":false}' 2>/dev/null | grep -o '"id":"hu.szabi.cameraviewer"' || true
echo BROKER
test -f /var/lib/webosbrew/remote-broker/enabled && echo enabled || echo disabled
pidof remote-broker || true
