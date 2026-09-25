#!/usr/bin/env python3
"""Local, non-persistent visual fixture for the Remote Mapper browser UI."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sys


REMOTE_CONTROL = Path(__file__).resolve().parents[1]
SUITE = REMOTE_CONTROL.parent
sys.path.insert(0, str(REMOTE_CONTROL))
import server  # noqa: E402


STATE = {
    "ok": True,
    "module": "remote-mapper",
    "hook": {"id": "org.webosbrew.inputhook", "version": "1.4.0"},
    "runtime": {"id": "hu.szabi.remote-broker", "available": True, "enabled": True,
                "active": True, "mode": "grab", "nativeHookLoaded": False, "failOpen": True},
    "buttons": [dict(item) for item in server.REMOTE_BUTTONS],
    "bindings": {
        "1037": {"action": "launch", "id": "cdp-30"},
        "1038": {"action": "launch", "id": "youtube.leanback.v4"},
        "1042": {"action": "ignore"},
        "1044": {"action": "ignore"},
        "1086": {"action": "ignore"},
        "1117": {"action": "ignore"},
    },
    "apps": [
        {"id": "hu.szabi.mediaoverlay", "title": "Media Overlay"},
        {"id": "hu.szabi.cameraviewer", "title": "Kamerák"},
        {"id": "hu.szabi.remotemapper", "title": "Távirányító gombok"},
        {"id": "org.lyrion.music", "title": "Lyrion Music Server"},
        {"id": "app.immich", "title": "Immich"},
        {"id": "youtube.leanback.v4", "title": "YouTube"},
        {"id": "cdp-30", "title": "Netflix"},
    ],
    "shortcuts": {
        "presets": [
            {"id": "kapu-preview", "kind": "image"},
            {"id": "gyerekszoba", "kind": "image"},
            {"id": "udvar-preview", "kind": "image"},
        ],
        "cameras": [
            {"cameraId": "kapu", "name": "Kapu"},
            {"cameraId": "gyerekszoba", "name": "Gyerekszoba"},
            {"cameraId": "udvar", "name": "Udvar"},
        ],
    },
}

OVERLAY = {
    "version": 1,
    "layout": {"corner": "top-right", "width": 640, "height": 360, "marginX": 32, "marginY": 32, "ttlMs": 0},
    "presets": [
        {"id": "kapu-preview", "kind": "image", "content": "http://127.0.0.1:8877/mock-camera.svg", "fit": "cover", "clickAction": "openCamera", "cameraId": "kapu"},
        {"id": "gyerekszoba", "kind": "image", "content": "http://127.0.0.1:8877/mock-camera.svg", "fit": "cover", "clickAction": "openCamera", "cameraId": "gyerekszoba"},
    ],
}
CAMERAS = {
    "version": 3,
    "settings": {"layoutSize": 3, "featuredCameraId": "gyerekszoba", "preventScreenSaver": True, "previewIntervalSeconds": 2},
    "profiles": [
        {"id": "profile-kapu", "cameraId": "kapu", "name": "Kapu", "scheme": "http", "host": "192.168.1.40", "port": 1984, "playerPort": 1985, "playerPath": "/webos-player.html", "primarySource": "kapu", "previewSource": "kapu_preview", "audio": True},
        {"id": "profile-gyerek", "cameraId": "gyerekszoba", "name": "Gyerekszoba", "scheme": "http", "host": "192.168.1.40", "port": 1984, "playerPort": 1985, "playerPath": "/webos-player.html", "primarySource": "gyerek", "previewSource": "gyerek_preview", "audio": True},
    ],
}
CONNECTIONS = {"controlOrigin": "http://192.168.1.20:8765", "tvHost": "192.168.1.30", "gatewayScheme": "http", "gatewayHost": "192.168.1.40", "mediaPort": 1984, "playerPort": 1985, "playerPath": "/webos-player.html"}
LAUNCHER = server.LauncherStore._default()
LAUNCHER["lastUsed"] = {"type": "app", "targetId": "hu.szabi.cameraviewer", "label": "Kamerák"}
LAUNCHER["settings"]["weatherEnabled"] = True
LAUNCHER["settings"]["weatherLabel"] = "Budapest"
LAUNCHER["settings"]["focusScalePercent"] = 20
LAUNCHER["rows"][0]["items"] = [
    {"id": "fav-camera", "type": "app", "targetId": "hu.szabi.cameraviewer", "label": "Kamerák", "visible": True},
    {"id": "fav-youtube", "type": "app", "targetId": "youtube.leanback.v4", "label": "YouTube", "visible": True},
    {"id": "fav-lyrion", "type": "app", "targetId": "org.lyrion.music", "label": "Lyrion Music Server", "visible": True},
    {"id": "fav-immich", "type": "app", "targetId": "app.immich", "label": "Immich", "visible": True},
]
LAUNCHER["rows"][1]["items"] = [
    {"id": f"app-{index}", "type": "app", "targetId": f"preview.app.{index}", "label": f"Alkalmazás {index}", "visible": True}
    for index in range(1, 13)
]
LAUNCHER["rows"][2]["items"] = [{"id": "link-nas", "type": "link", "targetId": "http://192.168.1.20:8765", "label": "Otthoni NAS", "visible": True}]
LAUNCHER["rows"][3]["items"] = [{"id": "preset-kapu", "type": "preset", "targetId": "kapu-preview", "label": "Kapu", "visible": True}]


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, content_type: str, payload: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_bytes("text/html; charset=utf-8", (REMOTE_CONTROL / "static" / "index.html").read_bytes())
        elif self.path == "/launcher/":
            self.send_bytes("text/html; charset=utf-8", b'<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/assets/launcher.css"></head><body class="launcher-tv-body" style="background:#000"><div id="launcher-boot" class="launcher-boot-cover" aria-hidden="true"></div><main id="launcher-root"></main><script src="/assets/launcher-ui.js"></script><script>LauncherUI.init(document.getElementById("launcher-root"),{apiBase:"",mode:"tv"});</script></body></html>')
        elif self.path == "/launcher-local/":
            offline = json.loads(json.dumps(LAUNCHER))
            offline["settings"]["weatherEnabled"] = False
            offline["settings"]["wallpaperEnabled"] = False
            state = {"ok": True, "config": offline, "apps": STATE["apps"], "presets": [{"id": item["id"], "kind": item["kind"], "content": item["content"], "fit": item["fit"], "clickAction": item["clickAction"], "cameraId": item["cameraId"], "previewAvailable": True} for item in OVERLAY["presets"]]}
            bootstrap = "localStorage.removeItem('hu.szabi.launcher.control-origin.v1');localStorage.setItem('hu.szabi.launcher.offline-state.v1'," + json.dumps(json.dumps(state)) + ");window.PalmSystem={launchParams:'{}',activate:function(){}};"
            html = '<!doctype html><html lang="hu"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/assets/launcher.css"></head><body class="launcher-tv-body" style="background:#000"><div id="launcher-boot" class="launcher-boot-cover" aria-hidden="true"></div><main id="launcher-root"></main><script>' + bootstrap + '</script><script src="/assets/launcher-ui.js"></script><script src="/assets/launcher-app.js"></script></body></html>'
            self.send_bytes("text/html; charset=utf-8", html.encode("utf-8"))
        elif self.path == "/tv/":
            source = (SUITE / "apps" / "remote-mapper" / "index.html").read_text(encoding="utf-8")
            source = source.replace('href="remote-ui.css"', 'href="/assets/remote-ui.css"')
            source = source.replace('src="remote-ui.js"', 'src="/assets/remote-ui.js"')
            source = source.replace('src="app.js"', 'src="/tv-app.js"')
            self.send_bytes("text/html; charset=utf-8", source.encode("utf-8"))
        elif self.path == "/tv-app.js":
            source = (SUITE / "apps" / "remote-mapper" / "app.js").read_text(encoding="utf-8")
            source = source.replace("http://192.168.0.223:8765", "http://127.0.0.1:8877")
            self.send_bytes("text/javascript; charset=utf-8", source.encode("utf-8"))
        elif self.path == "/assets/remote-ui.css":
            self.send_bytes("text/css; charset=utf-8", (SUITE / "apps" / "remote-mapper" / "remote-ui.css").read_bytes())
        elif self.path == "/assets/remote-ui.js":
            self.send_bytes("text/javascript; charset=utf-8", (SUITE / "apps" / "remote-mapper" / "remote-ui.js").read_bytes())
        elif self.path == "/assets/connections-ui.js":
            self.send_bytes("text/javascript; charset=utf-8", (REMOTE_CONTROL / "static" / "connections-ui.js").read_bytes())
        elif self.path == "/assets/launcher-admin.js":
            self.send_bytes("text/javascript; charset=utf-8", (REMOTE_CONTROL / "static" / "launcher-admin.js").read_bytes())
        elif self.path == "/assets/launcher-ui.js":
            self.send_bytes("text/javascript; charset=utf-8", (SUITE / "apps" / "launcher" / "launcher-ui.js").read_bytes())
        elif self.path == "/assets/launcher-app.js":
            self.send_bytes("text/javascript; charset=utf-8", (SUITE / "apps" / "launcher" / "app.js").read_bytes())
        elif self.path == "/assets/launcher.css":
            self.send_bytes("text/css; charset=utf-8", (SUITE / "apps" / "launcher" / "launcher.css").read_bytes())
        elif self.path == "/api/remote-mapper/state":
            self.send_bytes("application/json; charset=utf-8", json.dumps(STATE).encode("utf-8"))
        elif self.path == "/api/connections":
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "connections": CONNECTIONS}).encode("utf-8"))
        elif self.path == "/api/launcher/state":
            presets = [{"id": item["id"], "kind": item["kind"], "fit": item["fit"], "clickAction": item["clickAction"], "cameraId": item["cameraId"], "previewAvailable": True} for item in OVERLAY["presets"]]
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "config": LAUNCHER, "apps": STATE["apps"], "presets": presets}).encode("utf-8"))
        elif self.path.startswith("/api/launcher/camera-preview"):
            self.send_bytes("image/svg+xml", b'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="100%" height="100%" fill="#17435d"/><circle cx="320" cy="180" r="80" fill="#73d7ff"/></svg>')
        elif self.path == "/api/launcher/diagnostics":
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "diagnostics": {"cpuPercent": 18.4, "load": ["0.42", "0.31", "0.28"], "memory": {"totalKiB": 1096864, "usedKiB": 720000, "availableKiB": 376864}, "disks": [{"mount": "/", "percent": "42%"}], "temperatureC": 56.2, "processes": ["PID CPU MEM COMMAND", "123 8.0 4.2 WebAppMgr"], "processRows": [{"pid": "123", "user": "root", "cpu": "8.0", "memory": "4.2", "command": "WebAppMgr"}]}}).encode("utf-8"))
        elif self.path == "/api/launcher/weather":
            hourly = [
                {"time": f"2026-08-{29 + (index // 24):02d}T{index % 24:02d}:00", "temperature": 18 + (index % 8), "apparentTemperature": 18 + (index % 8), "precipitationProbability": (index * 7) % 60, "code": 1 if index < 12 else 61, "windSpeed": 8 + index % 7}
                for index in range(36)
            ]
            daily = [
                {"date": f"2026-09-{day:02d}", "min": 12 + day, "max": 23 + day, "code": [1, 2, 61, 3, 80, 0, 45][day - 1], "precipitationProbability": day * 9, "sunrise": "06:05", "sunset": "19:30"}
                for day in range(1, 8)
            ]
            weather = {"label": "Budapest", "min": 14, "max": 28, "code": 1, "current": {"temperature": 24.2, "apparentTemperature": 24.8, "code": 1, "windSpeed": 11.4, "isDay": True}, "hourly": hourly, "daily": daily}
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "enabled": True, "weather": weather}).encode("utf-8"))
        elif self.path.startswith("/api/tv-screen"):
            pixels = bytes((36, 54, 88, 0, 54, 111, 168, 0, 74, 144, 196, 0, 103, 189, 220, 0))
            self.send_bytes("image/png", server._png_from_bgrx(2, 2, pixels))
        elif self.path.startswith("/api/launcher/wallpaper"):
            self.send_bytes("image/svg+xml", b'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><defs><linearGradient id="w"><stop stop-color="#173650"/><stop offset="1" stop-color="#865d64"/></linearGradient></defs><rect width="1920" height="1080" fill="url(#w)"/></svg>')
        elif self.path.startswith("/api/apps/icon") or self.path == "/mock-camera.svg":
            self.send_bytes("image/svg+xml", b'<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><defs><linearGradient id="g"><stop stop-color="#55dfff"/><stop offset="1" stop-color="#5548cc"/></linearGradient></defs><rect width="320" height="180" fill="url(#g)"/><circle cx="160" cy="90" r="42" fill="#fff" opacity=".75"/></svg>')
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if self.path == "/api/remote-mapper/bind":
            key_code, binding = server.validate_remote_bind_request(body)
            if binding is None:
                STATE["bindings"].pop(str(key_code), None)
            else:
                STATE["bindings"][str(key_code)] = binding
            self.send_bytes("application/json; charset=utf-8", json.dumps({**STATE, "changed": True}).encode("utf-8"))
        elif self.path == "/api/remote-mapper/restore":
            self.send_bytes("application/json; charset=utf-8", json.dumps({**STATE, "changed": False}).encode("utf-8"))
        elif self.path == "/api/media-overlay/sync":
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "config": OVERLAY}).encode("utf-8"))
        elif self.path == "/api/camera-viewer/sync":
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "config": CAMERAS}).encode("utf-8"))
        elif self.path == "/api/connections":
            CONNECTIONS.update(body)
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "connections": CONNECTIONS}).encode("utf-8"))
        elif self.path == "/api/launcher/config":
            checked = server.validate_launcher_config(body)
            LAUNCHER.clear(); LAUNCHER.update(checked)
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "config": LAUNCHER}).encode("utf-8"))
        elif self.path == "/api/launcher/launch":
            self.send_bytes("application/json; charset=utf-8", json.dumps({"ok": True, "lastUsed": {"type": body["type"], "targetId": body["targetId"], "label": body["label"]}}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("LGTV_PREVIEW_HOST", "127.0.0.1"),
                         int(os.environ.get("LGTV_PREVIEW_PORT", "8877"))), Handler).serve_forever()
