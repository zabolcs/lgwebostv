#!/bin/sh
for proc in /proc/[0-9]*; do
  found=
  for fd in "$proc"/fd/*; do
    target=$(readlink "$fd" 2>/dev/null) || continue
    case "$target" in /dev/input/*)
      [ -n "$found" ] || { printf 'process %s ' "${proc##*/}"; cat "$proc/comm"; found=1; }
      printf '%s -> %s\n' "${fd##*/}" "$target"
    ;; esac
  done
done
ls /var/log | head -n 20
grep -iE 'uinput|event3|input device|M-RCU|remote-broker' /var/log/messages 2>/dev/null | tail -n 60
