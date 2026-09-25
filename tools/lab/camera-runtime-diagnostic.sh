#!/bin/sh
echo STATUS
/usr/bin/luna-send -t 1 -w 3000 -f \
  luna://com.webos.applicationManager/getAppStatus \
  '{"appId":"hu.szabi.cameraviewer"}'
echo RUNNING
/usr/bin/luna-send -t 1 -w 3000 -f \
  luna://com.webos.applicationManager/running '{}'
echo PROCESSES
ps aux | grep -E 'cameraviewer|WebAppMgr|WAM' | grep -v grep || true
echo LOG_FILES
find /var/log -maxdepth 2 -type f 2>/dev/null | head -n 80
echo RECENT_APP_LOG
grep -R -i -E 'cameraviewer|hu.szabi|webappmanager' /var/log 2>/dev/null | tail -n 120 || true
