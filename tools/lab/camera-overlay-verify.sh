#!/bin/sh
set -u
echo BEFORE_APP
/usr/bin/luna-send -t 1 -w 3000 -f \
  luna://com.webos.applicationManager/getForegroundAppInfo '{}'
echo BEFORE_WINDOWS
/usr/bin/luna-send -t 1 -w 3000 -f \
  luna://com.webos.surfacemanager/getForegroundWindowInfo '{}'
echo LAUNCH
/usr/bin/luna-send-pub -t 1 -w 5000 -f \
  luna://com.webos.applicationManager/launch \
  '{"id":"hu.szabi.cameraviewer","params":{"v":1,"action":"open","cameraId":"kapu","view":"full","requestId":"0123456789abcdef0123456789abcdef"}}'
sleep 4
echo AFTER_APP
/usr/bin/luna-send -t 1 -w 3000 -f \
  luna://com.webos.applicationManager/getForegroundAppInfo '{}'
echo AFTER_WINDOWS
/usr/bin/luna-send -t 1 -w 3000 -f \
  luna://com.webos.surfacemanager/getForegroundWindowInfo '{}'
