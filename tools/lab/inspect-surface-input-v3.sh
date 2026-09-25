#!/bin/sh
p=$(pidof surface-manager | awk '{print $1}')
readlink /proc/$p/exe
awk '{print $6}' /proc/$p/maps | sort -u | grep -Ei 'input|Qt|plugin|surface|luna|nyx'
command -v strings || true
ls /usr/lib/qt5/plugins/generic /usr/plugins/generic /usr/lib/qt/plugins/generic 2>/dev/null || true
grep -iE 'surface-manager.*(device|input|evdev)|physical-device.*(M-RCU|remove|add)' /var/log/legacy-log 2>/dev/null | tail -n 50
cat /proc/$p/fdinfo/120
cat /sys/class/input/event3/device/uevent
