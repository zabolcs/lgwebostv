# LG webOS custom launcher and control suite

Source-only checkpoint from 2026-09-25. It contains the editable source for:

- full, quick and overlay launcher variants using one shared core;
- Camera Viewer;
- Media Overlay / PiP;
- Remote Mapper;
- the `lgtv-control` web application for the control container;
- the native SSAP wake accelerator;
- the injection-free evdev remote broker;
- the restricted go2rtc player bridge;
- build/install scripts and regression tests.
- current diagnostic, recovery and measurement helpers under `tools/lab`;
- generated TV shell-script references under `tools/generated-tv-scripts`.

No IPK, native binary, compiler archive, private key, SSAP credential, production configuration,
container snapshot, TV snapshot or runtime log is included. Exact live restore material belongs in
the separate private NAS checkpoint.

## Current production versions

Launcher full/quick/overlay 0.3.11; Camera Viewer 0.3.11; Media Overlay 0.3.7;
Remote Mapper 0.2.0. The deployed Magic Remote overlay and webwrappers are preserved only in the
private live checkpoint because their current canonical editable source was not in this suite.

## Build

```sh
python scripts/build-all.py
```

Run the Python and Node tests under `tests/`, `remote-control/tests/`, and each app's `tests/`
directory before deployment. The native broker test always validates `remote-broker.c`; if CI first
builds `remote-broker/remote-broker`, it also validates that output as an ARM32 little-endian ELF.
See `TEST-REPORT.md`, `README-HU.md`, and the component READMEs.

## Safety-critical history

Do not restore the legacy InputHook/libphp injection. It caused confirmed crashes in `micomservice`
and `lginput2`. The current remote broker reads/relays evdev in userspace and does not inject into LG
processes. Do not edit Homebrew `startup.sh`, `jumpstart.sh`, the bootloader or immutable rootfs.

The next promising cold-boot experiment is documented in
`docs/AUTOSTART-ACTIVITYMANAGER-KISERLET.md`. Start with a timestamp-only callback and automatic
recovery; do not launch the production app until the timing and loop behavior are proven.

## Configuration

Copy `remote-control/config.example.json` and supply local network addresses and key paths outside
version control. Never commit SSH private keys, SSAP credentials or `/var/lib/lgtv-control` state.

No public license has been selected in this checkpoint. Add one before accepting outside
contributions or redistributing the code.
