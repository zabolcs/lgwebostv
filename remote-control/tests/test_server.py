#!/usr/bin/env python3

import json
import io
import base64
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server  # noqa: E402


class ValidationTests(unittest.TestCase):
    def test_tv_power_request_is_exact_and_normalized(self):
        self.assertEqual(server.validate_tv_power_request({"state": "ON"}), "on")
        self.assertEqual(server.validate_tv_power_request({"state": "off"}), "off")
        for value in ({}, {"state": "toggle"}, {"state": "on", "extra": True}, "on"):
            with self.subTest(value=value), self.assertRaises(server.RequestError):
                server.validate_tv_power_request(value)

    @unittest.skipIf(server.Image is None, "Pillow is optional on legacy installs")
    def test_launcher_thumbnail_downsizes_without_upscaling(self):
        for original, limit, expected in [((2304, 1296), (480, 270), (480, 270)),
                                           ((3840, 2160), (1280, 720), (1280, 720)),
                                           ((100, 100), (480, 270), (100, 100))]:
            raw = io.BytesIO()
            server.Image.new("RGB", original, "red").save(raw, "JPEG")
            mime, payload = server.launcher_thumbnail("image/jpeg", raw.getvalue(), limit)
            self.assertEqual(mime, "image/jpeg")
            with server.Image.open(io.BytesIO(payload)) as result:
                self.assertEqual(result.size, expected)

    def test_camera_presence_contract_constants(self):
        self.assertEqual(server.CAMERA_PRESENCE_PATH, "/api/tv-presence/camera-viewer")
        self.assertEqual(server.CAMERA_PRESENCE_TTL_SECONDS, 8.0)

    def test_direct_image_with_complete_layout(self):
        result = server.validate_show_request({
            "kind": "image",
            "url": "http://192.168.0.150:1984/api/stream.mjpeg?src=kapu_preview&quality=high",
            "fit": "cover",
            "corner": "bottom-right",
            "width": 800,
            "height": "450",
            "marginX": 20,
            "marginY": 30,
            "ttlMs": 0,
        })
        self.assertEqual(result["v"], 1)
        self.assertEqual(result["action"], "show")
        self.assertEqual(result["kind"], "image")
        self.assertEqual(result["width"], 800)
        self.assertEqual(result["height"], 450)
        self.assertEqual(result["ttlMs"], 0)
        self.assertRegex(result["requestId"], r"^[0-9a-f]{32}$")

    def test_direct_text(self):
        result = server.validate_show_request({"kind": "text", "text": "Ajtó nyitva"})
        self.assertEqual(result["text"], "Ajtó nyitva")
        self.assertNotIn("url", result)

    def test_preset(self):
        result = server.validate_show_request({"presetId": "kapu-preview", "ttlMs": 20_000})
        self.assertEqual(result["presetId"], "kapu-preview")
        self.assertNotIn("kind", result)

    def test_rejects_unknown_and_mixed_fields(self):
        with self.assertRaisesRegex(server.RequestError, "Ismeretlen"):
            server.validate_show_request({"kind": "text", "text": "x", "command": "id"})
        with self.assertRaisesRegex(server.RequestError, "Preset"):
            server.validate_show_request({"presetId": "kapu", "kind": "image"})

    def test_url_policy(self):
        allowed = "https://10.0.0.2/live/camera.m3u8?camera=front&quality=high"
        self.assertEqual(server.validate_media_url(allowed), allowed)
        denied = (
            "http://192.168.0.100/live",
            "http://8.8.8.8/live",
            "http://127.0.0.1/live",
            "http://169.254.1.2/live",
            "http://camera.local/live",
            "http://192.168.0.2/live?token=secret",
            "http://192.168.0.2/proxy/192.168.0.100/live",
            "http://user:pass@192.168.0.2/live",
        )
        for value in denied:
            with self.subTest(value=value):
                with self.assertRaises(server.RequestError):
                    server.validate_media_url(value)

    def test_numeric_limits(self):
        with self.assertRaisesRegex(server.RequestError, "width"):
            server.validate_show_request({"kind": "text", "text": "x", "width": 200})
        with self.assertRaisesRegex(server.RequestError, "ttlMs"):
            server.validate_show_request({"kind": "text", "text": "x", "ttlMs": -1})

    def test_configure_defaults(self):
        result = server.validate_configure_request({
            "corner": "top-right", "width": 720, "height": 405,
            "marginX": 18, "marginY": 24, "ttlMs": 0,
        })
        self.assertEqual(result["action"], "configure")
        self.assertEqual(result["ttlMs"], 0)
        self.assertRegex(result["requestId"], r"^[0-9a-f]{32}$")
        with self.assertRaisesRegex(server.RequestError, "Legalább"):
            server.validate_configure_request({})
        with self.assertRaisesRegex(server.RequestError, "Ismeretlen"):
            server.validate_configure_request({"url": "http://192.168.0.2/x.jpg"})

    def test_create_update_and_delete_preset_requests(self):
        saved = server.validate_preset_save_request({
            "presetId": "kapu-web", "kind": "image",
            "url": "http://192.168.0.150:1984/api/stream.mjpeg?src=kapu_preview",
            "fit": "cover", "clickAction": "openCamera", "cameraId": "kapu",
        })
        self.assertEqual(saved["action"], "preset-save")
        self.assertEqual(saved["clickAction"], "openCamera")
        self.assertEqual(saved["cameraId"], "kapu")
        deleted = server.validate_preset_delete_request({"presetId": "kapu-web"})
        self.assertEqual(deleted["action"], "preset-delete")
        with self.assertRaisesRegex(server.RequestError, "kamera-ID"):
            server.validate_preset_save_request({
                "presetId": "bad", "kind": "text", "text": "x",
                "clickAction": "openCamera", "cameraId": "../kapu",
            })

    def test_camera_crud_layout_and_open_requests(self):
        profile = {
            "id": "profile-garazs", "cameraId": "garazs", "name": "Garázs",
            "scheme": "http", "host": "192.168.0.150", "port": 1984,
            "playerPort": 1985, "playerPath": "/webos-player.html", "audio": True,
            "primarySource": "garazs_h264", "previewSource": "garazs_preview",
        }
        saved = server.validate_camera_save_request(profile)
        self.assertEqual(saved["action"], "camera-save")
        self.assertTrue(saved["audio"])
        self.assertEqual(server.validate_camera_delete_request({"cameraId": "garazs"})["action"], "camera-delete")
        self.assertEqual(server.validate_camera_open_request({"cameraId": "garazs"})["view"], "full")
        layout = server.validate_camera_configure_request({
            "layoutSize": 4, "featuredCameraId": "garazs", "preventScreenSaver": True,
            "previewIntervalSeconds": 8,
        })
        self.assertEqual(layout["layoutSize"], 4)
        self.assertEqual(layout["previewIntervalSeconds"], 8)
        reordered = server.validate_camera_reorder_request({"cameraIds": ["kapu", "garazs", "udvar"]})
        self.assertEqual(reordered["action"], "camera-reorder")
        self.assertEqual(reordered["cameraIds"], ["kapu", "garazs", "udvar"])
        with self.assertRaisesRegex(server.RequestError, "ismétlődő"):
            server.validate_camera_reorder_request({"cameraIds": ["kapu", "kapu"]})
        with self.assertRaises(server.RequestError):
            server.validate_camera_reorder_request({"cameraIds": ["../kapu"]})
        with self.assertRaises(server.RequestError):
            server.validate_camera_save_request({**profile, "host": "192.168.0.100"})
        with self.assertRaises(server.RequestError):
            server.validate_camera_save_request({**profile, "audio": "true"})

    def test_synced_configs_and_unlimited_camera_state(self):
        base = {
            "scheme": "http", "host": "192.168.0.150", "port": 1984,
            "playerPort": 1985, "playerPath": "/webos-player.html", "audio": False,
        }
        profiles = [{
            **base, "id": f"profile-{index}", "cameraId": f"camera-{index}",
            "name": f"Kamera {index}", "primarySource": f"source-{index}",
            "previewSource": f"preview-{index}",
        } for index in range(25)]
        config = server.validate_synced_config("camera-viewer", {
            "version": 3,
            "settings": {"layoutSize": 3, "featuredCameraId": "camera-0", "preventScreenSaver": True,
                         "previewIntervalSeconds": 5},
            "profiles": profiles,
        })
        self.assertEqual(len(config["profiles"]), 25)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = server.StateStore(path)
            self.assertIsNone(store.snapshot("camera-viewer"))
            store.update("camera-viewer", config)
            self.assertEqual(store.snapshot("camera-viewer")["profiles"][24]["cameraId"], "camera-24")
            reloaded = server.StateStore(path)
            self.assertEqual(len(reloaded.snapshot("camera-viewer")["profiles"]), 25)

    def test_synced_overlay_accepts_normalized_text_fit(self):
        config = server.validate_synced_config("media-overlay", {
            "version": 1,
            "layout": {
                "corner": "top-left", "width": 640, "height": 360,
                "marginX": 32, "marginY": 32, "ttlMs": 15000,
            },
            "presets": [{
                "id": "welcome", "kind": "text", "content": "Media Overlay",
                "fit": "contain", "clickAction": "", "cameraId": "",
            }],
        })
        self.assertEqual(config["presets"][0]["fit"], "contain")

    def test_remote_mapper_structured_actions_and_locked_buttons(self):
        key_code, binding = server.validate_remote_bind_request({
            "keyCode": 398, "action": "launch", "appId": "hu.szabi.mediaoverlay",
        })
        self.assertEqual(key_code, 398)
        self.assertEqual(binding, {"action": "launch", "id": "hu.szabi.mediaoverlay"})
        self.assertEqual(
            server.validate_remote_bind_request({"keyCode": 399, "action": "replace", "targetKeyCode": 400})[1],
            {"action": "replace", "keycode": 400},
        )
        self.assertIsNone(server.validate_remote_bind_request({"keyCode": 1037, "action": "original"})[1])
        home_code, home_binding = server.validate_remote_bind_request({"keyCode": 773, "action": "ignore"})
        self.assertEqual(home_code, 773)
        self.assertEqual(home_binding, {"action": "ignore"})
        home_code, home_binding = server.validate_remote_bind_request({"keyCode": 773, "action": "launcherHome"})
        self.assertEqual(home_code, 773)
        self.assertEqual(home_binding["bindingType"], "launcherHome")
        self.assertEqual(home_binding["appId"], server.LAUNCHER_APP_ID)
        self.assertIn(server.LAUNCHER_HOME_KEY, home_binding["command"])
        with self.assertRaisesRegex(server.RequestError, "Home"):
            server.validate_remote_bind_request({"keyCode": 398, "action": "launcherHome"})
        with self.assertRaises(server.RequestError):
            server.validate_remote_bind_request({"keyCode": 398, "action": "exec", "command": "reboot"})
        _, preset_binding = server.validate_remote_bind_request({
            "keyCode": 398, "action": "overlayPreset", "presetId": "gyerekszoba",
        })
        self.assertEqual(preset_binding["bindingType"], "overlayPreset")
        self.assertEqual(preset_binding["presetId"], "gyerekszoba")
        self.assertIn(server.LAUNCH_URI, preset_binding["command"])
        self.assertIn(server.APP_ID, preset_binding["command"])
        _, camera_binding = server.validate_remote_bind_request({
            "keyCode": 399, "action": "cameraOpen", "cameraId": "gyerekszoba",
        })
        self.assertEqual(camera_binding["bindingType"], "cameraOpen")
        self.assertIn(server.CAMERA_APP_ID, camera_binding["command"])
        _, command_binding = server.validate_remote_bind_request({
            "keyCode": 400, "action": "appCommand", "appId": server.APP_ID,
            "params": {"v": 1, "action": "show", "presetId": "gyerekszoba"},
        })
        self.assertEqual(command_binding["bindingType"], "appCommand")
        self.assertEqual(command_binding["params"]["presetId"], "gyerekszoba")
        self.assertNotIn("; reboot", command_binding["command"])
        with self.assertRaises(server.RequestError):
            server.validate_remote_bind_request({
                "keyCode": 398, "action": "appCommand", "appId": server.APP_ID,
                "params": "{}; reboot",
            })
        _, webhook_binding = server.validate_remote_bind_request({
            "keyCode": 401, "action": "webhook",
            "webhookUrl": "http://192.168.1.20:8123/api/webhook/light_toggle-1",
        })
        self.assertEqual(webhook_binding["bindingType"], "webhook")
        self.assertIn("/usr/bin/curl", webhook_binding["command"])
        self.assertIn("--request POST", webhook_binding["command"])
        self.assertFalse(webhook_binding["command"].rstrip().endswith("&"))
        self.assertNotIn(";", webhook_binding["command"])
        for bad_url in (
            "https://example.com/api/webhook/x", "http://192.168.1.20:8123/api/services/light/toggle",
            "http://user:pass@192.168.1.20/api/webhook/x", "http://192.168.1.20/api/webhook/x?bad=1",
            "http://192.168.1.20/api/webhook/x;reboot",
        ):
            with self.assertRaises(server.RequestError):
                server.validate_remote_bind_request({"keyCode": 401, "action": "webhook", "webhookUrl": bad_url})
        self.assertEqual(server.validate_remote_restore_request({"source": "previous"}), "previous")

    def test_connections_launcher_and_png_contracts(self):
        connections = server.validate_connections({
            "controlOrigin": "http://192.168.1.20:8765", "tvHost": "192.168.1.30",
            "gatewayScheme": "http", "gatewayHost": "192.168.1.40", "mediaPort": 1984,
            "playerPort": 1985, "playerPath": "/webos-player.html",
        })
        self.assertEqual(connections["tvHost"], "192.168.1.30")
        config = server.LauncherStore._default()
        config["rows"][2]["items"].append({
            "id": "nas", "type": "link", "targetId": "http://192.168.1.20:8765", "label": "NAS", "visible": True,
            "fit": "small", "iconUrl": "http://192.168.1.20/icon.png", "backgroundColor": "#123abc",
        })
        config["rows"] = [config["rows"][4], config["rows"][0], config["rows"][2], config["rows"][3], config["rows"][1]]
        checked = server.validate_launcher_config(config)
        self.assertEqual(checked["rows"][0]["id"], "utilities")
        self.assertEqual(len(checked["settings"]["wallpaperUrls"]), 40)
        self.assertEqual(checked["settings"]["wallpaperDimPercent"], 42)
        self.assertEqual(checked["settings"]["focusScalePercent"], 10)
        self.assertFalse(checked["settings"]["defaultHomeEnabled"])
        self.assertTrue(checked["settings"]["bootOverlayEnabled"])
        self.assertEqual(checked["settings"]["bootOverlayMaxSeconds"], 2)
        self.assertTrue(checked["settings"]["animationsEnabled"])
        self.assertTrue(checked["settings"]["visualEffectsEnabled"])
        self.assertFalse(checked["settings"]["resumeLastAppOnPowerEnabled"])
        self.assertEqual(checked["settings"]["homeLaunchMode"], "split")
        nas = checked["rows"][2]["items"][0]
        self.assertEqual((nas["fit"], nas["backgroundColor"]), ("small", "#123abc"))
        self.assertEqual(nas["iconKey"], "")
        self.assertEqual(nas["iconUrl"], "http://192.168.1.20/icon.png")
        bad = server.LauncherStore._default()
        bad["rows"][4]["items"][0]["backgroundColor"] = "red"
        with self.assertRaises(server.RequestError):
            server.validate_launcher_config(bad)
        bad_icon = server.LauncherStore._default()
        bad_icon["rows"][4]["items"][0]["iconKey"] = "unknown"
        with self.assertRaises(server.RequestError):
            server.validate_launcher_config(bad_icon)
        bad_weather = server.LauncherStore._default()
        bad_weather["settings"]["weatherEnabled"] = True
        bad_weather["settings"]["weatherLabel"] = "Kótaj"
        with self.assertRaises(server.RequestError):
            server.validate_launcher_config(bad_weather)
        png = server._png_from_bgrx(1, 1, b"\x01\x02\x03\x00")
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_launcher_animation_and_effect_preferences_are_independent(self):
        for animations in (False, True):
            for effects in (False, True):
                with self.subTest(animations=animations, effects=effects):
                    config = server.LauncherStore._default()
                    config["settings"]["animationsEnabled"] = animations
                    config["settings"]["visualEffectsEnabled"] = effects
                    config["settings"]["wallpaperEnabled"] = True
                    checked = server.validate_launcher_config(config)["settings"]
                    self.assertIs(checked["animationsEnabled"], animations)
                    self.assertIs(checked["visualEffectsEnabled"], effects)
                    self.assertTrue(checked["wallpaperEnabled"])
                    self.assertEqual(checked["wallpaperUrls"], config["settings"]["wallpaperUrls"])
        for rejected in (0, 1, None, "false", [], {}):
            with self.subTest(rejected=rejected):
                config = server.LauncherStore._default()
                config["settings"]["visualEffectsEnabled"] = rejected
                with self.assertRaises(server.RequestError):
                    server.validate_launcher_config(config)
        legacy = server.LauncherStore._default()
        legacy["settings"].pop("visualEffectsEnabled")
        legacy["settings"]["animationsEnabled"] = False
        self.assertTrue(server.validate_launcher_config(legacy)["settings"]["visualEffectsEnabled"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launcher.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            migrated = server.LauncherStore(path).snapshot()["settings"]
            self.assertTrue(migrated["visualEffectsEnabled"])
            self.assertFalse(migrated["animationsEnabled"])
            self.assertEqual(migrated["wallpaperEnabled"], legacy["settings"]["wallpaperEnabled"])

    def test_launcher_focus_scale_and_legacy_store_migration(self):
        for accepted in (5, 10, 15, 20):
            config = server.LauncherStore._default()
            config["settings"]["focusScalePercent"] = accepted
            self.assertEqual(server.validate_launcher_config(config)["settings"]["focusScalePercent"], accepted)
        for rejected in (6, 0, 25, True):
            config = server.LauncherStore._default()
            config["settings"]["focusScalePercent"] = rejected
            with self.assertRaises(server.RequestError):
                server.validate_launcher_config(config)
        legacy = server.LauncherStore._default()
        legacy["rows"][0]["items"].append({
            "id": "keep-me", "type": "app", "targetId": "com.example.keep", "label": "Marad",
            "visible": True, "fit": "contain", "iconUrl": "", "backgroundColor": "",
        })
        legacy["settings"].pop("focusScalePercent")
        legacy["settings"].pop("defaultHomeEnabled")
        legacy["settings"].pop("homeLaunchMode")
        legacy["settings"]["wallpaperUrls"] = legacy["settings"]["wallpaperUrls"][:20]
        legacy["settings"]["wallpaperUrls"].append(server.LEGACY_BAD_WALLPAPER_URL)
        legacy["settings"]["wallpaperUrls"].append(server.LEGACY_BAD_WALLPAPER_URL_2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launcher.json"
            path.write_text(json.dumps(legacy), encoding="utf-8")
            migrated = server.LauncherStore(path).snapshot()
            self.assertEqual(migrated["settings"]["focusScalePercent"], 10)
            self.assertFalse(migrated["settings"]["defaultHomeEnabled"])
            self.assertEqual(migrated["settings"]["homeLaunchMode"], "split")
            self.assertEqual(len(migrated["settings"]["wallpaperUrls"]), 40)
            self.assertNotIn(server.LEGACY_BAD_WALLPAPER_URL, migrated["settings"]["wallpaperUrls"])
            self.assertNotIn(server.LEGACY_BAD_WALLPAPER_URL_2, migrated["settings"]["wallpaperUrls"])
            self.assertEqual(migrated["rows"][0]["items"][0]["id"], "keep-me")

    def test_camera_snapshot_and_cpu_percent_contracts(self):
        self.assertEqual(
            server.launcher_snapshot_url("http://192.168.1.40:1984/api/stream.mjpeg?src=front"),
            "http://192.168.1.40:1984/api/stream.mjpeg?src=front",
        )
        self.assertEqual(
            server.launcher_frame_url("http://192.168.1.40:1984/api/stream.mjpeg?src=c210rtsp1_mjpeg"),
            "http://192.168.1.40:1984/api/frame.jpeg?src=c210rtsp1_mjpeg",
        )
        self.assertEqual(
            server.launcher_frame_url("http://192.168.1.40:1984/api/frame.jpeg?src=front"),
            "http://192.168.1.40:1984/api/frame.jpeg?src=front",
        )
        self.assertEqual(server.launcher_profile_frame_url({
            "id": "profile-front", "cameraId": "front", "name": "Front", "scheme": "http",
            "host": "192.168.1.40", "port": 1984, "playerPort": 1985,
            "playerPath": "/webos-player.html", "audio": True,
            "primarySource": "front_h264", "previewSource": "front_preview",
        }), "http://192.168.1.40:1984/api/frame.jpeg?src=front_preview")
        jpeg = b"\xff\xd8\xffframe-data\xff\xd9"
        self.assertEqual(server.extract_first_jpeg(b"--boundary\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"), jpeg)
        self.assertIsNone(server.extract_first_jpeg(b"incomplete \xff\xd8\xff frame"))
        fixture = "\n".join((
            "CPU", "cpu 100 0 100 800 0", "cpu 150 0 150 900 0",
            "LOAD", "0.42 0.31 0.28 1/100 1", "MEM", "MemTotal: 1000 kB", "MemAvailable: 400 kB",
            "DISK", "TEMP", "TOP", "PID CPU MEM COMMAND", "123 8.0 4.2 WebAppMgr",
        ))
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, fixture, "")
        manager = server.InputHookManager({
            "tv_host": "192.168.1.30", "ssh_key": "/key", "known_hosts": "/known",
        }, runner=runner)
        diagnostics = manager.diagnostics()
        self.assertEqual(diagnostics["cpuPercent"], 50.0)
        self.assertEqual(diagnostics["processRows"], [{"pid": "123", "user": "", "cpu": "8.0", "memory": "4.2", "command": "WebAppMgr"}])

    def test_launcher_adds_available_tv_and_hdmi_utilities(self):
        with tempfile.TemporaryDirectory() as directory:
            store = server.LauncherStore(Path(directory) / "launcher.json")
            config = store.snapshot()
            config["rows"][0]["items"].append({
                "id": "existing", "type": "app", "targetId": "com.example.app", "label": "Meglévő",
                "visible": True, "fit": "contain", "iconKey": "", "iconUrl": "", "backgroundColor": "",
            })
            config["rows"][4]["items"].append({
                "id": "utility-com-webos-app-hdmi3", "type": "app", "targetId": "com.webos.app.hdmi3",
                "label": "HDMI 3", "visible": True, "fit": "contain", "iconKey": "hdmi",
                "iconUrl": "", "backgroundColor": "",
            })
            store.update(config)
            utility_row = next(row for row in config["rows"] if row["id"] == "utilities")
            utility_row["items"] = [item for item in utility_row["items"] if item["id"] not in {"all-apps", "launcher-settings"}]
            store.update(config)
            store.seed([
                {"id": "com.webos.app.livetv", "title": "Live TV"},
                {"id": "com.webos.app.hdmi1", "title": "HDMI 1"},
                {"id": "com.webos.app.hdmi2", "title": "HDMI 2"},
            ], [])
            utilities = next(row for row in store.snapshot()["rows"] if row["id"] == "utilities")
            targets = [item["targetId"] for item in utilities["items"]]
            self.assertEqual(targets[-3:], ["com.webos.app.livetv", "com.webos.app.hdmi1", "com.webos.app.hdmi2"])
            self.assertNotIn("com.webos.app.hdmi3", targets)
            self.assertEqual(utilities["items"][-1]["iconKey"], "hdmi")
            self.assertEqual([item["id"] for item in utilities["items"][:2]], ["all-apps", "launcher-settings"])

    def test_state_store_wait_after_follows_tv_sync_update(self):
        with tempfile.TemporaryDirectory() as directory:
            store = server.StateStore(Path(directory) / "state.json")
            revision = store.revision("media-overlay")
            expected = {
                "version": 1,
                "layout": {"corner": "top-right", "width": 640, "height": 360,
                           "marginX": 32, "marginY": 32, "ttlMs": 0},
                "presets": [],
            }
            store.update("media-overlay", expected)
            self.assertEqual(store.wait_after("media-overlay", revision, timeout=0.01), expected)

    def test_remote_mapper_shortcuts_come_from_synced_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = server.StateStore(Path(directory) / "state.json")
            store.update("media-overlay", {
                "version": 1,
                "layout": {"corner": "top-right", "width": 640, "height": 360, "marginX": 20, "marginY": 20, "ttlMs": 0},
                "presets": [{"id": "gyerekszoba", "kind": "image", "content": "http://192.168.0.150:1984/api/stream.mjpeg?src=c210rtsp1_mjpeg", "fit": "cover", "clickAction": "openCamera", "cameraId": "gyerekszoba"}],
            })
            store.update("camera-viewer", {
                "version": 3,
                "settings": {"layoutSize": 2, "featuredCameraId": "", "preventScreenSaver": True, "previewIntervalSeconds": 2},
                "profiles": [{"id": "profile-gyerekszoba", "cameraId": "gyerekszoba", "name": "Gyerekszoba", "scheme": "http", "host": "192.168.0.150", "port": 1984, "playerPort": 1985, "playerPath": "/webos-player.html", "primarySource": "c210rtsp1", "previewSource": "c210rtsp1_mjpeg", "audio": True}],
            })
            shortcuts = server.remote_mapper_shortcuts(store)
            self.assertEqual(shortcuts["presets"][0]["id"], "gyerekszoba")
            self.assertEqual(shortcuts["cameras"][0]["name"], "Gyerekszoba")


class LauncherTests(unittest.TestCase):
    def test_parses_multiline_and_multiple_luna_responses(self):
        output = 'notice\n{\n  "subscribed": true,\n  "returnValue": true\n}\n{\n  "returnValue": true,\n  "appId": "hu.szabi.mediaoverlay"\n}\n'
        self.assertEqual(server.parse_luna_response(output)["appId"], "hu.szabi.mediaoverlay")

    def test_fixed_app_and_luna_target(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, '{"returnValue":true}\n', "")

        launcher = server.TvLauncher({
            "tv_host": "192.168.0.240",
            "tv_user": "root",
            "ssh_key": "/run/key",
            "known_hosts": "/run/known_hosts",
        }, runner=runner)
        response = launcher.launch({"v": 1, "action": "dismiss", "requestId": "0" * 32})
        self.assertTrue(response["returnValue"])
        command = calls[0][0]
        self.assertIn("-tt", command)
        self.assertNotIn("-T", command)
        self.assertIn("root@192.168.0.240", command)
        remote = command[-1]
        self.assertIn(server.LAUNCH_URI, remote)
        self.assertIn(server.APP_ID, remote)
        self.assertNotIn("shell=True", str(calls[0][1]))

    def test_rejects_failed_ssh_and_luna(self):
        def ssh_failure(command, **kwargs):
            return subprocess.CompletedProcess(command, 255, "", "Permission denied")

        launcher = server.TvLauncher({
            "tv_host": "192.168.0.240", "ssh_key": "/key", "known_hosts": "/known"
        }, runner=ssh_failure)
        with self.assertRaisesRegex(RuntimeError, "TV-parancs"):
            launcher.launch({"v": 1, "action": "dismiss"})

        def luna_failure(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, '{"returnValue":false}\n', "")

        launcher.runner = luna_failure
        with self.assertRaisesRegex(RuntimeError, "elutasította"):
            launcher.launch({"v": 1, "action": "dismiss"})

    def test_accepts_luna_reply_from_ssh_stderr(self):
        def stderr_reply(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 0, "", '{\n  "returnValue": true\n}\nConnection closed.\n'
            )

        launcher = server.TvLauncher({
            "tv_host": "192.168.0.240", "ssh_key": "/key", "known_hosts": "/known"
        }, runner=stderr_reply)
        self.assertTrue(launcher.launch({"v": 1, "action": "dismiss"})["returnValue"])


class TvPowerManagerTests(unittest.TestCase):
    def config(self):
        return {
            "tv_host": "192.168.0.240", "tv_user": "root", "ssh_key": "/key", "known_hosts": "/known",
            "tv_wifi_mac": "64:cb:e9:08:47:c6", "tv_wake_broadcasts": ["192.168.0.255"],
        }

    def test_status_uses_native_webos_power_state(self):
        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, '{"returnValue":true,"state":"Active"}\n', "")

        state = server.TvPowerManager(self.config(), runner=runner, probe=lambda host: True).status()
        self.assertEqual(state["state"], "on")
        self.assertTrue(state["on"])
        self.assertEqual(state["nativeState"], "Active")

    def test_wifi_wake_targets_configured_wlan_mac_on_both_ports(self):
        sends = []
        manager = server.TvPowerManager(
            self.config(), probe=lambda host: False,
            wake_sender=lambda packet, host, port: sends.append((packet, host, port)),
        )
        state = manager.set_state("on")
        self.assertEqual(state["state"], "turning_on")
        self.assertEqual(len(sends), 6)
        self.assertEqual({item[2] for item in sends}, {7, 9})
        self.assertEqual({item[1] for item in sends}, {"192.168.0.255"})
        self.assertEqual(sends[0][0], b"\xff" * 6 + bytes.fromhex("64cbe90847c6") * 16)

    def test_power_off_runs_native_command_in_background(self):
        commands = []

        def runner(command, **kwargs):
            commands.append(command[-1])
            if "getPowerState" in command[-1]:
                return subprocess.CompletedProcess(command, 0, '{"returnValue":true,"state":"Active"}\n', "")
            return subprocess.CompletedProcess(command, 0, "", "")

        state = server.TvPowerManager(self.config(), runner=runner, probe=lambda host: True).set_state("off")
        self.assertEqual(state["state"], "turning_off")
        shutdown = next(command for command in commands if "powerOff" in command)
        self.assertIn("nohup /bin/sh -c", shutdown)
        self.assertIn('reason', shutdown)

    def test_power_requests_are_idempotent_during_transition(self):
        sends = []
        manager = server.TvPowerManager(
            self.config(), probe=lambda host: False,
            wake_sender=lambda packet, host, port: sends.append((packet, host, port)),
        )
        manager.set_state("on")
        manager.set_state("on")
        self.assertEqual(len(sends), 6)


class LauncherAppCatalogTests(unittest.TestCase):
    def test_persists_catalog_and_blocks_parallel_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "apps.json"
            catalog = server.LauncherAppCatalog(path)
            self.assertTrue(catalog.should_refresh())
            self.assertTrue(catalog.begin_refresh())
            self.assertFalse(catalog.begin_refresh())
            catalog.finish_refresh([{"id": "hu.szabi.launcher", "title": "Launcher"}])
            self.assertEqual(catalog.snapshot(), [{"id": "hu.szabi.launcher", "title": "Launcher"}])
            self.assertFalse(catalog.should_refresh())
            restored = server.LauncherAppCatalog(path)
            self.assertEqual(restored.snapshot()[0]["id"], "hu.szabi.launcher")


class LauncherHomeManagerTests(unittest.TestCase):
    def make_manager(self):
        commands = []
        enabled = False

        def runner(command, **kwargs):
            nonlocal enabled
            remote = command[-1]
            commands.append(remote)
            if "mkdir -p" in remote or "printf %s" in remote or "base64 -d" in remote:
                return subprocess.CompletedProcess(command, 0, "", "")
            if "closeByAppId" in remote:
                return subprocess.CompletedProcess(command, 0, '{"appId":"hu.szabi.launcher","returnValue":true}', "")
            if "listRunningApps" in remote:
                return subprocess.CompletedProcess(command, 0, "running=0\n", "")
            if "suppress_until=$(cat /tmp/hu.szabi.launcher.full-close-suppress" in remote:
                return subprocess.CompletedProcess(command, 0, "", "")
            if remote.startswith("rm -f "):
                enabled = False
                return subprocess.CompletedProcess(command, 0, "", "")
            if "printf 'enabled=1" in remote or "printf 'enabled=0" in remote:
                return subprocess.CompletedProcess(command, 0, "enabled=%d\nrunning=%d\n" % (enabled, enabled), "")
            if remote.startswith("touch "):
                if server.LAUNCHER_HOME_ENABLED in remote:
                    enabled = True
                return subprocess.CompletedProcess(command, 0, "", "")
            if "pauseApp" in remote:
                return subprocess.CompletedProcess(command, 0, '{"appId":"hu.szabi.launcher","returnValue":true}', "")
            return subprocess.CompletedProcess(command, 1, "", "unexpected command")

        manager = server.LauncherHomeManager({
            "tv_host": "192.168.0.240", "tv_user": "root", "ssh_key": "/key", "known_hosts": "/known",
        }, runner=runner)
        return manager, commands

    def test_guard_uses_supported_homebrew_hook_and_lifecycle_subscriptions(self):
        manager, commands = self.make_manager()
        result = manager.set_enabled(True)
        self.assertTrue(result["enabled"])
        install = "\n".join(commands)
        self.assertIn(server.LAUNCHER_HOME_INIT, install)
        self.assertIn(server.LAUNCHER_HOME_KEY, install)
        self.assertIn(server.LAUNCHER_HOME_ENABLED, install)
        self.assertIn(".new.b64", install)
        self.assertIn("getForegroundAppInfo", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("getPowerState", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("POWER_STATE=/tmp/hu.szabi.launcher.power-state", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("wake_gap_loop", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("Never interrupt an already running app", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("[[:space:]]*:[[:space:]]*", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn(server.LAUNCHER_APP_ID, server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn('com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*)', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("launch_last_or_custom", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn('POWER_OFF_APP="$DIR/power-off-app"', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn('ACTIVE_APP="$DIR/active-app-at-power-off"', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("snapshot_power_off_app", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("Always ask Luna first", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn('if [ -f "$POWER_STARTUP" ]; then', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("payload=$(printf", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn('"$payload" 2>&1', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn('rm -f "$POWER_OFF_APP"', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("com.webos.app.livetv", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("com.webos.app.hdmi*", server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn("^$HOME_KEY_CODE => [012]$", server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn("HOME_KEY_CODE=${LAUNCHER_HOME_KEY_CODE:-773}", server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn("mode=overlay", server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn("mode=full", server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn("home-short", server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn("home-long", server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn('HOME_MODE="$DIR/home-mode"', server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn('full) mode=full', server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn('overlay) mode=overlay', server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn('QUICK_APP=hu.szabi.launcher.quick', server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn('FULL_APP=hu.szabi.launcher', server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn('touch "$visible"', server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertIn('close_quick', server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertNotIn('prewarm_launcher', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertNotIn('pauseApp', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertNotIn('$VISIBLE_MODE', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertNotIn('"$VISIBLE"', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn('own_popup_visible && return 0', server.LauncherHomeManager.GUARD_SCRIPT)
        self.assertIn('"controlOrigin":"%s"', server.LauncherHomeManager.GUARD_SCRIPT)
        manager.set_home_launch_mode("full")
        self.assertIn(server.LAUNCHER_HOME_MODE, commands[-1])
        self.assertIn("full", commands[-1])
        disabled = manager.set_enabled(False)
        self.assertFalse(disabled["enabled"])
        self.assertIn(server.LAUNCHER_HOME_INIT, commands[-2])
        self.assertNotIn(server.LAUNCHER_HOME_KEY, commands[-2])
        self.assertIn("python -c", commands[-2])
        self.assertIn("start", server.LauncherHomeManager.GUARD_SCRIPT)

    def test_factory_home_escape_uses_only_owned_marker(self):
        manager, commands = self.make_manager()
        manager.allow_factory_home()
        self.assertEqual(commands[-1], "touch " + server.LAUNCHER_HOME_ALLOW)
        manager.revoke_factory_home()
        self.assertEqual(commands[-1], "rm -f " + server.LAUNCHER_HOME_ALLOW)

    def test_launcher_can_be_hidden_and_really_restarted(self):
        manager, commands = self.make_manager()
        self.assertTrue(manager.park_launcher("quick")["returnValue"])
        self.assertIn("closeByAppId", commands[-1])
        self.assertIn("close-suppress", commands[-1])
        self.assertIn(server.LAUNCHER_HOME_ALLOW, commands[-1])
        self.assertIn(server.LAUNCHER_APP_ID, commands[-1])
        self.assertIn('close_attempt=0', commands[-1])
        self.assertIn('close_attempt\" -lt 3', commands[-1])
        self.assertNotIn('listRunningApps', commands[-1].split('closeByAppId', 1)[0])
        self.assertIn('listRunningApps', commands[-1])
        self.assertIn('2>&1 || true', commands[-1])
        self.assertNotIn('2>/dev/null || true', commands[-1])
        self.assertTrue(manager.terminate_launcher()["returnValue"])
        self.assertIn("closeByAppId", commands[-1])
        self.assertIn("close-suppress", commands[-1])
        self.assertIn(server.LAUNCHER_APP_ID, commands[-1])
        self.assertFalse(manager.launcher_running())
        self.assertTrue(manager.wait_launcher_state(False, 0.25))
        manager.mark_launcher_visible()
        self.assertIn("suppress_until=$(cat /tmp/hu.szabi.launcher.full-close-suppress", commands[-1])
        self.assertIn('[ "$now" -lt "$suppress_until" ]', commands[-1])
        manager.mark_launcher_prewarm_ready()
        self.assertEqual(commands[-1], "touch " + server.LAUNCHER_HOME_FULL_PREWARM_READY)

    def test_host_validation_and_full_back_preserve_process(self):
        hidden_manager, hidden_commands = self.make_manager()
        hidden_manager.mark_launcher_hidden("quick")
        self.assertEqual(hidden_commands[-1], "rm -f /tmp/hu.szabi.launcher.quick-visible")
        self.assertNotIn("closeByAppId", hidden_commands[-1])
        with self.assertRaises(server.RequestError):
            hidden_manager.mark_launcher_hidden("full")
        for mode in ("split", "full", "overlay"):
            config = server.LauncherStore._default()
            config["settings"].update(homeLaunchMode=mode, fullLauncherPresentation="overlay")
            checked = server.validate_launcher_config(config)
            self.assertEqual(checked["settings"]["homeLaunchMode"], mode)
            self.assertEqual(checked["settings"]["fullLauncherPresentation"], "overlay")
        self.assertEqual(server.LauncherHomeManager.host_from_request({"host":"full-overlay","mode":"full"}), "full-overlay")
        manager, commands = self.make_manager()
        manager.park_launcher("full-overlay")
        self.assertIn("closeByAppId", commands[-1])
        self.assertIn("hu.szabi.launcher.overlay", commands[-1])
        self.assertEqual(server.LauncherHomeManager.host_from_request({}), "full")
        self.assertEqual(server.LauncherHomeManager.host_from_request({"host": "quick", "mode": "overlay"}), "quick")
        for raw in ([], {"host": "quick", "mode": "full"}, {"host": "evil", "mode": "full"}, {"host": "full"}):
            with self.assertRaises(server.RequestError):
                server.LauncherHomeManager.host_from_request(raw)
        commands = []
        def runner(command, **kwargs):
            commands.append(command)
            output = "com.webos.app.plex" if command[-1].startswith("cat ") else '{"returnValue": true}'
            return subprocess.CompletedProcess(command, 0, output, "")
        manager = server.LauncherHomeManager({"tv_host": "192.168.0.240", "ssh_key": "/key", "known_hosts": "/known"}, runner=runner)
        manager.park_launcher("full")
        self.assertNotIn("closeByAppId", commands[-1][-1])
        self.assertIn("com.webos.app.plex", commands[-1][-1])
        self.assertIn("-tt", commands[-1])
        for host in ("full", "quick"):
            command = manager._verified_close_command(host)
            self.assertIn(server.LAUNCHER_HOSTS[host]["appId"], command)
            self.assertIn(server.LAUNCHER_HOSTS[host]["appId"].replace(".", "[.]"), command)

    def test_lifecycle_close_uses_forced_remote_tty(self):
        transports = []

        def runner(command, **kwargs):
            transports.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        manager = server.LauncherHomeManager({
            "tv_host": "192.168.0.240", "tv_user": "root", "ssh_key": "/key", "known_hosts": "/known",
        }, runner=runner)
        manager.park_launcher("quick")
        self.assertIn("-tt", transports[-1])
        self.assertNotIn("-T", transports[-1])
        manager.allow_factory_home()
        self.assertIn("-T", transports[-1])
        self.assertNotIn("-tt", transports[-1])

    def test_full_back_without_real_target_never_launches_factory_home(self):
        calls = []
        manager = server.LauncherHomeManager({"tv_host": "192.168.0.240", "ssh_key": "/key", "known_hosts": "/known"},
            runner=lambda command, **kwargs: calls.append(command) or subprocess.CompletedProcess(command, 0, "", ""))
        for target in ("", server.LAUNCHER_APP_ID, server.LAUNCHER_QUICK_APP_ID, "com.webos.app.home"):
            manager.last_app = lambda: target
            with self.assertRaises(server.RequestError):
                manager.park_launcher("full")
        self.assertEqual(calls, [], "No markers or app launches may run for a missing Back destination")


class InputHookManagerTests(unittest.TestCase):
    def make_manager(self, installed=True):
        stored = {
            "1037": {"action": "launch", "id": "cdp-30"},
            "9999": {"action": "exec", "command": "legacy-command"},
        }
        commands = []

        def runner(command, **kwargs):
            nonlocal stored
            remote = command[-1]
            commands.append(remote)
            if remote.startswith("cat "):
                return subprocess.CompletedProcess(command, 0, json.dumps(stored), "")
            if "listApps" in remote:
                apps = [
                    {"id": "hu.szabi.mediaoverlay", "title": "Media Overlay"},
                    {"id": "hu.szabi.launcher", "title": "Launcher"},
                ] if installed else []
                return subprocess.CompletedProcess(command, 0, json.dumps({"returnValue": True, "apps": apps}), "")
            if "base64 -d" in remote:
                match = re.search(r"printf '%s' ([A-Za-z0-9+/=]+|'[A-Za-z0-9+/=]+') \| base64", remote)
                if not match:
                    return subprocess.CompletedProcess(command, 1, "", "missing payload")
                encoded = match.group(1).strip("'")
                stored = json.loads(base64.b64decode(encoded).decode("utf-8"))
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(command, 1, "", "unexpected command")

        manager = server.InputHookManager({
            "tv_host": "192.168.0.240", "tv_user": "root", "ssh_key": "/key", "known_hosts": "/known",
        }, runner=runner)
        return manager, commands, lambda: stored

    def test_updates_one_binding_and_preserves_unknown_legacy_entries(self):
        manager, commands, get_stored = self.make_manager()
        result = manager.update_binding({"keyCode": 398, "action": "launch", "appId": "hu.szabi.mediaoverlay"})
        self.assertTrue(result["changed"])
        self.assertEqual(get_stored()["398"], {"action": "launch", "id": "hu.szabi.mediaoverlay"})
        self.assertEqual(get_stored()["9999"], {"action": "exec", "command": "legacy-command"})
        write_command = next(command for command in commands if "base64 -d" in command)
        self.assertIn(server.INPUT_HOOK_ORIGINAL, write_command)
        self.assertIn(server.INPUT_HOOK_PREVIOUS, write_command)

    def test_rejects_launching_an_app_not_installed_on_tv(self):
        manager, commands, get_stored = self.make_manager(installed=False)
        with self.assertRaisesRegex(server.RequestError, "telepített"):
            manager.update_binding({"keyCode": 398, "action": "launch", "appId": "hu.szabi.mediaoverlay"})
        self.assertFalse(any("base64 -d" in command for command in commands))
        self.assertNotIn("398", get_stored())

    def test_managed_preset_binding_requires_synced_preset_and_keeps_fixed_command(self):
        manager, commands, get_stored = self.make_manager()
        shortcuts = {"presets": [{"id": "gyerekszoba", "kind": "image"}], "cameras": []}
        result = manager.update_binding(
            {"keyCode": 398, "action": "overlayPreset", "presetId": "gyerekszoba"}, shortcuts,
        )
        self.assertTrue(result["changed"])
        binding = get_stored()["398"]
        self.assertEqual(binding["managedBy"], server.REMOTE_MAPPER_APP_ID)
        self.assertIn(server.LAUNCH_URI, binding["command"])
        self.assertIn("/usr/bin/luna-send-pub", binding["command"])
        self.assertIn("-t 1", binding["command"])
        self.assertNotIn("(sleep 4) |", binding["command"])
        with self.assertRaisesRegex(server.RequestError, "szinkronizált"):
            manager.update_binding(
                {"keyCode": 399, "action": "overlayPreset", "presetId": "nem-letezik"}, shortcuts,
            )

    def test_managed_home_binding_is_home_only_and_requires_installed_launcher(self):
        manager, commands, get_stored = self.make_manager()
        result = manager.update_binding({"keyCode": 773, "action": "launcherHome"})
        self.assertTrue(result["changed"])
        binding = get_stored()["773"]
        self.assertEqual(binding["bindingType"], "launcherHome")
        self.assertEqual(binding["command"], server.LAUNCHER_HOME_KEY + " >/dev/null 2>&1")
        self.assertNotIn("luna-send", binding["command"])
        self.assertIn("/bin/usleep 50000", server.LauncherHomeManager.HOME_KEY_SCRIPT)
        self.assertNotIn("sleep 0.05", server.LauncherHomeManager.HOME_KEY_SCRIPT)

        missing, _, _ = self.make_manager(installed=False)
        with self.assertRaisesRegex(server.RequestError, "telepített"):
            missing.update_binding({"keyCode": 773, "action": "launcherHome"})


class InputHookWatchdogManagerTests(unittest.TestCase):
    def test_installs_only_targeted_repair_and_disable_never_signals_stale_pid(self):
        commands = []

        def runner(command, **kwargs):
            commands.append(command[-1])
            return subprocess.CompletedProcess(command, 0, "", "")

        manager = server.InputHookWatchdogManager({
            "tv_host": "192.168.0.240", "tv_user": "root", "ssh_key": "/key", "known_hosts": "/known",
        }, runner=runner)
        manager.set_enabled(True)
        self.assertIn(server.INPUT_HOOK_WATCHDOG_INIT, commands[-1])
        self.assertIn(server.INPUT_HOOK_WATCHDOG_ENABLED, commands[-1])
        self.assertNotIn("org.webosbrew.inputhook.service/start", manager.WATCHDOG_SCRIPT)
        self.assertNotIn("luna-send", manager.WATCHDOG_SCRIPT)
        self.assertIn("repair-home-hook.sh", manager.WATCHDOG_SCRIPT)
        self.assertIn("flock -n 9", manager.WATCHDOG_SCRIPT)
        manager.set_enabled(False)
        self.assertEqual(commands[-1], "rm -f " + server.INPUT_HOOK_WATCHDOG_ENABLED + " " + server.INPUT_HOOK_WATCHDOG_INIT)

    def test_watchdog_requires_explicit_boolean_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for value in (None, False, True, "false", "true", 0, 1):
                config = {
                    "public_base_url": "http://192.168.0.223:8765",
                    "tv_wifi_mac": "64:cb:e9:08:47:c6", "tv_wake_broadcasts": ["192.168.0.255"],
                }
                if value is not None:
                    config["input_hook_watchdog_enabled"] = value
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.subTest(value=value):
                    if value is None or isinstance(value, bool):
                        self.assertIs(server.load_config(path)["input_hook_watchdog_enabled"], value is True)
                    else:
                        with self.assertRaisesRegex(ValueError, "input_hook_watchdog_enabled"):
                            server.load_config(path)
        example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.assertIs(example["input_hook_watchdog_enabled"], False)
        installer = (ROOT / "install-in-ct.sh").read_text(encoding="utf-8")
        self.assertIn('"input_hook_watchdog_enabled": false', installer)
        self.assertNotIn('"input_hook_watchdog_enabled": true', installer)


class RemoteBrokerManagerTests(unittest.TestCase):
    def make_manager(self, mode="grab", runner=None):
        return server.RemoteBrokerManager({
            "tv_host": "192.168.0.240", "tv_user": "root", "ssh_key": "/key",
            "known_hosts": "/known", "remote_broker_mode": mode,
        }, runner=runner or (lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "", "")))

    def test_compiles_only_structured_allowlisted_bindings(self):
        manager = self.make_manager()
        config, actions = manager.compile_bindings({
            "398": {"action": "ignore"},
            "399": {"action": "replace", "keycode": 400},
            "401": {"action": "launch", "id": "com.webos.app.livetv"},
            "773": {"action": "exec", "managedBy": server.REMOTE_MAPPER_APP_ID,
                    "bindingType": "launcherHome", "command": "evil legacy value"},
            "787": {"action": "exec", "managedBy": server.REMOTE_MAPPER_APP_ID,
                    "bindingType": "overlayPreset", "presetId": "kapu"},
            "994": {"action": "exec", "managedBy": server.REMOTE_MAPPER_APP_ID,
                    "bindingType": "cameraOpen", "cameraId": "bejaro"},
            "1037": {"action": "exec", "managedBy": server.REMOTE_MAPPER_APP_ID,
                     "bindingType": "appCommand", "appId": "hu.szabi.launcher", "params": {"v": 1}},
            "1038": {"action": "exec", "managedBy": server.REMOTE_MAPPER_APP_ID,
                     "bindingType": "webhook", "webhookUrl": "http://192.168.0.223:8123/api/webhook/tv-blue"},
            "1042": {"action": "exec", "command": "rm -rf /"},
            "1044": {"action": "exec", "managedBy": server.REMOTE_MAPPER_APP_ID,
                     "bindingType": "appCommand", "appId": "bad id", "params": {}},
            "9999": {"action": "ignore"},
        })
        self.assertIn("mode=grab", config)
        self.assertIn("device=LGE M-RCU - Builtin [0]", config)
        self.assertNotIn("device=LGE Simple Premium", config)
        self.assertNotIn("device=LGE RCU", config)
        self.assertIn("398=ignore", config)
        self.assertIn("399=replace:400", config)
        for code in (401, 773, 787, 994, 1037, 1038):
            self.assertIn(f"{code}=action", config)
            self.assertIn(code, actions)
        self.assertNotIn("1042=", config)
        self.assertNotIn("1044=", config)
        self.assertNotIn("9999=", config)
        all_actions = "\n".join(actions.values())
        self.assertNotIn("evil legacy value", all_actions)
        self.assertNotIn("rm -rf", all_actions)
        self.assertIn(server.LAUNCHER_HOME_KEY, actions[773])
        self.assertIn("LAUNCHER_HOME_KEY_CODE=773", actions[773])
        self.assertIn("hu.szabi.remote-broker.key-773.state", actions[773])
        self.assertIn('"presetId":"kapu"', actions[787])
        self.assertIn('"cameraId":"bejaro"', actions[994])
        self.assertIn("/api/webhook/tv-blue", actions[1038])

    def test_runtime_status_reports_native_hook_and_fail_open(self):
        def runner(command, **kwargs):
            output = "binary=1\nenabled=1\nactive=1\nmode=grab\nnativeHookLoaded=0\n"
            return subprocess.CompletedProcess(command, 0, output, "")
        status = self.make_manager(runner=runner).status()
        self.assertTrue(status["available"])
        self.assertTrue(status["enabled"])
        self.assertTrue(status["active"])
        self.assertFalse(status["nativeHookLoaded"])
        self.assertIsNone(status["failOpen"])
        self.assertTrue(status["grabReleasedOnExit"])
        self.assertEqual(status["transport"], "factory-evdev-relay")

    def test_enable_splits_generated_actions_into_bounded_ssh_commands(self):
        commands = []
        def runner(command, **kwargs):
            remote = command[-1]
            commands.append(remote)
            output = "4-evdev-relay" if remote.startswith("test -x ") else ""
            return subprocess.CompletedProcess(command, 0, output, "")
        manager = self.make_manager(runner=runner)
        bindings = {
            str(code): {"action": "exec", "managedBy": server.REMOTE_MAPPER_APP_ID,
                        "bindingType": "cameraOpen", "cameraId": "kamera"}
            for code in (398, 399, 400, 401, 787, 994, 1037, 1038, 1042, 1044, 1086)
        }
        manager.set_enabled(True, bindings)
        action_writes = [command for command in commands if "/actions.new/" in command and "base64 -d" in command]
        self.assertEqual(len(action_writes), len(bindings))
        self.assertLess(max(map(len, commands)), 8192)
        self.assertTrue(manager.enabled)

    def test_binding_sync_reloads_active_broker_without_recreating_clone(self):
        commands = []
        def runner(command, **kwargs):
            remote = command[-1]
            commands.append(remote)
            if "printf '%s' \"$p\"" in remote:
                return subprocess.CompletedProcess(command, 0, "4321", "")
            return subprocess.CompletedProcess(command, 0, "", "")
        manager = self.make_manager(runner=runner)
        manager.enabled = True
        manager.sync_bindings({"398": {"action": "ignore"}})
        self.assertTrue(any("kill -HUP 4321" in command for command in commands))
        self.assertFalse(any(command.startswith("rm -f " + server.REMOTE_BROKER_ENABLED) for command in commands))

    def test_broker_requires_explicit_grab_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            base = {
                "public_base_url": "http://192.168.0.223:8765",
                "tv_wifi_mac": "64:cb:e9:08:47:c6", "tv_wake_broadcasts": ["192.168.0.255"],
            }
            path.write_text(json.dumps(base), encoding="utf-8")
            loaded = server.load_config(path)
            self.assertIs(loaded["remote_broker_enabled"], False)
            self.assertEqual(loaded["remote_broker_mode"], "passive")
            path.write_text(json.dumps({**base,
                "remote_broker_enabled": True, "remote_broker_mode": "passive",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "grab módban"):
                server.load_config(path)
            path.write_text(json.dumps({**base,
                "remote_broker_enabled": True, "remote_broker_mode": "grab",
            }), encoding="utf-8")
            self.assertTrue(server.load_config(path)["remote_broker_enabled"])
        example = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.assertIs(example["remote_broker_enabled"], False)
        self.assertEqual(example["remote_broker_mode"], "passive")
        installer = (ROOT / "install-in-ct.sh").read_text(encoding="utf-8")
        self.assertIn('"remote_broker_enabled": false', installer)
        self.assertIn('"remote_broker_mode": "passive"', installer)

    def test_native_broker_contract_is_fail_open_and_has_no_shell_execution_api(self):
        broker_root = ROOT.parent / "remote-broker"
        source = (broker_root / "remote-broker.c").read_text(encoding="utf-8")
        self.assertIn("EVIOCGRAB", source)
        self.assertNotIn("UI_DEV_CREATE", source)
        self.assertNotIn("UI_DEV_DESTROY", source)
        self.assertIn("PR_SET_PDEATHSIG", source)
        self.assertIn('ACTION_ROOT "/%u"', source)
        self.assertIn("BROKER_KEY_MAX 2047U", source)
        self.assertIn("sources[i].ufd = open_output(cfg, &sources[i], true)", source)
        self.assertIn("LGE M-RCU - Builtin [2]", source)
        self.assertIn("LOCK_EX | LOCK_NB", source)
        self.assertNotIn("system(", source)
        self.assertNotIn("popen(", source)
        self.assertIn("crash circuit breaker", server.RemoteBrokerManager.SUPERVISOR_SCRIPT)
        self.assertIn("stale heartbeat", server.RemoteBrokerManager.SUPERVISOR_SCRIPT)
        self.assertNotIn("systemctl", server.RemoteBrokerManager.SUPERVISOR_SCRIPT)
        self.assertIn("trap 'exit 0' INT TERM HUP", server.RemoteBrokerManager.SUPERVISOR_SCRIPT)
        self.assertIn("--recover-output", server.RemoteBrokerManager.SUPERVISOR_SCRIPT)
        self.assertIn("held-key routes preserved", source)
        self.assertIn("write_key_state(code, event.value)", source)
        self.assertIn("sigaction(SIGHUP, &reload_action", source)
        binary_path = broker_root / "remote-broker"
        if binary_path.exists():
            binary = binary_path.read_bytes()
            self.assertEqual(binary[:4], b"\x7fELF")
            self.assertEqual(binary[4:6], b"\x01\x01")  # ELF32, little endian
            self.assertEqual(struct.unpack_from("<H", binary, 18)[0], 40)  # EM_ARM
        installer = (broker_root / "install-on-tv.sh").read_text(encoding="utf-8")
        self.assertIn("--check-config", installer)
        self.assertIn("nincs engedélyezve", installer)
        self.assertNotIn('touch "$ROOT/enabled"', installer)


class StaticTests(unittest.TestCase):
    def test_ui_contains_show_dismiss_and_yaml(self):
        source = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn("/api/show", source)
        self.assertIn("/api/configure", source)
        self.assertIn("/api/presets/save", source)
        self.assertIn("/api/presets/delete", source)
        self.assertIn("/api/cameras/save", source)
        self.assertIn("/api/cameras/delete", source)
        self.assertIn("/api/cameras/configure", source)
        self.assertIn("/api/cameras/reorder", source)
        self.assertIn("/api/cameras/open", source)
        self.assertIn('id="tv-power-toggle"', source)
        self.assertIn("/assets/power-control.js", source)
        power_source = (ROOT / "static" / "power-control.js").read_text(encoding="utf-8")
        self.assertIn("/api/tv/power", power_source)
        self.assertIn("Wi-Fi", power_source)
        self.assertIn('id="preset-list"', source)
        self.assertIn('id="camera-list"', source)
        self.assertIn('id="layout-size"', source)
        self.assertIn('id="featured-camera"', source)
        self.assertIn('id="prevent-screensaver"', source)
        self.assertIn('id="camera-order"', source)
        self.assertIn("setAttribute('draggable','true')", source)
        self.assertIn("/api/dismiss", source)
        self.assertIn('data-page="remote"', source)
        self.assertIn('id="rm-remote"', source)
        self.assertIn("/assets/remote-ui.js", source)
        self.assertIn("HA YAML", source)
        self.assertNotIn("access-token", source)
        self.assertNotIn("Bearer", source)
        self.assertNotIn("192.168.0.240", source)
        self.assertIn('value="dismiss"', source)
        self.assertIn("/api/tv-key", (ROOT / "static" / "launcher-admin.js").read_text(encoding="utf-8"))
        self.assertIn("/api/media-overlay/state", source)
        self.assertIn("/api/camera-viewer/state", source)
        self.assertIn("loadCachedState()", source)
        self.assertNotIn("Promise.all([refreshOverlay(),refreshCamera()])", source)

    def test_remote_mapper_ui_uses_only_structured_api(self):
        app_root = ROOT.parent / "apps" / "remote-mapper"
        source = (app_root / "remote-ui.js").read_text(encoding="utf-8")
        app_source = (app_root / "app.js").read_text(encoding="utf-8")
        app_html = (app_root / "index.html").read_text(encoding="utf-8")
        self.assertIn("/api/remote-mapper/state", source)
        self.assertIn("/api/remote-mapper/bind", source)
        self.assertIn("/api/remote-mapper/restore", source)
        self.assertNotIn("command:", source)
        self.assertNotIn("access-token", source)
        self.assertIn("requireArm: true", app_source)
        self.assertIn("confirmSave: true", app_source)
        self.assertIn('id="rm-arm"', app_html)
        self.assertIn('id="rm-home-warning"', app_html)
        self.assertIn('isCritical', source)
        self.assertIn('isLocked', source)

    def test_launcher_tv_navigation_and_whole_page_layout(self):
        launcher_root = ROOT.parent / "apps" / "launcher"
        source = (launcher_root / "launcher-ui.js").read_text(encoding="utf-8")
        styles = (launcher_root / "launcher.css").read_text(encoding="utf-8")
        self.assertIn("code === 37 || code === 38 || code === 39 || code === 40", source)
        self.assertIn("rowId === 'favorites' || rowId === 'cameras' ? 5", source)
        self.assertIn("strip.scrollLeft", source)
        self.assertIn("launcher-page-spacer", source)
        self.assertIn("calc((100vw - 288px)/5)", styles)
        self.assertIn("margin-left:40px", styles)
        self.assertIn("scroll-snap-type:none", styles)
        self.assertIn("scroll-snap-align:none", styles)
        self.assertIn("visibleRowTiles(nextRow)[0]", source)
        self.assertIn("visibleRowTiles(currentStrip)", source)
        self.assertIn("if (!pinTop && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });", source)
        self.assertIn("scrollPageTop", source)
        self.assertIn("strip.scrollLeft + tileRectangle.left - stripRectangle.left - stripPadding", source)
        self.assertIn("--launcher-focus-safe", source)
        self.assertIn("font-size:18px", styles)
        self.assertIn("scale(var(--launcher-focus-scale))", styles)
        self.assertIn("outline:0!important", styles)
        self.assertIn(".launcher-icon-action,.launcher-close{outline:0!important", styles)
        self.assertIn(".launcher-icon-action:hover,.launcher-icon-action:focus,.launcher-close:hover,.launcher-close:focus{z-index:6;outline:0!important;transform:scale(1.2)}", styles)
        self.assertIn(".launcher-tv-body .launcher-icon-action:hover:not(:focus)", styles)
        self.assertIn(".launcher-tv-body .launcher-content{padding:44px 52px 42px}", styles)
        self.assertIn(".launcher-tv-body .launcher-top{margin-bottom:30px}", styles)
        self.assertIn("opacity:0", styles)
        self.assertIn(".launcher-shell [hidden]{display:none!important}", styles)
        self.assertIn("Kilépés az LG Home menübe", source)
        self.assertIn("defaultHomeEnabled", source)
        self.assertIn("/api/launcher/system-home", source)
        self.assertIn("Launcher alkalmazás teljes újraindítása", source)
        self.assertIn("/api/launcher/restart", source)
        self.assertIn("launcher-parked", styles)
        self.assertIn("top:0;right:0;bottom:0;left:0", styles)
        self.assertNotIn("inset:0", styles)
        self.assertIn("hover:not(:focus)", styles)
        self.assertIn("launcher-fit-cover", styles)
        self.assertIn("launcher-fit-small", styles)
        self.assertIn("okHoldTimer", source)
        self.assertIn("enterEditMode(active)", source)
        self.assertIn("moveEditedTile", source)
        self.assertIn("strip.insertBefore", source)
        self.assertIn("savedTile.classList.remove('launcher-editing')", source)
        self.assertIn("launcher-camera-preview", source)
        self.assertIn("editorModeEnabled", source)
        self.assertIn("launcher-add-tile", source)
        self.assertNotIn("node.classList.contains('launcher-add-tile')", source)
        self.assertIn("soronként + csempe", source)
        self.assertIn("preload.onload", source)
        self.assertIn("Keep the currently displayed image", source)
        self.assertIn("launcher-edit-toolbar", source)
        self.assertIn("launcher-process-table", source)
        self.assertIn("launcher-resume-icon", source)
        self.assertNotIn('aria-hidden="true">↻', source)
        self.assertIn("fallback.hidden = true", source)
        self.assertIn("fallbackTimer", source)
        self.assertIn("bootOverlayMaxSeconds", source)
        self.assertIn("animationsEnabled", source)
        self.assertIn("resumeLastAppOnPowerEnabled", source)
        app_source = (launcher_root / "app.js").read_text(encoding="utf-8")
        self.assertIn("webOSRelaunch", app_source)
        self.assertIn("PalmSystem.activate", app_source)
        self.assertIn("controller.resume", app_source)
        self.assertIn("hu.szabi.launcher.offline-state.v1", app_source)
        self.assertIn("PalmServiceBridge", app_source)
        self.assertIn("localRequest", app_source)
        self.assertIn("syncFromNas", app_source)
        self.assertIn("forecast_hours=36", app_source)
        self.assertIn("typeof options.request === 'function'", source)
        self.assertIn("useState: function", source)
        self.assertIn(".launcher-setting-toggle select", styles)
        self.assertIn("launcher-boot", (launcher_root / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((launcher_root / "appinfo.json").read_text(encoding="utf-8"))["splashBackground"], "splash-black.png")
        self.assertIn("launcher-tile-settings-form", source)
        self.assertIn("iconUrl", source)
        self.assertIn("backgroundColor", source)
        self.assertIn("ICON_CATALOG", source)
        self.assertIn("suggestedIconKey", source)
        self.assertIn("moonlight", source)
        self.assertIn("lyrion", source)
        self.assertIn("immich", source)
        self.assertIn("hdmi", source)
        self.assertIn("LAUNCHER_ICON_CATALOG", (ROOT / "server.py").read_text(encoding="utf-8"))
        self.assertIn("launcher-tile-icon-key", source)
        self.assertIn("/api/launcher/camera-preview?presetId=", source)
        self.assertIn("directPresetGo2rtc", source)
        self.assertIn("preset.content", source)
        self.assertIn("preset.previewUrl", source)
        self.assertIn("parsed.pathname !== '/api/frame.jpeg' && parsed.pathname !== '/api/stream.mjpeg'", source)
        self.assertIn("privateHost", source)
        self.assertIn('"previewUrl": launcher_profile_frame_url(profile)', (ROOT / "server.py").read_text(encoding="utf-8"))
        self.assertIn("global.setTimeout(refreshPreviews, 60000)", source)
        self.assertIn("__launcherArmFallback", source)
        self.assertIn("launcher-weather-detail", source)
        self.assertIn("Következő 36 óra", source)
        self.assertIn('{"presetId", "_launcher"}', (ROOT / "server.py").read_text(encoding="utf-8"))
        self.assertIn("focusScalePercent", source)
        self.assertIn("diag.cpuPercent", source)
        admin = (ROOT / "static" / "launcher-admin.js").read_text(encoding="utf-8")
        self.assertIn("launcher-default-home", admin)
        self.assertIn("/api/launcher/system-home", admin)
        self.assertIn("Teljes csempe kitöltése", admin)
        self.assertIn("Saját ikon vagy kép URL", admin)
        self.assertIn("launcher-focus-scale", admin)
        self.assertIn("focusScalePercent", admin)
        self.assertIn("Beépített ikon", admin)
        self.assertIn("iconKey", admin)
        self.assertIn("launcher-admin-tile-tools", admin)
        self.assertIn("dragstart", admin)
        self.assertIn("launcher-admin-camera-thumb", admin)
        self.assertIn("launcher-admin-camera-thumb img", styles)
        self.assertIn("read_json(allow_text_plain=True)", (ROOT / "server.py").read_text(encoding="utf-8"))
        self.assertIn('"editorModeEnabled"', (ROOT / "server.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
