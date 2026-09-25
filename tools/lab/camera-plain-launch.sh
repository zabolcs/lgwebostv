#!/bin/sh
echo LAUNCH_PLAIN
/usr/bin/luna-send-pub -t 1 -w 5000 -f \
  luna://com.webos.applicationManager/launch \
  '{"id":"hu.szabi.cameraviewer"}'
sleep 2
echo STATUS
/usr/bin/luna-send -t 1 -w 3000 -f \
  luna://com.webos.applicationManager/getAppStatus \
  '{"appId":"hu.szabi.cameraviewer"}'
echo WINDOWS
/usr/bin/luna-send -t 1 -w 3000 -f \
  luna://com.webos.surfacemanager/getForegroundWindowInfo '{}'
