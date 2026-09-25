# Launcher work — 2026-09-23

## Production state

All three launcher packages (full card, quick popup, full overlay) are now version **0.3.11**, shared runtime verified by SHA-256 after installation. No remote broker binary, supervisor, NAS service, Home guard, camera package, root exploit chain or native OS partitions changed.

Kept two small lifecycle fixes:

1. `launcher-ui.js`: resume clears parked/parkRequested state even if initial data has not loaded yet; subsequent render respects that real activation. Previously an early relaunch during hidden preload could be lost.
2. `app.js`: a SAM-activated and visible full card, like the popup, skips duplicate native activate(). Added startup timestamp diagnostic.

`scripts/install-local-on-tv.sh` now captures stderr too: this firmware logs successful Luna JSON replies there. Installer additionally verifies manifest; deploy helper verifies actual runtime hashes.

Validation: all nine launcher JS test scripts and three packaging tests pass. Added regression tests for early-preload activation and already-activated full-card relaunch. Physical startup samples below; do not claim a measured major speed improvement.

## Measurements and rejected experiment

- Original Quick Start sample: power-on API request to native launcher surface ~14.14s. Launcher page retained its preloaded ID across suspend. Guard Active23:55:13, ack23:55:17, wake settled23:55:25. Settlement includes two-second visibility confirmation.
- First patched standby sample: native surface at23.64s request-relative, but first reachable measurement only15.81s; network/wake variability makes it unsuitable as a claimed regression or speedup. Later natural wake06:01:30/31, ack06:01:33, UI-ready06:01:36.784, JS first paint06:01:38.102, guard settled06:01:44.
- Controlled cold-renderer launch on a fully booted TV: v0.3.9 native surface **3.969s**, ack1.391s. UI first-paint marker ~0.56s after navigation. A native surface query is stronger than ACK but not direct physical-screen/video measurement.
- Per-app `networkStableTimeout:0.25` experiment (v0.3.10): native surface **3.985s**, ack1.375s. No meaningful improvement, so the field was REMOVED in v0.3.11. Do not leave or reintroduce it without further evidence.
- Real TV libraries expose `networkStableTimeout` and `SetNetworkStableTimeout(double)`. Primary WAM/Chromium79 source verifies seconds and FMP network-idleness gate. Existence does not establish it is the current bottleneck. `stageReady()` exists on TV but is a no-op in public WAM source; not used as a speculative fix.

## Full OS reboot (authorized)

`measure-launcher-20260922.py reboot`, initiated06:10:19 approximately. Uptime reset from4502 to39; do NOT require boot_id change on LG snapshot firmware.

- Native port3000: initially goes down, opens at24.281s, briefly drops29.828s, reopens30.469s.
- Root SSH port22: opens36.859s.
- First SSH surface sample39.562s: HDMI2, no launcher page.
- Launcher renderer page42.484s; native launcher surface47.047s.
- Launcher stayed visible through remaining observations. Native magicnum/spinner windows appeared from user/firmware; not evidence of launcher crashes. DevTools HTTP occasionally timed out under load; same renderer ID survived.

This establishes a **potential** earlier native-network route than the root hook, not proof app launch works at first port-open. Existing documented init.d hook comes after slow root setup; do not modify startup.sh/jumpstart.sh or immutable OS to move it earlier.

## Native NAS accelerator and repeatable pairing — deployed

User explicitly approved pairing, remote screenshot-verified OK, accelerator installation, and keeping the current TV guard as fallback. New `lgtv-launcher-early.service` enabled and active on NAS CT125; existing TV broker/guard/root boot chain are unchanged. Debian `python3-websocket` installed. New modules: `lg_ssap.py`, `launcher_early.py`, `ssap_pairing.py`.

Native WSS uses certificate pinning and service-owned mode0600 credentials `/var/lib/lgtv-control/lg-ssap.json`. No client key is exposed in HTTP or logs. Initial minimal pairing could not read power: the target TV's `/usr/palm/services/com.webos.service.secondscreen.gateway/interfaces/com.webos.service.tvpower.interface` explicitly requires `CONTROL_POWER` for `/power/getPowerState`, not only `READ_POWER_STATE`. Fixed manifest; user approved the new native prompt at approximately18:11UTC. Fresh saved-key reconnect successfully reads Active and launcher foreground. Real prompt window is `com.webos.app.alert` / `_WEBOS_WINDOW_TYPE_ALERT`; screenshot showed Igen selected.

NAS web UI has a **Natív LG-kapcsolat / TV párosítása / újrapárosítása** panel. GET/POST `/api/tv/pairing`; start, cancel(session id), approve(session id). User reviews a fresh TV screenshot then explicitly sends one OK; backend requires pending matching session and native alert. Pairing is90sec bounded. Failed/cancelled candidate does not overwrite the previous key. Successful candidate must pass power and foreground reads before atomic replacement. Accelerator pauses during repair and recovers on changed credentials; rejected keys do not trigger repeated pairing prompts.

Safety: accelerator dispatches only within20sec of observed native OFF→Active, never on a network reconnection alone or every Home visit. Real foreground apps cancel the attempt. Ambiguous launch timeout is not retried. Unknown-state cold reboot still uses the unchanged TV-local guard; no claim of faster unobserved cold boot. Native card-foreground API cannot reliably detect popups, so unrestricted Home replacement was rejected.

Validation:128 Python tests pass (10 platform/optional skips on Windows); this includes23 accelerator and35 transport/pairing tests. Deployment helper verifies installed hashes. NAS rollback directories `/var/backups/lgtv-control/native-launcher.IJkQSi` (original backend), `native-launcher.RqU33u` (subsequent snapshot), and `native-launcher.oDVSMs` (before cooperation gate).

18:11:37UTC accelerator connected. Authorized standby test observed Active Standby18:11:54 and Suspend18:11:59, then disconnected. First network wake failed (TV remained unreachable for50sec); second on request sent18:13UTC, user confirmed TV on. Native connection18:13:18.765, Active18:13:18.869, launch dispatch18:13:18.953, accepted18:13:22.824. However TV-local guard had already dispatched at18:13:16, so this is NOT evidence of speed improvement. Added read-only cooperation gate: if root SSH is available, check existing last-launch marker (15sec) and native popup/launcher surfaces; defer this wake to fallback if already in progress or inspection is inconclusive. Root-unavailable early path remains available. No TV scripts/markers modified by this check.

Final authorized OS reboot18:17UTC: native port first22.719sec with two later reconnects; SSH41.922sec; renderer48.063sec; native launcher surface53.594sec and stable through100sec. Firmware emitted no native OFF transition before forced reboot, so accelerator correctly did NOT infer wake from mere disconnection; unchanged TV-local fallback launched it. Thus immediate startup/full-OS-reboot acceleration is NOT achieved or claimed. Normal power-off/on with observed OFF is eligible for native path. Both NAS services active, accelerator systemd enabled, saved pairing connected after OS reboot, TV broker enabled+active (native hook false). No further disruptive tests planned.

## Rollback / tooling

- Initial v0.3.8 backup: TV `/var/lib/webosbrew/launcher-v039-backup.ilibd3` (app tar + previous IPKs).
- Before experiment: `/var/lib/webosbrew/launcher-v039-backup.2JMWX4` (v0.3.9 full).
- Before final full: `/var/lib/webosbrew/launcher-v039-backup.sI0PDk`.
- Before final quick/overlay: `/var/lib/webosbrew/launcher-v039-backup.UnL8am` (v0.3.9 popup IPKs).
- Local tools: `deploy-launcher-v039.py` now accepts optional slugs and dynamically builds current source versions; `measure-launcher-app.py` deliberately interrupts current app and cold-starts full renderer; `measure-launcher-20260922.py standby|reboot|observe` deliberately cycles except observe; `launcher-timing-read.mjs` reads current full page only by default.

Do not rerun power-cycle scripts for status-only requests. No relevant material was deleted.
