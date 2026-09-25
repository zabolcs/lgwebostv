#!/bin/sh
ls -l /proc/[0-9]*/fd 2>/dev/null | awk '/^\/proc\// {process=$0} / -> \/dev\/input\// {print process; print $0}'
ps | grep -E 'surface|physical|input|uinput' || true
ls /var/log | head -n 20
grep -iE 'uinput|event3|input device|M-RCU|remote-broker' /var/log/legacy-log 2>/dev/null | tail -n 50
