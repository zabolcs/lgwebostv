#!/usr/bin/env python3
"""Package-level checks for the shared full/quick launcher runtime."""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("launcher_build", ROOT / "scripts" / "build-all.py")
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import setup guard
    raise RuntimeError("build-all.py cannot be loaded")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def ar_members(payload: bytes) -> dict[str, bytes]:
    if not payload.startswith(b"!<arch>\n"):
        raise AssertionError("not an ar archive")
    result: dict[str, bytes] = {}
    position = 8
    while position < len(payload):
        header = payload[position : position + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise AssertionError("invalid ar member header")
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        position += 60
        result[name] = payload[position : position + size]
        position += size + (size % 2)
    return result


def data_files(ipk: bytes) -> dict[str, bytes]:
    compressed = ar_members(ipk)["data.tar.gz"]
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(compressed)), mode="r:") as archive:
        return {
            item.name: archive.extractfile(item).read()
            for item in archive.getmembers()
            if item.isfile()
        }


class LauncherPackagingTests(unittest.TestCase):
    def test_full_overlay_shares_entire_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            BUILDER.BUILD = Path(temporary)
            full, _ = BUILDER.build("launcher", BUILDER.APPS["launcher"])
            overlay, _ = BUILDER.build("launcher-overlay", BUILDER.APPS["launcher-overlay"])
            full, overlay = data_files(full.read_bytes()), data_files(overlay.read_bytes())
            a = "usr/palm/applications/hu.szabi.launcher/"
            b = "usr/palm/applications/hu.szabi.launcher.overlay/"
            for name in set(BUILDER.LAUNCHER_FILES) - {"appinfo.json", "launcher-host.js"}:
                self.assertEqual(full[a + name], overlay[b + name], name)
            manifest = json.loads(overlay[b + "appinfo.json"])
            self.assertIn(b'<script src="launcher-runtime.js"></script>', overlay[b + "index.html"])
            self.assertNotIn(b'<script src="app.js">', overlay[b + "index.html"])
            self.assertEqual(overlay[b + "launcher-runtime.js"], b";\n".join(overlay[b + name] for name in
                ("launcher-cache.js", "launcher-quick-core.js", "launcher-popup-lifecycle.js", "launcher-ui.js", "app.js")))
            self.assertEqual(manifest["defaultWindowType"], "popup")
            self.assertTrue(manifest["transparent"])
            self.assertIn(b'"host":"full-overlay"', overlay[b + "launcher-host.js"])

    def test_dual_hosts_share_runtime_and_build_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            BUILDER.BUILD = Path(temporary)
            full_path, full_digest = BUILDER.build("launcher", BUILDER.APPS["launcher"])
            quick_path, quick_digest = BUILDER.build("launcher-quick", BUILDER.APPS["launcher-quick"])
            full_once = full_path.read_bytes()
            quick_once = quick_path.read_bytes()

            full_path, full_digest_again = BUILDER.build("launcher", BUILDER.APPS["launcher"])
            quick_path, quick_digest_again = BUILDER.build("launcher-quick", BUILDER.APPS["launcher-quick"])
            self.assertEqual(full_once, full_path.read_bytes())
            self.assertEqual(quick_once, quick_path.read_bytes())
            self.assertEqual(full_digest, full_digest_again)
            self.assertEqual(quick_digest, quick_digest_again)

            full = data_files(full_once)
            quick = data_files(quick_once)
            full_root = "usr/palm/applications/hu.szabi.launcher/"
            quick_root = "usr/palm/applications/hu.szabi.launcher.quick/"

            full_manifest = json.loads(full[full_root + "appinfo.json"])
            quick_manifest = json.loads(quick[quick_root + "appinfo.json"])
            self.assertEqual((full_manifest["transparent"], full_manifest["defaultWindowType"]), (False, "card"))
            self.assertEqual((quick_manifest["transparent"], quick_manifest["defaultWindowType"]), (True, "popup"))
            self.assertEqual(full_manifest["version"], quick_manifest["version"])

            full_host = full[full_root + "launcher-host.js"].decode("ascii")
            quick_host = quick[quick_root + "launcher-host.js"].decode("ascii")
            self.assertIn('"host":"full"', full_host)
            self.assertIn('"appId":"hu.szabi.launcher"', full_host)
            self.assertIn('"host":"quick"', quick_host)
            self.assertIn('"appId":"hu.szabi.launcher.quick"', quick_host)

            shared = set(BUILDER.LAUNCHER_FILES) - {"appinfo.json", "launcher-host.js"}
            self.assertIn("launcher-cache.js", shared)
            for filename in shared:
                self.assertEqual(full[full_root + filename], quick[quick_root + filename], filename)

            full_package = json.loads(full["usr/palm/packages/hu.szabi.launcher/packageinfo.json"])
            quick_package = json.loads(quick["usr/palm/packages/hu.szabi.launcher.quick/packageinfo.json"])
            self.assertEqual(full_package["app"], "hu.szabi.launcher")
            self.assertEqual(quick_package["app"], "hu.szabi.launcher.quick")

    def test_diagnostic_package_includes_activity_manager_service(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            BUILDER.BUILD = Path(temporary)
            path, digest = BUILDER.build(
                "launcher-startup-probe",
                BUILDER.DIAGNOSTIC_APPS["launcher-startup-probe"],
            )
            first = path.read_bytes()
            path, digest_again = BUILDER.build(
                "launcher-startup-probe",
                BUILDER.DIAGNOSTIC_APPS["launcher-startup-probe"],
            )
            self.assertEqual(first, path.read_bytes())
            self.assertEqual(digest, digest_again)

            files = data_files(first)
            app_id = "hu.szabi.launcher.startupprobe"
            service_id = app_id + ".service"
            app_root = f"usr/palm/applications/{app_id}/"
            service_root = f"usr/palm/services/{service_id}/"
            package = json.loads(files[f"usr/palm/packages/{app_id}/packageinfo.json"])
            manifest = json.loads(files[app_root + "appinfo.json"])

            self.assertEqual(package["app"], app_id)
            self.assertEqual(package["services"], [service_id])
            self.assertEqual(manifest["version"], "0.0.3")
            self.assertIn("activity.operation", manifest["requiredACG"])
            for filename in ("package.json", "services.json", "service-core.js", "service.js"):
                self.assertIn(service_root + filename, files)

    def test_quick_directory_contains_metadata_only(self) -> None:
        entries = sorted(path.name for path in (ROOT / "apps" / "launcher-quick").iterdir())
        self.assertEqual(entries, ["README-HU.md", "appinfo.json"])


if __name__ == "__main__":
    unittest.main()
