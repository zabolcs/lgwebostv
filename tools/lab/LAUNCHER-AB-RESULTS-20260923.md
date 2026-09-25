# Two bounded launcher experiments — 2026-09-23 evening

User explicitly requested both tests. Input broker, quick launcher, camera and full-overlay packages were not modified. New isolated `hu.szabi.launcher.startupprobe` contains two usable buttons (YouTube and full launcher), 5.7KB self-contained HTML and the same full-card manifest flags. Existing icon/splash assets reused. No network data is required for probe UI.

## 1. Minimal launcher, cold renderer on a warm TV

Alternating full/probe/full/probe, native compositor window appearance measured from launch request. This is not OS-boot timing, nor physical-camera first-pixel measurement.

| Variant | Sample1 | Sample2 | Mean |
| --- | ---: | ---: | ---: |
| Full production0.3.11 | 4.187s | 3.859s | 4.023s |
| Minimal two-button probe | 3.313s | 3.141s | 3.227s |

Minimal app saves about0.8sec in this small sample, not the reported10–15sec wake delay. Full application navigation-to-software-paint:1.045/0.822sec; minimal0.514/0.288sec. Probe has no native startup-priority privileges. This does not justify a major UI rewrite as a proven solution for wake delay.

## 2. Full-card `handlesRelaunch:false`

Temporary full-only0.3.12 package differs from production only in version and this flag. Rollback original0.3.11 IPK and app tar stored on TV at `/var/lib/webosbrew/launcher-relaunch-backup.7jggva`. Original source manifest remained unchanged; experimental metadata is `work/launcher-startup-probe/full-autoactivate.json`.

Originaltrue valid retained-page samples:2.578/2.375sec native surface. Page IDs equal before/after each trial; before query uses the DevTools page inventory, not Runtime.evaluate on a frozen hidden renderer. Earlier2.766/2.906sec attempts lacked prelaunch page ID and are not used for the strongest comparison.

False variant cold:4.172sec; valid retained:2.860sec. Second retained attempt discarded because WAM no longer reported the app running. Do not call that discarded attempt a measured regression, crash or proven OOM; kernel OOM-filter query returned no lines.

Actual standby/wake with false: native launcher surface19.344sec after network wake request. TV stayed on same OS uptime; the launcher document navigation started after wake (1790189698695), ready1790189705700, paint1790189707957. Thus this wake needed a new document, not only retained-surface activation. NAS accelerator dispatched20:54:57.932 and timed out waiting for acknowledgement; TV fallback accepted20:54:58 and retried20:55:07. This concurrent fallback activity and wake variability prevent treating this as a clean quantitative true/false A/B comparison. It nevertheless did not demonstrate the desired improvement. Broker remained enabled/active after wake.

Decision: restore original0.3.11 handlesRelaunchtrue, remove the isolated probe from TV, preserve local source/IPK and evidence. No claimed near-instant startup or10sec saving. Need to distinguish system startup/renderer creation from app JS rendering before any further production change.

Tools: `install-launcher-startup-probe.py`, `install-launcher-relaunch-variant.py experiment|restore`, `measure-launcher-ab.py cold|retained|preload`, `measure-launcher-cdp.mjs`. Power-cycle helper accepts optional standby dwell seconds;15sec dwell woke successfully in this trial.
