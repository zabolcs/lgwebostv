#!/bin/sh
for bin in luna-send luna-send-pub; do
  echo "$bin foreground"
  "$bin" -n 1 -w 3000 luna://com.webos.applicationManager/getForegroundAppInfo '{}' 2>&1 || true
  echo "$bin surface"
  "$bin" -n 1 -w 3000 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>&1 || true
done
for bin in luna-send luna-send-pub; do
  echo "$bin timing foreground"
  "$bin" -t 1 -w 3000 luna://com.webos.applicationManager/getForegroundAppInfo '{}' 2>&1 || true
  echo "$bin timing surface"
  "$bin" -t 1 -w 3000 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>&1 || true
done
