#!/bin/sh
set -x
manifest=/media/developer/apps/usr/palm/applications/hu.szabi.cameraviewer/appinfo.json
if [ -f "$manifest" ]; then
  cat "$manifest"
else
  echo MISSING
fi
echo T_VARIANT
/usr/bin/luna-send-pub -t 1 -w 30000 -f \
  luna://com.webos.appInstallService/dev/install \
  '{"id":"com.ares.defaultName","ipkUrl":"/tmp/hu.szabi.cameraviewer_0.3.11_all.ipk","subscribe":true}'
echo T_RC=$?
sleep 2
echo AFTER
if [ -f "$manifest" ]; then
  cat "$manifest"
else
  echo MISSING
fi
