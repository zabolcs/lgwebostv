#!/bin/sh
set -eu

pct exec 125 -- ssh -T \
  -o BatchMode=yes \
  -o ConnectTimeout=5 \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/etc/lgtv-control/known_hosts \
  -i /etc/lgtv-control/id_rsa \
  root@192.168.0.240 sh -s <<'TVEOF'
printf 'SYSTEM\n'
uname -a

printf 'UINPUT\n'
ls -l /dev/uinput /dev/input/uinput 2>&1 || true
grep -i uinput /proc/devices 2>/dev/null || true
lsmod 2>/dev/null | grep -i uinput || true

printf 'TOOLS\n'
for executable in cc gcc clang python3 node luna-send-pub luna-send; do
  command -v "$executable" 2>/dev/null || true
done

printf 'INPUTS\n'
for event_path in /sys/class/input/event*; do
  test -e "$event_path" || continue
  printf '%s | ' "${event_path##*/}"
  cat "$event_path/device/name" 2>/dev/null || printf '?\n'
done

printf 'PROC_INPUT\n'
cat /proc/bus/input/devices 2>/dev/null || true
TVEOF
