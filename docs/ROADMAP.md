# LG webOS control suite – roadmap

This is the canonical development roadmap for the GitHub source checkpoint imported on 2026-09-25.

## Primary objective

Reduce the time until the custom launcher is visibly usable after both a cold TV reboot and a Quick Start wake. The repository/CI work is infrastructure for that goal, not the product goal itself. The current leading hypothesis is that launch dispatch happens too late in the boot/wake sequence; therefore trigger timing must be improved before further UI micro-optimization.

## Baseline

- Repository workflow: `develop` is the active development branch; `master` is the stable/release branch.
- Imported checkpoint commit: `f66d85c` (`chore: import LGTV source checkpoint`).
- Suite handoff generation: 0.4.1 lineage, with independently versioned webOS applications.
- Production versions recorded by the 2026-09-25 handoff:
  - Launcher full/quick/overlay: 0.3.11
  - Camera Viewer: 0.3.11
  - Media Overlay: 0.3.7
  - Remote Mapper: 0.2.0
- Shared launcher source lives under `apps/launcher/`; full, quick and overlay must not fork into separate UI implementations.
- `launcher-runtime.js` is a build artifact generated in memory by `scripts/build-all.py`; it is intentionally not source-controlled.
- The handoff describes `remote-broker/` as canonical source. The original 2026-09-25 GitHub export accidentally omitted that directory while excluding the same-named compiled `remote-broker` binary. A follow-up source-completeness audit found the canonical C source intact in the original project/private checkpoint and also found 33 omitted development/diagnostic helper scripts plus seven generated TV-script reference copies. The corrected export contains 237 source files and was imported to `develop` in commit `3c38561`; the complete broker contract now runs in CI.
- Exact live restore material, credentials, compiled production binaries, logs and snapshots remain outside Git.

## Non-negotiable safety constraints

- Never restore the legacy InputHook/libphp injection. It caused confirmed crashes in `micomservice` and `lginput2`.
- Do not modify Homebrew `startup.sh`, `jumpstart.sh`, the bootloader or immutable rootfs.
- Keep remote/input changes fail-open and rollbackable.
- A launch ACK is not proof of a visible frame; dispatch, ACK, WAM navigation/paint and Surface Manager visibility are separate measurements.
- Reboot, power-cycle, production deployment and any experiment that can interrupt the active TV require explicit operator approval.
- Before touching live files, create a dated rollback copy and record hashes.
- Never commit SSH keys, SSAP credentials, production config/state, private NAS checkpoint content or runtime secrets.

## P0 – Repository baseline and reproducible validation

### P0.1 Import and branch bootstrap — DONE

- [x] Create `master` stable branch.
- [x] Create `develop` active branch.
- [x] Safely inspect the source checkpoint archive.
- [x] Import the source-only checkpoint without private live material.
- [x] Remove the archive from the repository after import.

### P0.2 Canonical project control — MOSTLY DONE

- [x] Establish this file as the canonical roadmap.
- [x] Replace the one-shot checkpoint inspection workflow with normal source validation.
- [x] Add a read-only CI gate on the self-hosted Linux/X64 runner.
- [x] Run the complete safe offline regression suite.
- [x] Run the deterministic IPK build.
- [x] Record generated artifact names and SHA-256 hashes in CI evidence.
- [x] Verify a second build produces byte-identical IPKs.
- [ ] Resolve documentation paths left over from the pre-GitHub `source/current-suite/` layout.
- [ ] Reconcile old historical test reports with the 2026-09-25 production handoff; historical reports must not be presented as current release evidence.

### P0.3 Source completeness audit — DONE FOR CANONICAL EDITABLE SOURCE

- [x] Confirm the public checkpoint contains the launcher, Camera Viewer, Media Overlay, Remote Mapper, CT125 control app, CT120 camera bridge, build/install scripts and regression tests.
- [x] Confirm `launcher-runtime.js` is generated and is not missing source.
- [x] Make the native broker contract test explicitly SKIP when the canonical broker source is absent; this skip is evidence of incompleteness, not a passing broker validation.
- [x] Recover the canonical `remote-broker/remote-broker.c` from the original project/full checkpoint and fix the export filter. Corrected source SHA-256: `a2e1ba57a32670a038576f7696da8d29fc09added04a5452a645dbff51397d7c`.
- [x] Audit the corrected export for additional omissions: 33 development/diagnostic helper scripts and seven generated TV-script reference copies were restored; no other editable application source was found missing.
- [x] Import the corrected 237-file export into GitHub `develop`, preserving repository-only CI/roadmap files added after the original export. Import commit: `3c38561`.
- [x] Re-enable the native broker contract test without a source-missing skip and require PASS.
- [ ] Decide whether editable source for Magic Remote overlay and webwrappers should be recovered into the public source repository; current handoff says only deployed copies are preserved privately.
- [x] Import and verify the corrected `SOURCE-SHA256SUMS.txt` / source-completeness audit in GitHub. Corrected package evidence: ZIP SHA-256 `1b5ddcafb739f8e1d9900626a353f42209173ed99f8efe6007b4683e638f735e`; TAR SHA-256 `3a9b51861a19888a91e430ff9732a8ce076987cd39e6373098d4b430946c11cf`.

### P0.4 Baseline parity and reproducibility gate — REQUIRED BEFORE LIVE EXPERIMENTS

- [x] Get all available-source Python and Node regression suites green on the self-hosted runner.
- [x] Produce all six webOS IPKs from GitHub source.
- [x] Build twice and prove byte-identical SHA-256 hashes.
- [x] Record/inspect skips: the remaining environment-dependent Pillow thumbnail test is intentionally optional; broker validation is active and passing.
- [x] Compare app manifests with the 2026-09-25 handoff; production manifest versions match.
- [x] Classify source state: canonical editable suite is source-complete; Magic Remote overlay and some webwrappers remain private-restore-only because no canonical editable source existed in the original project.
- [ ] Normalize stale pre-GitHub paths so the repository itself is the primary source of truth.
- [x] Launcher/control source and validation gate satisfied. Reboot/power-cycle still requires explicit operator approval.

### P0.5 GitHub baseline hygiene — REQUIRED BEFORE STABLE PROMOTION, NOT A BLOCKER FOR LATENCY EXPERIMENTS

- [x] Import the corrected audited source export, including `remote-broker/`, the 33 restored helper scripts, seven generated TV-script reference copies and `docs/SOURCE-COMPLETENESS-AUDIT.md`.
- [x] Re-run the complete CI with the broker contract test active, not skipped.
- [ ] Normalize current component versions in top-level documentation to match manifests/handoff.
- [ ] Replace stale pre-GitHub source paths with repository-root paths while preserving clearly marked private-restore references.
- [ ] Confirm the validated `develop` commit is the intended stable baseline.
- [ ] Fast-forward `master` from the initial upload placeholder to that validated baseline.
- [ ] Remove the redundant legacy `main` branch after `master` is established and no reference depends on it.
- [ ] Keep `develop` as the active development branch after baseline promotion.

## P1 – Safe CI and development workflow

- [x] CI runs offline/read-only validation by default.
- [x] Validate Python syntax and unit tests.
- [x] Validate Node syntax and unit tests.
- [ ] Validate shell syntax for non-destructive scripts.
- [x] Build all six webOS IPKs deterministically.
- [x] Publish build/test logs and IPK hashes as CI evidence where practical.
- [x] Keep deployment, TV access and reboot/power-cycle out of normal push CI.
- [ ] Add explicit/manual workflows later for LAN diagnostics and deployment, with narrow allowlisted operations and rollback evidence.

## P2 – Documentation normalization

- [ ] Make repository-root paths canonical; remove stale `source/current-suite/` and `source/current-development/` instructions where they no longer apply.
- [ ] Keep historical deployment/test reports as history, clearly dated.
- [ ] Make `README.md`, `README-HU.md`, handoff and component READMEs agree on current versions and architecture.
- [ ] Document the GitHub → Actions → self-hosted runner → LAN/TV execution model.
- [ ] Document release/version rules after the baseline suite has been validated; do not silently couple independent app versions without an explicit decision.

## P3 – Launcher startup timing investigation — NEXT

The immediate goal is not a generic live-state audit. It is to identify and remove the delay between the point at which webOS can already launch apps and the point at which the current guard/SSAP path dispatches the custom launcher.

- [ ] Establish a no-reboot baseline timeline for the current launch path.
- [ ] Measure TV-ready/app-launchable state versus current launcher dispatch time.
- [ ] Keep dispatch ACK, WAM navigation/paint and Surface Manager visibility as separate timestamps.
- [ ] Determine cold-boot and Quick Start wake paths separately; they may require different triggers.
- [ ] Prefer earlier native webOS lifecycle signals over faster polling.

### Supporting live-state parity

- [ ] Establish a read-only/manual diagnostics workflow for the self-hosted runner; no deployment or reboot.
- [ ] Capture current CT125/TV component versions, service state and launcher configuration without changing them.
- [ ] Compare the live state to GitHub manifests and the 2026-09-25 handoff.
- [ ] Standardize timestamped measurement output for dispatch, ACK, WAM navigation/paint and Surface Manager visibility.
- [ ] Keep credentials and exact private restore material outside Git.
- [ ] Document rollback ownership and the single source of launch responsibility before any boot experiment.

## P4 – Activity Manager cold-boot experiment

Source of truth: `docs/AUTOSTART-ACTIVITYMANAGER-KISERLET.md`.

Prepared diagnostic package: `hu.szabi.launcher.startupprobe` 0.0.2 with `hu.szabi.launcher.startupprobe.service`; CI contract coverage: `tests/launcher-startup-probe-service.test.js` plus package-level validation.

- [ ] Read-only Activity Manager capability/ACG inspection.
- [x] Timestamp-only callback service source and deterministic diagnostic package prepared; no launcher dispatch. Live callback validation is still pending.
- [ ] Prove one-shot semantics and automatic recovery path.
- [ ] Compare callback uptime with LG Home, Homebrew guard and root SSH timing.
- [ ] Only if timing is materially earlier, test the minimal startup probe.
- [ ] Require explicit operator approval before every reboot/power-cycle.
- [ ] Require at least three successful cold-boot measurements before considering production launcher dispatch.
- [ ] Preserve the TV-local guard as fallback and prevent duplicate launch ownership.

## P5 – Launcher latency measurement and optimization

- [ ] Measure dispatch, ACK, WAM navigation/first paint and native Surface Manager visibility separately.
- [ ] Measure quick popup first surface without rebuilding the existing popup architecture.
- [ ] Preserve Plex/YouTube/HDMI/Live TV behavior and stable Home/long-Home/Back semantics.
- [ ] Change one variable per measurement.
- [ ] Reject optimizations that improve ACK only but not visible surface latency.

## P6 – UI and operational refinements

- [ ] Improve TV settings focus order/categories after boot-path work.
- [ ] Review CT125 admin UI usability and diagnostics.
- [ ] Keep Camera Viewer/WebRTC fallback behavior covered by regression tests.
- [ ] Keep URL policy and LAN-only restrictions covered by tests.

## Release gate

A release candidate may move from `develop` toward `master` only when:

1. the safe offline regression suite passes for all source that is present;
2. every skipped test is explicitly explained and no skip hides a changed subsystem;
3. deterministic builds pass twice with identical hashes;
4. source/version manifests are internally consistent;
5. the changed subsystem is source-complete in Git; the corrected export has restored and validated the canonical remote-broker source;
6. no private material is present in the Git diff;
7. all live changes have explicit rollback instructions;
8. required TV/CT live checks for the changed area have been completed and documented;
9. safety-critical input/boot paths have not regressed.

## Working rule for AI-assisted changes

Work in coherent, reviewable commits. Read the relevant handoff/result notes before changing a subsystem. Prefer tests and measurements over assumptions. Never use a live TV reboot, power-cycle or destructive deployment merely as a convenient validation step.
