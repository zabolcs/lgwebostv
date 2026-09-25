#!/bin/sh
for e in /sys/class/input/event*/device; do
  n=$(cat "$e/name" 2>/dev/null)
  case "$n" in
    'LGE M-RCU - Builtin [0]'|'LGE M-RCU - Builtin [2]')
      echo "$e $n"
      for cap in ev key rel abs; do printf '%s=' "$cap"; cat "$e/capabilities/$cap"; done
      ;;
  esac
done
test ! -f /var/lib/webosbrew/remote-broker/enabled && echo broker_disabled
pidof remote-broker || true
