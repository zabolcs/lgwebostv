# Source completeness audit

Audit date: 2026-09-25. The GitHub bundle was compared path by path with the 174-file canonical `lgtv-remote-broker` suite and with the source-like top-level files in the current development workspace.

The original packaging bug that excluded the whole `remote-broker` directory has been fixed. `remote-broker/remote-broker.c` and its Makefile, installer, tests, example configuration and documentation are present. All 33 previously unselected source-like lab helpers and the broker ABI C probe are present under `tools/lab`.

Exactly 54 canonical paths are intentionally absent at their original locations: 24 IPK packages, 3 compressed build archives, 14 Python bytecode/cache files, 4 native broker binaries, 2 generated checksum lists and 7 generated TV scripts. The seven text scripts are retained as source references under `tools/generated-tv-scripts`; the native binaries, IPKs, archives, caches and generated checksum lists remain excluded.

The package includes Camera Viewer, the shared full/quick/overlay launcher core and wrappers, Media Overlay/PiP, Remote Mapper, the NAS control web application, the go2rtc TV bridge, the native SSAP wake helper, the evdev remote broker, build scripts and tests.

Known scope limit: the deployed Magic Remote overlay and webwrapper snapshots exist in the separate private NAS checkpoint, but this suite did not contain their current canonical editable source. They were not silently dropped by the GitHub packager.
