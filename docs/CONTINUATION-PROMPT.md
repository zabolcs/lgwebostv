# Continuation prompt for another AI

Continue the LG webOS custom launcher/control suite from this repository. Read `README.md`,
`docs/TECHNICAL-HANDOFF-LOCAL-DEPLOYMENT.md`, `docs/AUTOSTART-ACTIVITYMANAGER-KISERLET.md`,
`TEST-REPORT.md`, and the launcher result notes under `tools/lab/` before changing code.

The repository contains editable source only. It intentionally excludes production keys, SSAP
credentials, configs, compiled IPKs/native binaries, logs, TV/CT snapshots and toolchains. Ask the
operator for the separate private 2026-09-25 NAS checkpoint only when exact live restore material is
needed; never commit any of it.

The current production family is launcher full/quick/overlay 0.3.11, Camera Viewer 0.3.11, Media
Overlay 0.3.7 and Remote Mapper 0.2.0. All launcher modes share `apps/launcher`; do not fork the UI
into three implementations. The CT web UI/backend is under `remote-control`, the stable input path is
`remote-broker`, and the camera bridge is under `gateway/go2rtc-tv-player`.

Critical rule: never restore the old InputHook/libphp injection. It caused confirmed `micomservice`
and `lginput2` crashes. Do not edit Homebrew `startup.sh`, `jumpstart.sh`, bootloader or immutable
rootfs. Keep the injection-free evdev relay and its fail-open supervisor.

Primary goal: reduce cold/warm launcher appearance latency and LG Home visibility while preserving
Plex/YouTube/HDMI/Live TV and stable Home/long-Home/Back behavior. A launch acknowledgement is not a
visible frame; separately measure dispatch, ACK, WAM navigation/paint and Surface Manager visibility.
Power cycles or reboots require explicit operator approval.

The next promising experiment is the webOS Activity Manager boot callback described in the dedicated
document. Start with a timestamp-only service callback and an automatic recovery path. Prove ACG
permissions, one-shot behavior and earlier timing before launching the minimal startup probe, and prove
that before targeting the production launcher. Permit one dispatch per boot and no retry after an
ambiguous timeout.

Before deployment, make a dated rollback of every touched live file, run the relevant Python/Node
tests, build deterministic IPKs with `python scripts/build-all.py`, verify hashes, and change one
variable per measurement. Document final diffs, artifact hashes, deployment outcome, timing evidence
and rollback commands.
