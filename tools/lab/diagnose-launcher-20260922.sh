#!/bin/sh
date -Iseconds
cat /proc/uptime
printf '\nINIT\n'
cat /var/lib/webosbrew/init.d/launcher-home
ls /etc/init/*brew* /etc/init/*developer* /etc/init/*app* 2>/dev/null
printf '\nAPPS\n'
luna-send -t 1 -f -w 1500 luna://com.webos.applicationManager/listRunningApps '{}'
printf '\nLOGS\n'
ls -lh /var/log/messages* /var/log/*wam* /var/log/*boot* 2>/dev/null
grep -E 'hu.szabi.launcher|webosbrew|FIRST_FRAME|FIRST_PAINT' /var/log/messages 2>/dev/null | tail -n 100
printf '\nWAM\n'
ps -ef | grep -E 'WebAppMgr|webapp|WAM|webosbrew' | head -n 20
printf '\nINSTALLED\n'
cat /media/developer/apps/usr/palm/applications/hu.szabi.launcher/appinfo.json
du -h /media/developer/apps/usr/palm/applications/hu.szabi.launcher/* 2>/dev/null
printf '\nPORTS\n'
netstat -lnt 2>/dev/null
