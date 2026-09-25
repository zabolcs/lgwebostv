# Launcher startup diagnosis — 2026-09-22

Read-only production inspection; no TV/NAS production files or settings changed.
Stable input broker intentionally left alone. User reports multi-day stability.

## Observations

- Current full-presentation setting is `app`, NOT `overlay` (user changed it since previous testing). Full app `hu.szabi.launcher` version 0.3.8, packaged runtime bundle.
- Latest boot: `/var/log/bootd.log` puts factory Home foreground at uptime 19.244s, minimal-boot-done 22.204s, own launcher foreground 49.258s, boot-done 63.057s.
- Guard starts 23:25:39; Active/wake armed 23:25:40; boot manager/window ready 23:25:41; launch accepted 23:25:42; wake settled visible 23:25:50. Absolute time vs uptime implies guard starts around uptime41s. Rough conversion only; foreground is not proof of first visible physical frame.
- Thus substantial delay BEFORE guard starts, plus several seconds after launch acceptance. Wake settled includes a deliberate two-second visibility check, so do not equate 8s acceptance-to-settlement with an exact 8s rendering delay.
- Current later preloaded full launcher via DevTools: navigationStart1790112824327; ready1790112825250 (~923ms); firstPaint1790112825530 (~1203ms); cached offline state9452bytes. This is a later warm-system preload, NOT measurement of initial boot app render. No NAS state request on critical path; only prewarm-ready request observed.
- Standard webosbrew `startup.sh` runs user init hooks after root setup, synchronous filesystem sync, 2s sleep, telemetry bind mounts and elevate-service. Its own comments warn NOT to modify startup/jumpstart exploit-chain scripts. Earlier startup would need carefully scoped supported integration; do NOT edit immutable rootfs/native Home or alter root chain casually.
- Root init hooks order: screensaver50 hook (simple bind mount), launcher-home, remote-broker, VNC. No obvious large sleep inside launcher init.
- WAM debug port9998 reachable. Native process includes network-quiet-timeout10, but this alone does NOT prove a first-paint wait; avoid speculative global WAM changes.
- `com.webos.applicationManager/listRunningApps` is NOT a method on this firmware. Do not depend on it without checking correct service/category.

## Previous work status

Power-aware broker/launcher timing changes deployed Sep21. Standby test successful. Full reboot also autonomously started broker and launcher, but old measurement script required changed boot_id. LG snapshot reboot reset uptime while preserving boot_id, so its success criterion was invalid. Correct detection before repeating (uptime/process lifetime and observed disconnect), not just boot_id. No exact near-instant cold-boot performance has been established.

## Next test

Asked asynchronously whether current YouTube may be interrupted for one standby/wake timing test. No answer yet at note creation. Do not power-cycle in this turn without that response. Measure initial guard wake/dispatch, page navigation/ready/firstpaint and compositor visibility separately; preserve explicit user-launched Plex/YouTube. Then compare actual cold OS boot if approved. Do not change stable input binary/supervisor merely to speed launcher.

Helpers: `diagnose-launcher-20260922.sh`, `launcher-timing-read.mjs` (read-only DevTools page inspection).
