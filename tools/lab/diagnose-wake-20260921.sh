#!/bin/sh
printf '\nBOOT\n'
date -Iseconds
cat /proc/sys/kernel/random/boot_id /proc/uptime
printf '\nPOWER_T\n'
/usr/bin/luna-send -t 1 -w 2000 luna://com.webos.service.tvpower/power/getPowerState '{}'
printf '\nPOWER_N\n'
/usr/bin/luna-send -n 1 -w 2000 luna://com.webos.service.tvpower/power/getPowerState '{}'
printf '\nBOOT_STATUS\n'
/usr/bin/luna-send -t 1 -w 2000 luna://com.webos.bootManager/getBootStatus '{}'
printf '\nFOREGROUND\n'
/usr/bin/luna-send -t 1 -w 2000 luna://com.webos.applicationManager/getForegroundAppInfo '{}'
printf '\nLAUNCHER_FLAGS\n'
ls -la /var/lib/webosbrew/launcher-home /var/lib/webosbrew/init.d
for f in /var/lib/webosbrew/launcher-home/home-mode /var/lib/webosbrew/launcher-home/full-presentation /tmp/hu.szabi.launcher.power-state /tmp/hu.szabi.launcher-home.pid /tmp/hu.szabi.launcher.active-since /tmp/hu.szabi.launcher.last-launch; do printf '%s=' "$f"; cat "$f" 2>/dev/null; done
printf '\nLAUNCHER_LOG\n'
tail -n 90 /tmp/hu.szabi.launcher-wake.log /tmp/hu.szabi.launcher-home.log /tmp/hu.szabi.launcher-prewarm.log 2>/dev/null
printf '\nPROCESSES\n'
ps -ef | grep -E 'remote-broker|launcher-home|luna-send|lginput2|surface-manager' | head -n 50
printf '\nINPUT_NAMES\n'
for f in /sys/class/input/event*/device/name; do printf '%s=' "$f"; cat "$f"; done
printf '\nBROKER_PREFLIGHT\n'
/var/lib/webosbrew/remote-broker/remote-broker --config /var/lib/webosbrew/remote-broker/bindings.conf --check-devices
printf '\nRECENT_KERNEL_ERRORS\n'
dmesg | grep -Ei 'remote-broker|out of memory|killed process|segfault|oom-kill' | tail -n 25
printf '\nSCRIPTS_HASH\n'
sha256sum /var/lib/webosbrew/launcher-home/guard.sh /var/lib/webosbrew/launcher-home/home-key.sh /var/lib/webosbrew/launcher-home/prewarm.sh
