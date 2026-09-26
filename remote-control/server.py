#!/usr/bin/env python3
"""Small extensible LG TV LAN control panel, hosted outside the TV."""

from __future__ import annotations

import argparse
import base64
import ipaddress
import io
import json
import re
import secrets
import shlex
import socket
import struct
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

try:
    from PIL import Image
except ImportError:
    Image = None  # Optional on older control installations; keep images usable.


APP_ID = "hu.szabi.mediaoverlay"
CAMERA_APP_ID = "hu.szabi.cameraviewer"
REMOTE_MAPPER_APP_ID = "hu.szabi.remotemapper"
LAUNCHER_APP_ID = "hu.szabi.launcher"
LAUNCHER_QUICK_APP_ID = "hu.szabi.launcher.quick"
LAUNCHER_OVERLAY_APP_ID = "hu.szabi.launcher.overlay"
REMOTE_MANAGED_TYPES = {"launcherHome", "overlayPreset", "cameraOpen", "appCommand", "webhook"}
CAMERA_PRESENCE_PATH = "/api/tv-presence/camera-viewer"
CAMERA_PRESENCE_TTL_SECONDS = 8.0
APP_IDS = {
    "media-overlay": APP_ID,
    "camera-viewer": CAMERA_APP_ID,
    "launcher": LAUNCHER_APP_ID,
    "launcher-quick": LAUNCHER_QUICK_APP_ID,
    "launcher-overlay": LAUNCHER_OVERLAY_APP_ID,
}
LAUNCHER_HOSTS = {
    "full": {"appId": LAUNCHER_APP_ID, "mode": "full"},
    "quick": {"appId": LAUNCHER_QUICK_APP_ID, "mode": "overlay"},
    "full-overlay": {"appId": LAUNCHER_OVERLAY_APP_ID, "mode": "full"},
}
LAUNCH_URI = "luna://com.webos.applicationManager/launch"
BLOCKED_HOST = "192.168.0.100"
CORNERS = {"top-left", "top-right", "bottom-left", "bottom-right"}
KINDS = {"text", "image", "video"}
FITS = {"contain", "cover"}
LAUNCHER_ICON_KEYS = {
    "", "installed", "youtube", "netflix", "disney", "prime", "plex", "spotify", "moonlight", "lyrion", "immich",
    "camera", "overlay", "remote", "launcher", "tv", "hdmi", "browser", "home-assistant",
    "apps", "settings", "web",
}
LAUNCHER_ICON_CATALOG = (
    {"key": "youtube", "label": "YouTube"},
    {"key": "netflix", "label": "Netflix"},
    {"key": "disney", "label": "Disney+"},
    {"key": "prime", "label": "Prime Video"},
    {"key": "plex", "label": "Plex"},
    {"key": "spotify", "label": "Spotify"},
    {"key": "moonlight", "label": "Moonlight"},
    {"key": "lyrion", "label": "Lyrion Music Server"},
    {"key": "immich", "label": "Immich"},
    {"key": "camera", "label": "Camera Viewer"},
    {"key": "overlay", "label": "Media Overlay / PiP"},
    {"key": "remote", "label": "Távirányító"},
    {"key": "launcher", "label": "Launcher"},
    {"key": "tv", "label": "Élő TV"},
    {"key": "hdmi", "label": "HDMI bemenet"},
    {"key": "browser", "label": "Böngésző"},
    {"key": "home-assistant", "label": "Home Assistant"},
    {"key": "apps", "label": "Összes app"},
    {"key": "settings", "label": "Beállítások"},
    {"key": "web", "label": "Weboldal"},
)
LAUNCHER_SYSTEM_INPUTS = (
    {"id": "com.webos.app.livetv", "label": "Élő TV", "iconKey": "tv"},
    {"id": "com.webos.app.hdmi1", "label": "HDMI 1", "iconKey": "hdmi"},
    {"id": "com.webos.app.hdmi2", "label": "HDMI 2", "iconKey": "hdmi"},
    {"id": "com.webos.app.hdmi3", "label": "HDMI 3", "iconKey": "hdmi"},
    {"id": "com.webos.app.hdmi4", "label": "HDMI 4", "iconKey": "hdmi"},
)
LAUNCHER_SYSTEM_INPUT_IDS = {item["id"] for item in LAUNCHER_SYSTEM_INPUTS}
SENSITIVE_QUERY_PARTS = {"token", "access_token", "password", "auth", "key", "signature"}
SHOW_FIELDS = {
    "presetId", "kind", "text", "url", "fit", "corner", "width", "height",
    "margin", "marginX", "marginY", "ttlMs", "mode", "clickAction", "cameraId",
}
CONFIGURE_FIELDS = {"corner", "width", "height", "margin", "marginX", "marginY", "ttlMs"}
PRESET_SAVE_FIELDS = {"presetId", "kind", "text", "url", "fit", "clickAction", "cameraId"}
PRESET_DELETE_FIELDS = {"presetId"}
CAMERA_FIELDS = {
    "id", "cameraId", "name", "scheme", "host", "port", "playerPort", "playerPath",
    "primarySource", "previewSource", "audio",
}


def run_daemon_after(delay_seconds: float, label: str, action: Callable[[], None]) -> None:
    """Run a short TV lifecycle action after the HTTP response can leave the app."""
    def guarded() -> None:
        try:
            action()
        except Exception as error:
            print(label + " failed: " + str(error), flush=True)

    timer = threading.Timer(delay_seconds, guarded)
    timer.daemon = True
    timer.start()

# The legacy Input Hook JSON remains the on-TV binding database for backwards
# compatibility, but the native injected hook is intentionally not required.
# RemoteBrokerManager compiles the same structured bindings into a standalone
# evdev -> uinput broker configuration. Buttons marked locked are visible in
# the UI, but cannot be changed here.
REMOTE_BUTTONS = (
    {"keyCode": 116, "name": "Bekapcsoló", "short": "⏻", "zone": "top", "locked": True},
    {"keyCode": 241, "name": "Bemenetek", "short": "INPUT", "zone": "top", "locked": True},
    {"keyCode": 139, "name": "Beállítások", "short": "⚙", "zone": "top", "locked": True},
    {"keyCode": 2, "name": "1", "short": "1", "zone": "numbers", "locked": True},
    {"keyCode": 3, "name": "2", "short": "2", "zone": "numbers", "locked": True},
    {"keyCode": 4, "name": "3", "short": "3", "zone": "numbers", "locked": True},
    {"keyCode": 5, "name": "4", "short": "4", "zone": "numbers", "locked": True},
    {"keyCode": 6, "name": "5", "short": "5", "zone": "numbers", "locked": True},
    {"keyCode": 7, "name": "6", "short": "6", "zone": "numbers", "locked": True},
    {"keyCode": 8, "name": "7", "short": "7", "zone": "numbers", "locked": True},
    {"keyCode": 9, "name": "8", "short": "8", "zone": "numbers", "locked": True},
    {"keyCode": 10, "name": "9", "short": "9", "zone": "numbers", "locked": True},
    {"keyCode": 787, "name": "Lista", "short": "LIST", "zone": "numbers", "locked": False},
    {"keyCode": 11, "name": "0", "short": "0", "zone": "numbers", "locked": True},
    {"keyCode": 994, "name": "További műveletek", "short": "•••", "zone": "numbers", "locked": False},
    {"keyCode": 115, "name": "Hangerő +", "short": "VOL +", "zone": "rockers", "locked": True},
    {"keyCode": 113, "name": "Némítás", "short": "MUTE", "zone": "rockers", "locked": True},
    {"keyCode": 402, "name": "Csatorna +", "short": "CH +", "zone": "rockers", "locked": True},
    {"keyCode": 114, "name": "Hangerő −", "short": "VOL −", "zone": "rockers", "locked": True},
    # Home is deliberately editable: it is useful for launching the custom
    # launcher, a fixed PiP preset, or a local Home Assistant action.  Keep a
    # separate marker so both UIs can warn about hiding the factory Home screen.
    {"keyCode": 773, "name": "Home", "short": "⌂", "zone": "rockers", "locked": False, "critical": True},
    {"keyCode": 403, "name": "Csatorna −", "short": "CH −", "zone": "rockers", "locked": True},
    {"keyCode": 103, "name": "Fel", "short": "▲", "zone": "navigation", "locked": True},
    {"keyCode": 105, "name": "Balra", "short": "◀", "zone": "navigation", "locked": True},
    {"keyCode": 272, "name": "OK / görgő", "short": "OK", "zone": "navigation", "locked": True},
    {"keyCode": 106, "name": "Jobbra", "short": "▶", "zone": "navigation", "locked": True},
    {"keyCode": 108, "name": "Le", "short": "▼", "zone": "navigation", "locked": True},
    {"keyCode": 412, "name": "Vissza", "short": "↶", "zone": "middle", "locked": True},
    {"keyCode": 428, "name": "Hangvezérlés", "short": "MIC", "zone": "middle", "locked": True},
    {"keyCode": 398, "name": "Piros", "short": "", "zone": "colors", "locked": False, "color": "red"},
    {"keyCode": 399, "name": "Zöld", "short": "", "zone": "colors", "locked": False, "color": "green"},
    {"keyCode": 400, "name": "Sárga", "short": "", "zone": "colors", "locked": False, "color": "yellow"},
    {"keyCode": 401, "name": "Kék", "short": "", "zone": "colors", "locked": False, "color": "blue"},
    {"keyCode": 1037, "name": "Netflix", "short": "NETFLIX", "zone": "apps", "locked": False, "color": "netflix"},
    {"keyCode": 1038, "name": "Prime Video", "short": "prime", "zone": "apps", "locked": False, "color": "prime"},
    {"keyCode": 1042, "name": "Disney+", "short": "Disney+", "zone": "apps", "locked": False, "color": "disney"},
    {"keyCode": 1044, "name": "Rakuten TV", "short": "Rakuten", "zone": "apps", "locked": False, "color": "rakuten"},
    {"keyCode": 1117, "name": "Google Assistant", "short": "Google", "zone": "assistants", "locked": False},
    {"keyCode": 1086, "name": "Alexa", "short": "Alexa", "zone": "assistants", "locked": False},
)
REMOTE_BUTTON_BY_CODE = {int(item["keyCode"]): item for item in REMOTE_BUTTONS}
REMOTE_EDITABLE_CODES = {
    code for code, item in REMOTE_BUTTON_BY_CODE.items() if item["locked"] is False
}
REMOTE_LONG_BACK_CODE = 412
REMOTE_REPLACE_CODES = set(REMOTE_BUTTON_BY_CODE) - {116}
INPUT_HOOK_CONFIG = "/home/root/.config/lginputhook/keybinds.json"
INPUT_HOOK_ORIGINAL = "/home/root/.config/lginputhook/keybinds.before-remotemapper.json"
INPUT_HOOK_PREVIOUS = "/home/root/.config/lginputhook/keybinds.previous.json"
VNC_CONFIG = "/media/developer/apps/usr/palm/services/org.webosbrew.vncserver.service/config.json"
VNC_REMOTE_KEYS = {
    "left": 0xFF51, "up": 0xFF52, "right": 0xFF53, "down": 0xFF54,
    "ok": 0xFF0D, "back": 0xFF1B, "home": 0x1008FF18,
    "playPause": 0x1008FF14, "stop": 0x1008FF15,
    "volumeUp": 0x1008FF13, "volumeDown": 0x1008FF11, "mute": 0x1008FF12,
    "channelUp": 0x1008FF27, "channelDown": 0x1008FF26,
}
LAUNCHER_HOME_DIR = "/var/lib/webosbrew/launcher-home"
LAUNCHER_HOME_GUARD = LAUNCHER_HOME_DIR + "/guard.sh"
LAUNCHER_HOME_KEY = LAUNCHER_HOME_DIR + "/home-key.sh"
LAUNCHER_HOME_ENABLED = LAUNCHER_HOME_DIR + "/enabled"
LAUNCHER_HOME_MODE = LAUNCHER_HOME_DIR + "/home-mode"
LAUNCHER_HOME_ORIGIN = LAUNCHER_HOME_DIR + "/control-origin"
LAUNCHER_HOME_INIT = "/var/lib/webosbrew/init.d/launcher-home"
LAUNCHER_HOME_ALLOW = "/tmp/hu.szabi.launcher.allow-home"
LAUNCHER_HOME_PID = "/tmp/hu.szabi.launcher-home.pid"
LAUNCHER_HOME_FULL_VISIBLE = "/tmp/hu.szabi.launcher.full-visible"
LAUNCHER_HOME_QUICK_VISIBLE = "/tmp/hu.szabi.launcher.quick-visible"
LAUNCHER_HOME_FULL_PREWARM_READY = "/tmp/hu.szabi.launcher.full-prewarm-ready"
LAUNCHER_HOME_QUICK_PREWARM_READY = "/tmp/hu.szabi.launcher.quick-prewarm-ready"
INPUT_HOOK_WATCHDOG_DIR = "/var/lib/webosbrew/inputhook-watchdog"
INPUT_HOOK_WATCHDOG_SCRIPT = INPUT_HOOK_WATCHDOG_DIR + "/watchdog.sh"
INPUT_HOOK_WATCHDOG_ENABLED = INPUT_HOOK_WATCHDOG_DIR + "/enabled"
INPUT_HOOK_WATCHDOG_INIT = "/var/lib/webosbrew/init.d/inputhook-watchdog"
INPUT_HOOK_WATCHDOG_PID = "/tmp/hu.szabi.inputhook-watchdog.pid"
REMOTE_BROKER_DIR = "/var/lib/webosbrew/remote-broker"
REMOTE_BROKER_BINARY = REMOTE_BROKER_DIR + "/remote-broker"
REMOTE_BROKER_CONFIG = REMOTE_BROKER_DIR + "/bindings.conf"
REMOTE_BROKER_ACTIONS = REMOTE_BROKER_DIR + "/actions"
REMOTE_BROKER_SUPERVISOR = REMOTE_BROKER_DIR + "/supervisor.sh"
REMOTE_BROKER_ENABLED = REMOTE_BROKER_DIR + "/enabled"
REMOTE_BROKER_HEARTBEAT = "/tmp/hu.szabi.remote-broker.heartbeat"
REMOTE_BROKER_PID = "/tmp/hu.szabi.remote-broker.pid"
REMOTE_BROKER_SUPERVISOR_PID = "/tmp/hu.szabi.remote-broker-supervisor.pid"
REMOTE_BROKER_RELOAD_ACK = "/tmp/hu.szabi.remote-broker.reload"
REMOTE_BROKER_INIT = "/var/lib/webosbrew/init.d/remote-broker"

DEFAULT_WALLPAPER_URLS = [
    "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1470770841072-f978cf4d019e?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1428908728789-d2de25dbd4e2?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1433086966358-54859d0ed716?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1443632864897-14973fa006cf?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1472396961693-142e6e269027?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1470770903676-69b98201ea1c?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1483347756197-71ef80e95f73?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1505765050516-f72dcac9c60e?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1501854140801-50d01698950b?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1501785888041-af3ef285b470?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1472214103451-9374bd1c798e?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1497250681960-ef046c08a56e?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1439853949127-fa647821eba0?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1418065460487-3e41a6c84dc5?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1464278533981-50106e6176b1?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1497435334941-8c899ee9e8e9?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1470252649378-9c29740c9fa8?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1469474968028-56623f02e42e?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1511497584788-876760111969?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1473445361085-b9a07f55608b?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1518837695005-2083093ee35b?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1493246507139-91e8fad9978e?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1476514525535-07fb3b4ae5f1?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1465146344425-f00d5f5c8f07?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1447752875215-b2761acb3c5d?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1500534623283-312aade485b7?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1449824913935-59a10b8d2000?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1540206395-68808572332f?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1542601906990-b4d3fb778b09?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1513836279014-a89f7a76ae86?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1520962922320-2038eebab146?auto=format&fit=crop&w=1920&q=85",
    "https://images.unsplash.com/photo-1510784722466-f2aa9c52fff6?auto=format&fit=crop&w=1920&q=85",
]
LEGACY_BAD_WALLPAPER_URL = "https://images.unsplash.com/photo-14734434806-91a8f8a5f2aa?auto=format&fit=crop&w=1920&q=85"
LEGACY_BAD_WALLPAPER_URL_2 = "https://images.unsplash.com/photo-1534088568595-a130f7a76ae4?auto=format&fit=crop&w=1920&q=85"
LEGACY_WALLPAPER_REPLACEMENTS = {
    LEGACY_BAD_WALLPAPER_URL: DEFAULT_WALLPAPER_URLS[25],
    LEGACY_BAD_WALLPAPER_URL_2: DEFAULT_WALLPAPER_URLS[34],
}


class RequestError(ValueError):
    pass


def validate_launcher_host_request(raw: Any, default_host: str) -> tuple[str, str, str]:
    """Resolve a lifecycle request to one of the two installed launcher hosts.

    No caller-supplied application id is accepted.  The empty object remains a
    narrow compatibility path for an app instance from before the dual-host
    upgrade; new callers identify their generated host and matching view mode.
    """
    if default_host not in LAUNCHER_HOSTS:
        raise ValueError("invalid default launcher host")
    if not isinstance(raw, dict):
        raise RequestError("A launcher életciklus-kérése érvénytelen.")
    if raw == {}:
        host = default_host
    else:
        if set(raw) not in ({"host"}, {"host", "mode"}):
            raise RequestError("A launcher életciklus-kérése érvénytelen.")
        host = str(raw.get("host") or "")
        if host not in LAUNCHER_HOSTS:
            raise RequestError("A launcher hostja érvénytelen.")
    spec = LAUNCHER_HOSTS[host]
    mode = str(spec["mode"])
    if "mode" in raw and raw.get("mode") != mode:
        raise RequestError("A launcher hostja és nézetmódja nem egyezik.")
    return host, str(spec["appId"]), mode


def canonical_integer(value: Any, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool):
        raise RequestError(f"A(z) {field} csak egész szám lehet.")
    text = str(value)
    if not re.fullmatch(r"[0-9]+", text):
        raise RequestError(f"A(z) {field} csak egész szám lehet.")
    number = int(text)
    if number < minimum or number > maximum:
        raise RequestError(f"A(z) {field} értéke {minimum} és {maximum} között lehet.")
    return number


def validate_media_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 2048:
        raise RequestError("A média URL 1–2048 karakter legyen.")
    if "%" in text or any(ord(char) <= 32 or ord(char) == 127 for char in text):
        raise RequestError("A média URL nem tartalmazhat kódolt részt vagy szóközt.")
    try:
        parsed = urlsplit(text)
        host = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise RequestError("A média URL hibás.") from error
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password or parsed.fragment:
        raise RequestError("Csak teljes, userinfo és fragment nélküli HTTP/HTTPS URL használható.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise RequestError("A médiahost kanonikus, numerikus privát IPv4-cím legyen.") from error
    private_networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )
    if address.version != 4 or not any(address in network for network in private_networks) or str(address) != host or host == BLOCKED_HOST:
        raise RequestError("A médiahost nem engedélyezett privát IPv4-cím.")
    if address.packed[-1] in {0, 255}:
        raise RequestError("Hálózati vagy broadcast cím nem engedélyezett.")
    if port is not None and not 1 <= port <= 65535:
        raise RequestError("A médiaport érvénytelen.")
    path = parsed.path or "/"
    if "//" in path or any(marker in path for marker in ("\\", ":", "@")):
        raise RequestError("A média URL útvonala érvénytelen.")
    if any(segment in {".", ".."} for segment in path.split("/")):
        raise RequestError("A média URL útvonala érvénytelen.")
    combined = path + "?" + parsed.query
    if re.search(r"(^|[^0-9])(?:[0-9]+\.){1,3}[0-9]+([^0-9]|$)", combined) or "0x" in combined.lower():
        raise RequestError("IP-alakú proxycél útvonalban vagy queryben nem használható.")
    for field in parsed.query.split("&") if parsed.query else ():
        name = field.split("=", 1)[0]
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", name):
            raise RequestError("A query paraméterneve érvénytelen.")
        lowered = name.lower()
        parts = set(re.split(r"[^a-z0-9]+", lowered))
        if lowered in SENSITIVE_QUERY_PARTS or parts.intersection(SENSITIVE_QUERY_PARTS):
            raise RequestError("Titkot hordozó query paraméternév nem engedélyezett.")
    return text


def validate_show_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RequestError("A kérés JSON objektum legyen.")
    unknown = set(raw) - SHOW_FIELDS
    if unknown:
        raise RequestError("Ismeretlen mező: " + ", ".join(sorted(unknown)))

    result: dict[str, Any] = {"v": 1, "action": "show", "requestId": secrets.token_hex(16)}
    preset_id = raw.get("presetId")
    if preset_id not in (None, ""):
        preset_id = str(preset_id)
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", preset_id):
            raise RequestError("A preset azonosítója érvénytelen.")
        if any(raw.get(name) not in (None, "") for name in ("kind", "text", "url", "fit", "clickAction", "cameraId")):
            raise RequestError("Preset használatakor közvetlen tartalom és kattintási művelet nem adható meg.")
        result["presetId"] = preset_id
    else:
        kind = str(raw.get("kind") or "")
        if kind not in KINDS:
            raise RequestError("A közvetlen forrás típusa text, image vagy video lehet.")
        result["kind"] = kind
        if kind == "text":
            text = str(raw.get("text") or "")
            if not 1 <= len(text) <= 2048:
                raise RequestError("A szöveg 1–2048 karakter legyen.")
            if raw.get("url") not in (None, "") or raw.get("fit") not in (None, ""):
                raise RequestError("Szövegnél URL és illesztés nem adható meg.")
            result["text"] = text
        else:
            result["url"] = validate_media_url(raw.get("url"))
            fit = str(raw.get("fit") or "contain")
            if fit not in FITS:
                raise RequestError("Az illesztés contain vagy cover lehet.")
            result["fit"] = fit

        click_action = str(raw.get("clickAction") or "")
        camera_id = str(raw.get("cameraId") or "")
        if click_action not in {"", "openCamera", "dismiss"}:
            raise RequestError("A kattintási művelet érvénytelen.")
        if click_action == "openCamera":
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", camera_id):
                raise RequestError("A kamera-ID érvénytelen.")
            result.update({"clickAction": click_action, "cameraId": camera_id})
        elif camera_id:
            raise RequestError("Kamera-ID csak openCamera művelethez adható meg.")
        elif click_action == "dismiss":
            result["clickAction"] = "dismiss"

    if raw.get("corner") not in (None, ""):
        corner = str(raw["corner"])
        if corner not in CORNERS:
            raise RequestError("A sarok érvénytelen.")
        result["corner"] = corner
    ranges = {
        "width": (240, 1920), "height": (135, 1080), "margin": (0, 300),
        "marginX": (0, 400), "marginY": (0, 300), "ttlMs": (0, 3_600_000),
    }
    for field, limits in ranges.items():
        if raw.get(field) not in (None, ""):
            result[field] = canonical_integer(raw[field], limits[0], limits[1], field)
    if raw.get("mode") not in (None, ""):
        if raw["mode"] != "fullscreen":
            raise RequestError("A mode csak fullscreen lehet.")
        result["mode"] = "fullscreen"
    return result


def validate_configure_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RequestError("A kérés JSON objektum legyen.")
    unknown = set(raw) - CONFIGURE_FIELDS
    if unknown:
        raise RequestError("Ismeretlen mező: " + ", ".join(sorted(unknown)))
    if not raw:
        raise RequestError("Legalább egy alapértelmezett beállítást meg kell adni.")
    result: dict[str, Any] = {"v": 1, "action": "configure", "requestId": secrets.token_hex(16)}
    if raw.get("corner") not in (None, ""):
        corner = str(raw["corner"])
        if corner not in CORNERS:
            raise RequestError("A sarok érvénytelen.")
        result["corner"] = corner
    ranges = {
        "width": (240, 1920), "height": (135, 1080), "margin": (0, 300),
        "marginX": (0, 400), "marginY": (0, 300), "ttlMs": (0, 3_600_000),
    }
    for field, limits in ranges.items():
        if raw.get(field) not in (None, ""):
            result[field] = canonical_integer(raw[field], limits[0], limits[1], field)
    return result


def validate_preset_save_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RequestError("A kérés JSON objektum legyen.")
    unknown = set(raw) - PRESET_SAVE_FIELDS
    if unknown:
        raise RequestError("Ismeretlen mező: " + ", ".join(sorted(unknown)))
    preset_id = str(raw.get("presetId") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", preset_id):
        raise RequestError("A preset azonosítója érvénytelen.")
    direct = {key: value for key, value in raw.items() if key != "presetId"}
    click_action = str(direct.pop("clickAction", "") or "")
    camera_id = str(direct.pop("cameraId", "") or "")
    if click_action not in {"", "openCamera", "dismiss"}:
        raise RequestError("A kattintási művelet érvénytelen.")
    if click_action == "openCamera":
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", camera_id):
            raise RequestError("A kamera-ID érvénytelen.")
    elif camera_id:
        raise RequestError("Kamera-ID csak openCamera művelethez adható meg.")
    content = validate_show_request(direct)
    result = {
        key: value for key, value in content.items()
        if key in {"kind", "text", "url", "fit"}
    }
    result.update({"v": 1, "action": "preset-save", "presetId": preset_id, "requestId": secrets.token_hex(16)})
    if click_action:
        result["clickAction"] = click_action
        if click_action == "openCamera":
            result["cameraId"] = camera_id
    return result


def validate_preset_delete_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RequestError("A kérés JSON objektum legyen.")
    unknown = set(raw) - PRESET_DELETE_FIELDS
    if unknown:
        raise RequestError("Ismeretlen mező: " + ", ".join(sorted(unknown)))
    preset_id = str(raw.get("presetId") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", preset_id):
        raise RequestError("A preset azonosítója érvénytelen.")
    return {"v": 1, "action": "preset-delete", "presetId": preset_id, "requestId": secrets.token_hex(16)}


def validate_private_host(value: Any) -> str:
    host = str(value or "").strip()
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise RequestError("A kamera hostja kanonikus privát IPv4-cím legyen.") from error
    private_networks = (
        ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )
    if address.version != 4 or str(address) != host or not any(address in network for network in private_networks):
        raise RequestError("A kamera hostja kanonikus privát IPv4-cím legyen.")
    if host == BLOCKED_HOST or address.packed[-1] in {0, 255}:
        raise RequestError("A kamera hostja nem engedélyezett.")
    return host


def validate_private_origin(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    try:
        parsed = urlsplit(text)
        host = validate_private_host(parsed.hostname)
        port = parsed.port
    except (ValueError, RequestError) as error:
        raise RequestError("A vezérlő címe teljes, privát IPv4-es HTTP/HTTPS origin legyen.") from error
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise RequestError("A vezérlő címe teljes, privát IPv4-es HTTP/HTTPS origin legyen.")
    if port is not None and not 1 <= port <= 65535:
        raise RequestError("A vezérlő portja érvénytelen.")
    expected = parsed.scheme + "://" + host + ((":" + str(port)) if port is not None else "")
    if expected != text:
        raise RequestError("A vezérlő címe kanonikus alakban adható meg.")
    return text


def validate_player_path(value: Any) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"/[A-Za-z0-9._/-]{1,191}", text) or "//" in text or any(part in {".", ".."} for part in text.split("/")):
        raise RequestError("A player útvonala érvénytelen.")
    return text


def validate_connections(raw: Any) -> dict[str, Any]:
    required = {"controlOrigin", "tvHost", "gatewayScheme", "gatewayHost", "mediaPort", "playerPort", "playerPath"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise RequestError("A kapcsolati beállítások mezői hiányosak vagy ismeretlen mezőt tartalmaznak.")
    scheme = str(raw.get("gatewayScheme") or "")
    if scheme not in {"http", "https"}:
        raise RequestError("A kameraátjáró sémája HTTP vagy HTTPS lehet.")
    return {
        "controlOrigin": validate_private_origin(raw.get("controlOrigin")),
        "tvHost": validate_private_host(raw.get("tvHost")),
        "gatewayScheme": scheme,
        "gatewayHost": validate_private_host(raw.get("gatewayHost")),
        "mediaPort": canonical_integer(raw.get("mediaPort"), 1, 65535, "mediaPort"),
        "playerPort": canonical_integer(raw.get("playerPort"), 1, 65535, "playerPort"),
        "playerPath": validate_player_path(raw.get("playerPath")),
    }


def validate_wallpaper_url(value: Any) -> str:
    text = str(value or "").strip()
    if not 1 <= len(text) <= 2048 or any(ord(char) <= 32 for char in text):
        raise RequestError("A háttérkép URL érvénytelen.")
    try:
        parsed = urlsplit(text)
    except ValueError as error:
        raise RequestError("A háttérkép URL érvénytelen.") from error
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RequestError("Háttérképhez teljes, HTTPS URL szükséges.")
    return text


def validate_public_wallpaper_target(value: Any) -> str:
    text = validate_wallpaper_url(value)
    parsed = urlsplit(text)
    try:
        port = parsed.port or 443
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
    except (OSError, ValueError) as error:
        raise RuntimeError("A háttérkép kiszolgálója nem oldható fel.") from error
    if not addresses or any(not ipaddress.ip_address(address.split("%", 1)[0]).is_global for address in addresses):
        raise RuntimeError("A háttérkép csak nyilvános HTTPS-kiszolgálóról tölthető le.")
    return text


class SafeWallpaperRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, file_pointer: Any, code: int, message: str, headers: Any, new_url: str) -> Any:
        validate_public_wallpaper_target(new_url)
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def fetch_wallpaper(value: Any) -> tuple[str, bytes]:
    url = validate_public_wallpaper_target(value)
    opener = urllib.request.build_opener(SafeWallpaperRedirectHandler())
    request = urllib.request.Request(url, headers={"User-Agent": "LGTV-Control/1.2", "Accept": "image/jpeg,image/png;q=0.9,image/webp;q=0.8,*/*;q=0.1"})
    with opener.open(request, timeout=10) as response:
        validate_public_wallpaper_target(response.geturl())
        content_type = str(response.headers.get_content_type() or "").lower()
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise RuntimeError("A háttérkép URL nem támogatott képet adott vissza.")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > 8_388_608:
            raise RuntimeError("A háttérkép túl nagy.")
        payload = response.read(8_388_609)
    if not payload or len(payload) > 8_388_608:
        raise RuntimeError("A háttérkép üres vagy túl nagy.")
    return content_type, payload


class NoMediaRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, file_pointer: Any, code: int, message: str, headers: Any, new_url: str) -> None:
        return None


def launcher_snapshot_url(value: Any) -> str:
    """Validate the original camera source used for launcher frame extraction."""
    return validate_media_url(value)


def launcher_frame_url(value: Any) -> str:
    """Convert a go2rtc stream URL to its one-frame HTTP endpoint."""
    url = launcher_snapshot_url(value)
    parsed = urlsplit(url)
    path = parsed.path
    if path.endswith("/api/stream.mjpeg"):
        path = path[:-len("/api/stream.mjpeg")] + "/api/frame.jpeg"
    elif path.endswith("/stream.mjpeg"):
        path = path[:-len("/stream.mjpeg")] + "/frame.jpeg"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def launcher_profile_frame_url(profile: Any) -> str:
    """Build the launcher frame URL only from a validated camera profile."""
    checked = validate_camera_profile(profile)
    return launcher_frame_url(
        str(checked["scheme"]) + "://" + str(checked["host"]) + ":" + str(checked["port"])
        + "/api/stream.mjpeg?src=" + quote(str(checked["previewSource"]), safe="")
    )


def extract_first_jpeg(payload: bytes) -> bytes | None:
    """Return the first complete JPEG from a multipart/MJPEG byte sequence."""
    start = payload.find(b"\xff\xd8\xff")
    if start < 0:
        return None
    end = payload.find(b"\xff\xd9", start + 3)
    return payload[start:end + 2] if end >= 0 else None


def launcher_thumbnail(content_type: str, payload: bytes, size: tuple[int, int]) -> tuple[str, bytes]:
    """Downsize off the TV, with bounded decode size and no upscaling."""
    if Image is None:
        return content_type, payload
    with Image.open(io.BytesIO(payload)) as image:
        if image.width * image.height > 24_000_000:
            raise RuntimeError("A launcher-kép felbontása túl nagy.")
        image.draft("RGB", size)
        image.thumbnail(size, Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=76)
        return "image/jpeg", output.getvalue()


def fetch_launcher_camera_preview(value: Any) -> tuple[str, bytes]:
    """Extract one bounded frame; never relay a continuous MJPEG response."""
    url = launcher_snapshot_url(value)
    opener = urllib.request.build_opener(NoMediaRedirectHandler())
    request = urllib.request.Request(url, headers={
        "User-Agent": "LGTV-Control/1.2",
        "Accept": "multipart/x-mixed-replace,image/jpeg,image/png;q=0.9,image/webp;q=0.8,*/*;q=0.1",
        "Connection": "close",
    })
    maximum = 2_097_152
    with opener.open(request, timeout=7) as response:
        validate_media_url(response.geturl())
        content_type = str(response.headers.get_content_type() or "").lower()
        if content_type not in {"multipart/x-mixed-replace", "image/jpeg", "image/png", "image/webp", "application/octet-stream"}:
            raise RuntimeError("A kameraforrás nem adott MJPEG-et vagy támogatott képet.")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > maximum:
            raise RuntimeError("A kamera-előnézeti kép túl nagy.")
        payload = bytearray()
        while len(payload) <= maximum:
            chunk = response.read(min(65536, maximum + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if content_type in {"multipart/x-mixed-replace", "image/jpeg", "application/octet-stream"}:
                jpeg = extract_first_jpeg(bytes(payload))
                if jpeg is not None:
                    return "image/jpeg", jpeg
    if not payload or len(payload) > maximum:
        raise RuntimeError("A kamera-előnézeti kép üres vagy túl nagy.")
    raw = bytes(payload)
    if content_type == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", raw
    if content_type == "image/webp" and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp", raw
    raise RuntimeError("Az MJPEG-forrásból nem sikerült teljes JPEG képkockát kinyerni.")


def validate_launcher_url(value: Any) -> str:
    text = str(value or "").strip()
    if not 1 <= len(text) <= 2048 or any(ord(char) <= 32 for char in text):
        raise RequestError("A webes hivatkozás URL-je érvénytelen.")
    try:
        parsed = urlsplit(text)
    except ValueError as error:
        raise RequestError("A webes hivatkozás URL-je érvénytelen.") from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RequestError("A webes hivatkozás teljes HTTP/HTTPS URL legyen.")
    if parsed.scheme == "http":
        validate_private_host(parsed.hostname)
    return text


def validate_launcher_webhook_url(value: Any) -> str:
    text = validate_launcher_url(value)
    parsed = urlsplit(text)
    validate_private_host(parsed.hostname)
    return text


def validate_launcher_link_options(raw: Any) -> tuple[str, str, str]:
    if not isinstance(raw, dict):
        raise RequestError("A launcher webes művelete érvénytelen.")
    mode = str(raw.get("linkMode") or "website")
    method = str(raw.get("webhookMethod") or "GET").upper()
    body = raw.get("webhookBody", "")
    if mode not in {"website", "webhook"}:
        raise RequestError("A webes csempe módja Weboldal vagy Webhook lehet.")
    if method not in {"GET", "POST"}:
        raise RequestError("A webhook metódusa GET vagy POST lehet.")
    if not isinstance(body, str) or len(body.encode("utf-8")) > 8192 or "\x00" in body:
        raise RequestError("A webhook body legfeljebb 8192 bájtos szöveg lehet.")
    if mode == "website":
        return "website", "GET", ""
    if method == "GET" and body:
        raise RequestError("GET webhookhoz nem adható body.")
    return "webhook", method, body


def send_launcher_webhook(url: str, method: str, body: str) -> int:
    target = validate_launcher_webhook_url(url)
    method = method.upper()
    payload = body.encode("utf-8") if method == "POST" else None
    headers = {"User-Agent": "SzabiLauncher/1.0"}
    if method == "POST":
        content_type = "text/plain; charset=utf-8"
        if body.strip():
            try:
                json.loads(body)
            except (ValueError, TypeError):
                pass
            else:
                content_type = "application/json"
        headers["Content-Type"] = content_type
    request = urllib.request.Request(target, data=payload, headers=headers, method=method)
    opener = urllib.request.build_opener(NoMediaRedirectHandler())
    try:
        with opener.open(request, timeout=5) as response:
            status = int(response.getcode() or 0)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"A webhook HTTP {error.code} választ adott.") from error
    except urllib.error.URLError as error:
        raise RuntimeError("A webhook nem érhető el: " + str(error.reason)[:160]) from error
    if not 200 <= status < 300:
        raise RuntimeError(f"A webhook HTTP {status} választ adott.")
    return status


def validate_launcher_launch_request(raw: Any) -> dict[str, Any]:
    required = {"type", "targetId", "label"}
    optional = {"linkMode", "webhookMethod", "webhookBody"}
    if not isinstance(raw, dict) or not required.issubset(raw) or set(raw) - required - optional:
        raise RequestError("A launcher indítási kérése érvénytelen.")
    item_type = str(raw.get("type") or "")
    target_id = str(raw.get("targetId") or "")
    label = str(raw.get("label") or target_id).strip()[:64]
    if item_type not in {"app", "preset", "link"} or not label:
        raise RequestError("A launcher indítási kérése érvénytelen.")
    result = {"type": item_type, "targetId": target_id, "label": label}
    link_fields = {"linkMode", "webhookMethod", "webhookBody"}
    if item_type == "link":
        result["targetId"] = validate_launcher_url(target_id)
        mode, method, body = validate_launcher_link_options(raw)
        if mode == "webhook":
            result["targetId"] = validate_launcher_webhook_url(target_id)
        result.update(linkMode=mode, webhookMethod=method, webhookBody=body)
    elif any(field in raw for field in link_fields):
        raise RequestError("Webhook-beállítás csak webes csempéhez adható.")
    return result


def validate_launcher_item(raw: Any, row_id: str) -> dict[str, Any]:
    required = {"id", "type", "targetId", "label", "visible"}
    optional = {"fit", "iconUrl", "backgroundColor", "iconKey", "linkMode", "webhookMethod", "webhookBody"}
    if not isinstance(raw, dict) or not required.issubset(raw) or set(raw) - required - optional:
        raise RequestError("A launcher egyik csempéje érvénytelen.")
    item_id = str(raw.get("id") or "")
    item_type = str(raw.get("type") or "")
    target_id = str(raw.get("targetId") or "")
    label = str(raw.get("label") or "").strip()
    fit = str(raw.get("fit") or "contain")
    icon_key = str(raw.get("iconKey") or "")
    icon_url = str(raw.get("iconUrl") or "").strip()
    background_color = str(raw.get("backgroundColor") or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", item_id):
        raise RequestError("A launcher-csempe azonosítója érvénytelen.")
    allowed_types = {"app"} if row_id in {"favorites", "apps"} else ({"link"} if row_id == "links" else ({"preset"} if row_id == "cameras" else {"app", "allApps", "settings"}))
    if item_type not in allowed_types:
        raise RequestError("A launcher-csempe típusa ebben a sorban nem használható.")
    if item_type == "app" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", target_id):
        raise RequestError("A launcher alkalmazásazonosítója érvénytelen.")
    if item_type == "preset" and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", target_id):
        raise RequestError("A launcher presetazonosítója érvénytelen.")
    link_fields = {"linkMode", "webhookMethod", "webhookBody"}
    if item_type == "link":
        target_id = validate_launcher_url(target_id)
        link_mode, webhook_method, webhook_body = validate_launcher_link_options(raw)
        if link_mode == "webhook":
            target_id = validate_launcher_webhook_url(target_id)
    elif any(field in raw for field in link_fields):
        raise RequestError("Webhook-beállítás csak webes csempéhez adható.")
    if item_type in {"allApps", "settings"} and target_id:
        raise RequestError("A launcher segédcsempéjéhez nem tartozhat célazonosító.")
    if not 1 <= len(label) <= 64 or not isinstance(raw.get("visible"), bool):
        raise RequestError("A launcher-csempe felirata vagy láthatósága érvénytelen.")
    if fit not in {"small", "contain", "cover"}:
        raise RequestError("A launcher-csempe képillesztése érvénytelen.")
    if icon_key not in LAUNCHER_ICON_KEYS:
        raise RequestError("A launcher-csempe beépített ikonja érvénytelen.")
    if icon_url:
        icon_url = validate_launcher_url(icon_url)
    if background_color and not re.fullmatch(r"#[0-9a-f]{6}", background_color):
        raise RequestError("A launcher-csempe háttérszíne #RRGGBB formátumú legyen.")
    result = {"id": item_id, "type": item_type, "targetId": target_id, "label": label, "visible": raw["visible"], "fit": fit, "iconKey": icon_key, "iconUrl": icon_url, "backgroundColor": background_color}
    if item_type == "link":
        result.update(linkMode=link_mode, webhookMethod=webhook_method, webhookBody=webhook_body)
    return result


def validate_launcher_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"version", "rows", "settings", "lastUsed"} or raw.get("version") != 1:
        raise RequestError("A launcher konfigurációja érvénytelen.")
    rows_raw = raw.get("rows")
    if not isinstance(rows_raw, list) or len(rows_raw) != 5:
        raise RequestError("A launchernek pontosan öt rendezhető sora legyen.")
    expected = {"favorites", "apps", "links", "cameras", "utilities"}
    rows = []
    seen_items: set[str] = set()
    seen_rows: set[str] = set()
    for item in rows_raw:
        if not isinstance(item, dict) or set(item) != {"id", "title", "visible", "items"} or item.get("id") not in expected or item.get("id") in seen_rows:
            raise RequestError("A launcher sorainak szerkezete vagy sorrendje érvénytelen.")
        row_id = str(item["id"])
        seen_rows.add(row_id)
        title = str(item.get("title") or "").strip()
        if not 1 <= len(title) <= 48 or not isinstance(item.get("visible"), bool) or not isinstance(item.get("items"), list) or len(item["items"]) > 128:
            raise RequestError("A launcher egyik sora érvénytelen.")
        checked_items = []
        for raw_item in item["items"]:
            checked = validate_launcher_item(raw_item, row_id)
            if checked["id"] in seen_items:
                raise RequestError("Ismétlődő launcher-csempeazonosító.")
            seen_items.add(checked["id"])
            checked_items.append(checked)
        rows.append({"id": row_id, "title": title, "visible": item["visible"], "items": checked_items})
    settings = raw.get("settings")
    required_settings = {"wallpaperEnabled", "wallpaperIntervalMinutes", "wallpaperDimPercent", "wallpaperUrls", "weatherEnabled", "weatherLabel", "latitude", "longitude", "cameraPreviewsEnabled"}
    allowed_settings = required_settings | {
        "focusScalePercent", "editorModeEnabled", "defaultHomeEnabled",
        "bootOverlayEnabled", "bootOverlayMaxSeconds", "animationsEnabled", "visualEffectsEnabled",
        "resumeLastAppOnPowerEnabled", "homeLaunchMode", "fullLauncherPresentation",
    }
    if not isinstance(settings, dict) or not required_settings.issubset(settings) or set(settings) - allowed_settings:
        raise RequestError("A launcher beállításai érvénytelenek.")
    if not all(isinstance(settings.get(field), bool) for field in ("wallpaperEnabled", "weatherEnabled", "cameraPreviewsEnabled")):
        raise RequestError("A launcher kapcsolóinak értéke érvénytelen.")
    editor_mode_enabled = settings.get("editorModeEnabled", True)
    if not isinstance(editor_mode_enabled, bool):
        raise RequestError("A launcher szerkesztő mód kapcsolója érvénytelen.")
    default_home_enabled = settings.get("defaultHomeEnabled", False)
    if not isinstance(default_home_enabled, bool):
        raise RequestError("Az alapértelmezett kezdőképernyő kapcsolója érvénytelen.")
    boot_overlay_enabled = settings.get("bootOverlayEnabled", True)
    animations_enabled = settings.get("animationsEnabled", True)
    visual_effects_enabled = settings.get("visualEffectsEnabled", True)
    resume_last_app = settings.get("resumeLastAppOnPowerEnabled", False)
    if not all(isinstance(value, bool) for value in (boot_overlay_enabled, animations_enabled, visual_effects_enabled, resume_last_app)):
        raise RequestError("A launcher indulási vagy animációs kapcsolója érvénytelen.")
    presentation = settings.get("fullLauncherPresentation", "app")
    if not isinstance(presentation, str) or presentation not in {"app", "overlay"}:
        raise RequestError("A teljes launcher megjelenítési módja érvénytelen.")
    home_launch_mode = settings.get("homeLaunchMode", "split")
    if home_launch_mode not in {"split", "full", "overlay"}:
        raise RequestError("A Home gomb launcher-módja érvénytelen.")
    boot_overlay_seconds = canonical_integer(settings.get("bootOverlayMaxSeconds", 2), 1, 10, "bootOverlayMaxSeconds")
    urls_raw = settings.get("wallpaperUrls")
    if not isinstance(urls_raw, list) or not 1 <= len(urls_raw) <= 100:
        raise RequestError("A háttérkép-lista 1–100 URL-t tartalmazhat.")
    urls = [validate_wallpaper_url(value) for value in urls_raw]
    if len(set(urls)) != len(urls):
        raise RequestError("A háttérkép-listában ismétlődő URL van.")
    weather_label = str(settings.get("weatherLabel") or "").strip()
    if len(weather_label) > 64:
        raise RequestError("Az időjárási hely neve túl hosszú.")
    try:
        latitude = float(settings.get("latitude"))
        longitude = float(settings.get("longitude"))
    except (TypeError, ValueError) as error:
        raise RequestError("A szélesség és hosszúság szám legyen.") from error
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise RequestError("Az időjárási koordináták érvénytelenek.")
    if settings["weatherEnabled"] and abs(latitude) < 0.0001 and abs(longitude) < 0.0001:
        raise RequestError("Az időjáráshoz add meg a település valódi koordinátáit; a 0,0 az Atlanti-óceánra mutat.")
    last_used_raw = raw.get("lastUsed")
    last_used = None
    if last_used_raw is not None:
        if not isinstance(last_used_raw, dict) or set(last_used_raw) != {"type", "targetId", "label"} or last_used_raw.get("type") not in {"app", "preset"}:
            raise RequestError("A Folytatás elem érvénytelen.")
        target_id = str(last_used_raw.get("targetId") or "")
        label = str(last_used_raw.get("label") or "").strip()
        if last_used_raw["type"] == "app" and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", target_id):
            raise RequestError("A Folytatás alkalmazásazonosítója érvénytelen.")
        if last_used_raw["type"] == "preset" and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", target_id):
            raise RequestError("A Folytatás presetazonosítója érvénytelen.")
        if not 1 <= len(label) <= 64:
            raise RequestError("A Folytatás felirata érvénytelen.")
        last_used = {"type": last_used_raw["type"], "targetId": target_id, "label": label}
    focus_scale = canonical_integer(settings.get("focusScalePercent", 10), 5, 20, "focusScalePercent")
    if focus_scale not in {5, 10, 15, 20}:
        raise RequestError("A kijelölt csempe nagyítása 5, 10, 15 vagy 20 százalék lehet.")
    return {"version": 1, "rows": rows, "lastUsed": last_used, "settings": {
        "wallpaperEnabled": settings["wallpaperEnabled"],
        "wallpaperIntervalMinutes": canonical_integer(settings.get("wallpaperIntervalMinutes"), 1, 10, "wallpaperIntervalMinutes"),
        "wallpaperDimPercent": canonical_integer(settings.get("wallpaperDimPercent"), 0, 85, "wallpaperDimPercent"),
        "wallpaperUrls": urls,
        "weatherEnabled": settings["weatherEnabled"], "weatherLabel": weather_label,
        "latitude": latitude, "longitude": longitude,
        "cameraPreviewsEnabled": settings["cameraPreviewsEnabled"], "editorModeEnabled": editor_mode_enabled,
        "defaultHomeEnabled": default_home_enabled,
        "bootOverlayEnabled": boot_overlay_enabled,
        "bootOverlayMaxSeconds": boot_overlay_seconds,
        "animationsEnabled": animations_enabled,
        "visualEffectsEnabled": visual_effects_enabled,
        "resumeLastAppOnPowerEnabled": resume_last_app,
        "homeLaunchMode": home_launch_mode,
        "fullLauncherPresentation": presentation,
        "focusScalePercent": focus_scale,
    }}


def validate_camera_profile(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RequestError("A kameraprofil JSON objektum legyen.")
    unknown = set(raw) - CAMERA_FIELDS
    if unknown:
        raise RequestError("Ismeretlen kamera mező: " + ", ".join(sorted(unknown)))
    profile_id = str(raw.get("id") or "")
    camera_id = str(raw.get("cameraId") or "")
    name = str(raw.get("name") or "").strip()
    source_pattern = r"[A-Za-z0-9][A-Za-z0-9._-]{0,47}"
    if not re.fullmatch(source_pattern, profile_id):
        raise RequestError("A profil-ID érvénytelen.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", camera_id):
        raise RequestError("A kamera-ID érvénytelen.")
    if not 1 <= len(name) <= 48:
        raise RequestError("A kameranév 1–48 karakter legyen.")
    scheme = str(raw.get("scheme") or "")
    if scheme not in {"http", "https"}:
        raise RequestError("A kamera sémája HTTP vagy HTTPS lehet.")
    player_path = str(raw.get("playerPath") or "")
    if player_path and (len(player_path) > 192 or not re.fullmatch(r"/[A-Za-z0-9._/-]+", player_path) or "//" in player_path or any(part in {".", ".."} for part in player_path.split("/"))):
        raise RequestError("A player path érvénytelen.")
    if raw.get("audio") is not None and not isinstance(raw.get("audio"), bool):
        raise RequestError("A hang beállítása logikai érték legyen.")
    sources: dict[str, str] = {}
    for field in ("primarySource", "previewSource"):
        source = str(raw.get(field) or "")
        if not re.fullmatch(source_pattern, source) or re.fullmatch(r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}", source) or BLOCKED_HOST in source:
            raise RequestError(f"A(z) {field} streamalias érvénytelen.")
        sources[field] = source
    return {
        "id": profile_id, "cameraId": camera_id, "name": name, "scheme": scheme,
        "host": validate_private_host(raw.get("host")),
        "port": canonical_integer(raw.get("port"), 1, 65535, "port"),
        "playerPort": canonical_integer(raw.get("playerPort"), 1, 65535, "playerPort"),
        "playerPath": player_path, "audio": raw.get("audio") is True,
        **sources,
    }


def validate_camera_save_request(raw: Any) -> dict[str, Any]:
    profile = validate_camera_profile(raw)
    return {"v": 1, "action": "camera-save", **profile, "requestId": secrets.token_hex(16)}


def validate_camera_delete_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"cameraId"}:
        raise RequestError("A kameratörléshez pontosan egy cameraId szükséges.")
    camera_id = str(raw.get("cameraId") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", camera_id):
        raise RequestError("A kamera-ID érvénytelen.")
    return {"v": 1, "action": "camera-delete", "cameraId": camera_id, "requestId": secrets.token_hex(16)}


def validate_camera_configure_request(raw: Any) -> dict[str, Any]:
    required = {"layoutSize", "featuredCameraId", "preventScreenSaver"}
    allowed = required | {"previewIntervalSeconds"}
    if not isinstance(raw, dict) or not required.issubset(raw) or not set(raw).issubset(allowed):
        raise RequestError("A layout-kérés mezői érvénytelenek.")
    layout = canonical_integer(raw.get("layoutSize"), 2, 4, "layoutSize")
    if layout not in {2, 3, 4}:
        raise RequestError("A layout 2×2, 3×3 vagy 4×4 lehet.")
    featured = str(raw.get("featuredCameraId") or "")
    if featured and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", featured):
        raise RequestError("A kiemelt kamera-ID érvénytelen.")
    if not isinstance(raw.get("preventScreenSaver"), bool):
        raise RequestError("A képernyőkímélő-védelem logikai érték legyen.")
    preview_interval = canonical_integer(raw.get("previewIntervalSeconds", 5), 1, 60, "previewIntervalSeconds")
    return {
        "v": 1, "action": "configure", "layoutSize": layout,
        "featuredCameraId": featured, "preventScreenSaver": raw["preventScreenSaver"],
        "previewIntervalSeconds": preview_interval,
        "requestId": secrets.token_hex(16),
    }


def validate_camera_reorder_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"cameraIds"} or not isinstance(raw.get("cameraIds"), list):
        raise RequestError("A kamerasorrendhez pontosan egy cameraIds lista szükséges.")
    camera_ids: list[str] = []
    seen: set[str] = set()
    for value in raw["cameraIds"]:
        camera_id = str(value or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", camera_id):
            raise RequestError("A kamerasorrend egyik kamera-ID-ja érvénytelen.")
        if camera_id in seen:
            raise RequestError("A kamerasorrend ismétlődő kamera-ID-t tartalmaz.")
        seen.add(camera_id)
        camera_ids.append(camera_id)
    return {
        "v": 1, "action": "camera-reorder", "cameraIds": camera_ids,
        "requestId": secrets.token_hex(16),
    }


def validate_camera_open_request(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {"cameraId"}:
        raise RequestError("A kameranyitáshoz pontosan egy cameraId szükséges.")
    camera_id = str(raw.get("cameraId") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", camera_id):
        raise RequestError("A kamera-ID érvénytelen.")
    return {"v": 1, "action": "open", "cameraId": camera_id, "view": "full", "requestId": secrets.token_hex(16)}


def validate_remote_launch_params(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RequestError("Az alkalmazásparaméterek JSON objektum legyenek.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise RequestError("Az alkalmazásparaméterek csak szabályos JSON-adatot tartalmazhatnak.") from error
    if len(encoded.encode("utf-8")) > 4096:
        raise RequestError("Az alkalmazásparaméterek legfeljebb 4096 bájtosak lehetnek.")
    return json.loads(encoded)


def validate_home_assistant_webhook(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 512 or "%" in text:
        raise RequestError("A webhook URL 1–512 karakteres, kódolatlan URL legyen.")
    try:
        parsed = urlsplit(text)
        host = validate_private_host(parsed.hostname)
        port = parsed.port
    except (ValueError, RequestError) as error:
        raise RequestError("A webhook csak kanonikus, helyi privát IPv4-címet használhat.") from error
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RequestError("A webhook URL formátuma érvénytelen.")
    if port is not None and not 1 <= port <= 65535:
        raise RequestError("A webhook portja érvénytelen.")
    if not re.fullmatch(r"/api/webhook/[A-Za-z0-9._~-]{1,200}", parsed.path):
        raise RequestError("A Home Assistant webhook útvonala /api/webhook/AZONOSÍTÓ legyen.")
    expected = parsed.scheme + "://" + host + ((":" + str(port)) if port is not None else "") + parsed.path
    if text != expected:
        raise RequestError("A webhook URL kanonikus alakban adható meg.")
    return text


def managed_launch_binding(binding_type: str, app_id: str, launch_params: dict[str, Any], **metadata: Any) -> dict[str, Any]:
    if binding_type not in REMOTE_MANAGED_TYPES:
        raise ValueError("unsupported managed remote binding")
    launch_payload = json.dumps(
        {"id": app_id, "params": launch_params}, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    )
    # Current webOS builds acknowledge one-shot requests reliably with -t 1;
    # the older -n 1 form can silently exit from a non-interactive process.
    command = (
        "/usr/bin/luna-send-pub -t 1 -w 10000 -f "
        + shlex.quote(LAUNCH_URI) + " " + shlex.quote(launch_payload)
        + " >/dev/null 2>&1"
    )
    return {
        "action": "exec",
        "command": command,
        "managedBy": REMOTE_MAPPER_APP_ID,
        "bindingType": binding_type,
        **metadata,
    }


def validate_remote_bind_request(raw: Any) -> tuple[int, dict[str, Any] | None]:
    if not isinstance(raw, dict):
        raise RequestError("A gombkötés JSON objektum legyen.")
    if set(raw) - {"keyCode", "action", "appId", "targetKeyCode", "presetId", "cameraId", "params", "webhookUrl"}:
        raise RequestError("A gombkötés ismeretlen mezőt tartalmaz.")
    key_code = canonical_integer(raw.get("keyCode"), 1, 4096, "keyCode")
    if key_code not in REMOTE_EDITABLE_CODES:
        raise RequestError("Ez a fontos távirányítógomb itt nem módosítható.")
    action = str(raw.get("action") or "")
    if action == "original":
        if set(raw) != {"keyCode", "action"}:
            raise RequestError("Az eredeti működéshez nem adható további mező.")
        return key_code, None
    if action == "ignore":
        if set(raw) != {"keyCode", "action"}:
            raise RequestError("A letiltáshoz nem adható további mező.")
        return key_code, {"action": "ignore"}
    if action == "launcherHome":
        if set(raw) != {"keyCode", "action"}:
            raise RequestError("A launcher Home-kezeléshez nem adható további mező.")
        if key_code != 773:
            raise RequestError("A rövid/hosszú launcher mód csak a Home gombhoz használható.")
        return key_code, {
            "action": "exec",
            "command": shlex.quote(LAUNCHER_HOME_KEY) + " >/dev/null 2>&1",
            "managedBy": REMOTE_MAPPER_APP_ID,
            "bindingType": "launcherHome",
            "appId": LAUNCHER_APP_ID,
        }
    if action == "launch":
        if set(raw) != {"keyCode", "action", "appId"}:
            raise RequestError("Az alkalmazásindításhoz pontosan egy appId szükséges.")
        app_id = str(raw.get("appId") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", app_id):
            raise RequestError("Az alkalmazásazonosító érvénytelen.")
        return key_code, {"action": "launch", "id": app_id}
    if action == "replace":
        if set(raw) != {"keyCode", "action", "targetKeyCode"}:
            raise RequestError("A gombcseréhez pontosan egy célgomb szükséges.")
        target = canonical_integer(raw.get("targetKeyCode"), 1, 4096, "targetKeyCode")
        if target not in REMOTE_REPLACE_CODES:
            raise RequestError("Ez a célgomb nem engedélyezett.")
        return key_code, {"action": "replace", "keycode": target}
    if action == "overlayPreset":
        if set(raw) != {"keyCode", "action", "presetId"}:
            raise RequestError("A PiP preset indításához pontosan egy presetId szükséges.")
        preset_id = str(raw.get("presetId") or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", preset_id):
            raise RequestError("A PiP preset azonosítója érvénytelen.")
        return key_code, managed_launch_binding(
            "overlayPreset", APP_ID, {"v": 1, "action": "show", "presetId": preset_id}, presetId=preset_id,
        )
    if action == "cameraOpen":
        if set(raw) != {"keyCode", "action", "cameraId"}:
            raise RequestError("A kameranyitáshoz pontosan egy cameraId szükséges.")
        camera_id = str(raw.get("cameraId") or "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", camera_id):
            raise RequestError("A kameraazonosító érvénytelen.")
        return key_code, managed_launch_binding(
            "cameraOpen", CAMERA_APP_ID,
            {"v": 1, "action": "open", "cameraId": camera_id, "view": "full"}, cameraId=camera_id,
        )
    if action == "appCommand":
        if set(raw) != {"keyCode", "action", "appId", "params"}:
            raise RequestError("Az egyéni app-parancshoz appId és params szükséges.")
        app_id = str(raw.get("appId") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", app_id):
            raise RequestError("Az alkalmazásazonosító érvénytelen.")
        params = validate_remote_launch_params(raw.get("params"))
        return key_code, managed_launch_binding(
            "appCommand", app_id, params, appId=app_id, params=params,
        )
    if action == "webhook":
        if set(raw) != {"keyCode", "action", "webhookUrl"}:
            raise RequestError("A webhook-kötéshez pontosan egy webhookUrl szükséges.")
        webhook_url = validate_home_assistant_webhook(raw.get("webhookUrl"))
        command = (
            "/usr/bin/curl --fail --silent --show-error --max-time 4 --request POST "
            "--header " + shlex.quote("Content-Type: application/json") + " "
            "--data " + shlex.quote("{}") + " " + shlex.quote(webhook_url) + " >/dev/null 2>&1"
        )
        return key_code, {
            "action": "exec", "command": command, "managedBy": REMOTE_MAPPER_APP_ID,
            "bindingType": "webhook", "webhookUrl": webhook_url,
        }
    raise RequestError("A kiválasztott távirányító-művelet nem támogatott.")


def validate_remote_restore_request(raw: Any) -> str:
    if not isinstance(raw, dict) or set(raw) != {"source"}:
        raise RequestError("A visszaállításhoz pontosan egy source szükséges.")
    source = str(raw.get("source") or "")
    if source not in {"previous", "original"}:
        raise RequestError("A visszaállítás forrása previous vagy original lehet.")
    return source


def validate_tv_power_request(raw: Any) -> str:
    if not isinstance(raw, dict) or set(raw) != {"state"}:
        raise RequestError("A TV-kapcsoláshoz pontosan egy state szükséges.")
    state = str(raw.get("state") or "").lower()
    if state not in {"on", "off"}:
        raise RequestError("A TV állapota on vagy off lehet.")
    return state


def parse_luna_response(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    responses: list[dict[str, Any]] = []
    position = 0
    while position < len(output):
        start = output.find("{", position)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(output, start)
        except json.JSONDecodeError:
            position = start + 1
            continue
        position = end
        if isinstance(value, dict):
            responses.append(value)
    if responses:
        return responses[-1]
    raise RuntimeError("A TV nem adott értelmezhető Luna-választ.")


def _recv_exact(connection: socket.socket, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = connection.recv(length - len(chunks))
        if not chunk:
            raise RuntimeError("A VNC-kapcsolat idő előtt megszakadt.")
        chunks.extend(chunk)
    return bytes(chunks)


def _reverse_bits(value: int) -> int:
    result = 0
    for _ in range(8):
        result = (result << 1) | (value & 1)
        value >>= 1
    return result


def _vnc_response(password: str, challenge: bytes) -> bytes:
    key = (password.encode("latin-1", "ignore")[:8] + b"\x00" * 8)[:8]
    key = bytes(_reverse_bits(value) for value in key)
    command = ["openssl", "enc", "-des-ecb", "-K", key.hex(), "-nosalt", "-nopad"]
    completed = subprocess.run(command, input=challenge, capture_output=True, timeout=4, check=False)
    if completed.returncode != 0 or len(completed.stdout) != 16:
        legacy = command + ["-provider", "legacy"]
        completed = subprocess.run(legacy, input=challenge, capture_output=True, timeout=4, check=False)
    if completed.returncode != 0 or len(completed.stdout) != 16:
        raise RuntimeError("A VNC-hitelesítéshez szükséges DES nem érhető el.")
    return completed.stdout


def _png_from_bgrx(width: int, height: int, pixels: bytes) -> bytes:
    if width < 1 or height < 1 or width > 3840 or height > 2160 or len(pixels) != width * height * 4:
        raise RuntimeError("A VNC képkocka mérete érvénytelen.")
    rows = bytearray()
    stride = width * 4
    for y in range(height):
        source = pixels[y * stride:(y + 1) * stride]
        rows.append(0)
        for offset in range(0, len(source), 4):
            rows.extend((source[offset + 2], source[offset + 1], source[offset]))
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack("!I", len(payload)) + kind + payload + struct.pack("!I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(rows), 6)) + chunk(b"IEND", b"")


def capture_vnc_png(host: str, port: int, password: str) -> bytes:
    with socket.create_connection((host, port), timeout=5) as connection:
        connection.settimeout(8)
        version = _recv_exact(connection, 12)
        if not version.startswith(b"RFB 003."):
            raise RuntimeError("A TV VNC-verziója nem támogatott.")
        connection.sendall(b"RFB 003.008\n")
        count = _recv_exact(connection, 1)[0]
        if count == 0:
            length = struct.unpack("!I", _recv_exact(connection, 4))[0]
            raise RuntimeError("A VNC-szerver elutasította a kapcsolatot: " + _recv_exact(connection, min(length, 200)).decode("utf-8", "replace"))
        security_types = _recv_exact(connection, count)
        if 2 in security_types:
            connection.sendall(b"\x02")
            connection.sendall(_vnc_response(password, _recv_exact(connection, 16)))
            if struct.unpack("!I", _recv_exact(connection, 4))[0] != 0:
                raise RuntimeError("A TV VNC-hitelesítése sikertelen.")
        elif 1 in security_types:
            connection.sendall(b"\x01")
            if struct.unpack("!I", _recv_exact(connection, 4))[0] != 0:
                raise RuntimeError("A TV VNC-kapcsolata sikertelen.")
        else:
            raise RuntimeError("A TV VNC-hitelesítése nem támogatott.")
        connection.sendall(b"\x01")
        width, height = struct.unpack("!HH", _recv_exact(connection, 4))
        _recv_exact(connection, 16)
        name_length = struct.unpack("!I", _recv_exact(connection, 4))[0]
        _recv_exact(connection, min(name_length, 4096))
        if name_length > 4096:
            raise RuntimeError("A VNC-szerver neve túl hosszú.")
        pixel_format = struct.pack("!BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)
        connection.sendall(b"\x00\x00\x00\x00" + pixel_format)
        connection.sendall(struct.pack("!BBHi", 2, 0, 1, 0))
        connection.sendall(struct.pack("!BBHHHH", 3, 0, 0, 0, width, height))
        while True:
            message_type = _recv_exact(connection, 1)[0]
            if message_type == 0:
                _recv_exact(connection, 1)
                rectangles = struct.unpack("!H", _recv_exact(connection, 2))[0]
                canvas = bytearray(width * height * 4)
                for _ in range(rectangles):
                    x, y, rect_width, rect_height, encoding = struct.unpack("!HHHHi", _recv_exact(connection, 12))
                    if encoding != 0 or x + rect_width > width or y + rect_height > height:
                        raise RuntimeError("A VNC-képkocka kódolása nem támogatott.")
                    raw = _recv_exact(connection, rect_width * rect_height * 4)
                    for row in range(rect_height):
                        source_start = row * rect_width * 4
                        target_start = ((y + row) * width + x) * 4
                        canvas[target_start:target_start + rect_width * 4] = raw[source_start:source_start + rect_width * 4]
                return _png_from_bgrx(width, height, bytes(canvas))
            if message_type == 2:
                continue
            if message_type == 3:
                _recv_exact(connection, 3)
                length = struct.unpack("!I", _recv_exact(connection, 4))[0]
                _recv_exact(connection, min(length, 1_048_576))
                continue
            raise RuntimeError("Ismeretlen VNC-szerverüzenet.")


def send_vnc_key(host: str, port: int, password: str, key_name: str) -> None:
    key = VNC_REMOTE_KEYS.get(key_name)
    if key is None:
        raise RequestError("Ez a távirányító-gomb nem engedélyezett.")
    with socket.create_connection((host, port), timeout=5) as connection:
        connection.settimeout(8)
        version = _recv_exact(connection, 12)
        if not version.startswith(b"RFB 003."):
            raise RuntimeError("A TV VNC-verziója nem támogatott.")
        connection.sendall(b"RFB 003.008\n")
        count = _recv_exact(connection, 1)[0]
        if count == 0:
            raise RuntimeError("A VNC-szerver elutasította a kapcsolatot.")
        security_types = _recv_exact(connection, count)
        if 2 in security_types:
            connection.sendall(b"\x02")
            connection.sendall(_vnc_response(password, _recv_exact(connection, 16)))
            if struct.unpack("!I", _recv_exact(connection, 4))[0] != 0:
                raise RuntimeError("A TV VNC-hitelesítése sikertelen.")
        elif 1 in security_types:
            connection.sendall(b"\x01")
            if struct.unpack("!I", _recv_exact(connection, 4))[0] != 0:
                raise RuntimeError("A TV VNC-kapcsolata sikertelen.")
        else:
            raise RuntimeError("A TV VNC-hitelesítése nem támogatott.")
        connection.sendall(b"\x01")
        _recv_exact(connection, 4)
        _recv_exact(connection, 16)
        name_length = struct.unpack("!I", _recv_exact(connection, 4))[0]
        if name_length > 4096:
            raise RuntimeError("A VNC-szerver neve túl hosszú.")
        _recv_exact(connection, name_length)
        connection.sendall(struct.pack("!BBxxI", 4, 1, key))
        connection.sendall(struct.pack("!BBxxI", 4, 0, key))


def validate_synced_config(module: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise RequestError("A TV konfigurációja JSON objektum legyen.")
    if module == "media-overlay":
        if raw.get("version") != 1 or set(raw) != {"version", "layout", "presets"} or not isinstance(raw.get("presets"), list):
            raise RequestError("A TV PiP-konfigurációja érvénytelen.")
        layout_raw = raw.get("layout")
        if not isinstance(layout_raw, dict):
            raise RequestError("A TV PiP-layoutja érvénytelen.")
        layout_params = validate_configure_request(layout_raw)
        layout = {key: value for key, value in layout_params.items() if key in CONFIGURE_FIELDS}
        if len(raw["presets"]) > 32:
            raise RequestError("Legfeljebb 32 preset fogadható a TV-től.")
        presets = []
        seen = set()
        for item in raw["presets"]:
            if not isinstance(item, dict):
                raise RequestError("A TV presetlistája érvénytelen.")
            request = {
                "presetId": item.get("id"), "kind": item.get("kind"),
                "clickAction": item.get("clickAction"), "cameraId": item.get("cameraId"),
            }
            if item.get("kind") == "text":
                request["text"] = item.get("content")
            else:
                request["url"] = item.get("content")
                request["fit"] = item.get("fit")
            checked = validate_preset_save_request(request)
            if checked["presetId"] in seen:
                raise RequestError("Ismétlődő preset a TV konfigurációjában.")
            seen.add(checked["presetId"])
            presets.append({
                "id": checked["presetId"], "kind": checked["kind"],
                "content": checked.get("text", checked.get("url")), "fit": checked.get("fit", "contain"),
                "clickAction": checked.get("clickAction", ""), "cameraId": checked.get("cameraId", ""),
            })
        return {"version": 1, "layout": layout, "presets": presets}

    if module == "camera-viewer":
        if raw.get("version") != 3 or set(raw) != {"version", "settings", "profiles"} or not isinstance(raw.get("profiles"), list):
            raise RequestError("A TV kamera-konfigurációja érvénytelen.")
        settings_raw = raw.get("settings")
        settings_params = validate_camera_configure_request(settings_raw)
        settings = {
            "layoutSize": settings_params["layoutSize"],
            "featuredCameraId": settings_params["featuredCameraId"],
            "preventScreenSaver": settings_params["preventScreenSaver"],
            "previewIntervalSeconds": settings_params["previewIntervalSeconds"],
        }
        profiles = []
        seen_ids: set[str] = set()
        seen_camera_ids: set[str] = set()
        for item in raw["profiles"]:
            profile = validate_camera_profile(item)
            if profile["id"] in seen_ids or profile["cameraId"] in seen_camera_ids:
                raise RequestError("Ismétlődő kamera a TV konfigurációjában.")
            seen_ids.add(profile["id"])
            seen_camera_ids.add(profile["cameraId"])
            profiles.append(profile)
        if settings["featuredCameraId"] and settings["featuredCameraId"] not in seen_camera_ids:
            settings["featuredCameraId"] = ""
        return {"version": 3, "settings": settings, "profiles": profiles}
    raise RequestError("Ismeretlen TV-modul.")


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.condition = threading.Condition()
        self.data: dict[str, Any] = {"media-overlay": None, "camera-viewer": None}
        self.revisions = {"media-overlay": 0, "camera-viewer": 0}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            for module in self.data:
                if isinstance(loaded, dict) and loaded.get(module) is not None:
                    self.data[module] = validate_synced_config(module, loaded[module])
        except (OSError, ValueError, RequestError):
            pass

    def update(self, module: str, config: Any) -> dict[str, Any]:
        normalized = validate_synced_config(module, config)
        with self.condition:
            self.data[module] = normalized
            self.revisions[module] += 1
            temporary = self.path.with_suffix(self.path.suffix + ".new")
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            temporary.replace(self.path)
            self.condition.notify_all()
            return normalized

    def revision(self, module: str) -> int:
        with self.condition:
            return self.revisions[module]

    def snapshot(self, module: str) -> Any:
        with self.condition:
            return self.data[module]

    def wait_after(self, module: str, revision: int, timeout: float = 6.0) -> Any:
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.revisions[module] <= revision:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.condition.wait(remaining)
            return self.data[module]


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()

    def _read(self) -> Any:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, value: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".new")
        temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temporary.replace(self.path)


class ConnectionStore(JsonStore):
    def __init__(self, path: Path, config: dict[str, Any], state_store: StateStore):
        super().__init__(path)
        camera_state = state_store.snapshot("camera-viewer") or {}
        profiles = camera_state.get("profiles") if isinstance(camera_state, dict) else []
        profile = profiles[0] if isinstance(profiles, list) and profiles else {}
        initial = {
            "controlOrigin": config["_public_base_url"],
            "tvHost": str(config["tv_host"]),
            "gatewayScheme": str(profile.get("scheme") or config.get("gateway_scheme") or "http"),
            "gatewayHost": str(profile.get("host") or config.get("gateway_host") or config["tv_host"]),
            "mediaPort": profile.get("port") or config.get("gateway_media_port") or 80,
            "playerPort": profile.get("playerPort") or config.get("gateway_player_port") or 80,
            "playerPath": str(profile.get("playerPath") or config.get("gateway_player_path") or "/webos-player.html"),
        }
        try:
            initial.update(self._read())
        except (OSError, ValueError):
            pass
        self.data = validate_connections(initial)
        self._write(self.data)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.data))

    def update(self, raw: Any) -> dict[str, Any]:
        checked = validate_connections(raw)
        with self.lock:
            self.data = checked
            self._write(self.data)
            return self.snapshot()


class LauncherAppCatalog(JsonStore):
    """Persistent app catalog so opening the launcher never waits on TV SSH."""

    def __init__(self, path: Path):
        super().__init__(path)
        self.data: dict[str, Any] = {"updatedAt": 0.0, "apps": []}
        self.refreshing = False
        try:
            loaded = self._read()
            apps = loaded.get("apps") if isinstance(loaded, dict) else None
            if isinstance(apps, list) and len(apps) <= 2048:
                checked = []
                for item in apps:
                    if not isinstance(item, dict) or set(item) != {"id", "title"}:
                        raise ValueError
                    app_id = str(item["id"])
                    title = str(item["title"])
                    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", app_id) or not 1 <= len(title) <= 96:
                        raise ValueError
                    checked.append({"id": app_id, "title": title})
                self.data = {"updatedAt": float(loaded.get("updatedAt") or 0), "apps": checked}
        except (OSError, ValueError, TypeError):
            pass

    def snapshot(self) -> list[dict[str, str]]:
        with self.lock:
            return json.loads(json.dumps(self.data["apps"]))

    def should_refresh(self, max_age_seconds: float = 300.0) -> bool:
        with self.lock:
            return not self.data["apps"] or time.time() - float(self.data["updatedAt"]) >= max_age_seconds

    def begin_refresh(self) -> bool:
        with self.lock:
            if self.refreshing:
                return False
            self.refreshing = True
            return True

    def finish_refresh(self, apps: list[dict[str, str]] | None) -> None:
        with self.lock:
            try:
                if apps is not None:
                    self.data = {"updatedAt": time.time(), "apps": [{"id": item["id"], "title": item["title"]} for item in apps]}
                    self._write(self.data)
            finally:
                self.refreshing = False


class LauncherStore(JsonStore):
    def __init__(self, path: Path):
        super().__init__(path)
        self.data = self._default()
        try:
            loaded = self._read()
            if isinstance(loaded, dict) and isinstance(loaded.get("settings"), dict):
                loaded["settings"].setdefault("focusScalePercent", 10)
                loaded["settings"].setdefault("defaultHomeEnabled", False)
                loaded["settings"].setdefault("bootOverlayEnabled", True)
                loaded["settings"].setdefault("bootOverlayMaxSeconds", 2)
                loaded["settings"].setdefault("animationsEnabled", True)
                loaded["settings"].setdefault("visualEffectsEnabled", True)
                loaded["settings"].setdefault("resumeLastAppOnPowerEnabled", False)
                loaded["settings"].setdefault("homeLaunchMode", "split")
                loaded["settings"].setdefault("fullLauncherPresentation", "app")
                urls = loaded["settings"].get("wallpaperUrls")
                if isinstance(urls, list) and any(url in LEGACY_WALLPAPER_REPLACEMENTS for url in urls):
                    migrated_urls = []
                    for url in urls:
                        candidate = LEGACY_WALLPAPER_REPLACEMENTS.get(url, url)
                        if candidate not in migrated_urls:
                            migrated_urls.append(candidate)
                    loaded["settings"]["wallpaperUrls"] = urls = migrated_urls
                original_defaults = DEFAULT_WALLPAPER_URLS[:20]
                if isinstance(urls, list) and all(url in urls for url in original_defaults):
                    for url in DEFAULT_WALLPAPER_URLS:
                        if url not in urls and len(urls) < 100:
                            urls.append(url)
            self.data = validate_launcher_config(loaded)
            self._write(self.data)
        except (OSError, ValueError, RequestError):
            self._write(self.data)

    @staticmethod
    def _default() -> dict[str, Any]:
        return {
            "version": 1,
            "lastUsed": None,
            "rows": [
                {"id": "favorites", "title": "Kedvencek", "visible": True, "items": []},
                {"id": "apps", "title": "Alkalmazások", "visible": True, "items": []},
                {"id": "links", "title": "Web", "visible": True, "items": []},
                {"id": "cameras", "title": "Kamerák", "visible": True, "items": []},
                {"id": "utilities", "title": "Eszközök", "visible": True, "items": [
                    {"id": "all-apps", "type": "allApps", "targetId": "", "label": "Összes alkalmazás", "visible": True, "fit": "contain", "iconKey": "", "iconUrl": "", "backgroundColor": ""},
                    {"id": "launcher-settings", "type": "settings", "targetId": "", "label": "Launcher beállítások", "visible": True, "fit": "contain", "iconKey": "", "iconUrl": "", "backgroundColor": ""},
                ]},
            ],
            "settings": {
                "wallpaperEnabled": True, "wallpaperIntervalMinutes": 5, "wallpaperDimPercent": 42,
                "wallpaperUrls": list(DEFAULT_WALLPAPER_URLS), "weatherEnabled": False,
                "weatherLabel": "", "latitude": 0.0, "longitude": 0.0,
                "cameraPreviewsEnabled": True, "focusScalePercent": 10, "editorModeEnabled": True,
                "defaultHomeEnabled": False,
                "bootOverlayEnabled": True, "bootOverlayMaxSeconds": 2,
                "animationsEnabled": True, "visualEffectsEnabled": True, "resumeLastAppOnPowerEnabled": False,
                "homeLaunchMode": "split",
                "fullLauncherPresentation": "app",
            },
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.data))

    def update(self, raw: Any) -> dict[str, Any]:
        checked = validate_launcher_config(raw)
        with self.lock:
            self.data = checked
            self._write(self.data)
            return self.snapshot()

    def record_last(self, item_type: str, target_id: str, label: str) -> None:
        if item_type not in {"app", "preset"}:
            return
        if item_type == "app" and target_id in {LAUNCHER_APP_ID, LAUNCHER_QUICK_APP_ID, LAUNCHER_OVERLAY_APP_ID}:
            return
        with self.lock:
            self.data["lastUsed"] = {"type": item_type, "targetId": target_id, "label": label[:64] or target_id}
            self._write(self.data)

    def seed(self, apps: list[dict[str, str]], presets: list[dict[str, str]]) -> None:
        with self.lock:
            available_app_ids = {app["id"] for app in apps}
            utility_row = next(row for row in self.data["rows"] if row["id"] == "utilities")
            protected_utilities = (
                {"id": "all-apps", "type": "allApps", "targetId": "", "label": "Összes alkalmazás", "visible": True, "fit": "contain", "iconKey": "", "iconUrl": "", "backgroundColor": ""},
                {"id": "launcher-settings", "type": "settings", "targetId": "", "label": "Launcher beállítások", "visible": True, "fit": "contain", "iconKey": "", "iconUrl": "", "backgroundColor": ""},
            )
            existing_ids = {item["id"] for item in utility_row["items"]}
            protected_added = False
            for protected in reversed(protected_utilities):
                if protected["id"] not in existing_ids:
                    utility_row["items"].insert(0, protected)
                    existing_ids.add(protected["id"])
                    protected_added = True
            original_utility_count = len(utility_row["items"])
            utility_row["items"] = [
                item for item in utility_row["items"]
                if not (
                    item["id"].startswith("utility-com-webos-app-")
                    and item["targetId"] in LAUNCHER_SYSTEM_INPUT_IDS
                    and item["targetId"] not in available_app_ids
                )
            ]
            existing_targets = {item["targetId"] for item in utility_row["items"] if item["type"] == "app"}
            utilities_changed = protected_added or len(utility_row["items"]) != original_utility_count
            for system_input in LAUNCHER_SYSTEM_INPUTS:
                if system_input["id"] not in available_app_ids or system_input["id"] in existing_targets:
                    continue
                utility_row["items"].append({
                    "id": "utility-" + system_input["id"].replace(".", "-"),
                    "type": "app", "targetId": system_input["id"], "label": system_input["label"],
                    "visible": True, "fit": "contain", "iconKey": system_input["iconKey"],
                    "iconUrl": "", "backgroundColor": "",
                })
                existing_targets.add(system_input["id"])
                utilities_changed = True
            if any(row["items"] for row in self.data["rows"] if row["id"] in {"favorites", "apps", "cameras"}):
                if utilities_changed:
                    self._write(self.data)
                return
            favorites = []
            preferred_ids = {CAMERA_APP_ID, APP_ID, "com.webos.app.livetv"}
            preferred_words = ("youtube", "netflix", "plex", "disney", "prime")
            for app in apps:
                if app["id"] in preferred_ids or any(word in app["title"].casefold() for word in preferred_words):
                    favorites.append({"id": "fav-" + re.sub(r"[^a-z0-9._-]", "-", app["id"].lower())[:54], "type": "app", "targetId": app["id"], "label": app["title"], "visible": True, "fit": "contain", "iconKey": "", "iconUrl": "", "backgroundColor": ""})
                if len(favorites) >= 8:
                    break
            favorite_ids = {item["targetId"] for item in favorites}
            other = [
                {"id": "app-" + re.sub(r"[^a-z0-9._-]", "-", app["id"].lower())[:54], "type": "app", "targetId": app["id"], "label": app["title"], "visible": True, "fit": "contain", "iconKey": "", "iconUrl": "", "backgroundColor": ""}
                for app in apps if app["id"] not in favorite_ids and app["id"] not in {LAUNCHER_APP_ID, LAUNCHER_QUICK_APP_ID, LAUNCHER_OVERLAY_APP_ID}
            ][:12]
            cameras = [
                {"id": "preset-" + item["id"], "type": "preset", "targetId": item["id"], "label": item["id"], "visible": True, "fit": "cover", "iconKey": "", "iconUrl": "", "backgroundColor": ""}
                for item in presets[:32]
            ]
            for row in self.data["rows"]:
                if row["id"] == "favorites": row["items"] = favorites
                elif row["id"] == "apps": row["items"] = other
                elif row["id"] == "cameras": row["items"] = cameras
            self._write(self.data)

def remote_mapper_shortcuts(store: StateStore) -> dict[str, list[dict[str, str]]]:
    overlay = store.snapshot("media-overlay") or {}
    camera = store.snapshot("camera-viewer") or {}
    presets = []
    for item in overlay.get("presets", []):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            presets.append({"id": item["id"], "kind": str(item.get("kind") or "")})
    cameras = []
    for item in camera.get("profiles", []):
        if isinstance(item, dict) and isinstance(item.get("cameraId"), str):
            cameras.append({"cameraId": item["cameraId"], "name": str(item.get("name") or item["cameraId"])})
    return {"presets": presets, "cameras": cameras}


class TvLauncher:
    def __init__(self, config: dict[str, Any], runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.tv_host = str(config["tv_host"])
        self.tv_user = str(config.get("tv_user", "root"))
        self.ssh_key = str(config["ssh_key"])
        self.known_hosts = str(config["known_hosts"])
        self.timeout = canonical_integer(config.get("ssh_timeout_seconds", 12), 2, 30, "ssh_timeout_seconds")
        self.runner = runner

    def launch(self, params: dict[str, Any], app_id: str = APP_ID, allow_any: bool = False) -> dict[str, Any]:
        if not allow_any and app_id not in APP_IDS.values():
            raise RuntimeError("Nem engedélyezett TV-alkalmazás.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", app_id):
            raise RuntimeError("Érvénytelen TV-alkalmazásazonosító.")
        envelope = json.dumps({"id": app_id, "params": params}, ensure_ascii=False, separators=(",", ":"))
        remote_command = (
            "luna-send-pub -t 1 -w 10000 -f " + shlex.quote(LAUNCH_URI) + " " + shlex.quote(envelope)
        )
        command = [
            # luna-send-pub exits without a reply when ssh inherits /dev/null
            # from systemd. A forced remote PTY keeps its session alive until
            # the one requested Luna response arrives.
            "ssh", "-tt", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-i", self.ssh_key, f"{self.tv_user}@{self.tv_host}", remote_command,
        ]
        completed = self.runner(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "SSH hiba").strip().splitlines()[-1]
            raise RuntimeError("A TV-parancs sikertelen: " + detail[:300])
        # Some webOS/ssh combinations write luna-send's JSON reply to stderr
        # when the command is started by a systemd service, even though the
        # same command writes to stdout in an interactive shell.  Both streams
        # belong to the same trusted local command, so parse their combined
        # output instead of incorrectly reporting an empty Luna response.
        response = parse_luna_response((completed.stdout or "") + "\n" + (completed.stderr or ""))
        if response.get("returnValue") is not True:
            raise RuntimeError("A TV elutasította az alkalmazásindítást.")
        return response


class TvPowerManager:
    """LAN power control with rooted-TV shutdown and Wi-Fi magic-packet wake."""

    POWER_STATE_URI = "luna://com.webos.service.tvpower/power/getPowerState"
    POWER_OFF_URI = "luna://com.webos.service.tvpower/power/powerOff"
    ON_STATES = {"Active", "Screen Saver", "Screen Off"}
    OFF_STATES = {"Suspend", "Active Standby", "Power Off"}

    def __init__(
        self,
        config: dict[str, Any],
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        probe: Callable[[str], bool] | None = None,
        wake_sender: Callable[[bytes, str, int], None] | None = None,
    ):
        self.tv_host = str(config["tv_host"])
        self.tv_user = str(config.get("tv_user", "root"))
        self.ssh_key = str(config["ssh_key"])
        self.known_hosts = str(config["known_hosts"])
        self.timeout = canonical_integer(config.get("ssh_timeout_seconds", 12), 2, 30, "ssh_timeout_seconds")
        self.wifi_mac = str(config["tv_wifi_mac"])
        self.broadcasts = tuple(str(value) for value in config["tv_wake_broadcasts"])
        self.runner = runner
        self.probe = probe or self._tcp_probe
        self.wake_sender = wake_sender or self._udp_wake
        self.lock = threading.RLock()
        self.last_request: tuple[str, float] | None = None

    @staticmethod
    def _tcp_probe(host: str) -> bool:
        try:
            with socket.create_connection((host, 22), timeout=0.8):
                return True
        except OSError:
            return False

    @staticmethod
    def _udp_wake(packet: bytes, broadcast: str, port: int) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sender.settimeout(1)
            sender.sendto(packet, (broadcast, port))

    def _run(self, remote_command: str) -> str:
        command = [
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=3",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-i", self.ssh_key, f"{self.tv_user}@{self.tv_host}", remote_command,
        ]
        completed = self.runner(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "SSH hiba").strip().splitlines()[-1]
            raise RuntimeError("A TV energia-parancsa sikertelen: " + detail[:300])
        return (completed.stdout or "") + "\n" + (completed.stderr or "")

    def status(self) -> dict[str, Any]:
        with self.lock:
            reachable = self.probe(self.tv_host)
            native_state = ""
            error = ""
            if reachable:
                try:
                    response = parse_luna_response(self._run(
                        "/usr/bin/luna-send -t 1 -w 3000 -f "
                        + shlex.quote(self.POWER_STATE_URI) + " '{}'"
                    ))
                    native_state = str(response.get("state") or "")
                    if response.get("returnValue") is not True or not native_state:
                        raise RuntimeError("A TV nem adott energiaállapotot.")
                except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
                    error = str(exc)[:300]
            if native_state in self.ON_STATES:
                state = "on"
            elif not reachable or native_state in self.OFF_STATES:
                state = "off"
            else:
                state = "unknown"
            if self.last_request is not None:
                requested, requested_at = self.last_request
                age = time.monotonic() - requested_at
                if requested == "on" and state == "off" and age < 45:
                    state = "turning_on"
                elif requested == "off" and state == "on" and age < 20:
                    state = "turning_off"
                elif (requested == "on" and state == "on") or (requested == "off" and state == "off") or age >= 45:
                    self.last_request = None
            result: dict[str, Any] = {
                "state": state,
                "on": state in {"on", "turning_on"},
                "reachable": reachable,
                "nativeState": native_state or None,
                "wakeTransport": "wifi-magic-packet",
            }
            if error:
                result["error"] = error
            return result

    def _wake(self) -> None:
        mac = bytes.fromhex(self.wifi_mac.replace(":", ""))
        packet = b"\xff" * 6 + mac * 16
        for _ in range(3):
            for broadcast in self.broadcasts:
                for port in (9, 7):
                    self.wake_sender(packet, broadcast, port)

    def set_state(self, requested: str) -> dict[str, Any]:
        if requested not in {"on", "off"}:
            raise ValueError("unsupported TV power state")
        with self.lock:
            current = self.status()
            if requested == "on":
                if current["state"] in {"on", "turning_on"}:
                    return current
                self._wake()
                self.last_request = ("on", time.monotonic())
            else:
                if current["state"] in {"off", "turning_off"}:
                    return current
                worker = (
                    "sleep 1; exec /usr/bin/luna-send -t 1 -w 5000 -f "
                    + shlex.quote(self.POWER_OFF_URI) + " " + shlex.quote('{"reason":"remoteKey"}')
                )
                self._run(
                    "nohup /bin/sh -c " + shlex.quote(worker)
                    + " </dev/null >/tmp/hu.szabi.rest-poweroff.log 2>&1 &"
                )
                self.last_request = ("off", time.monotonic())
            return self.status()

    def reboot(self) -> dict[str, Any]:
        """Perform a real webOS reboot, bypassing Quick Start standby."""
        with self.lock:
            current = self.status()
            if current.get("state") not in {"on", "turning_on"} or not current.get("reachable"):
                raise RuntimeError("A teljes újraindításhoz a TV-nek elérhetőnek kell lennie.")
            worker = "sleep 1; sync; /sbin/reboot"
            self._run("nohup /bin/sh -c " + shlex.quote(worker) + " </dev/null >/tmp/hu.szabi.full-reboot.log 2>&1 &")
            self.last_request = None
            return {"accepted": True, "state": "rebooting"}


class LauncherHomeManager:
    """Manage the reversible Homebrew launcher guard on the TV."""

    INIT_SCRIPT = """#!/bin/sh
DIR=/var/lib/webosbrew/launcher-home
[ -f "$DIR/enabled" ] || exit 0
nohup "$DIR/guard.sh" </dev/null >>/tmp/hu.szabi.launcher-home.log 2>&1 &
exit 0
"""

    HOME_KEY_SCRIPT = """#!/bin/sh
DIR=/var/lib/webosbrew/launcher-home
LOG=${LAUNCHER_HOME_KEY_LOG:-/tmp/lginput-hook-lginput2.log}
HOME_KEY_CODE=${LAUNCHER_HOME_KEY_CODE:-773}
case "$HOME_KEY_CODE" in ''|*[!0-9]*) HOME_KEY_CODE=773;; esac
FULL_APP=hu.szabi.launcher
if [ "$(cat "$DIR/full-presentation" 2>/dev/null)" = overlay ]; then FULL_APP=hu.szabi.launcher.overlay; fi
QUICK_APP=hu.szabi.launcher.quick
HOME_ACTIVE=/tmp/hu.szabi.launcher.home-active
FULL_VISIBLE=/tmp/hu.szabi.launcher.full-visible
QUICK_VISIBLE=/tmp/hu.szabi.launcher.quick-visible
QUICK_CLOSE_SUPPRESS=/tmp/hu.szabi.launcher.quick-close-suppress
ALLOW=/tmp/hu.szabi.launcher.allow-home
HOME_MODE="$DIR/home-mode"
CONTROL_ORIGIN="$DIR/control-origin"
FORCE_MODE=${LAUNCHER_HOME_FORCE_MODE:-}
FORCE_SOURCE=${LAUNCHER_HOME_FORCE_SOURCE:-}

mkdir -p "$DIR"
exec 7>/tmp/hu.szabi.launcher-home-key.flock
flock -n 7 || exit 0
touch "$HOME_ACTIVE"
cleanup() { rm -f "$HOME_ACTIVE"; }
trap cleanup EXIT INT TERM

quick_running() {
  line=$(luna-send -t 1 -w 1000 luna://com.webos.service.webappmanager/listRunningApps '{"includeSysApps":false}' 2>/dev/null)
  echo "$line" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher[.]quick"'
}

recent_quick_close() {
  suppress_until=$(cat "$QUICK_CLOSE_SUPPRESS" 2>/dev/null)
  case "$suppress_until" in ''|*[!0-9]*) return 1;; esac
  now=$(date +%s)
  [ "$now" -lt "$suppress_until" ]
}

close_quick() {
  rm -f "$QUICK_VISIBLE"
  close_attempt=0
  while [ "$close_attempt" -lt 3 ]; do
    quick_running || return 0
    /usr/bin/luna-send -t 1 -w 2000 -f luna://com.webos.service.applicationmanager/closeByAppId \
      '{"id":"hu.szabi.launcher.quick"}' >/dev/null 2>&1 || true
    close_attempt=$((close_attempt + 1))
    /bin/usleep 300000
  done
  ! quick_running
}

launch_mode() {
  mode=$1
  source=$2
  if [ -n "$FORCE_MODE" ]; then
    case "$FORCE_MODE" in full|overlay) mode=$FORCE_MODE;; *) exit 2;; esac
  else
    configured_mode=$(cat "$HOME_MODE" 2>/dev/null)
    case "$configured_mode" in
      full) mode=full;;
      overlay) mode=overlay;;
    esac
  fi
  if [ "$mode" = "overlay" ]; then
    app=$QUICK_APP
    host=quick
    visible=$QUICK_VISIBLE
  else
    app=$FULL_APP
    host=full
    visible=$FULL_VISIBLE
    if [ "$app" = hu.szabi.launcher.overlay ]; then host=full-overlay; visible=/tmp/hu.szabi.launcher.full-overlay-visible; fi
  fi

  # The retained popup knows whether it is open or natively hidden. A unique
  # request id also prevents initial/duplicate relaunch events closing it.
  [ "$source" = home-short ] && [ "$host" = quick ] && source=home-short-toggle
  request_id="$$-$(date +%s)"

  # Never leave an old full popup above a newly selected host.
  if [ "$host" != "full-overlay" ] && [ -f /tmp/hu.szabi.launcher.full-overlay-visible ]; then
    /usr/bin/luna-send -t 1 -w 2000 luna://com.webos.service.applicationmanager/closeByAppId '{"id":"hu.szabi.launcher.overlay"}' >/dev/null 2>&1 || true
    rm -f /tmp/hu.szabi.launcher.full-overlay-visible
  fi
  source=${source%-open}
  if [ "$host" != "quick" ] && [ -f "$QUICK_VISIBLE" ]; then
    close_quick || true
  fi
  origin=$(cat "$CONTROL_ORIGIN" 2>/dev/null)
  display=$(cat "$DIR/display-preferences.json" 2>/dev/null); [ -n "$display" ] || display='{}'
  payload=$(printf '{"id":"%s","noSplash":true,"params":{"mode":"%s","source":"%s","launcherHost":"%s","controlOrigin":"%s","displayPreferences":%s,"homeRequestId":"%s"}}' \
    "$app" "$mode" "$source" "$host" "$origin" "$display" "$request_id")
  attempt=0
  while [ "$attempt" -lt 4 ]; do
    result=$(/usr/bin/luna-send-pub -t 1 -w 5000 -f luna://com.webos.applicationManager/launch "$payload" 2>&1)
    if echo "$result" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
      rm -f "$ALLOW"
      touch "$visible"
      [ "$host" != "quick" ] && rm -f "$QUICK_VISIBLE"
      [ "$host" = "quick" ] && rm -f "$FULL_VISIBLE"
      return 0
    fi
    attempt=$((attempt + 1))
  done
  /usr/bin/luna-send-pub -t 1 -w 10000 -f luna://com.webos.applicationManager/launch "$payload" >/dev/null 2>&1
}

# A broker-level long Back explicitly requests the full launcher.  This path
# bypasses the Home short/long split but reuses the same safe launch payload.
if [ -n "$FORCE_MODE" ]; then
  launch_mode "$FORCE_MODE" "${FORCE_SOURCE:-external-force}"
  exit $?
fi

# Both press lengths have the same destination in full mode. Dispatch on the
# key-down hook without waiting for release/long-press detection in the log.
case "$(cat "$HOME_MODE" 2>/dev/null)" in
  full) launch_mode full home-short; exit $?;;
  overlay) launch_mode overlay home-short; exit $?;;
esac

if [ ! -r "$LOG" ]; then
  launch_mode overlay home-short
  exit 0
fi

mode=overlay
source=home-short
count=0
while [ "$count" -lt 16 ]; do
  state=$(grep "^$HOME_KEY_CODE => [012]$" "$LOG" 2>/dev/null | tail -n 1 | sed 's/.* => //')
  case "$state" in
    0) break ;;
    2) mode=full; source=home-long; break ;;
  esac
  count=$((count + 1))
  if [ "$count" -ge 16 ]; then
    mode=full
    source=home-long
    break
  fi
  /bin/usleep 50000
done
launch_mode "$mode" "$source"
"""

    PREWARM_SCRIPT = r"""#!/bin/sh
# Native hidden preload. The sole guard worker calls this after wake settles.
DIR=/var/lib/webosbrew/launcher-home
HOST=${1:-full}
REQUESTED_HOST="$HOST"
TARGET=hu.szabi.launcher
ATTEMPT=/tmp/hu.szabi.launcher.prewarm-attempt
QUICK_ATTEMPT=/tmp/hu.szabi.launcher.quick-prewarm-attempt
COVER_ATTEMPT=/tmp/hu.szabi.launcher.quick-cover-prewarm-attempt
COVER_READY=/tmp/hu.szabi.launcher.full-overlay-prewarm-ready
[ -f "$DIR/enabled" ] || exit 0
case "$HOST" in
  cover)
    TARGET=hu.szabi.launcher.overlay
    HOST=full-overlay
    epoch=$(cat /tmp/hu.szabi.launcher.active-since 2>/dev/null)
    case "$epoch" in ''|*[!0-9]*) exit 0;; esac
    [ "$(cat "$COVER_ATTEMPT" 2>/dev/null)" != "$epoch" ] || exit 0
    [ -f /tmp/hu.szabi.launcher.boot-ready ] || exit 0
    after=0
    ;;
  quick)
    [ "$(cat "$DIR/home-mode" 2>/dev/null)" != full ] || exit 0
    TARGET=hu.szabi.launcher.quick
    epoch=$(cat /tmp/hu.szabi.launcher.active-since 2>/dev/null)
    case "$epoch" in ''|*[!0-9]*) exit 0;; esac
    [ "$(cat "$QUICK_ATTEMPT" 2>/dev/null)" != "$epoch" ] || exit 0
    [ -f /tmp/hu.szabi.launcher.boot-ready ] || exit 0
    after=$(cat /tmp/hu.szabi.launcher.quick-prewarm-after 2>/dev/null)
    ;;
  full)
    [ "$(cat "$DIR/home-mode" 2>/dev/null)" != overlay ] || exit 0
    if [ "$(cat "$DIR/full-presentation" 2>/dev/null)" = overlay ]; then
      TARGET=hu.szabi.launcher.overlay
      HOST=full-overlay
      epoch=$(cat /tmp/hu.szabi.launcher.active-since 2>/dev/null)
      case "$epoch" in ''|*[!0-9]*) exit 0;; esac
      [ -f /tmp/hu.szabi.launcher.boot-ready ] || exit 0
      [ "$(cat "$ATTEMPT" 2>/dev/null)" != "overlay:$epoch" ] || exit 0
    fi
    after=$(cat /tmp/hu.szabi.launcher.prewarm-after 2>/dev/null)
    ;;
  *) exit 0;;
esac
exec 8>/tmp/hu.szabi.launcher.prewarm-flock
flock -n 8 || exit 0
power_safe() {
  [ -f "$DIR/enabled" ] || return 1
  [ ! -f /tmp/hu.szabi.launcher.power-startup ] || return 1
  [ ! -f /tmp/hu.szabi.launcher.wake-signal ] || return 1
  [ ! -f /tmp/hu.szabi.launcher.home-active ] || return 1
  power=$(luna-send -t 1 -f -w 1500 luna://com.webos.service.tvpower/power/getPowerState '{}' 2>&1)
  echo "$power" | grep -Eq '"state"[[:space:]]*:[[:space:]]*"Active"' || return 1
  [ ! -f /tmp/hu.szabi.launcher.wake-signal ]
}
after=${after:-0}
[ "$(date +%s)" -ge "$after" ] || exit 0
last=$(cat /tmp/hu.szabi.launcher.last-launch 2>/dev/null); last=${last:-0}
[ $(( $(date +%s) - last )) -ge 2 ] || exit 0
power_safe || exit 0
line=$(luna-send -t 1 -f -w 1500 luna://com.webos.applicationManager/getForegroundAppInfo '{}' 2>&1)
app=$(echo "$line" | sed -n 's/.*"appId"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
case "$app" in
  ''|*[!A-Za-z0-9._-]*|com.webos.app.home|com.webos.app.notification*|com.webos.app.volume*|com.webos.app.power*|com.webos.app.quicksettings*) exit 0;;
esac
if [ "$REQUESTED_HOST" = cover ]; then
  echo "$epoch" >"$COVER_ATTEMPT"
  available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  case "$available" in ''|*[!0-9]*) exit 0;; esac
  [ "$available" -ge 131072 ] || exit 0
elif [ "$HOST" = quick ]; then
  # At most one attempt per real wake, including memory rejection/reclamation.
  # Never repopulate a reclaimed popup in a loop during video playback.
  echo "$epoch" >"$QUICK_ATTEMPT"
  available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  case "$available" in ''|*[!0-9]*) exit 0;; esac
  [ "$available" -ge 131072 ] || exit 0
elif [ "$HOST" = full-overlay ]; then
  case "$app" in hu.szabi.launcher*) exit 0;; esac
  echo "overlay:$epoch" >"$ATTEMPT"
  available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  case "$available" in ''|*[!0-9]*) exit 0;; esac
  [ "$available" -ge 131072 ] || exit 0
else
  case "$app" in hu.szabi.launcher*|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*) exit 0;; esac
  [ "$(cat "$ATTEMPT" 2>/dev/null)" != "$app" ] || exit 0
  echo "$app" >"$ATTEMPT"
fi
line=$(luna-send -t 1 -f -w 1500 luna://com.webos.service.webappmanager/listRunningApps '{"includeSysApps":false}' 2>&1)
pattern=$(echo "$TARGET" | sed 's/\./[.]/g')
if echo "$line" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"'"$pattern"'"'; then
  [ "$REQUESTED_HOST" != cover ] || [ -f "$COVER_READY" ]
  exit 0
fi
origin=$(cat "$DIR/control-origin" 2>/dev/null)
display=$(cat "$DIR/display-preferences.json" 2>/dev/null); [ -n "$display" ] || display='{}'
# WAM's preload flag prevents surface activation before the app's JS runs.
# source=preload also initializes our shared UI parked, ready for Home relaunch.
payload=$(printf '{"id":"%s","preload":"full","keepAlive":true,"noSplash":true,"params":{"source":"preload","launcherHost":"%s","controlOrigin":"%s","displayPreferences":%s}}' "$TARGET" "$HOST" "$origin" "$display")
power_safe || exit 0
luna-send-pub -t 1 -f -w 4000 luna://com.webos.applicationManager/launch "$payload"
"""

    STOP_GUARD_PY = r"""import os, signal, sys

# Python 2/3 compatible; the TV has Python 2. Match exact owned scripts, then
# descendants captured before signalling. Never trust a stale PID file.
records = {}
for name in os.listdir('/proc'):
    if not name.isdigit():
        continue
    try:
        stat = open('/proc/' + name + '/stat').read()
        fields = stat[stat.rfind(')') + 2:].split()
        cmd = open('/proc/' + name + '/cmdline', 'rb').read().replace(b'\x00', b' ').strip()
        records[int(name)] = (int(fields[1]), fields[19], cmd)
    except (IOError, ValueError, IndexError):
        pass
protected = int(sys.argv[1]) if len(sys.argv) > 1 else 0
commands = (b'/bin/sh /var/lib/webosbrew/launcher-home/guard.sh',
            b'/bin/sh /var/lib/webosbrew/launcher-home/prewarm.sh')
roots = set(pid for pid, row in records.items() if row[2] in commands)
if protected:
    roots = set([protected]) if protected in roots else set()
owned = set(roots)
ordered = list(roots)
while True:
    more = set(pid for pid, row in records.items() if row[0] in owned) - owned
    if not more:
        break
    ordered.extend(more)
    owned.update(more)
for pid in reversed(ordered):
    if pid <= 1 or pid in (os.getpid(), protected):
        continue
    try:
        stat = open('/proc/' + str(pid) + '/stat').read()
        fields = stat[stat.rfind(')') + 2:].split()
        if fields[19] == records[pid][1]:
            os.kill(pid, signal.SIGTERM)
    except (IOError, OSError, IndexError):
        pass
"""

    GUARD_SCRIPT = r"""#!/bin/sh
# v0.4.0 guard: prewarmed Quick Start cover plus direct full-launch fallback.
DIR=/var/lib/webosbrew/launcher-home
ENABLED="$DIR/enabled"
PIDFILE=/tmp/hu.szabi.launcher-home.pid
ALLOW=/tmp/hu.szabi.launcher.allow-home
FOREGROUND=/tmp/hu.szabi.launcher.foreground
LAST_LAUNCH=/tmp/hu.szabi.launcher.last-launch
POWER_STARTUP=/tmp/hu.szabi.launcher.power-startup
WAKE_WAIT_UNTIL=/tmp/hu.szabi.launcher.wake-wait-until
WAKE_RETRY_UNTIL=/tmp/hu.szabi.launcher.wake-retry-until
POWER_STATE=/tmp/hu.szabi.launcher.power-state
WAKE_SIGNAL=/tmp/hu.szabi.launcher.wake-signal
POWER_EVENT=/tmp/hu.szabi.launcher.power-event
FOREGROUND_EVENT=/tmp/hu.szabi.launcher.foreground-event
WAKE_HEARTBEAT=/tmp/hu.szabi.launcher.wake-heartbeat
BOOT_READY=/tmp/hu.szabi.launcher.boot-ready
ACTIVE_SINCE=/tmp/hu.szabi.launcher.active-since
PREWARM_AFTER=/tmp/hu.szabi.launcher.prewarm-after
QUICK_PREWARM_AFTER=/tmp/hu.szabi.launcher.quick-prewarm-after
QUICK_PREWARM_ATTEMPT=/tmp/hu.szabi.launcher.quick-prewarm-attempt
QUICK_WAKE_ARMED=/tmp/hu.szabi.launcher.quick-wake-armed
QUICK_FAST_ATTEMPT=/tmp/hu.szabi.launcher.quick-fast-attempt
QUICK_COVER_READY=/tmp/hu.szabi.launcher.full-overlay-prewarm-ready
QUICK_COVER_QUEUE=/tmp/hu.szabi.launcher.quick-cover-prewarm-queued
EIM_BASE=/var/lib/webosbrew/launcher-eim
WAKE_VISIBLE_APP=/tmp/hu.szabi.launcher.wake-visible-app
WAKE_VISIBLE_SINCE=/tmp/hu.szabi.launcher.wake-visible-since
FULL_VISIBLE=/tmp/hu.szabi.launcher.full-visible
QUICK_VISIBLE=/tmp/hu.szabi.launcher.quick-visible
OVERLAY_VISIBLE=/tmp/hu.szabi.launcher.full-overlay-visible
FULL_CLOSE_SUPPRESS=/tmp/hu.szabi.launcher.full-close-suppress
HOME_ACTIVE=/tmp/hu.szabi.launcher.home-active
RESUME_LAST="$DIR/resume-last-app"
LAST_APP="$DIR/last-app"
POWER_OFF_APP="$DIR/power-off-app"
ACTIVE_APP="$DIR/active-app-at-power-off"
APP=hu.szabi.launcher
OVERLAY_APP=hu.szabi.launcher.overlay
QUICK_APP=hu.szabi.launcher.quick
CONTROL_ORIGIN="$DIR/control-origin"
FACTORY_HOME=com.webos.app.home
DIAGNOSTIC=/tmp/hu.szabi.launcher-wake.log

[ -f "$ENABLED" ] || exit 0
# Kernel locks cannot remain stale after a killed process or a PID reuse.
exec 9>/tmp/hu.szabi.launcher.guard-flock
flock -n 9 || exit 0
echo $$ >"$PIDFILE"
cleanup() {
  trap - EXIT INT TERM
  python -c @@STOP_HELPERS@@ "$$"
  rm -f "$PIDFILE"
  exit 0
}
trap cleanup EXIT INT TERM

json_value() {
  echo "$1" | sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p"
}

diagnostic() {
  # Bounded RAM log, only decisions/transitions; never persistent flash polling.
  size=$(wc -c "$DIAGNOSTIC" 2>/dev/null | awk '{print $1}'); size=${size:-0}
  [ "$size" -lt 32768 ] || mv -f "$DIAGNOSTIC" "$DIAGNOSTIC.1"
  printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >>"$DIAGNOSTIC"
}

fresh_power() {
  line=$(luna-send -t 1 -f -w 1500 luna://com.webos.service.tvpower/power/getPowerState '{}' 2>&1)
  json_value "$line" state
}

arm_power_startup() {
  now=$(date +%s)
  touch "$POWER_STARTUP"
  echo "$now" >"$ACTIVE_SINCE"
  echo $((now + 180)) >"$WAKE_WAIT_UNTIL"
  echo $((now + 8)) >"$PREWARM_AFTER"
  echo $((now + 4)) >"$QUICK_PREWARM_AFTER"
  rm -f "$BOOT_READY" "$WAKE_RETRY_UNTIL" "$WAKE_VISIBLE_APP" "$WAKE_VISIBLE_SINCE" "$LAST_LAUNCH" "$ALLOW"
  diagnostic 'wake armed'
}

settle_wake() {
  diagnostic "wake $1 foreground=$current"
  rm -f "$POWER_STARTUP" "$WAKE_WAIT_UNTIL" "$WAKE_RETRY_UNTIL" "$POWER_OFF_APP" "$WAKE_VISIBLE_APP" "$WAKE_VISIBLE_SINCE" "$QUICK_WAKE_ARMED" "$QUICK_FAST_ATTEMPT"
}

wake_window_open() {
  # Only the worker owns these files. Neither polling nor failed requests
  # extends a deadline; missing state fails closed after a partial restart.
  now=$(date +%s)
  if [ -f "$WAKE_RETRY_UNTIL" ]; then
    deadline=$(cat "$WAKE_RETRY_UNTIL" 2>/dev/null)
    expiry=expired
  else
    deadline=$(cat "$WAKE_WAIT_UNTIL" 2>/dev/null)
    expiry=boot-wait-expired
  fi
  deadline=${deadline:-0}
  if [ "$now" -ge "$deadline" ]; then
    settle_wake "$expiry"
    return 1
  fi
  return 0
}

snapshot_power_off_app() {
  # No new Luna RPC while the firmware suspends. The foreground subscriber
  # already recorded the last stable real app while Active.
  app=$(cat "$ACTIVE_APP" 2>/dev/null)
  case "$app" in
    ''|*[!A-Za-z0-9._-]*) rm -f "$POWER_OFF_APP";;
    *) printf '%s\n' "$app" >"$POWER_OFF_APP";;
  esac
}

quick_fast_lane_safe() {
  [ -f "$EIM_BASE/enabled" ] || return 1
  [ -f "$EIM_BASE/last-good" ] || return 1
  [ ! -e "$EIM_BASE/boot-pending" ] || return 1
  [ ! -e "$EIM_BASE/disabled-failsafe" ] || return 1
  mountpoint -q /var/lib/eim || return 1
  mountpoint -q "$EIM_BASE/frozen-view" || return 1
  return 0
}

quick_start_fast_launch() {
  [ -f "$QUICK_WAKE_ARMED" ] || return 1
  [ ! -f "$QUICK_FAST_ATTEMPT" ] || return 1
  if [ -f "$HOME_ACTIVE" ]; then
    diagnostic 'quick fast lane blocked: explicit Home interaction active'
    return 1
  fi
  if ! quick_fast_lane_safe; then
    diagnostic 'quick fast lane blocked: EIM overlay not healthy'
    return 1
  fi
  # QUICK_WAKE_ARMED is created only by a real native standby state. A fresh
  # power RPC immediately before dispatch is therefore sufficient here; the
  # slower conservative path still handles every rejected/late launch.
  if [ "$(fresh_power)" != Active ]; then
    diagnostic 'quick fast lane blocked: power not Active'
    return 1
  fi
  touch "$QUICK_FAST_ATTEMPT"
  now=$(date +%s)
  echo "$now" >"$LAST_LAUNCH"
  origin=$(cat "$CONTROL_ORIGIN" 2>/dev/null)
  display=$(cat "$DIR/display-preferences.json" 2>/dev/null); [ -n "$display" ] || display='{}'

  if [ -f "$QUICK_COVER_READY" ]; then
    running=$(luna-send -t 1 -f -w 900 luna://com.webos.service.webappmanager/listRunningApps '{"includeSysApps":false}' 2>&1)
    if echo "$running" | grep -Eq '"id"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher[.]overlay"'; then
      cover_payload=$(printf '{"id":"%s","noSplash":true,"params":{"source":"quick-start-cover","launcherHost":"full-overlay","controlOrigin":"%s","displayPreferences":%s}}' "$OVERLAY_APP" "$origin" "$display")
      diagnostic 'quick cover dispatch'
      cover_result=$(luna-send-pub -w 1200 -t 1 -f luna://com.webos.applicationManager/launch "$cover_payload" 2>&1)
      if echo "$cover_result" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
        diagnostic 'quick cover accepted'
      else
        rm -f "$QUICK_COVER_READY"
        diagnostic 'quick cover failed; continuing with full launcher'
      fi
    else
      rm -f "$QUICK_COVER_READY"
      diagnostic 'quick cover stale; full launcher only'
    fi
  fi

  payload=$(printf '{"id":"%s","noSplash":true,"params":{"source":"quick-start-fast-lane","controlOrigin":"%s","displayPreferences":%s}}' "$APP" "$origin" "$display")
  diagnostic 'quick fast lane dispatch'
  result=$(luna-send-pub -w 2500 -t 1 -f luna://com.webos.applicationManager/launch "$payload" 2>&1)
  date +%s >"$LAST_LAUNCH"
  if echo "$result" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
    diagnostic 'quick fast lane accepted'
    return 0
  fi
  diagnostic 'quick fast lane failed; fallback remains armed'
  return 1
}

handle_power_state() {
  state=$1
  previous=$(cat "$POWER_STATE" 2>/dev/null)
  [ "$state" = "$previous" ] && return 0
  printf '%s\n' "$state" >"$POWER_STATE"
  diagnostic "power ${previous:-unknown} -> ${state:-unknown}"
  case "$state" in
    Active)
      # Screensaver dismissal is a user action, not a fresh TV power-on.
      if [ "$previous" != 'Screen Saver' ]; then
        arm_power_startup
        if [ -f "$QUICK_WAKE_ARMED" ]; then
          quick_start_fast_launch || true
          rm -f "$QUICK_WAKE_ARMED"
        fi
      fi
      ;;
    'Screen Saver')
      rm -f "$POWER_STARTUP" "$WAKE_WAIT_UNTIL" "$WAKE_RETRY_UNTIL" "$QUICK_WAKE_ARMED" "$QUICK_FAST_ATTEMPT"
      ;;
    'Active Standby'|Suspend|'Screen Off')
      [ "$previous" = Active ] && snapshot_power_off_app
      touch "$QUICK_WAKE_ARMED"
      rm -f "$QUICK_FAST_ATTEMPT" "$BOOT_READY" "$POWER_STARTUP" "$WAKE_WAIT_UNTIL" "$WAKE_RETRY_UNTIL"
      ;;
    *)
      [ "$previous" = Active ] && snapshot_power_off_app
      rm -f "$BOOT_READY" "$POWER_STARTUP" "$WAKE_WAIT_UNTIL" "$WAKE_RETRY_UNTIL"
      ;;
  esac
}

automatic_ready() {
  [ -f "$ENABLED" ] || return 1
  [ "$(cat "$POWER_STATE" 2>/dev/null)" = Active ] || return 1
  [ ! -f "$WAKE_SIGNAL" ] || return 1
  if [ ! -f "$BOOT_READY" ]; then
    since=$(cat "$ACTIVE_SINCE" 2>/dev/null); since=${since:-0}
    [ $(( $(date +%s) - since )) -ge 1 ] || return 1
    boot=$(luna-send -t 1 -f -w 1500 luna://com.webos.bootManager/getBootStatus '{}' 2>&1)
    # These fields were verified on this TV. Fail closed if unavailable;
    # explicit remote-control Home still works independently of this guard.
    echo "$boot" | grep -Eq '"powerStatus"[[:space:]]*:[[:space:]]*"active"' || return 1
    # boot-done also waits for unrelated background services (observed 13-20s
    # after the TV already shows its first app). The initial app and minimal
    # boot ready flags suffice when the native foreground surface is visible.
    if ! echo "$boot" | grep -Eq '"boot-done"[[:space:]]*:[[:space:]]*true'; then
      echo "$boot" | grep -Eq '"minimal-boot-done"[[:space:]]*:[[:space:]]*true' || return 1
      echo "$boot" | grep -Eq '"firstAppLaunched"[[:space:]]*:[[:space:]]*true' || return 1
    fi
    touch "$BOOT_READY"
    diagnostic 'boot manager ready'
  fi
  return 0
}

foreground_app() {
  # Always ask Luna first; a frozen subscription is never proof of visibility.
  line=$(luna-send -t 1 -f -w 1500 luna://com.webos.applicationManager/getForegroundAppInfo '{}' 2>&1)
  json_value "$line" appId
}

own_popup_visible() {
  line=$(luna-send -t 1 -f -w 1500 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>&1)
  echo "$line" | grep -Eq '"appId"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher[.](quick|overlay)"'
}

foreground_surface_visible() {
  # Reuse only this attempt's compositor reply from own_popup_visible.
  # Do not launch over an as-yet invisible firmware app during resume.
  surface_pattern=$(printf '%s' "$current" | sed 's/\./[.]/g')
  echo "$foreground_window" | grep -Eq '"appId"[[:space:]]*:[[:space:]]*"'"$surface_pattern"'"'
}

foreground_decision() {
  current=$(foreground_app)
  case "$current" in
    "$FACTORY_HOME"|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*) return 0;;
    ''|com.webos.app.notification*|com.webos.app.volume*|com.webos.app.power*|com.webos.app.quicksettings*) return 2;;
    *) return 1;;
  esac
}

record_foreground() {
  [ -n "$current" ] || return 0
  old_app=$(cat "$FOREGROUND" 2>/dev/null)
  printf '%s\n' "$current" >"$FOREGROUND"
  [ "$current" != "$old_app" ] || return 0
  # A new Home visit after an actually observed app is not a duplicate of an
  # earlier launch. Keep the longer cooldown only inside the wake attempt.
  if [ "$current" = "$FACTORY_HOME" ] && [ -n "$old_app" ] && [ ! -f "$POWER_STARTUP" ]; then
    rm -f "$LAST_LAUNCH"
  fi
  case "$current" in
    "$APP"|"$OVERLAY_APP"|"$QUICK_APP"|"$FACTORY_HOME"|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*)
      rm -f "$ACTIVE_APP"
      [ "$current" != "$APP" ] || rm -f /tmp/hu.szabi.launcher.prewarm-attempt
      ;;
    com.webos.app.notification*|com.webos.app.volume*|com.webos.app.power*|com.webos.app.quicksettings*) ;;
    *[!A-Za-z0-9._-]*) ;;
    *) printf '%s\n' "$current" >"$LAST_APP"; printf '%s\n' "$current" >"$ACTIVE_APP";;
  esac
}

launch_id() {
  target=$1
  source=$2
  automatic_ready || return 1
  [ ! -f "$HOME_ACTIVE" ] || return 1
  now=$(date +%s)
  last=$(cat "$LAST_LAUNCH" 2>/dev/null); last=${last:-0}
  # Accepted and failed requests both cool down; never flood SAM with retries.
  cooldown=5
  [ ! -f "$POWER_STARTUP" ] || cooldown=8
  [ $((now - last)) -ge "$cooldown" ] || return 1
  # A power-off notification arriving during a foreground/boot RPC invalidates
  # the decision. Also ask tvpower immediately before the only dispatch site.
  [ "$(fresh_power)" = Active ] || return 1
  [ ! -f "$WAKE_SIGNAL" ] || return 1
  [ -f "$ENABLED" ] || return 1
  # A slow readiness/power RPC must not dispatch after the bounded window.
  if [ -f "$POWER_STARTUP" ]; then wake_window_open || return 1; fi
  echo "$now" >"$LAST_LAUNCH"
  origin=$(cat "$CONTROL_ORIGIN" 2>/dev/null)
  display=$(cat "$DIR/display-preferences.json" 2>/dev/null); [ -n "$display" ] || display='{}'
  payload=$(printf '{"id":"%s","noSplash":true,"params":{"source":"%s","controlOrigin":"%s","displayPreferences":%s}}' "$target" "$source" "$origin" "$display")
  result=$(luna-send-pub -w 4000 -t 1 -f luna://com.webos.applicationManager/launch "$payload" 2>&1)
  # Count from the response, so a slow launch acknowledgement cannot consume
  # its own cooldown and trigger an immediate duplicate request.
  date +%s >"$LAST_LAUNCH"
  if echo "$result" | grep -Eq '"returnValue"[[:space:]]*:[[:space:]]*true'; then
    diagnostic "launch accepted target=$target source=$source"
    return 0
  fi
  diagnostic "launch failed target=$target source=$source"
  return 1
}

launch_custom() {
  automatic_ready || return 1
  [ ! -f "$HOME_ACTIVE" ] || return 1
  if [ "$1" != foreground-checked ]; then
    own_popup_visible && return 1
    foreground_decision
    [ "$?" -eq 0 ] || return 1
  fi
  if [ "$current" = "$FACTORY_HOME" ]; then
    rm -f "$ALLOW" "$FULL_CLOSE_SUPPRESS"
  else
    [ ! -f "$ALLOW" ] || return 1
    suppress=$(cat "$FULL_CLOSE_SUPPRESS" 2>/dev/null); suppress=${suppress:-0}
    [ "$(date +%s)" -ge "$suppress" ] || return 1
  fi
  full_target=$APP
  [ "$(cat "$DIR/full-presentation" 2>/dev/null)" != overlay ] || full_target=$OVERLAY_APP
  launch_id "$full_target" default-home-guard
}

launch_last_or_custom() {
  if [ -f "$RESUME_LAST" ]; then
    last_app=$(cat "$POWER_OFF_APP" 2>/dev/null)
    case "$last_app" in
      ''|*[!A-Za-z0-9._-]*|hu.szabi.launcher*|"$FACTORY_HOME"|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*) ;;
      *)
        # Preserve the saved target until visible, but allow a failed/unavailable
        # last app to fall back after ten seconds of this wake attempt.
        retry_until=$(cat "$WAKE_RETRY_UNTIL" 2>/dev/null); retry_until=${retry_until:-40}
        since=$((retry_until - 40))
        if [ $(( $(date +%s) - since )) -lt 10 ]; then
          launch_id "$last_app" power-resume
          return $?
        fi
        ;;
    esac
  fi
  launch_custom foreground-checked
}

retry_power_startup() {
  [ -f "$POWER_STARTUP" ] || return 0
  wake_window_open || return 1
  [ -f "$ENABLED" ] || return 1
  [ "$(cat "$POWER_STATE" 2>/dev/null)" = Active ] || return 1
  [ ! -f "$WAKE_SIGNAL" ] || return 1
  since=$(cat "$ACTIVE_SINCE" 2>/dev/null); since=${since:-0}
  [ $((now - since)) -ge 1 ] || return 1
  [ ! -f "$HOME_ACTIVE" ] || return 1
  boot_ready=0
  automatic_ready && boot_ready=1
  # Never interrupt an already running app or a natively visible popup.
  # Observe these even before boot readiness: a user app seen during a slow
  # boot permanently ends this wake attempt, including a later HDMI switch.
  if own_popup_visible; then
    current=native-popup
    settle_wake popup-preserved
    return 0
  fi
  foreground_window=$line
  foreground_decision
  decision=$?
  record_foreground
  if [ "$decision" -eq 1 ]; then
    if [ "$current" != "$APP" ]; then
      settle_wake real-app-preserved
      return 0
    fi
    # An accepted launch may lose foreground to the firmware's restored input.
    # Require two seconds of actual visibility and at least six since Active.
    if ! foreground_surface_visible; then
      rm -f "$WAKE_VISIBLE_APP" "$WAKE_VISIBLE_SINCE"
      return 1
    fi
    now=$(date +%s)
    visible_app=$(cat "$WAKE_VISIBLE_APP" 2>/dev/null)
    if [ "$visible_app" != "$current" ]; then
      echo "$current" >"$WAKE_VISIBLE_APP"
      echo "$now" >"$WAKE_VISIBLE_SINCE"
    fi
    visible_since=$(cat "$WAKE_VISIBLE_SINCE")
    since=$(cat "$ACTIVE_SINCE")
    if [ $((now - visible_since)) -ge 2 ] && [ $((now - since)) -ge 6 ]; then
      settle_wake visible
    fi
    return 0
  fi
  rm -f "$WAKE_VISIBLE_APP" "$WAKE_VISIBLE_SINCE"
  [ "$decision" -eq 0 ] || return 1
  [ "$boot_ready" -eq 1 ] || return 1
  foreground_surface_visible || return 1
  # Boot and compositor RPCs may have crossed the wait/attempt deadline.
  wake_window_open || return 1
  if [ ! -f "$WAKE_RETRY_UNTIL" ]; then
    echo $((now + 40)) >"$WAKE_RETRY_UNTIL"
    rm -f "$WAKE_WAIT_UNTIL"
    diagnostic 'wake launch window ready'
  fi
  # HDMI/Live TV are eligible only inside this bounded wake window.
  launch_last_or_custom
}

replace_visible_factory_home() {
  automatic_ready || return 1
  [ ! -f "$HOME_ACTIVE" ] || return 1
  current=$(foreground_app)
  record_foreground
  [ "$current" = "$FACTORY_HOME" ] || return 0
  own_popup_visible && return 0
  # In an already settled session SAM reports Home before its surface arrives.
  # Dispatch now: waiting for that surface makes the LG animation visible.
  # The stronger native-surface gate remains in the power-on path above.
  launch_custom foreground-checked
}

queue_prewarm() {
  [ ! -f "$POWER_STARTUP" ] || return 0
  automatic_ready || return 0
  [ ! -f "$WAKE_SIGNAL" ] || return 0
  [ "$(cat "$POWER_STATE" 2>/dev/null)" = Active ] || return 0
  [ ! -f "$HOME_ACTIVE" ] || return 0
  epoch=$(cat "$ACTIVE_SINCE" 2>/dev/null)
  if [ -n "$epoch" ] && [ ! -f "$QUICK_COVER_READY" ]; then
    if [ "$(cat "$QUICK_COVER_QUEUE" 2>/dev/null)" = "$epoch" ]; then
      # The cover preload is still pending (or failed). Do not start another
      # renderer in parallel during this active epoch.
      return 0
    fi
    if [ -x "$DIR/prewarm.sh" ]; then
      echo "$epoch" >"$QUICK_COVER_QUEUE"
      "$DIR/prewarm.sh" cover </dev/null >>/tmp/hu.szabi.launcher-prewarm.log 2>&1 9>&-
      return 0
    fi
  fi
  quick_after=$(cat "$QUICK_PREWARM_AFTER" 2>/dev/null); quick_after=${quick_after:-0}
  if [ -n "$epoch" ] && [ "$(cat "$DIR/home-mode" 2>/dev/null)" != full ] &&
     [ "$(cat "$QUICK_PREWARM_ATTEMPT" 2>/dev/null)" != "$epoch" ] &&
     [ "$(date +%s)" -ge "$quick_after" ] && [ -x "$DIR/prewarm.sh" ]; then
    "$DIR/prewarm.sh" quick </dev/null >>/tmp/hu.szabi.launcher-prewarm.log 2>&1 9>&-
    return 0
  fi
  after=$(cat "$PREWARM_AFTER" 2>/dev/null); after=${after:-0}
  [ "$(date +%s)" -ge "$after" ] || return 0
  case "$current" in
    ''|hu.szabi.launcher*|com.webos.app.home|com.webos.app.livetv|com.webos.app.hdmi*|com.webos.app.externalinput*|com.webos.app.notification*|com.webos.app.volume*|com.webos.app.power*|com.webos.app.quicksettings*) return 0;;
  esac
  attempt_key=$current
  [ "$(cat "$DIR/full-presentation" 2>/dev/null)" != overlay ] || attempt_key="overlay:$epoch"
  [ "$(cat /tmp/hu.szabi.launcher.prewarm-attempt 2>/dev/null)" != "$attempt_key" ] || return 0
  [ -x "$DIR/prewarm.sh" ] || return 0
  "$DIR/prewarm.sh" </dev/null >>/tmp/hu.szabi.launcher-prewarm.log 2>&1 9>&-
}

foreground_loop() {
  while [ -f "$ENABLED" ]; do
    luna-send -i luna://com.webos.applicationManager/getForegroundAppInfo '{"subscribe":true}' 2>/dev/null |
    while IFS= read -r line; do
      app=$(json_value "$line" appId)
      [ -n "$app" ] || continue
      # The event wakes the sole worker; its cached app never authorizes launch.
      printf '%s\n' "$app" >"$FOREGROUND_EVENT.new"
      mv -f "$FOREGROUND_EVENT.new" "$FOREGROUND_EVENT"
    done
    sleep 2
  done
}

power_loop() {
  while [ -f "$ENABLED" ]; do
    luna-send -i luna://com.webos.service.tvpower/power/getPowerState '{"subscribe":true}' 2>/dev/null |
    while IFS= read -r line; do
      state=$(json_value "$line" state)
      [ -n "$state" ] || continue
      # Never wait on another Luna call here: Suspend must invalidate a launch
      # even while the single worker is blocked in a foreground/boot query.
      case "$state" in Active|'Screen Saver') ;; *) touch "$WAKE_SIGNAL";; esac
      printf '%s\n' "$state" >"$POWER_EVENT.new"
      mv -f "$POWER_EVENT.new" "$POWER_EVENT"
    done
    sleep 2
  done
}

wake_gap_loop() {
  while [ -f "$ENABLED" ]; do
    before=$(date +%s)
    sleep 1
    after=$(date +%s)
    # This loop does no RPC/work between its timestamps. A slow SAM answer
    # therefore cannot be mistaken for another suspend/resume cycle.
    if [ $((after - before)) -ge 7 ]; then
      touch "$WAKE_SIGNAL"
      echo "$after" >"$WAKE_HEARTBEAT"
    fi
  done
}

control_tick() {
  # Called exclusively by the main worker. No other loop launches or preloads.
  # During normal viewing, a Home event can skip the periodic power query;
  # the actual dispatch still rechecks power immediately before launching.
  if [ "$1" = foreground-event ] && [ -f "$BOOT_READY" ] &&
     [ "$(cat "$POWER_STATE" 2>/dev/null)" = Active ] &&
     [ ! -f "$POWER_STARTUP" ] && [ ! -f "$WAKE_SIGNAL" ] &&
     [ ! -f "$POWER_EVENT" ]; then
    replace_visible_factory_home
    return
  fi
  if [ -f "$WAKE_SIGNAL" ]; then
    rm -f "$WAKE_SIGNAL"
    snapshot_power_off_app
    handle_power_state unknown
  fi
  state=$(fresh_power)
  handle_power_state "$state"
  [ "$state" = Active ] || return 0
  if [ -f "$POWER_STARTUP" ]; then
    retry_power_startup
  else
    replace_visible_factory_home
    queue_prewarm
  fi
}

run_pending_tick() {
  now_tick=$(date +%s)
  if [ -f "$POWER_EVENT" ] || [ -f "$FOREGROUND_EVENT" ] ||
     [ -f "$WAKE_SIGNAL" ] || [ "$now_tick" -ge "$next_poll" ]; then
    tick_reason=poll
    [ ! -f "$FOREGROUND_EVENT" ] || tick_reason=foreground-event
    # Consume before the RPCs: an event delivered while they run must remain
    # pending for the next iteration. Cached event contents never allow launch.
    rm -f "$FOREGROUND_EVENT"
    # Move atomically so the exact event consumed determines the reason, even
    # if the subscriber publishes between the predicate and this handoff.
    if mv -f "$POWER_EVENT" "$POWER_EVENT.processing" 2>/dev/null; then
      tick_reason=power-event
      rm -f "$POWER_EVENT.processing"
    fi
    control_tick "$tick_reason"
    # Delay is measured after work. RPC latency never creates a retry burst.
    delay=2; [ ! -f "$POWER_STARTUP" ] || delay=1
    next_poll=$(( $(date +%s) + delay ))
  fi
}

# START WORKER (test fixtures source only the functions above).
rm -f "$ALLOW" "$POWER_STATE" "$POWER_EVENT" "$FOREGROUND_EVENT" "$BOOT_READY" "$LAST_LAUNCH" "$WAKE_SIGNAL" "$QUICK_WAKE_ARMED" "$QUICK_FAST_ATTEMPT"
foreground_loop 9>&- &
power_loop 9>&- &
wake_gap_loop 9>&- &
diagnostic 'guard v0.4.0 started'
next_poll=0
while [ -f "$ENABLED" ]; do
  run_pending_tick
  /bin/usleep 250000
done
""".replace("@@STOP_HELPERS@@", shlex.quote(STOP_GUARD_PY))

    def __init__(self, config: dict[str, Any], runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.tv_host = str(config["tv_host"])
        self.tv_user = str(config.get("tv_user", "root"))
        self.ssh_key = str(config["ssh_key"])
        self.known_hosts = str(config["known_hosts"])
        self.timeout = canonical_integer(config.get("ssh_timeout_seconds", 12), 2, 30, "ssh_timeout_seconds")
        self.runner = runner
        self.control_origin = str(config.get("control_origin", "http://192.168.0.223:8765"))
        self.lock = threading.Lock()

    def _run(self, remote_command: str) -> str:
        command = [
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-i", self.ssh_key, f"{self.tv_user}@{self.tv_host}", remote_command,
        ]
        completed = self.runner(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "SSH hiba").strip().splitlines()[-1]
            raise RuntimeError("A launcher kezdőképernyő-őr nem érhető el: " + detail[:300])
        return (completed.stdout or "") + (completed.stderr or "")

    def _run_lifecycle(self, remote_command: str) -> str:
        """Run Luna lifecycle commands with a remote PTY.

        On this TV luna-send can acknowledge no request at all when ssh inherits
        /dev/null from systemd.  File/status operations do not need a TTY, but
        closeByAppId must use the same forced-PTY transport as app launching.
        """
        command = [
            "ssh", "-tt", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-i", self.ssh_key, f"{self.tv_user}@{self.tv_host}", remote_command,
        ]
        completed = self.runner(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "SSH hiba").strip().splitlines()[-1]
            raise RuntimeError("A launcher életciklus-parancsa sikertelen: " + detail[:300])
        return (completed.stdout or "") + (completed.stderr or "")

    @staticmethod
    def _encoded(content: str) -> str:
        return base64.b64encode(content.encode("utf-8")).decode("ascii")

    def _write_remote_file(self, target: str, content: str) -> None:
        """Upload a guard file without exceeding the TV's small SSH command buffer."""
        encoded = self._encoded(content)
        temporary_encoded = target + ".new.b64"
        temporary_target = target + ".new"
        self._run(
            "mkdir -p " + shlex.quote(LAUNCHER_HOME_DIR)
            + "; rm -f " + shlex.quote(temporary_encoded) + " " + shlex.quote(temporary_target)
        )
        for offset in range(0, len(encoded), 2048):
            chunk = encoded[offset:offset + 2048]
            self._run("printf %s " + shlex.quote(chunk) + " >> " + shlex.quote(temporary_encoded))
        self._run(
            "set -e; base64 -d " + shlex.quote(temporary_encoded) + " > " + shlex.quote(temporary_target)
            + "; chmod 755 " + shlex.quote(temporary_target)
            + "; sh -n " + shlex.quote(temporary_target)
            + "; mv -f " + shlex.quote(temporary_target) + " " + shlex.quote(target)
            + "; rm -f " + shlex.quote(temporary_encoded)
        )

    def _sync_files_locked(self) -> None:
        self._run("mkdir -p " + shlex.quote(LAUNCHER_HOME_DIR) + "; printf %s " + shlex.quote(self.control_origin) + " > " + shlex.quote(LAUNCHER_HOME_ORIGIN))
        self._write_remote_file(LAUNCHER_HOME_GUARD, self.GUARD_SCRIPT)
        self._write_remote_file(LAUNCHER_HOME_KEY, self.HOME_KEY_SCRIPT)
        self._write_remote_file(LAUNCHER_HOME_DIR + "/prewarm.sh", self.PREWARM_SCRIPT)
        self._write_remote_file(LAUNCHER_HOME_INIT, self.INIT_SCRIPT)

    def sync_files(self) -> None:
        """Refresh owned TV files without starting or restarting the launcher."""
        with self.lock:
            self._sync_files_locked()

    @staticmethod
    def _stop_guard_command() -> str:
        return "python -c " + shlex.quote(LauncherHomeManager.STOP_GUARD_PY) + "; rm -f " + shlex.quote(LAUNCHER_HOME_PID)

    def set_display_preferences(self, settings: dict[str, Any]) -> None:
        preferences = {key: settings.get(key) is not False for key in ("animationsEnabled", "visualEffectsEnabled")}
        path = LAUNCHER_HOME_DIR + "/display-preferences.json"
        with self.lock:
            self._run("mkdir -p " + shlex.quote(LAUNCHER_HOME_DIR) + "; printf %s "
                      + shlex.quote(json.dumps(preferences, separators=(",", ":")))
                      + " > " + shlex.quote(path + ".new") + "; mv " + shlex.quote(path + ".new") + " " + shlex.quote(path))

    def set_full_presentation(self, presentation: str) -> None:
        if not isinstance(presentation, str) or presentation not in {"app", "overlay"}:
            raise ValueError("invalid full launcher presentation")
        with self.lock:
            self._run("mkdir -p " + shlex.quote(LAUNCHER_HOME_DIR) + "; printf %s "
                      + shlex.quote(presentation) + " > " + shlex.quote(LAUNCHER_HOME_DIR + "/full-presentation"))

    def set_home_launch_mode(self, mode: str) -> None:
        if mode not in {"split", "full", "overlay"}:
            raise ValueError("invalid launcher Home mode")
        with self.lock:
            self._run(
                "mkdir -p " + shlex.quote(LAUNCHER_HOME_DIR) + "; printf '%s\\n' "
                + shlex.quote(mode) + " > " + shlex.quote(LAUNCHER_HOME_MODE)
            )

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        with self.lock:
            if enabled:
                self._sync_files_locked()
                self._run("touch " + shlex.quote(LAUNCHER_HOME_ENABLED) + "; " + shlex.quote(LAUNCHER_HOME_INIT))
            else:
                command = (
                    "rm -f " + shlex.quote(LAUNCHER_HOME_ENABLED) + " " + shlex.quote(LAUNCHER_HOME_INIT) + " "
                    + shlex.quote(LAUNCHER_HOME_ALLOW)
                    + "; rmdir /tmp/hu.szabi.launcher-home-key.lock 2>/dev/null || true"
                    + "; " + self._stop_guard_command()
                )
                self._run(command)
            return self.status()

    def status(self) -> dict[str, Any]:
        output = self._run(
            "if [ -f " + shlex.quote(LAUNCHER_HOME_ENABLED) + " ]; then printf 'enabled=1\\n'; else printf 'enabled=0\\n'; fi; "
            "if [ -r " + shlex.quote(LAUNCHER_HOME_PID) + " ] && kill -0 $(cat " + shlex.quote(LAUNCHER_HOME_PID)
            + ") 2>/dev/null; then printf 'running=1\\n'; else printf 'running=0\\n'; fi"
        )
        return {"enabled": "enabled=1" in output, "running": "running=1" in output}

    def last_app(self) -> str:
        """Read the last non-launcher foreground app recorded by the TV guard."""
        output = self._run("cat " + shlex.quote(LAUNCHER_HOME_DIR + "/last-app") + " 2>/dev/null || true")
        candidate = output.strip().splitlines()[-1] if output.strip() else ""
        return candidate if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", candidate) else ""

    def allow_factory_home(self) -> None:
        self._run("touch " + shlex.quote(LAUNCHER_HOME_ALLOW))

    def revoke_factory_home(self) -> None:
        self._run("rm -f " + shlex.quote(LAUNCHER_HOME_ALLOW))

    @staticmethod
    def _verified_close_command(host: str = "full") -> str:
        application = LAUNCHER_HOSTS[host]["appId"]
        app_id = shlex.quote(json.dumps({"id": application}))
        running = (
            "line=$(luna-send -n 1 -w 1500 luna://com.webos.service.webappmanager/listRunningApps "
            + shlex.quote('{"includeSysApps":false}')
            + " 2>&1 || true); echo \"$line\" | grep -Eq '"
            + '"id"[[:space:]]*:[[:space:]]*"' + application.replace(".", "[.]") + '"'
            + "'"
        )
        return (
            # The TV may acknowledge a close while the popup process survives,
            # and listRunningApps output is not reliable enough over service SSH
            # to gate the close.  Repeated closes are idempotent and guarantee
            # that the still-alive WAM instance receives a later request.
            "close_attempt=0; while [ \"$close_attempt\" -lt 3 ]; do "
            "luna-send -n 1 -w 1500 -f luna://com.webos.service.applicationmanager/closeByAppId "
            + app_id + " >/dev/null 2>&1 || true; "
            "close_attempt=$((close_attempt + 1)); /bin/usleep 400000; done; "
            + running + " && exit 1; exit 0"
        )

    @staticmethod
    def host_from_request(raw: Any) -> str:
        if raw == {}:  # Legacy full-launcher clients and the browser admin.
            return "full"
        if not isinstance(raw, dict) or set(raw) != {"host", "mode"}:
            raise RequestError("Érvénytelen launcher host.")
        host = raw.get("host")
        if not isinstance(host, str) or host not in LAUNCHER_HOSTS or raw["mode"] != LAUNCHER_HOSTS[host]["mode"]:
            raise RequestError("Érvénytelen launcher host/mód.")
        return host

    def park_launcher(self, host: str = "full") -> dict[str, Any]:
        with self.lock:
            marker = "/tmp/hu.szabi.launcher." + host + "-visible"
            suppress = "/tmp/hu.szabi.launcher." + host + "-close-suppress"
            prefix = ("touch " + shlex.quote(LAUNCHER_HOME_ALLOW)
                      + "; rm -f " + shlex.quote(marker)
                      + "; now=$(date +%s); echo $((now + 3)) > " + shlex.quote(suppress) + "; ")
            if host != "full":
                self._run_lifecycle(prefix + self._verified_close_command(host))
            else:
                # Background a normal card, never close it on Back. The guard's
                # last stable real app is independent of the Continue tile.
                target = self.last_app()
                if not target or target in {LAUNCHER_APP_ID, LAUNCHER_QUICK_APP_ID, LAUNCHER_OVERLAY_APP_ID, "com.webos.app.home"}:
                    raise RequestError("Nincs korábbi alkalmazás, ahová vissza lehet térni.")
                payload = shlex.quote(json.dumps({"id": target, "params": {}}))
                # A frozen/hidden card may deliver a delayed Back request on
                # wake. Only the currently visible full card may return to an
                # app; ignore stale requests before changing guard markers.
                check = (
                    "window=$(luna-send -n 1 -w 1500 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>/dev/null); "
                    "if ! echo \"$window\" | grep -Eq "
                    + shlex.quote(r'"appId"[[:space:]]*:[[:space:]]*"hu[.]szabi[.]launcher"')
                    + "; then printf '%s\\n' '{\"returnValue\":true,\"ignored\":true}'; else "
                )
                output = self._run_lifecycle(check + prefix + "luna-send-pub -n 1 -w 4000 "
                    + LAUNCH_URI + " " + payload + "; fi")
                if not re.search(r'"returnValue"\s*:\s*true', output):
                    raise RuntimeError("A launcher nem helyezhető háttérbe.")
                if re.search(r'"ignored"\s*:\s*true', output):
                    print("Ignored background full launcher park", flush=True)
                    return {"returnValue": True, "ignored": True}
        return {"returnValue": True}

    def terminate_launcher(self, host: str = "full") -> dict[str, Any]:
        with self.lock:
            self._run_lifecycle(
                "rm -f /tmp/hu.szabi.launcher." + host + "-visible; "
                "now=$(date +%s); echo $((now + 15)) > /tmp/hu.szabi.launcher." + host + "-close-suppress; "
                + self._verified_close_command(host)
            )
        return {"returnValue": True}

    def launcher_running(self, host: str = "full") -> bool:
        pattern = LAUNCHER_HOSTS[host]["appId"].replace(".", "[.]")
        output = self._run(
            "line=$(luna-send -n 1 -w 1500 luna://com.webos.service.webappmanager/listRunningApps "
            + shlex.quote('{"includeSysApps":false}')
            + " 2>/dev/null || true); if echo \"$line\" | grep -Eq "
            + shlex.quote('"id"[[:space:]]*:[[:space:]]*"' + pattern + '"')
            + "; then printf 'running=1\\n'; else printf 'running=0\\n'; fi")
        return "running=1" in output

    def wait_launcher_state(self, running: bool, timeout_seconds: float = 6.0, host: str = "full") -> bool:
        deadline = time.monotonic() + max(0.2, timeout_seconds)
        while time.monotonic() < deadline:
            if self.launcher_running(host) is running:
                return True
            time.sleep(0.2)
        return self.launcher_running(host) is running

    def mark_launcher_hidden(self, host: str) -> None:
        if host not in {"quick", "full-overlay"}:
            raise RequestError("Csak az overlay launcher rejthető el natívan.")
        self._run("rm -f /tmp/hu.szabi.launcher." + host + "-visible")

    def mark_launcher_visible(self, host: str = "full") -> None:
        suppress = "/tmp/hu.szabi.launcher." + host + "-close-suppress"
        self._run(
            "now=$(date +%s); suppress_until=$(cat " + suppress + " 2>/dev/null); "
            "case \"$suppress_until\" in ''|*[!0-9]*) suppress_until=0;; esac; "
            "if [ \"$now\" -lt \"$suppress_until\" ]; then exit 0; fi; "
            "rm -f " + suppress + "; touch /tmp/hu.szabi.launcher." + host + "-visible")

    def mark_launcher_prewarm_ready(self, host: str = "full") -> None:
        self._run("touch /tmp/hu.szabi.launcher." + host + "-prewarm-ready")

    def set_resume_last_app(self, enabled: bool) -> None:
        marker = LAUNCHER_HOME_DIR + "/resume-last-app"
        command = "mkdir -p " + shlex.quote(LAUNCHER_HOME_DIR) + "; "
        command += ("touch " if enabled else "rm -f ") + shlex.quote(marker)
        self._run(command)


class InputHookWatchdogManager:
    """Install a tiny, reversible keepalive for the Homebrew Input Hook service."""

    INIT_SCRIPT = """#!/bin/sh
DIR=/var/lib/webosbrew/inputhook-watchdog
[ -f "$DIR/enabled" ] || exit 0
"$DIR/watchdog.sh" >>/tmp/hu.szabi.inputhook-watchdog.log 2>&1 &
exit 0
"""

    REPAIR_SCRIPT = r"""#!/bin/sh
# Reattach the already installed Input Hook to a replaced lginput2 process only.
# Never inject into micomservice, restart an LG process, or inject twice.
ROOT=/var/lib/webosbrew/inputhook-watchdog
ASSETS=/media/developer/apps/usr/palm/services/org.webosbrew.inputhook.service/inputhook
LOCK=/tmp/hu.szabi.inputhook-repair.lock
ATTEMPT=/tmp/hu.szabi.inputhook-repair-attempt
RELOADED=/tmp/hu.szabi.inputhook-reloaded
[ -f "$ROOT/enabled" ] || exit 0
[ -f /var/lib/webosbrew/launcher-home/enabled ] || exit 0
[ -f /tmp/hu.szabi.launcher.boot-ready ] || exit 0
[ ! -f /tmp/hu.szabi.launcher.power-startup ] || exit 0
[ ! -f /tmp/hu.szabi.launcher.wake-signal ] || exit 0
[ "$(cat /tmp/hu.szabi.launcher.power-state 2>/dev/null)" = Active ] || exit 0
exec 8>"$LOCK"
flock -n 8 || exit 0
pid=$(pidof lginput2)
case "$pid" in ''|*[!0-9]*) exit 0;; esac
[ "$(cat /proc/$pid/comm 2>/dev/null)" = lginput2 ] || exit 0
start=$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)
[ -n "$start" ] || exit 0
identity="$pid:$start"
epoch=$(cat /tmp/hu.szabi.launcher.active-since 2>/dev/null)
case "$epoch" in ''|*[!0-9]*) exit 0;; esac
reload_identity="$identity:$epoch"
reload_bindings() {
  [ "$(cat "$RELOADED" 2>/dev/null)" != "$reload_identity" ] || return 0
  # Quick Start retains native code but its PHP key map can be stale. Reload
  # once per Active epoch, without attaching another hook or starting a service.
  touch /home/root/.config/lginputhook/keybinds.json || return 1
  echo "$reload_identity" >"$RELOADED"
  printf '%s keybind reload pid=%s wake=%s\n' "$(date -Iseconds)" "$pid" "$epoch"
}
if grep -q 'libphp' /proc/$pid/maps; then
  [ "$(cat "$RELOADED" 2>/dev/null)" != "$reload_identity" ] || exit 0
else
  [ "$(cat "$ATTEMPT" 2>/dev/null)" != "$identity" ] || exit 0
fi
lib="$ASSETS/libcrypt1/libphp.so"
[ ! -f /usr/lib/libcrypt.so.2 ] || lib="$ASSETS/libcrypt2/libphp.so"
[ -x "$ASSETS/ezinject" ] && [ -r "$lib" ] && [ -r "$ASSETS/lginput-hook.php" ] || exit 0
power=$(luna-send -n 1 -w 1500 luna://com.webos.service.tvpower/power/getPowerState '{}' 2>/dev/null)
echo "$power" | grep -Eq '"state"[[:space:]]*:[[:space:]]*"Active"' || exit 0
# Firmware can still report Active while processing a suspend request.
# If supplied, processing must be the empty string; unknown forms fail closed.
if echo "$power" | grep -Eq '"processing"[[:space:]]*:'; then
  echo "$power" | grep -Eq '"processing"[[:space:]]*:[[:space:]]*""' || exit 0
fi
echo "$power" | grep -Eq '"onOff"[[:space:]]*:[[:space:]]*"off"' && exit 0
[ ! -f /tmp/hu.szabi.launcher.wake-signal ] || exit 0
[ "$(awk '{print $22}' /proc/$pid/stat 2>/dev/null)" = "$start" ] || exit 0
[ -f "$ROOT/enabled" ] && [ -f /var/lib/webosbrew/launcher-home/enabled ] || exit 0
[ ! -f /tmp/hu.szabi.launcher.power-startup ] || exit 0
# The installed service might have attached while the power RPC was pending.
if grep -q 'libphp' /proc/$pid/maps; then reload_bindings; exit $?; fi
# One attempt per process identity, even after failure; no repeated native attach.
echo "$identity" >"$ATTEMPT"
printf '%s repair lginput2 pid=%s start=%s\n' "$(date -Iseconds)" "$pid" "$start"
"$ASSETS/ezinject" "$pid" "$lib" "$ASSETS/lginput-hook.php" lginput2 >/tmp/hu.szabi.inputhook-repair-detail.log 2>&1
sleep 1
if grep -q 'libphp' /proc/$pid/maps; then
  reload_bindings
  printf '%s repair attached pid=%s\n' "$(date -Iseconds)" "$pid"
else
  printf '%s repair not-attached pid=%s\n' "$(date -Iseconds)" "$pid"
fi
"""

    WATCHDOG_SCRIPT = r"""#!/bin/sh
# v0.3.7: opt-in lginput2 repair only; never start the broad injector service.
DIR=/var/lib/webosbrew/inputhook-watchdog
ENABLED="$DIR/enabled"
PIDFILE=/tmp/hu.szabi.inputhook-watchdog.pid
[ -f "$ENABLED" ] || exit 0
exec 9>/tmp/hu.szabi.inputhook-watchdog.flock
flock -n 9 || exit 0
echo $$ >"$PIDFILE"
cleanup() { trap - EXIT INT TERM; rm -f "$PIDFILE"; exit 0; }
trap cleanup EXIT INT TERM
while [ -f "$ENABLED" ]; do
  # The helper owns power/boot/wake gates, its lock and PID/start identity.
  # Starting the original Node service would inject into other LG services.
  [ ! -x "$DIR/repair-home-hook.sh" ] || "$DIR/repair-home-hook.sh" 9>&-
  sleep 2
done
"""

    def __init__(self, config: dict[str, Any], runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.tv_host = str(config["tv_host"])
        self.tv_user = str(config.get("tv_user", "root"))
        self.ssh_key = str(config["ssh_key"])
        self.known_hosts = str(config["known_hosts"])
        self.timeout = canonical_integer(config.get("ssh_timeout_seconds", 12), 2, 30, "ssh_timeout_seconds")
        self.runner = runner
        self.lock = threading.Lock()

    @staticmethod
    def _encoded(content: str) -> str:
        return base64.b64encode(content.encode("utf-8")).decode("ascii")

    def _run(self, remote_command: str) -> str:
        command = [
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-i", self.ssh_key, f"{self.tv_user}@{self.tv_host}", remote_command,
        ]
        completed = self.runner(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "SSH hiba").strip().splitlines()[-1]
            raise RuntimeError("Az Input Hook figyelő nem telepíthető: " + detail[:300])
        return (completed.stdout or "") + (completed.stderr or "")

    def set_enabled(self, enabled: bool) -> None:
        with self.lock:
            if enabled:
                self._run("mkdir -p " + shlex.quote(INPUT_HOOK_WATCHDOG_DIR))
                # Reuse the chunked, syntax-checked uploader for owned scripts.
                LauncherHomeManager._write_remote_file(self, INPUT_HOOK_WATCHDOG_SCRIPT, self.WATCHDOG_SCRIPT)
                LauncherHomeManager._write_remote_file(self, INPUT_HOOK_WATCHDOG_DIR + "/repair-home-hook.sh", self.REPAIR_SCRIPT)
                LauncherHomeManager._write_remote_file(self, INPUT_HOOK_WATCHDOG_INIT, self.INIT_SCRIPT)
                command = "touch " + shlex.quote(INPUT_HOOK_WATCHDOG_ENABLED) + "; " + shlex.quote(INPUT_HOOK_WATCHDOG_INIT)

            else:
                # Let the owned loop finish naturally. A snapshot-restored PID
                # file may name an unrelated process; never signal that PID or
                # interrupt a native attach already in progress.
                command = (
                    "rm -f " + shlex.quote(INPUT_HOOK_WATCHDOG_ENABLED) + " " + shlex.quote(INPUT_HOOK_WATCHDOG_INIT)
                )
            self._run(command)


class InputHookManager:
    """Safe adapter around the already installed LG Input Hook configuration."""

    def __init__(self, config: dict[str, Any], runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.tv_host = str(config["tv_host"])
        self.tv_user = str(config.get("tv_user", "root"))
        self.ssh_key = str(config["ssh_key"])
        self.known_hosts = str(config["known_hosts"])
        self.timeout = canonical_integer(config.get("ssh_timeout_seconds", 12), 2, 30, "ssh_timeout_seconds")
        self.runner = runner
        self.lock = threading.Lock()

    def _run(self, remote_command: str, tty: bool = False) -> str:
        command = [
            "ssh", "-tt" if tty else "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-i", self.ssh_key, f"{self.tv_user}@{self.tv_host}", remote_command,
        ]
        completed = self.runner(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "SSH hiba").strip().splitlines()[-1]
            raise RuntimeError("Az Input Hook elérése sikertelen: " + detail[:300])
        return (completed.stdout or "") + ("\n" + completed.stderr if tty else "")

    @staticmethod
    def _validate_existing_config(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or len(raw) > 512:
            raise RuntimeError("Az Input Hook konfigurációja érvénytelen vagy túl nagy.")
        for key, value in raw.items():
            if not isinstance(key, str) or not re.fullmatch(r"[0-9]{1,5}", key) or not isinstance(value, dict):
                raise RuntimeError("Az Input Hook konfigurációja érvénytelen.")
        return raw

    def read_config(self, path: str = INPUT_HOOK_CONFIG) -> dict[str, Any]:
        if path not in {INPUT_HOOK_CONFIG, INPUT_HOOK_ORIGINAL, INPUT_HOOK_PREVIOUS}:
            raise RuntimeError("Nem engedélyezett Input Hook konfigurációs útvonal.")
        output = self._run("cat " + shlex.quote(path))
        try:
            return self._validate_existing_config(json.loads(output))
        except json.JSONDecodeError as error:
            raise RuntimeError("Az Input Hook konfigurációja nem olvasható JSON-ként.") from error

    def _available_system_input_ids(self) -> set[str]:
        remote_command = (
            "luna-send -n 1 -f "
            + shlex.quote("luna://com.webos.service.eim/getAllInputStatus")
            + " " + shlex.quote('{"subscribe":false}')
        )
        response = parse_luna_response(self._run(remote_command, tty=True))
        result = {"com.webos.app.livetv"}
        if response.get("returnValue") is not True or not isinstance(response.get("devices"), list):
            return result
        for device in response["devices"][:8]:
            app_id = str(device.get("appId") or "") if isinstance(device, dict) else ""
            if app_id in LAUNCHER_SYSTEM_INPUT_IDS:
                result.add(app_id)
        return result

    def list_apps(self, include_icon_paths: bool = False, include_system_inputs: bool = False) -> list[dict[str, Any]]:
        available_system_inputs = self._available_system_input_ids() if include_system_inputs else set()
        remote_command = (
            "luna-send -n 1 "
            + shlex.quote("luna://com.webos.applicationManager/listApps")
            + " " + shlex.quote("{}")
        )
        response = parse_luna_response(self._run(remote_command, tty=True))
        raw_apps = response.get("apps")
        if response.get("returnValue") is not True or not isinstance(raw_apps, list):
            raise RuntimeError("A TV alkalmazáslistája nem kérhető le.")
        apps: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_apps[:1024]:
            if not isinstance(item, dict):
                continue
            app_id = str(item.get("id") or "")
            title = str(item.get("title") or app_id).strip()
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", app_id) or app_id in seen:
                continue
            seen.add(app_id)
            if (item.get("visible") is False or item.get("noDisplay") is True) and app_id not in available_system_inputs:
                continue
            app: dict[str, Any] = {"id": app_id, "title": title[:96] or app_id}
            if include_icon_paths:
                folder = str(item.get("folderPath") or "").rstrip("/")
                allowed_folders = tuple(base + app_id for base in (
                    "/media/developer/apps/usr/palm/applications/",
                    "/media/cryptofs/apps/usr/palm/applications/",
                    "/media/system/apps/usr/palm/applications/",
                    "/usr/palm/applications/",
                ))
                icon_candidates = []
                if folder in allowed_folders:
                    for field in ("largeIcon", "icon"):
                        relative = str(item.get(field) or "")
                        parts = relative.split("/")
                        if (relative and not relative.startswith("/") and len(relative) <= 255
                                and all(part not in {"", ".", ".."} for part in parts)
                                and re.fullmatch(r"[A-Za-z0-9._ /-]+", relative)
                                and relative.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg"))):
                            icon_candidates.append(folder + "/" + relative)
                app["_iconCandidates"] = icon_candidates
            apps.append(app)
        apps.sort(key=lambda item: (item["title"].casefold(), item["id"]))
        return apps

    def app_icon(self, app_id: str) -> tuple[str, bytes] | None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", app_id):
            raise RequestError("Az alkalmazásazonosító érvénytelen.")
        apps = self.list_apps(include_icon_paths=True, include_system_inputs=True)
        app = next((item for item in apps if item["id"] == app_id), None)
        if app is None:
            raise RequestError("Az alkalmazás nincs a TV telepített alkalmazásai között.")
        roots = (
            "/media/developer/apps/usr/palm/applications/" + app_id,
            "/media/cryptofs/apps/usr/palm/applications/" + app_id,
            "/media/system/apps/usr/palm/applications/" + app_id,
            "/usr/palm/applications/" + app_id,
        )
        candidates = list(app.get("_iconCandidates") or [])
        for root in roots:
            for name in ("icon-large.png", "icon.png", "largeIcon.png", "icon130.png", "icon80.png", "icon.jpg", "icon.jpeg"):
                candidates.append(root + "/" + name)
        candidates = list(dict.fromkeys(candidates))
        command = "for f in " + " ".join(shlex.quote(path) for path in candidates) + "; do if [ -f \"$f\" ]; then base64 \"$f\"; exit 0; fi; done; exit 1"
        try:
            encoded = "".join(self._run(command).split())
            payload = base64.b64decode(encoded, validate=True)
        except (RuntimeError, ValueError):
            return None
        if not payload or len(payload) > 2_097_152:
            return None
        if payload.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png", payload
        if payload.startswith(b"\xff\xd8\xff"):
            return "image/jpeg", payload
        if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
            return "image/webp", payload
        if b"<svg" in payload[:1024].lower():
            return "image/svg+xml", payload
        return None

    def diagnostics(self) -> dict[str, Any]:
        command = " ".join((
            "printf 'CPU\\n'; grep '^cpu ' /proc/stat; sleep 1; grep '^cpu ' /proc/stat;",
            "printf 'LOAD\\n'; cat /proc/loadavg;",
            "printf 'MEM\\n'; grep -E '^(MemTotal|MemAvailable|MemFree|Buffers|Cached):' /proc/meminfo;",
            "printf 'DISK\\n'; df -k / /media/developer 2>/dev/null | tail -n +2;",
            "printf 'TEMP\\n'; for f in /sys/class/thermal/thermal_zone*/temp; do [ -r \"$f\" ] && printf '%s=' \"$f\" && cat \"$f\"; done;",
            "printf 'TOP\\n'; top -b -n 1 2>/dev/null | head -n 16 || ps | head -n 16;",
        ))
        output = self._run(command)
        sections: dict[str, list[str]] = {name: [] for name in ("CPU", "LOAD", "MEM", "DISK", "TEMP", "TOP")}
        active = ""
        for line in output.splitlines():
            if line in sections:
                active = line
            elif active:
                sections[active].append(line.rstrip())
        memory: dict[str, int] = {}
        for line in sections["MEM"]:
            match = re.match(r"([A-Za-z]+):\s+([0-9]+)", line)
            if match: memory[match.group(1)] = int(match.group(2))
        total = memory.get("MemTotal", 0)
        available = memory.get("MemAvailable", memory.get("MemFree", 0) + memory.get("Buffers", 0) + memory.get("Cached", 0))
        cpu_percent = None
        if len(sections["CPU"]) >= 2:
            try:
                first = [int(value) for value in sections["CPU"][0].split()[1:]]
                second = [int(value) for value in sections["CPU"][1].split()[1:]]
                first_total, second_total = sum(first), sum(second)
                first_idle = first[3] + (first[4] if len(first) > 4 else 0)
                second_idle = second[3] + (second[4] if len(second) > 4 else 0)
                elapsed = second_total - first_total
                if elapsed > 0:
                    cpu_percent = round(100 * (elapsed - (second_idle - first_idle)) / elapsed, 1)
            except (ValueError, IndexError):
                cpu_percent = None
        temperatures = []
        for line in sections["TEMP"]:
            match = re.search(r"=([0-9]+)", line)
            if match:
                value = int(match.group(1))
                temperatures.append(round(value / 1000 if value > 1000 else value, 1))
        disks = []
        for line in sections["DISK"]:
            fields = line.split()
            if len(fields) >= 6 and fields[1].isdigit():
                disks.append({"mount": fields[-1], "totalKiB": int(fields[1]), "usedKiB": int(fields[2]), "availableKiB": int(fields[3]), "percent": fields[4]})
        load_parts = (sections["LOAD"][0].split() if sections["LOAD"] else [])[:3]
        process_rows = []
        top_lines = [line for line in sections["TOP"] if line.strip()]
        header_index = next((index for index, line in enumerate(top_lines) if re.search(r"\bPID\b", line) and re.search(r"\bCOMMAND\b", line)), -1)
        if header_index >= 0:
            headers = top_lines[header_index].split()
            aliases = {"CPU": ("%CPU", "CPU%", "CPU"), "MEM": ("%MEM", "MEM%", "MEM")}
            def field_index(names: tuple[str, ...]) -> int:
                return next((headers.index(name) for name in names if name in headers), -1)
            indexes = {
                "pid": field_index(("PID",)), "user": field_index(("USER",)),
                "cpu": field_index(aliases["CPU"]), "memory": field_index(aliases["MEM"]),
                "command": field_index(("COMMAND", "CMD")),
            }
            for line in top_lines[header_index + 1:]:
                fields = line.split(None, max(0, len(headers) - 1))
                if len(fields) < 2 or not fields[0].isdigit():
                    continue
                def value(name: str) -> str:
                    index = indexes[name]
                    return fields[index] if 0 <= index < len(fields) else ""
                process_rows.append({"pid": value("pid"), "user": value("user"), "cpu": value("cpu"), "memory": value("memory"), "command": value("command")})
                if len(process_rows) >= 10:
                    break
        return {
            "load": load_parts, "cpuPercent": cpu_percent,
            "memory": {"totalKiB": total, "usedKiB": max(0, total - available), "availableKiB": available},
            "disks": disks[:3], "temperatureC": max(temperatures) if temperatures else None,
            "processes": top_lines[:14], "processRows": process_rows,
            "updatedAt": int(time.time()),
        }

    def tv_screen(self) -> bytes:
        try:
            raw = json.loads(self._run("cat " + shlex.quote(VNC_CONFIG)))
        except (ValueError, RuntimeError) as error:
            raise RuntimeError("A telepített webos-vncserver konfigurációja nem olvasható.") from error
        if not isinstance(raw, dict):
            raise RuntimeError("A telepített webos-vncserver konfigurációja érvénytelen.")
        password = str(raw.get("password") or "")
        if not password or len(password) > 64:
            raise RuntimeError("A webos-vncserver jelszava nincs beállítva.")
        return capture_vnc_png(self.tv_host, 5900, password)

    def tv_key(self, key_name: str) -> None:
        try:
            raw = json.loads(self._run("cat " + shlex.quote(VNC_CONFIG)))
        except (ValueError, RuntimeError) as error:
            raise RuntimeError("A telepített webos-vncserver konfigurációja nem olvasható.") from error
        password = str(raw.get("password") or "") if isinstance(raw, dict) else ""
        if not password or len(password) > 64:
            raise RuntimeError("A webos-vncserver jelszava nincs beállítva.")
        send_vnc_key(self.tv_host, 5900, password, key_name)

    def state(self) -> dict[str, Any]:
        bindings = self.read_config()
        return {
            "ok": True,
            "module": "remote-mapper",
            "hook": {"id": "org.webosbrew.inputhook", "version": "1.4.0"},
            "buttons": [dict(item) for item in REMOTE_BUTTONS],
            "bindings": bindings,
            "apps": self.list_apps(),
        }

    def _write_config(self, config: dict[str, Any]) -> None:
        payload = json.dumps(config, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = base64.b64encode(payload).decode("ascii")
        config_path = shlex.quote(INPUT_HOOK_CONFIG)
        original_path = shlex.quote(INPUT_HOOK_ORIGINAL)
        previous_path = shlex.quote(INPUT_HOOK_PREVIOUS)
        temporary_path = shlex.quote(INPUT_HOOK_CONFIG + ".new")
        remote_command = " ".join((
            "set -eu;",
            "mkdir -p /home/root/.config/lginputhook;",
            f"[ -f {config_path} ] || printf '{{}}' > {config_path};",
            f"[ -f {original_path} ] || cp {config_path} {original_path};",
            f"cp {config_path} {previous_path};",
            f"printf '%s' {shlex.quote(encoded)} | base64 -d > {temporary_path};",
            f"chmod 600 {temporary_path};",
            f"mv {temporary_path} {config_path}",
        ))
        self._run(remote_command)

    def update_binding(self, raw: Any, shortcuts: dict[str, Any] | None = None) -> dict[str, Any]:
        key_code, binding = validate_remote_bind_request(raw)
        with self.lock:
            current = self.read_config()
            if binding is not None and binding.get("action") == "exec" and binding.get("managedBy") == REMOTE_MAPPER_APP_ID:
                shortcuts = shortcuts or {"presets": [], "cameras": []}
                binding_type = binding.get("bindingType")
                if binding_type == "overlayPreset":
                    preset_ids = {item["id"] for item in shortcuts.get("presets", []) if isinstance(item, dict) and "id" in item}
                    if binding.get("presetId") not in preset_ids:
                        raise RequestError("Csak a TV-ről szinkronizált PiP preset választható.")
                elif binding_type == "cameraOpen":
                    camera_ids = {item["cameraId"] for item in shortcuts.get("cameras", []) if isinstance(item, dict) and "cameraId" in item}
                    if binding.get("cameraId") not in camera_ids:
                        raise RequestError("Csak a TV-ről szinkronizált kamera választható.")
            if binding is not None and (
                binding.get("action") == "launch" or binding.get("bindingType") in {"appCommand", "launcherHome"}
            ):
                installed = {item["id"] for item in self.list_apps()}
                app_id = binding.get("id") if binding.get("action") == "launch" else binding.get("appId")
                if app_id not in installed:
                    raise RequestError("Csak a TV-re telepített alkalmazás választható.")
            updated = dict(current)
            key = str(key_code)
            if binding is None:
                updated.pop(key, None)
            else:
                updated[key] = binding
            changed = updated != current
            if changed:
                self._write_config(updated)
        result = self.state()
        result["changed"] = changed
        return result

    def restore(self, source: str) -> dict[str, Any]:
        path = INPUT_HOOK_PREVIOUS if source == "previous" else INPUT_HOOK_ORIGINAL
        with self.lock:
            restored = self.read_config(path)
            current = self.read_config()
            changed = restored != current
            if changed:
                self._write_config(restored)
        result = self.state()
        result["changed"] = changed
        result["restoredFrom"] = source
        return result


class RemoteBrokerManager:
    """Compile structured bindings for a standalone fail-open evdev broker.

    The broker never loads code into an LG process.  It grabs only explicitly
    named remote-control event devices and forwards to a separate existing
    factory evdev output. No virtual devices or LG service restarts are used.
    Closing the source descriptor releases its kernel grab. End-to-end TV
    operation must still be verified on the actual firmware.
    """

    INIT_SCRIPT = r"""#!/bin/sh
ROOT=/var/lib/webosbrew/remote-broker
[ -f "$ROOT/enabled" ] || exit 0
[ -x "$ROOT/supervisor.sh" ] || exit 0
if [ -s /tmp/hu.szabi.remote-broker-supervisor.pid ]; then
  old=$(cat /tmp/hu.szabi.remote-broker-supervisor.pid 2>/dev/null || true)
  case "$old" in *[!0-9]*|'') old=0;; esac
  if [ "$old" -gt 1 ] && [ -r "/proc/$old/cmdline" ] && tr '\000' ' ' <"/proc/$old/cmdline" | grep -F "$ROOT/supervisor.sh" >/dev/null 2>&1; then
    exit 0
  fi
fi
"$ROOT/supervisor.sh" >>/tmp/hu.szabi.remote-broker.log 2>&1 &
"""

    SUPERVISOR_SCRIPT = r"""#!/bin/sh
set -u
ROOT=/var/lib/webosbrew/remote-broker
ENABLED=$ROOT/enabled
BROKER=$ROOT/remote-broker
CONFIG=$ROOT/bindings.conf
HEARTBEAT=/tmp/hu.szabi.remote-broker.heartbeat
PIDFILE=/tmp/hu.szabi.remote-broker.pid
SUPERVISOR_PID=/tmp/hu.szabi.remote-broker-supervisor.pid
RELOAD_ACK=/tmp/hu.szabi.remote-broker.reload
DISABLED_REASON=$ROOT/disabled-reason
STATEFILE=/tmp/hu.szabi.remote-broker.state
LOG=/tmp/hu.szabi.remote-broker.log
# Keep the lock inode: unlinking a held lock would permit a second supervisor.
exec 9>/tmp/hu.szabi.remote-broker-supervisor.lock
flock -n 9 || exit 0
child=
child_status=0

set_state() {
  [ "$(cat "$STATEFILE" 2>/dev/null)" = "$1" ] && return 0
  printf '%s\n' "$1" >"$STATEFILE"
  # Reopen the log on every transition, keeping a bounded RAM history.
  size=$(wc -c <"$LOG" 2>/dev/null); size=${size:-0}
  [ "$size" -lt 32768 ] || tail -c 16384 "$LOG" >"$LOG.previous"
  if [ "$size" -ge 32768 ]; then : >"$LOG"; fi
  printf '%s state=%s power=%s child_status=%s\n' "$(date -Iseconds)" "$1" "${power:-unknown}" "$child_status" >>"$LOG"
}

power_state() {
  reply=$(luna-send -t 1 -f -w 1500 luna://com.webos.service.tvpower/power/getPowerState '{}' 2>&1)
  printf '%s\n' "$reply" | sed -n 's/.*"state"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1
}

trip() {
  stop_child
  set_state fault
  # Capture the last exit code and native messages before reboot clears /tmp.
  { printf '%s %s; exit=%s power=%s boot=%s\n' "$(date -Iseconds)" "$1" "$child_status" "${power:-unknown}" "$(cat /proc/sys/kernel/random/boot_id)";
    tail -c 8192 "$LOG" 2>/dev/null; } >"$ROOT/last-failure.log"
  printf '%s %s; exit=%s power=%s\n' "$(date -Iseconds)" "$1" "$child_status" "${power:-unknown}" >"$DISABLED_REASON"
  rm -f "$ENABLED"
  exit 1
}

stop_child() {
  [ -n "$child" ] || return 0
  if kill -0 "$child" 2>/dev/null; then
    kill "$child" 2>/dev/null || true
    tries=0
    while kill -0 "$child" 2>/dev/null && [ "$tries" -lt 20 ]; do
      /bin/usleep 100000
      tries=$((tries + 1))
    done
    if kill -0 "$child" 2>/dev/null; then kill -9 "$child" 2>/dev/null || true; fi
  fi
  wait "$child" 2>/dev/null || child_status=$?
  child=
}

cleanup() {
  trap - EXIT INT TERM HUP
  stop_child
  if [ "$child_status" != 0 ]; then
    # Only clear held keys on the dedicated factory relay output. Never
    # restart LG services or destroy input devices.
    "$BROKER" --config "$CONFIG" --recover-output 9>&- || true
  fi
  rm -f "$PIDFILE" "$SUPERVISOR_PID" "$HEARTBEAT" "$RELOAD_ACK" "$STATEFILE"
}
trap cleanup EXIT
trap 'exit 0' INT TERM HUP
printf '%s\n' "$$" >"$SUPERVISOR_PID"
[ -f "$ENABLED" ] || exit 0
if [ ! -x "$BROKER" ] || ! "$BROKER" --config "$CONFIG" --check-config; then
  trip 'invalid broker/config'
fi
rm -f "$HEARTBEAT" "$RELOAD_ACK"
last_heartbeat=
stale_samples=0
active_samples=0
while [ -f "$ENABLED" ]; do
  power=$(power_state)
  case "$power" in
    Active|'Screen Saver'|'Screen Off') active_samples=$((active_samples + 1));;
    '')
      # An unavailable Luna service at boot is not a broker crash. Never
      # acquire input until Active is positively established.
      active_samples=0
      if [ -z "$child" ]; then set_state waiting-for-tv; sleep 1; continue; fi
      ;;
    *)
      stop_child
      active_samples=0
      stale_samples=0
      last_heartbeat=
      set_state standby
      sleep 1
      continue
      ;;
  esac
  if [ -z "$child" ]; then
    if [ "$active_samples" -lt 2 ]; then set_state waiting-for-tv; sleep 1; continue; fi
    # No grabs/writes: wait for one compatible and idle factory source/sink.
    # Missing devices and a held key during boot are retried without seizing input.
    if ! "$BROKER" --config "$CONFIG" --check-devices 9>&- >/dev/null 2>&1; then
      set_state waiting-for-input
      sleep 1
      continue
    fi
    child_status=0
    rm -f "$HEARTBEAT" "$RELOAD_ACK"
    "$BROKER" --config "$CONFIG" --heartbeat "$HEARTBEAT" --pid-file "$PIDFILE" 9>&- >>"$LOG" 2>&1 &
    child=$!
    last_heartbeat=
    stale_samples=0
    set_state active
  fi
  if ! kill -0 "$child" 2>/dev/null; then
    stop_child
    # Shutdown may signal the broker before tvpower publishes standby.
    # Allow that short ordering gap, never restart an unexplained Active exit.
    attempt=0
    while [ "$attempt" -lt 3 ] && [ -f "$ENABLED" ]; do
      sleep 1
      power=$(power_state)
      case "$power" in 'Active Standby'|Suspend|'Power Off') break;; esac
      attempt=$((attempt + 1))
    done
    [ -f "$ENABLED" ] || break
    case "$power" in
      'Active Standby'|Suspend|'Power Off') active_samples=0; set_state standby; continue;;
      *) trip 'broker exited; crash circuit breaker opened';;
    esac
  fi
  heartbeat=$(cat "$HEARTBEAT" 2>/dev/null || printf '0')
  case "$heartbeat" in *[!0-9]*|'') heartbeat=0;; esac
  if [ "$heartbeat" -gt 0 ] && [ "$heartbeat" != "$last_heartbeat" ]; then
    last_heartbeat=$heartbeat
    stale_samples=0
  else
    stale_samples=$((stale_samples + 1))
  fi
  # Count unchanged observations instead of comparing /proc/uptime with the
  # broker's CLOCK_MONOTONIC value. Those clocks diverge across TV standby.
  if [ "$stale_samples" -ge 6 ]; then
    trip 'stale heartbeat; releasing remote grab; no automatic retry'
  fi
  sleep 1
done
"""

    def __init__(self, config: dict[str, Any], runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
        self.tv_host = str(config["tv_host"])
        self.tv_user = str(config.get("tv_user", "root"))
        self.ssh_key = str(config["ssh_key"])
        self.known_hosts = str(config["known_hosts"])
        self.timeout = canonical_integer(config.get("ssh_timeout_seconds", 12), 2, 30, "ssh_timeout_seconds")
        self.enabled = config.get("remote_broker_enabled", False) is True
        self.mode = str(config.get("remote_broker_mode", "passive"))
        if self.mode not in {"passive", "grab"}:
            raise ValueError("A remote_broker_mode passive vagy grab legyen.")
        self.runner = runner
        self.lock = threading.Lock()

    def _run(self, remote_command: str) -> str:
        command = [
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}",
            "-i", self.ssh_key, f"{self.tv_user}@{self.tv_host}", remote_command,
        ]
        completed = self.runner(command, capture_output=True, text=True, timeout=self.timeout, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "SSH hiba").strip().splitlines()[-1]
            raise RuntimeError("A Remote Broker elérése sikertelen: " + detail[:300])
        return completed.stdout or ""

    @staticmethod
    def _encoded_write(path: str, content: str, mode: str = "600") -> str:
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        target = shlex.quote(path)
        temporary = shlex.quote(path + ".new")
        return " ".join((
            f"printf '%s' {shlex.quote(encoded)} | base64 -d > {temporary};",
            f"chmod {mode} {temporary};",
            f"mv {temporary} {target};",
        ))

    @staticmethod
    def _launch_script(app_id: str, params: dict[str, Any]) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,127}", app_id):
            raise RuntimeError("A broker alkalmazásazonosítója érvénytelen.")
        checked_params = validate_remote_launch_params(params)
        payload = json.dumps({"id": app_id, "params": checked_params}, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        return "\n".join((
            "#!/bin/sh", "set -eu", "umask 077",
            "/usr/bin/luna-send-pub -t 1 -w 10000 -f "
            + shlex.quote(LAUNCH_URI) + " " + shlex.quote(payload) + " >/dev/null 2>&1",
            "",
        ))

    @staticmethod
    def _long_back_action_script() -> str:
        return "\n".join((
            "#!/bin/sh", "set -eu",
            "export LAUNCHER_HOME_FORCE_MODE=full",
            "export LAUNCHER_HOME_FORCE_SOURCE=back-long",
            "exec " + shlex.quote(LAUNCHER_HOME_KEY), "",
        ))

    @classmethod
    def _action_script(cls, binding: dict[str, Any], code: int | None = None) -> str | None:
        action = binding.get("action")
        if action == "launch":
            return cls._launch_script(str(binding.get("id") or ""), {})
        if action != "exec" or binding.get("managedBy") != REMOTE_MAPPER_APP_ID:
            return None
        binding_type = str(binding.get("bindingType") or "")
        if binding_type == "launcherHome":
            if code is None or code < 0 or code > 2047:
                return None
            return "\n".join((
                "#!/bin/sh", "set -eu",
                "export LAUNCHER_HOME_KEY_CODE=" + str(code),
                "export LAUNCHER_HOME_KEY_LOG=/tmp/hu.szabi.remote-broker.key-" + str(code) + ".state",
                "exec " + shlex.quote(LAUNCHER_HOME_KEY), "",
            ))
        if binding_type == "overlayPreset":
            preset_id = str(binding.get("presetId") or "")
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", preset_id):
                return None
            return cls._launch_script(APP_ID, {"v": 1, "action": "show", "presetId": preset_id})
        if binding_type == "cameraOpen":
            camera_id = str(binding.get("cameraId") or "")
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", camera_id):
                return None
            return cls._launch_script(CAMERA_APP_ID, {"v": 1, "action": "open", "cameraId": camera_id, "view": "full"})
        if binding_type == "appCommand":
            return cls._launch_script(str(binding.get("appId") or ""), binding.get("params"))
        if binding_type == "webhook":
            webhook_url = validate_home_assistant_webhook(binding.get("webhookUrl"))
            return "\n".join((
                "#!/bin/sh", "set -eu", "umask 077",
                "exec /usr/bin/curl --fail --silent --show-error --max-time 4 --request POST --header "
                + shlex.quote("Content-Type: application/json") + " --data " + shlex.quote("{}") + " "
                + shlex.quote(webhook_url) + " >/dev/null 2>&1",
                "",
            ))
        return None

    def compile_bindings(self, bindings: dict[str, Any]) -> tuple[str, dict[int, str]]:
        if not isinstance(bindings, dict):
            raise RuntimeError("A broker gombkiosztása érvénytelen.")
        lines = [
            "version=2", "mode=" + self.mode,
            "device=LGE M-RCU - Builtin [0]",
            "output=LGE M-RCU - Builtin [2]",
        ]
        # Back remains locked in the editor, but its long press is a protected
        # system binding: short Back passes through; only repeat events launch
        # the full custom launcher.
        actions: dict[int, str] = {REMOTE_LONG_BACK_CODE: self._long_back_action_script()}
        lines.append(f"{REMOTE_LONG_BACK_CODE}=long-action")
        for raw_code, raw_binding in sorted(bindings.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 99999):
            if not str(raw_code).isdigit() or not isinstance(raw_binding, dict):
                continue
            code = int(raw_code)
            if code not in REMOTE_EDITABLE_CODES:
                continue
            action = raw_binding.get("action")
            if action == "ignore":
                lines.append(f"{code}=ignore")
            elif action == "replace":
                target = raw_binding.get("keycode")
                if isinstance(target, int) and not isinstance(target, bool) and target in REMOTE_REPLACE_CODES:
                    lines.append(f"{code}=replace:{target}")
            else:
                try:
                    script = self._action_script(raw_binding, code)
                except (RequestError, RuntimeError, TypeError, ValueError):
                    script = None
                if script is not None:
                    actions[code] = script
                    lines.append(f"{code}=action")
        return "\n".join(lines) + "\n", actions

    def _stop_locked(self) -> None:
        command = " ".join((
            "rm -f " + shlex.quote(REMOTE_BROKER_ENABLED) + ";",
            "if [ -s " + shlex.quote(REMOTE_BROKER_SUPERVISOR_PID) + " ]; then",
            "p=$(cat " + shlex.quote(REMOTE_BROKER_SUPERVISOR_PID) + " 2>/dev/null || true);",
            "case \"$p\" in *[!0-9]*|'') p=0;; esac;",
            "if [ \"$p\" -gt 1 ] && [ -r \"/proc/$p/cmdline\" ] &&",
            "tr '\\000' ' ' <\"/proc/$p/cmdline\" | grep -F " + shlex.quote(REMOTE_BROKER_SUPERVISOR) + " >/dev/null 2>&1; then",
            "kill \"$p\"; i=0; while kill -0 \"$p\" 2>/dev/null && [ \"$i\" -lt 80 ]; do /bin/usleep 100000; i=$((i+1)); done; fi; fi;",
            "if [ -s " + shlex.quote(REMOTE_BROKER_PID) + " ]; then",
            "b=$(cat " + shlex.quote(REMOTE_BROKER_PID) + " 2>/dev/null || true);",
            "case \"$b\" in *[!0-9]*|'') b=0;; esac;",
            "if [ \"$b\" -gt 1 ] && [ -r \"/proc/$b/cmdline\" ] &&",
            "tr '\\000' ' ' <\"/proc/$b/cmdline\" | grep -F " + shlex.quote(REMOTE_BROKER_BINARY) + " >/dev/null 2>&1; then",
            "kill \"$b\" 2>/dev/null || true; i=0; while kill -0 \"$b\" 2>/dev/null && [ \"$i\" -lt 20 ]; do /bin/usleep 100000; i=$((i+1)); done;",
            "if kill -0 \"$b\" 2>/dev/null; then kill -9 \"$b\" 2>/dev/null || true; fi; fi; fi;",
            "rm -f " + shlex.quote(REMOTE_BROKER_PID) + " " + shlex.quote(REMOTE_BROKER_SUPERVISOR_PID) + " " + shlex.quote(REMOTE_BROKER_HEARTBEAT) + " " + shlex.quote(REMOTE_BROKER_RELOAD_ACK),
        ))
        self._run(command)

    def _replace_actions_locked(self, actions: dict[int, str]) -> None:
        staging = REMOTE_BROKER_ACTIONS + ".new"
        previous = REMOTE_BROKER_ACTIONS + ".previous"
        self._run(" ".join((
            "set -eu;", "umask 077;", "mkdir -p " + shlex.quote(REMOTE_BROKER_DIR) + ";",
            "rm -rf " + shlex.quote(staging) + ";", "mkdir -m 700 " + shlex.quote(staging),
        )))
        # Dropbear on older webOS releases has a small remote-command buffer.
        # Keep every generated action in a separate bounded SSH request.
        for code, script in actions.items():
            self._run(self._encoded_write(staging + f"/{code}", script, "700"))
        self._run(" ".join((
            "set -eu;", "rm -rf " + shlex.quote(previous) + ";",
            "if [ -d " + shlex.quote(REMOTE_BROKER_ACTIONS) + " ]; then mv "
            + shlex.quote(REMOTE_BROKER_ACTIONS) + " " + shlex.quote(previous) + "; fi;",
            "mv " + shlex.quote(staging) + " " + shlex.quote(REMOTE_BROKER_ACTIONS),
        )))

    def _wait_active_locked(self) -> None:
        command = " ".join((
            "i=0; while [ \"$i\" -lt 50 ]; do",
            "p=$(cat " + shlex.quote(REMOTE_BROKER_PID) + " 2>/dev/null || true);",
            "case \"$p\" in *[!0-9]*|'') p=0;; esac;",
            "if [ \"$p\" -gt 1 ] && [ -r \"/proc/$p/cmdline\" ] &&",
            "tr '\\000' ' ' <\"/proc/$p/cmdline\" | grep -F " + shlex.quote(REMOTE_BROKER_BINARY) + " >/dev/null 2>&1; then exit 0; fi;",
            "/bin/usleep 100000; i=$((i+1)); done; exit 1",
        ))
        try:
            self._run(command)
        except RuntimeError as error:
            raise RuntimeError("A Remote Broker nem vált aktívvá 5 másodpercen belül.") from error

    def _active_pid_locked(self) -> int | None:
        command = " ".join((
            "p=$(cat " + shlex.quote(REMOTE_BROKER_PID) + " 2>/dev/null || true);",
            "case \"$p\" in *[!0-9]*|'') exit 1;; esac;",
            "[ \"$p\" -gt 1 ] && [ -r \"/proc/$p/cmdline\" ] &&",
            "tr '\\000' ' ' <\"/proc/$p/cmdline\" | grep -F " + shlex.quote(REMOTE_BROKER_BINARY) + " >/dev/null 2>&1;",
            "if [ $? -ne 0 ]; then exit 1; fi; printf '%s' \"$p\"",
        ))
        try:
            value = self._run(command).strip()
        except RuntimeError:
            return None
        return int(value) if value.isdigit() and int(value) > 1 else None

    def _reload_locked(self, pid: int) -> None:
        command = " ".join((
            "set -eu;", "rm -f " + shlex.quote(REMOTE_BROKER_RELOAD_ACK) + ";",
            "kill -HUP " + str(pid) + ";", "i=0; while [ \"$i\" -lt 30 ]; do",
            "ack=$(cat " + shlex.quote(REMOTE_BROKER_RELOAD_ACK) + " 2>/dev/null || true);",
            "[ \"$ack\" = " + shlex.quote(str(pid)) + " ] && exit 0;",
            "/bin/usleep 100000; i=$((i+1)); done; exit 1",
        ))
        try:
            self._run(command)
        except RuntimeError as error:
            raise RuntimeError("A Remote Broker nem igazolta a helyben t�rt�n� �jrat�lt�st.") from error

    def sync_bindings(self, bindings: dict[str, Any]) -> None:
        config_text, actions = self.compile_bindings(bindings)
        with self.lock:
            active_pid = self._active_pid_locked() if self.enabled else None
            self._replace_actions_locked(actions)
            self._run(self._encoded_write(REMOTE_BROKER_CONFIG, config_text, "600"))
            if active_pid is not None:
                self._reload_locked(active_pid)
                return
            self._stop_locked()
            if self.enabled:
                self._run("umask 077; : > " + shlex.quote(REMOTE_BROKER_ENABLED) + "; " + shlex.quote(REMOTE_BROKER_INIT))
                self._wait_active_locked()

    def set_enabled(self, enabled: bool, bindings: dict[str, Any] | None = None) -> None:
        with self.lock:
            if not enabled:
                self._stop_locked()
                self._run("rm -f " + shlex.quote(REMOTE_BROKER_ENABLED) + " " + shlex.quote(REMOTE_BROKER_INIT))
                self.enabled = False
                return
            if bindings is None:
                raise ValueError("A Remote Broker engedélyezéséhez gombkiosztás szükséges.")
            if self._run("test -x " + shlex.quote(REMOTE_BROKER_BINARY) + " && " + shlex.quote(REMOTE_BROKER_BINARY) + " --version").strip() != "4-evdev-relay":
                raise RuntimeError("A TV-re az új, 4-evdev-relay broker bináris szükséges.")
            config_text, actions = self.compile_bindings(bindings)
            self._run("set -eu; umask 077; mkdir -p " + shlex.quote(REMOTE_BROKER_DIR))
            self._run(self._encoded_write(REMOTE_BROKER_SUPERVISOR, self.SUPERVISOR_SCRIPT, "700"))
            self._run(self._encoded_write(REMOTE_BROKER_INIT, self.INIT_SCRIPT, "700"))
            active_pid = self._active_pid_locked()
            self._replace_actions_locked(actions)
            self._run(self._encoded_write(REMOTE_BROKER_CONFIG, config_text, "600"))
            if active_pid is not None:
                self.enabled = True
                self._reload_locked(active_pid)
                return
            self._stop_locked()
            self._run("umask 077; rm -f " + shlex.quote(REMOTE_BROKER_DIR + "/disabled-reason")
                      + "; : > " + shlex.quote(REMOTE_BROKER_ENABLED))
            self.enabled = True
            self._run(shlex.quote(REMOTE_BROKER_INIT))
            self._wait_active_locked()

    def status(self) -> dict[str, Any]:
        command = " ".join((
            "printf 'binary=%s\\n' \"$([ -x " + shlex.quote(REMOTE_BROKER_BINARY) + " ] && echo 1 || echo 0)\";",
            "printf 'enabled=%s\\n' \"$([ -f " + shlex.quote(REMOTE_BROKER_ENABLED) + " ] && echo 1 || echo 0)\";",
            "p=$(cat " + shlex.quote(REMOTE_BROKER_PID) + " 2>/dev/null || true); case \"$p\" in *[!0-9]*|'') p=0;; esac;",
            "active=0; if [ \"$p\" -gt 1 ] && [ -r \"/proc/$p/cmdline\" ] && tr '\\000' ' ' <\"/proc/$p/cmdline\" | grep -F " + shlex.quote(REMOTE_BROKER_BINARY) + " >/dev/null 2>&1; then active=1; fi;",
            "printf 'active=%s\\n' \"$active\";",
            "printf 'lifecycle=%s\\n' \"$(cat /tmp/hu.szabi.remote-broker.state 2>/dev/null || true)\";",
            "printf 'mode=%s\\n' \"$(sed -n 's/^mode=//p' " + shlex.quote(REMOTE_BROKER_CONFIG) + " 2>/dev/null | head -n 1)\";",
            "printf 'version=%s\\n' \"$(" + shlex.quote(REMOTE_BROKER_BINARY) + " --version 2>/dev/null || true)\";",
            "printf 'reason=%s\\n' \"$(head -c 300 " + shlex.quote(REMOTE_BROKER_DIR + "/disabled-reason") + " 2>/dev/null || true)\";",
            "lg=$(pidof lginput2 2>/dev/null | awk '{print $1}'); mic=$(pidof micomservice 2>/dev/null | awk '{print $1}'); native=0;",
            "[ -n \"$lg\" ] && grep -q libphp \"/proc/$lg/maps\" 2>/dev/null && native=1 || true;",
            "[ -n \"$mic\" ] && grep -q libphp \"/proc/$mic/maps\" 2>/dev/null && native=1 || true;",
            "printf 'nativeHookLoaded=%s\\n' \"$native\";",
        ))
        try:
            output = self._run(command)
            values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
            return {
                "id": "hu.szabi.remote-broker", "available": values.get("binary") == "1",
                "enabled": values.get("enabled") == "1", "active": values.get("active") == "1",
                "mode": values.get("mode") or self.mode,
                "compatible": values.get("version") == "4-evdev-relay",
                "lifecycle": values.get("lifecycle", ""),
                "disabledReason": values.get("reason", ""),
                "nativeHookLoaded": values.get("nativeHookLoaded") == "1",
                "failOpen": None, "grabReleasedOnExit": True,
                "transport": "factory-evdev-relay",
            }
        except (RuntimeError, subprocess.TimeoutExpired) as error:
            return {
                "id": "hu.szabi.remote-broker", "available": False, "enabled": False,
                "active": False, "mode": self.mode, "nativeHookLoaded": None,
                "failOpen": None, "grabReleasedOnExit": True,
                "transport": "factory-evdev-relay", "error": str(error),
            }


class RemoteBrokerSwitch(JsonStore):
    """Persist the user's switch independently of service config/deployment.

    A NAS restart never silently rearms a TV-side crash circuit breaker.
    OFF is saved before contacting the TV so an SSH outage cannot lose it.
    """
    def __init__(self, path: Path, broker: RemoteBrokerManager, input_hook: InputHookManager):
        super().__init__(path)
        self.broker = broker
        self.input_hook = input_hook
        try:
            self.requested = self._read().get("enabled") is True
        except (OSError, ValueError, AttributeError):
            self.requested = False

    def _save(self, enabled: bool) -> None:
        self._write({"enabled": enabled})
        self.requested = enabled

    def status(self) -> dict[str, Any]:
        result = self.broker.status()
        result["requestedEnabled"] = self.requested
        return result

    def restore(self) -> None:
        with self.lock:
            if not self.requested:
                self.broker.set_enabled(False)
                return
            live = self.broker.status()
            if live.get("enabled") and live.get("compatible"):
                self.broker.mode = "grab"
                self.broker.set_enabled(True, self.input_hook.read_config())
            else:
                self.broker.enabled = False

    def set_enabled(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict) or set(raw) != {"enabled"} or type(raw["enabled"]) is not bool:
            raise RequestError("A kapcsolóhoz egy enabled: true/false érték szükséges.")
        enabled = raw["enabled"]
        with self.lock:
            if not enabled:
                try:
                    self._save(False)
                finally:
                    self.broker.enabled = False
                    self.broker.set_enabled(False)
            else:
                live = self.broker.status()
                if not live.get("compatible") or live.get("nativeHookLoaded") is not False:
                    raise RuntimeError("A bekapcsoláshoz az új broker és kikapcsolt régi Input Hook szükséges.")
                self.broker.mode = "grab"
                try:
                    self.broker.set_enabled(True, self.input_hook.read_config())
                    live = self.broker.status()
                    if not live.get("enabled") or not live.get("active"):
                        raise RuntimeError("A broker nem igazolta a bekapcsolást.")
                    self._save(True)
                except Exception:
                    try:
                        self._save(False)
                    finally:
                        self.broker.enabled = False
                        self.broker.set_enabled(False)
                    raise
            result = self.status()
            if not enabled and (result.get("active") or result.get("enabled") or result.get("error")):
                raise RuntimeError("A kikapcsolás mentve, de a TV leállása még nem igazolható. Próbáld újra a leállítást.")
            return result


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "LGTVControl/1.1"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' http: https:; img-src 'self' data: http: https:; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        super().end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def json_response(self, status: HTTPStatus, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authorized_network(self) -> bool:
        try:
            address = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        return any(address in network for network in self.server.allowed_networks)  # type: ignore[attr-defined]

    def read_json(self, sync_callback: bool = False, allow_text_plain: bool = False) -> Any:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        allowed_types = {"text/plain"} if sync_callback else {"application/json"}
        if allow_text_plain:
            allowed_types.add("text/plain")
        if content_type not in allowed_types:
            raise RequestError("A Content-Type érvénytelen.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise RequestError("A Content-Length hibás.") from error
        maximum = 524_288 if sync_callback else 65_536
        if length < 0 or length > maximum:
            raise RequestError("A kérés túl nagy.")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RequestError("A JSON kérés hibás.") from error

    def do_OPTIONS(self) -> None:
        if self.path.startswith("/api/remote-mapper/"):
            self.send_response(HTTPStatus.NO_CONTENT.value)
            self.end_headers()
            return
        self.json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Nincs ilyen végpont."})

    def launcher_apps(self) -> list[dict[str, str]]:
        catalog = self.server.launcher_app_catalog  # type: ignore[attr-defined]
        cached = catalog.snapshot()
        if not cached:
            if not catalog.begin_refresh():
                return []
            try:
                apps = self.server.input_hook.list_apps(include_system_inputs=True)  # type: ignore[attr-defined]
                catalog.finish_refresh(apps)
                return apps
            except Exception:
                catalog.finish_refresh(None)
                raise
        if catalog.should_refresh() and catalog.begin_refresh():
            server_ref = self.server
            def refresh_catalog() -> None:
                try:
                    apps = server_ref.input_hook.list_apps(include_system_inputs=True)  # type: ignore[attr-defined]
                    server_ref.launcher_app_catalog.finish_refresh(apps)  # type: ignore[attr-defined]
                except Exception:
                    server_ref.launcher_app_catalog.finish_refresh(None)  # type: ignore[attr-defined]
            threading.Thread(target=refresh_catalog, name="launcher-app-catalog", daemon=True).start()
        return cached

    def do_GET(self) -> None:
        request_url = urlsplit(self.path)
        request_path = request_url.path
        if self.path == "/":
            payload = self.server.index_html  # type: ignore[attr-defined]
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        static_assets = {
            "/assets/ssap-control.js": ("text/javascript; charset=utf-8", getattr(self.server, "ssap_control_js", b"")),
            "/assets/broker-control.js": ("text/javascript; charset=utf-8", self.server.broker_control_js),
            "/assets/power-control.js": ("text/javascript; charset=utf-8", self.server.power_control_js),  # type: ignore[attr-defined]
            "/assets/remote-ui.css": ("text/css; charset=utf-8", self.server.remote_ui_css),  # type: ignore[attr-defined]
            "/assets/remote-ui.js": ("text/javascript; charset=utf-8", self.server.remote_ui_js),  # type: ignore[attr-defined]
            "/assets/connections-ui.js": ("text/javascript; charset=utf-8", self.server.connections_ui_js),  # type: ignore[attr-defined]
            "/assets/launcher-ui.js": ("text/javascript; charset=utf-8", self.server.launcher_ui_js),  # type: ignore[attr-defined]
            "/assets/launcher-admin.js": ("text/javascript; charset=utf-8", self.server.launcher_admin_js),  # type: ignore[attr-defined]
            "/assets/dashboard-control.js": ("text/javascript; charset=utf-8", self.server.dashboard_control_js),  # type: ignore[attr-defined]
            "/assets/launcher.css": ("text/css; charset=utf-8", self.server.launcher_css),  # type: ignore[attr-defined]
        }
        if self.path in static_assets:
            content_type, payload = static_assets[self.path]
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if request_path == "/api/tv/pairing":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem olvashat párosítási állapotot."})
                return
            self.json_response(HTTPStatus.OK, {"ok": True, **self.server.ssap_pairing.snapshot()})
            return
        if request_path == "/api/tv/power":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem kérheti le a TV állapotát."})
                return
            try:
                self.json_response(HTTPStatus.OK, {"ok": True, "power": self.server.tv_power.status()})  # type: ignore[attr-defined]
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if request_path == "/api/apps/icon":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem kérhet alkalmazásikont."})
                return
            app_id = parse_qs(request_url.query).get("appId", [""])[0]
            try:
                cached = self.server.app_icon_cache.get(app_id)  # type: ignore[attr-defined]
                if cached is None:
                    cached = self.server.input_hook.app_icon(app_id)  # type: ignore[attr-defined]
                    self.server.app_icon_cache[app_id] = cached  # type: ignore[attr-defined]
                if cached is None:
                    self.json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Ehhez az alkalmazáshoz nincs elérhető ikon."})
                    return
                content_type, payload = cached
                self.send_response(HTTPStatus.OK.value)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (RequestError, RuntimeError, subprocess.TimeoutExpired) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if request_path == "/api/launcher/camera-preview":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem kérhet kamera-előnézetet."})
                return
            try:
                query = parse_qs(request_url.query, keep_blank_values=True)
                if not set(query).issubset({"presetId", "_launcher"}) or "presetId" not in query or len(query["presetId"]) != 1:
                    raise RequestError("A kamera-előnézeti kérés paraméterei érvénytelenek.")
                if "_launcher" in query and (len(query["_launcher"]) != 1 or not re.fullmatch(r"[0-9]{1,20}", query["_launcher"][0])):
                    raise RequestError("A kamera-előnézeti gyorsítótár-kulcs érvénytelen.")
                preset_id = query["presetId"][0]
                if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,31}", preset_id):
                    raise RequestError("A kamera-preset azonosítója érvénytelen.")
                overlay = self.server.state_store.snapshot("media-overlay") or {}  # type: ignore[attr-defined]
                preset = next((item for item in overlay.get("presets", []) if item.get("id") == preset_id), None)
                if not isinstance(preset, dict) or preset.get("kind") != "image":
                    raise RequestError("Ehhez a presethez nincs kamera-előnézet.")
                camera_id = str(preset.get("cameraId") or "")
                camera_state = self.server.state_store.snapshot("camera-viewer") or {}  # type: ignore[attr-defined]
                profile = next((item for item in camera_state.get("profiles", []) if item.get("cameraId") == camera_id), None)
                if not isinstance(profile, dict):
                    raise RequestError("A presethez tartozó kamera nincs szinkronizálva.")
                source = launcher_profile_frame_url(profile)
                with self.server.camera_preview_locks_guard:  # type: ignore[attr-defined]
                    source_lock = self.server.camera_preview_locks.setdefault(source, threading.Lock())  # type: ignore[attr-defined]
                with source_lock:
                    cached = self.server.camera_preview_cache.get(source)  # type: ignore[attr-defined]
                    if cached is None or cached[0] <= time.monotonic():
                        content_type, payload = fetch_launcher_camera_preview(source)
                        content_type, payload = launcher_thumbnail(content_type, payload, (480, 270))
                        cached = (time.monotonic() + 58, content_type, payload)
                        self.server.camera_preview_cache[source] = cached  # type: ignore[attr-defined]
                self.send_response(HTTPStatus.OK.value)
                self.send_header("Content-Type", cached[1])
                self.send_header("Content-Length", str(len(cached[2])))
                self.end_headers()
                self.wfile.write(cached[2])
            except (RequestError, RuntimeError, OSError, ValueError, urllib.error.URLError) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if request_path == "/api/tv-screen":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem kérhet TV-képet."})
                return
            try:
                payload = self.server.input_hook.tv_screen()  # type: ignore[attr-defined]
                self.send_response(HTTPStatus.OK.value)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (RuntimeError, subprocess.TimeoutExpired, socket.timeout, OSError) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if request_path == "/api/launcher/wallpaper":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem kérhet launcher-háttérképet."})
                return
            settings = self.server.launcher_store.snapshot()["settings"]  # type: ignore[attr-defined]
            try:
                index_text = parse_qs(request_url.query).get("index", [""])[0]
                index = int(index_text)
                if not settings["wallpaperEnabled"] or not 0 <= index < len(settings["wallpaperUrls"]):
                    raise RequestError("A háttérkép indexe érvénytelen.")
                url = settings["wallpaperUrls"][index]
                cached = self.server.wallpaper_cache.get(url)  # type: ignore[attr-defined]
                if cached is None or cached[0] <= time.monotonic():
                    content_type, payload = fetch_wallpaper(url)
                    content_type, payload = launcher_thumbnail(content_type, payload, (1280, 720))
                    cached = (time.monotonic() + 3600, content_type, payload)
                    self.server.wallpaper_cache[url] = cached  # type: ignore[attr-defined]
                self.send_response(HTTPStatus.OK.value)
                self.send_header("Content-Type", cached[1])
                self.send_header("Content-Length", str(len(cached[2])))
                self.end_headers()
                self.wfile.write(cached[2])
            except (RequestError, RuntimeError, OSError, ValueError, urllib.error.URLError) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if self.path == "/api/health":
            self.json_response(HTTPStatus.OK, {"ok": True, "service": "lgtv-control"})
            return
        if self.path == "/api/connections":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem olvashat kapcsolati beállítást."})
                return
            self.json_response(HTTPStatus.OK, {"ok": True, "connections": self.server.connection_store.snapshot()})  # type: ignore[attr-defined]
            return
        if self.path == "/api/launcher/state":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem olvashat launcher-beállítást."})
                return
            try:
                apps = self.launcher_apps()
                try:
                    last_app_id = self.server.launcher_home.last_app()  # type: ignore[attr-defined]
                except (RuntimeError, subprocess.TimeoutExpired):
                    last_app_id = ""
                if last_app_id and last_app_id not in {LAUNCHER_APP_ID, LAUNCHER_QUICK_APP_ID, LAUNCHER_OVERLAY_APP_ID, "com.webos.app.livetv"} and not last_app_id.startswith(("com.webos.app.hdmi", "com.webos.app.externalinput")):
                    last_app = next((item for item in apps if item.get("id") == last_app_id), None)
                    if last_app:
                        self.server.launcher_store.record_last("app", last_app_id, last_app.get("title", last_app_id))  # type: ignore[attr-defined]
                overlay = self.server.state_store.snapshot("media-overlay") or {}  # type: ignore[attr-defined]
                camera_state = self.server.state_store.snapshot("camera-viewer") or {}  # type: ignore[attr-defined]
                profiles = {
                    item["cameraId"]: item for item in camera_state.get("profiles", [])
                    if isinstance(item, dict) and isinstance(item.get("cameraId"), str)
                }
                presets = []
                for item in overlay.get("presets", []):
                    camera_id = str(item.get("cameraId") or "")
                    profile = profiles.get(camera_id)
                    preview_available = (
                        item.get("kind") == "image" and item.get("clickAction") == "openCamera" and profile is not None
                    )
                    presets.append({
                        "id": item["id"], "kind": item["kind"],
                        "content": item.get("content", ""),
                        "fit": item.get("fit", "cover"), "clickAction": item.get("clickAction", ""),
                        "cameraId": camera_id,
                        "previewAvailable": preview_available,
                        "previewUrl": launcher_profile_frame_url(profile) if preview_available else "",
                    })
                self.server.launcher_store.seed(apps, presets)  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {
                    "ok": True,
                    "config": self.server.launcher_store.snapshot(),  # type: ignore[attr-defined]
                    "apps": apps,
                    "presets": presets,
                    "icons": [dict(item) for item in LAUNCHER_ICON_CATALOG],
                })
            except (RequestError, RuntimeError, subprocess.TimeoutExpired) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if self.path == "/api/launcher/home-status":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem olvashat launcher-állapotot."})
                return
            try:
                self.json_response(HTTPStatus.OK, {
                    "ok": True,
                    "homeGuard": self.server.launcher_home.status(),  # type: ignore[attr-defined]
                    "launcherRunning": self.server.launcher_home.launcher_running("full"),  # type: ignore[attr-defined]
                })
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if self.path == "/api/launcher/diagnostics":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem olvashat TV-diagnosztikát."})
                return
            try:
                self.json_response(HTTPStatus.OK, {"ok": True, "diagnostics": self.server.input_hook.diagnostics()})  # type: ignore[attr-defined]
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        if self.path == "/api/launcher/weather":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem kérhet időjárást."})
                return
            settings = self.server.launcher_store.snapshot()["settings"]  # type: ignore[attr-defined]
            if not settings["weatherEnabled"]:
                self.json_response(HTTPStatus.OK, {"ok": True, "enabled": False})
                return
            cache_key = (settings["latitude"], settings["longitude"])
            cached = self.server.weather_cache  # type: ignore[attr-defined]
            if cached and cached[0] == cache_key and cached[1] > time.monotonic():
                self.json_response(HTTPStatus.OK, {"ok": True, "enabled": True, "weather": cached[2]})
                return
            weather_url = (
                "https://api.open-meteo.com/v1/forecast?latitude=" + quote(str(settings["latitude"]))
                + "&longitude=" + quote(str(settings["longitude"]))
                + "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day"
                + "&hourly=temperature_2m,apparent_temperature,precipitation_probability,weather_code,wind_speed_10m"
                + "&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max,sunrise,sunset"
                + "&timezone=auto&forecast_days=7&forecast_hours=36"
            )
            try:
                with urllib.request.urlopen(weather_url, timeout=5) as response:
                    raw_weather = json.loads(response.read(262_144).decode("utf-8"))
                daily = raw_weather["daily"]
                current = raw_weather.get("current") or {}
                hourly = raw_weather.get("hourly") or {}

                def hourly_value(name: str, index: int, default: Any = 0) -> Any:
                    values = hourly.get(name) or []
                    return values[index] if index < len(values) else default

                hourly_rows = [
                    {
                        "time": timestamp,
                        "temperature": hourly_value("temperature_2m", index),
                        "apparentTemperature": hourly_value("apparent_temperature", index),
                        "precipitationProbability": hourly_value("precipitation_probability", index),
                        "code": hourly_value("weather_code", index),
                        "windSpeed": hourly_value("wind_speed_10m", index),
                    }
                    for index, timestamp in enumerate((hourly.get("time") or [])[:36])
                ]

                def daily_value(name: str, index: int, default: Any = 0) -> Any:
                    values = daily.get(name) or []
                    return values[index] if index < len(values) else default

                daily_rows = [
                    {
                        "date": date,
                        "min": daily_value("temperature_2m_min", index),
                        "max": daily_value("temperature_2m_max", index),
                        "code": daily_value("weather_code", index),
                        "precipitationProbability": daily_value("precipitation_probability_max", index),
                        "sunrise": daily_value("sunrise", index, ""),
                        "sunset": daily_value("sunset", index, ""),
                    }
                    for index, date in enumerate((daily.get("time") or [])[:7])
                ]
                if not daily_rows:
                    raise ValueError("Az időjárási szolgáltató nem adott napi előrejelzést.")
                weather = {
                    "label": settings["weatherLabel"],
                    "timezone": raw_weather.get("timezone", ""),
                    "min": daily_rows[0]["min"],
                    "max": daily_rows[0]["max"],
                    "code": current.get("weather_code", daily_rows[0]["code"]),
                    "current": {
                        "time": current.get("time", ""),
                        "temperature": current.get("temperature_2m", daily_rows[0]["max"]),
                        "apparentTemperature": current.get("apparent_temperature", current.get("temperature_2m", daily_rows[0]["max"])),
                        "code": current.get("weather_code", daily_rows[0]["code"]),
                        "windSpeed": current.get("wind_speed_10m", 0),
                        "isDay": bool(current.get("is_day", 0)),
                    },
                    "hourly": hourly_rows,
                    "daily": daily_rows,
                }
                self.server.weather_cache = (cache_key, time.monotonic() + 900, weather)  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True, "enabled": True, "weather": weather})
            except (OSError, ValueError, KeyError, IndexError, urllib.error.URLError) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": "Az időjárás most nem kérhető le: " + str(error)[:160]})
            return
        if self.path == CAMERA_PRESENCE_PATH:
            if self.client_address[0] != self.server.tv_host:  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Csak a TV kérdezhet jelenléti állapotot."})
                return
            age = time.monotonic() - self.server.camera_presence_last_seen  # type: ignore[attr-defined]
            self.json_response(HTTPStatus.OK, {
                "ok": True,
                "active": 0 <= age < CAMERA_PRESENCE_TTL_SECONDS,
                "ttlSeconds": CAMERA_PRESENCE_TTL_SECONDS,
            })
            return
        if self.path == "/api/remote-mapper/runtime":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Tiltott hálózati cím."})
                return
            self.json_response(HTTPStatus.OK, {"ok": True, "runtime": self.server.remote_broker_switch.status()})
            return
        if self.path == "/api/remote-mapper/state":
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem olvashat gombkötést."})
                return
            try:
                result = self.server.input_hook.state()  # type: ignore[attr-defined]
                broker = getattr(self.server, "remote_broker", None)
                if broker is not None:
                    result["runtime"] = broker.status()
                result["hook"] = {
                    "id": "org.webosbrew.inputhook", "version": "1.4.0",
                    "enabled": bool(result.get("runtime", {}).get("nativeHookLoaded")),
                }
                result["shortcuts"] = remote_mapper_shortcuts(self.server.state_store)  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, result)
            except (RuntimeError, subprocess.TimeoutExpired) as error:
                self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})
            return
        state_paths = {
            "/api/media-overlay/state": "media-overlay",
            "/api/camera-viewer/state": "camera-viewer",
        }
        if self.path in state_paths:
            if not self.authorized_network():
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem olvashat TV-beállítást."})
                return
            module = state_paths[self.path]
            state = self.server.state_store.snapshot(module)  # type: ignore[attr-defined]
            self.json_response(HTTPStatus.OK, {"ok": True, "module": module, "config": state})
            return
        self.json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Nincs ilyen végpont."})

    def launch_with_sync(self, module: str, params: dict[str, Any]) -> dict[str, Any]:
        revision = self.server.state_store.revision(module)  # type: ignore[attr-defined]
        params = dict(params)
        params["syncUrl"] = self.server.sync_urls[module]  # type: ignore[attr-defined]
        self.server.launcher.launch(params, APP_IDS[module])  # type: ignore[attr-defined]
        state = self.server.state_store.wait_after(module, revision)  # type: ignore[attr-defined]
        if state is None:
            raise RuntimeError("A TV nem küldte vissza időben a friss konfigurációt.")
        return state

    def do_POST(self) -> None:
        if self.path == CAMERA_PRESENCE_PATH:
            if self.client_address[0] != self.server.tv_host:  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Csak a TV küldhet jelenléti állapotot."})
                return
            try:
                raw = self.read_json(sync_callback=True)
                if raw != {"active": True}:
                    raise RequestError("A kamera-jelenléti kérés érvénytelen.")
                self.server.camera_presence_last_seen = time.monotonic()  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True})
            except RequestError as error:
                self.json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
            return
        callback_paths = {
            "/api/tv-sync/media-overlay": "media-overlay",
            "/api/tv-sync/camera-viewer": "camera-viewer",
        }
        if self.path in callback_paths:
            if self.client_address[0] != self.server.tv_host:  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Csak a TV küldhet konfigurációt."})
                return
            try:
                module = callback_paths[self.path]
                raw = self.read_json(sync_callback=True)
                if not isinstance(raw, dict) or raw.get("module") != module or raw.get("version") != 1 or set(raw) != {"module", "version", "config"}:
                    raise RequestError("A TV szinkronkérése érvénytelen.")
                config = self.server.state_store.update(module, raw["config"])  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True, "module": module, "config": config})
            except RequestError as error:
                self.json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
            return
        if not self.authorized_network():
            self.json_response(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Ez a hálózati cím nem vezérelheti a TV-t."})
            return
        try:
            if self.path == "/api/tv/pairing":
                origin = self.headers.get("Origin")
                if origin and (urlsplit(origin).scheme not in {"http", "https"} or urlsplit(origin).netloc != self.headers.get("Host")):
                    raise RequestError("A párosítás csak a NAS saját webes felületéről indítható.")
                try:
                    result = self.server.ssap_pairing.command(self.read_json())
                except ValueError as error:
                    raise RequestError(str(error)) from error
                self.json_response(HTTPStatus.OK, {"ok": True, **result})
                return
            if self.path == "/api/tv/power":
                origin = self.headers.get("Origin")
                if origin and (urlsplit(origin).scheme not in {"http", "https"} or urlsplit(origin).netloc != self.headers.get("Host")):
                    raise RequestError("A TV-kapcsoló böngészőből csak a NAS saját webes felületéről használható.")
                requested = validate_tv_power_request(self.read_json())
                power = self.server.tv_power.set_state(requested)  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True, "requested": requested, "power": power})
                return
            if self.path == "/api/tv/reboot":
                origin = self.headers.get("Origin")
                if origin and (urlsplit(origin).scheme not in {"http", "https"} or urlsplit(origin).netloc != self.headers.get("Host")):
                    raise RequestError("A teljes újraindítás csak a NAS saját webes felületéről indítható.")
                raw = self.read_json()
                if raw != {"confirm": True}:
                    raise RequestError("A teljes újraindítást meg kell erősíteni.")
                result = self.server.tv_power.reboot()  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True, "reboot": result})
                return
            if self.path == "/api/remote-mapper/runtime":
                origin = self.headers.get("Origin")
                if origin and (urlsplit(origin).scheme not in {"http", "https"} or urlsplit(origin).netloc != self.headers.get("Host")):
                    raise RequestError("A kapcsoló csak a NAS saját webes felületéről használható.")
                runtime = self.server.remote_broker_switch.set_enabled(self.read_json())
                self.json_response(HTTPStatus.OK, {"ok": True, "runtime": runtime})
                return
            if self.path in {"/api/remote-mapper/bind", "/api/remote-mapper/restore"}:
                raw = self.read_json(allow_text_plain=True)
                if self.path == "/api/remote-mapper/bind":
                    shortcuts = remote_mapper_shortcuts(self.server.state_store)  # type: ignore[attr-defined]
                    result = self.server.input_hook.update_binding(raw, shortcuts)  # type: ignore[attr-defined]
                else:
                    result = self.server.input_hook.restore(validate_remote_restore_request(raw))  # type: ignore[attr-defined]
                broker = getattr(self.server, "remote_broker", None)
                if broker is not None:
                    if broker.enabled:
                        try:
                            broker.sync_bindings(result["bindings"])
                        except (RuntimeError, subprocess.TimeoutExpired) as error:
                            result["runtimeSyncError"] = str(error)
                    result["runtime"] = broker.status()
                result["hook"] = {
                    "id": "org.webosbrew.inputhook", "version": "1.4.0",
                    "enabled": bool(result.get("runtime", {}).get("nativeHookLoaded")),
                }
                result["shortcuts"] = remote_mapper_shortcuts(self.server.state_store)  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, result)
                return
            if self.path == "/api/tv-key":
                raw_key = self.read_json(allow_text_plain=True)
                if not isinstance(raw_key, dict) or set(raw_key) != {"key"}:
                    raise RequestError("A távirányító-kérés érvénytelen.")
                key_name = str(raw_key.get("key") or "")
                self.server.input_hook.tv_key(key_name)  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True, "key": key_name})
                return
            if self.path == "/api/connections":
                connections = self.server.connection_store.update(self.read_json())  # type: ignore[attr-defined]
                self.server.tv_host = connections["tvHost"]  # type: ignore[attr-defined]
                self.server.launcher.tv_host = connections["tvHost"]  # type: ignore[attr-defined]
                self.server.input_hook.tv_host = connections["tvHost"]  # type: ignore[attr-defined]
                self.server.launcher_home.tv_host = connections["tvHost"]  # type: ignore[attr-defined]
                self.server.input_hook_watchdog.tv_host = connections["tvHost"]  # type: ignore[attr-defined]
                self.server.remote_broker.tv_host = connections["tvHost"]  # type: ignore[attr-defined]
                self.server.tv_power.tv_host = connections["tvHost"]  # type: ignore[attr-defined]
                self.server.sync_urls = {module: connections["controlOrigin"] + "/api/tv-sync/" + module for module in ("media-overlay", "camera-viewer")}  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True, "connections": connections})
                return
            if self.path == "/api/launcher/config":
                # The TV launcher uses a text/plain JSON body for cross-origin
                # requests so that the webOS browser does not need an OPTIONS
                # preflight. Accept that transport here just like launch.
                checked = validate_launcher_config(self.read_json(allow_text_plain=True))
                installed = {item["id"] for item in self.server.input_hook.list_apps(include_system_inputs=True)}  # type: ignore[attr-defined]
                overlay = self.server.state_store.snapshot("media-overlay") or {}  # type: ignore[attr-defined]
                preset_ids = {item["id"] for item in overlay.get("presets", [])}
                for row in checked["rows"]:
                    for item in row["items"]:
                        if item["type"] == "app" and item["targetId"] not in installed:
                            raise RequestError("Csak a TV-re telepített alkalmazás tehető a launcherbe.")
                        if item["type"] == "preset" and item["targetId"] not in preset_ids:
                            raise RequestError("Csak szinkronizált PiP preset tehető a launcherbe.")
                previous = self.server.launcher_store.snapshot()  # type: ignore[attr-defined]
                desired_home = checked["settings"]["defaultHomeEnabled"]
                previous_home = previous["settings"].get("defaultHomeEnabled", False)
                desired_resume = checked["settings"]["resumeLastAppOnPowerEnabled"]
                previous_resume = previous["settings"].get("resumeLastAppOnPowerEnabled", False)
                desired_home_mode = checked["settings"]["homeLaunchMode"]
                previous_home_mode = previous["settings"].get("homeLaunchMode", "split")
                presentation = checked["settings"]["fullLauncherPresentation"]
                if presentation == "overlay" and LAUNCHER_OVERLAY_APP_ID not in installed:
                    raise RequestError("A teljes overlay launcher még nincs telepítve.")
                if presentation != previous["settings"].get("fullLauncherPresentation", "app"):
                    self.server.launcher_home.set_full_presentation(presentation)
                self.server.launcher_home.set_display_preferences(checked["settings"])
                home_guard = None
                if desired_resume != previous_resume:
                    self.server.launcher_home.set_resume_last_app(desired_resume)  # type: ignore[attr-defined]
                if desired_home_mode != previous_home_mode:
                    self.server.launcher_home.set_home_launch_mode(desired_home_mode)  # type: ignore[attr-defined]
                if desired_home != previous_home:
                    home_guard = self.server.launcher_home.set_enabled(desired_home)  # type: ignore[attr-defined]
                saved = self.server.launcher_store.update(checked)  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True, "config": saved, "homeGuard": home_guard})
                return
            if self.path == "/api/launcher/hidden":
                host = self.server.launcher_home.host_from_request(self.read_json(allow_text_plain=True))
                if host == "full":
                    raise RequestError("Csak az overlay launcher rejthető el natívan.")
                self.json_response(HTTPStatus.OK, {"ok": True, "scheduled": "hidden"})
                run_daemon_after(0, "Launcher hidden", lambda: self.server.launcher_home.mark_launcher_hidden(host))
                return
            if self.path == "/api/launcher/park":
                host = LauncherHomeManager.host_from_request(self.read_json(allow_text_plain=True))
                if host == "full":
                    result = self.server.launcher_home.park_launcher(host)  # type: ignore[attr-defined]
                    self.json_response(HTTPStatus.OK, {"ok": True, "response": result})
                    return
                self.json_response(HTTPStatus.OK, {"ok": True, "scheduled": "park"})
                run_daemon_after(0.1, "Launcher park", lambda: self.server.launcher_home.park_launcher(host))  # type: ignore[attr-defined]
                return
            if self.path == "/api/launcher/visible":
                host = LauncherHomeManager.host_from_request(self.read_json(allow_text_plain=True))
                self.json_response(HTTPStatus.OK, {"ok": True, "scheduled": "visible"})
                run_daemon_after(0, "Launcher visible", lambda: self.server.launcher_home.mark_launcher_visible(host))  # type: ignore[attr-defined]
                return
            if self.path == "/api/launcher/prewarm-ready":
                host = LauncherHomeManager.host_from_request(self.read_json(allow_text_plain=True))
                self.json_response(HTTPStatus.OK, {"ok": True, "scheduled": "prewarm-ready"})
                run_daemon_after(0, "Launcher prewarm-ready", lambda: self.server.launcher_home.mark_launcher_prewarm_ready(host))  # type: ignore[attr-defined]
                return
            if self.path == "/api/launcher/restart":
                host = LauncherHomeManager.host_from_request(self.read_json(allow_text_plain=True))

                def restart_launcher() -> None:
                    self.server.launcher_home.terminate_launcher(host)  # type: ignore[attr-defined]
                    if not self.server.launcher_home.wait_launcher_state(False, 6.0, host):  # type: ignore[attr-defined]
                        raise RuntimeError("A régi launcher-folyamat nem állt le időben.")
                    time.sleep(0.25)
                    launch_error = None
                    for attempt in range(2):
                        try:
                            self.server.launcher.launch(  # type: ignore[attr-defined]
                                {"mode": LAUNCHER_HOSTS[host]["mode"], "source": "settings-restart",
                                 "controlOrigin": self.server.connection_store.snapshot()["controlOrigin"]}, LAUNCHER_HOSTS[host]["appId"]
                            )
                        except Exception as error:
                            launch_error = error
                            # A régi webOS néha elveszíti a Luna választ annak
                            # ellenére, hogy az alkalmazást már elindította.
                            if self.server.launcher_home.wait_launcher_state(True, 1.5, host):  # type: ignore[attr-defined]
                                break
                            if attempt == 0:
                                time.sleep(0.5)
                                continue
                            raise
                        if self.server.launcher_home.wait_launcher_state(True, 4.0, host):  # type: ignore[attr-defined]
                            break
                        if attempt == 0:
                            time.sleep(0.5)
                    else:
                        raise RuntimeError("A launcher új folyamata nem indult el.") from launch_error
                    self.server.launcher_home.mark_launcher_visible(host)  # type: ignore[attr-defined]

                run_daemon_after(0.35, "Launcher restart", restart_launcher)
                self.json_response(HTTPStatus.OK, {"ok": True, "scheduled": "restart"})
                return
            if self.path == "/api/launcher/system-home":
                raw_home = self.read_json(allow_text_plain=True)
                if raw_home != {}:
                    raise RequestError("A gyári kezdőképernyő kérése érvénytelen.")
                self.server.launcher_home.allow_factory_home()  # type: ignore[attr-defined]
                try:
                    response = self.server.launcher.launch({}, "com.webos.app.home", allow_any=True)  # type: ignore[attr-defined]
                except Exception:
                    self.server.launcher_home.revoke_factory_home()  # type: ignore[attr-defined]
                    raise
                self.json_response(HTTPStatus.OK, {"ok": True, "response": response})
                return
            if self.path == "/api/launcher/launch":
                launch_request = validate_launcher_launch_request(self.read_json(allow_text_plain=True))
                item_type = launch_request["type"]
                target_id = launch_request["targetId"]
                label = launch_request["label"]
                webhook_status = None
                if item_type == "app":
                    if target_id not in {item["id"] for item in self.server.input_hook.list_apps(include_system_inputs=True)}:  # type: ignore[attr-defined]
                        raise RequestError("Az alkalmazás nincs a TV telepített alkalmazásai között.")
                    self.server.launcher.launch({}, target_id, allow_any=True)  # type: ignore[attr-defined]
                elif item_type == "preset":
                    overlay = self.server.state_store.snapshot("media-overlay") or {}  # type: ignore[attr-defined]
                    preset = next((item for item in overlay.get("presets", []) if item.get("id") == target_id), None)
                    if not isinstance(preset, dict):
                        raise RequestError("A PiP preset nem található.")
                    camera_id = str(preset.get("cameraId") or "")
                    if preset.get("clickAction") == "openCamera" and camera_id:
                        camera_state = self.server.state_store.snapshot("camera-viewer") or {}  # type: ignore[attr-defined]
                        if camera_id not in {item.get("cameraId") for item in camera_state.get("profiles", [])}:
                            raise RequestError("A presethez tartozó kamera nincs szinkronizálva.")
                        params = {"v": 1, "action": "open", "cameraId": camera_id, "view": "full"}
                        self.server.launcher.launch(params, CAMERA_APP_ID)  # type: ignore[attr-defined]
                    else:
                        params = {"v": 1, "action": "show", "presetId": target_id, "syncUrl": self.server.sync_urls["media-overlay"]}  # type: ignore[attr-defined]
                        self.server.launcher.launch(params, APP_ID)  # type: ignore[attr-defined]
                elif item_type == "link" and launch_request["linkMode"] == "webhook":
                    webhook_status = send_launcher_webhook(
                        target_id, launch_request["webhookMethod"], launch_request["webhookBody"]
                    )
                elif item_type == "link":
                    installed = {item["id"] for item in self.server.input_hook.list_apps(include_system_inputs=True)}  # type: ignore[attr-defined]
                    browser_id = "com.webos.app.browser"
                    if browser_id not in installed:
                        raise RequestError("A webOS böngésző nem található a TV-n.")
                    self.server.launcher.launch({"target": target_id}, browser_id, allow_any=True)  # type: ignore[attr-defined]
                else:
                    raise RequestError("Ez a launcher-művelet nem indítható.")
                self.server.launcher_store.record_last(item_type, target_id, label)  # type: ignore[attr-defined]
                response = {"ok": True, "lastUsed": self.server.launcher_store.snapshot()["lastUsed"]}  # type: ignore[attr-defined]
                if webhook_status is not None:
                    response["webhookStatus"] = webhook_status
                self.json_response(HTTPStatus.OK, response)
                return
            raw = self.read_json()
            module = "media-overlay"
            sync_response = False
            if self.path == "/api/show":
                params = validate_show_request(raw)
            elif self.path == "/api/configure":
                params = validate_configure_request(raw)
            elif self.path == "/api/presets/save":
                params = validate_preset_save_request(raw)
            elif self.path == "/api/presets/delete":
                params = validate_preset_delete_request(raw)
                sync_response = True
            elif self.path == "/api/media-overlay/sync":
                if raw != {}:
                    raise RequestError("A szinkronkérés törzse üres JSON objektum legyen.")
                params = {"v": 1, "action": "sync", "requestId": secrets.token_hex(16)}
                sync_response = True
            elif self.path == "/api/camera-viewer/sync":
                if raw != {}:
                    raise RequestError("A szinkronkérés törzse üres JSON objektum legyen.")
                module = "camera-viewer"
                params = {"v": 1, "action": "sync", "requestId": secrets.token_hex(16)}
                sync_response = True
            elif self.path == "/api/cameras/save":
                module = "camera-viewer"
                params = validate_camera_save_request(raw)
                sync_response = True
            elif self.path == "/api/cameras/delete":
                module = "camera-viewer"
                params = validate_camera_delete_request(raw)
                sync_response = True
            elif self.path == "/api/cameras/configure":
                module = "camera-viewer"
                params = validate_camera_configure_request(raw)
                sync_response = True
            elif self.path == "/api/cameras/reorder":
                module = "camera-viewer"
                params = validate_camera_reorder_request(raw)
                sync_response = True
            elif self.path == "/api/cameras/open":
                module = "camera-viewer"
                params = validate_camera_open_request(raw)
            elif self.path == "/api/dismiss":
                if raw != {}:
                    raise RequestError("A bezárási kérés törzse üres JSON objektum legyen.")
                params = {"v": 1, "action": "dismiss", "requestId": secrets.token_hex(16)}
            else:
                self.json_response(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Nincs ilyen végpont."})
                return
            if self.path in {"/api/configure", "/api/presets/save"}:
                sync_response = True
            if sync_response:
                state = self.launch_with_sync(module, params)
                self.json_response(HTTPStatus.OK, {"ok": True, "action": params["action"], "config": state})
            else:
                if module in self.server.sync_urls:  # type: ignore[attr-defined]
                    params = dict(params)
                    params.setdefault("syncUrl", self.server.sync_urls[module])  # type: ignore[attr-defined]
                self.server.launcher.launch(params, APP_IDS[module])  # type: ignore[attr-defined]
                self.json_response(HTTPStatus.OK, {"ok": True, "action": params["action"]})
        except RequestError as error:
            self.json_response(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(error)})
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
            self.json_response(HTTPStatus.BAD_GATEWAY, {"ok": False, "error": str(error)})


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("A konfiguráció JSON objektum legyen.")
    allowed = config.get("allowed_networks", ["127.0.0.0/8"])
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("Az allowed_networks nem üres lista legyen.")
    try:
        config["_allowed_networks"] = tuple(ipaddress.ip_network(str(value), strict=True) for value in allowed)
    except ValueError as error:
        raise ValueError("Az allowed_networks egyik eleme érvénytelen.") from error
    public_base_url = str(config.get("public_base_url") or "").rstrip("/")
    try:
        parsed = urlsplit(public_base_url)
        validate_private_host(parsed.hostname)
        if parsed.scheme != "http" or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
    except (ValueError, RequestError) as error:
        raise ValueError("A public_base_url teljes, privát IPv4-es HTTP-origin legyen.") from error
    config["_public_base_url"] = public_base_url
    watchdog_enabled = config.get("input_hook_watchdog_enabled", False)
    if not isinstance(watchdog_enabled, bool):
        raise ValueError("Az input_hook_watchdog_enabled logikai érték legyen.")
    config["input_hook_watchdog_enabled"] = watchdog_enabled
    broker_enabled = config.get("remote_broker_enabled", False)
    if not isinstance(broker_enabled, bool):
        raise ValueError("A remote_broker_enabled logikai érték legyen.")
    broker_mode = str(config.get("remote_broker_mode", "passive"))
    if broker_mode not in {"passive", "grab"}:
        raise ValueError("A remote_broker_mode passive vagy grab legyen.")
    if broker_enabled and broker_mode != "grab":
        raise ValueError("Engedélyezett Remote Broker csak grab módban futhat; a passive mód diagnosztikára való.")
    config["remote_broker_enabled"] = broker_enabled
    config["remote_broker_mode"] = broker_mode
    wifi_mac = str(config.get("tv_wifi_mac") or "").lower()
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", wifi_mac):
        raise ValueError("A tv_wifi_mac hat kettősponttal elválasztott hexadecimális pár legyen.")
    mac_bytes = bytes.fromhex(wifi_mac.replace(":", ""))
    if not any(mac_bytes) or mac_bytes[0] & 1:
        raise ValueError("A tv_wifi_mac egyedi Wi-Fi interfészcím legyen.")
    config["tv_wifi_mac"] = wifi_mac
    wake_broadcasts = config.get("tv_wake_broadcasts")
    if not isinstance(wake_broadcasts, list) or not 1 <= len(wake_broadcasts) <= 4:
        raise ValueError("A tv_wake_broadcasts 1–4 IPv4-címet tartalmazó lista legyen.")
    normalized_broadcasts = []
    try:
        for value in wake_broadcasts:
            address = ipaddress.ip_address(str(value))
            if not isinstance(address, ipaddress.IPv4Address) or address.is_loopback or address.is_multicast or address.is_unspecified:
                raise ValueError
            normalized_broadcasts.append(str(address))
    except ValueError as error:
        raise ValueError("A tv_wake_broadcasts egyik eleme érvénytelen IPv4-cím.") from error
    config["tv_wake_broadcasts"] = tuple(normalized_broadcasts)
    return config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    listen_host = str(config.get("listen_host", "127.0.0.1"))
    listen_port = canonical_integer(config.get("listen_port", 8765), 1, 65535, "listen_port")
    server = ThreadingHTTPServer((listen_host, listen_port), ControlHandler)
    server.daemon_threads = True
    server.allowed_networks = config["_allowed_networks"]  # type: ignore[attr-defined]
    state_path = Path(str(config.get("state_path", "/var/lib/lgtv-control/state.json")))
    server.state_store = StateStore(state_path)  # type: ignore[attr-defined]
    connection_path = Path(str(config.get("connection_state_path", "/var/lib/lgtv-control/connections.json")))
    server.connection_store = ConnectionStore(connection_path, config, server.state_store)  # type: ignore[attr-defined]
    connections = server.connection_store.snapshot()  # type: ignore[attr-defined]
    effective_config = dict(config)
    effective_config["tv_host"] = connections["tvHost"]
    effective_config["control_origin"] = connections["controlOrigin"]
    server.launcher = TvLauncher(effective_config)  # type: ignore[attr-defined]
    server.tv_power = TvPowerManager(effective_config)  # type: ignore[attr-defined]
    server.input_hook = InputHookManager(effective_config)  # type: ignore[attr-defined]
    server.launcher_home = LauncherHomeManager(effective_config)  # type: ignore[attr-defined]
    server.input_hook_watchdog = InputHookWatchdogManager(effective_config)  # type: ignore[attr-defined]
    server.remote_broker = RemoteBrokerManager(effective_config)  # type: ignore[attr-defined]
    server.remote_broker_switch = RemoteBrokerSwitch(
        Path(str(config.get("remote_broker_state_path", "/var/lib/lgtv-control/remote-broker-switch.json"))),
        server.remote_broker, server.input_hook)
    server.tv_host = connections["tvHost"]  # type: ignore[attr-defined]
    from ssap_pairing import PairingManager
    def pairing_dialog_visible() -> bool:
        output = server.launcher_home._run("luna-send -t 1 -f -w 1000 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>&1")
        response = parse_luna_response(output)
        return any(row.get("appId") in {"com.webos.app.notification", "com.webos.app.alert"}
                   for row in response.get("windows", []) if isinstance(row, dict))
    server.ssap_pairing = PairingManager(
        lambda: server.tv_host,
        Path(str(config.get("ssap_credentials_path", "/var/lib/lgtv-control/lg-ssap.json"))),
        lambda: server.input_hook.tv_key("ok"), pairing_dialog_visible)
    server.camera_presence_last_seen = 0.0  # type: ignore[attr-defined]
    server.sync_urls = {  # type: ignore[attr-defined]
        module: connections["controlOrigin"] + "/api/tv-sync/" + module for module in ("media-overlay", "camera-viewer")
    }
    launcher_path = Path(str(config.get("launcher_state_path", "/var/lib/lgtv-control/launcher.json")))
    server.launcher_store = LauncherStore(launcher_path)  # type: ignore[attr-defined]
    launcher_apps_path = Path(str(config.get("launcher_apps_state_path", "/var/lib/lgtv-control/launcher-apps.json")))
    server.launcher_app_catalog = LauncherAppCatalog(launcher_apps_path)  # type: ignore[attr-defined]
    server.app_icon_cache = {}  # type: ignore[attr-defined]
    server.weather_cache = None  # type: ignore[attr-defined]
    server.wallpaper_cache = {}  # type: ignore[attr-defined]
    server.camera_preview_cache = {}  # type: ignore[attr-defined]
    server.camera_preview_locks = {}  # type: ignore[attr-defined]
    server.camera_preview_locks_guard = threading.Lock()  # type: ignore[attr-defined]
    static_root = Path(__file__).parent / "static"
    server.index_html = (static_root / "index.html").read_bytes()  # type: ignore[attr-defined]
    server.broker_control_js = (static_root / "broker-control.js").read_bytes()
    server.power_control_js = (static_root / "power-control.js").read_bytes()  # type: ignore[attr-defined]
    server.ssap_control_js = (static_root / "ssap-control.js").read_bytes()
    remote_ui_root = static_root
    if not (remote_ui_root / "remote-ui.js").is_file():
        remote_ui_root = Path(__file__).parent.parent / "apps" / "remote-mapper"
    server.remote_ui_css = (remote_ui_root / "remote-ui.css").read_bytes()  # type: ignore[attr-defined]
    server.remote_ui_js = (remote_ui_root / "remote-ui.js").read_bytes()  # type: ignore[attr-defined]
    server.connections_ui_js = (static_root / "connections-ui.js").read_bytes()  # type: ignore[attr-defined]
    launcher_root = static_root
    if not (launcher_root / "launcher-ui.js").is_file():
        launcher_root = Path(__file__).parent.parent / "apps" / "launcher"
    server.launcher_ui_js = (launcher_root / "launcher-ui.js").read_bytes()  # type: ignore[attr-defined]
    server.launcher_css = (launcher_root / "launcher.css").read_bytes()  # type: ignore[attr-defined]
    server.launcher_admin_js = (static_root / "launcher-admin.js").read_bytes()
    server.dashboard_control_js = (static_root / "dashboard-control.js").read_bytes()  # type: ignore[attr-defined]
    def install_tv_supervisors() -> None:
        try:
            # Guard lifecycle is independent from every low-level input engine.
            # A disabled native hook must never prevent guard/home/prewarm sync.
            server.launcher_home.sync_files()  # type: ignore[attr-defined]
            launcher_settings = server.launcher_store.snapshot()["settings"]  # type: ignore[attr-defined]
            resume_enabled = launcher_settings.get("resumeLastAppOnPowerEnabled", False)
            server.launcher_home.set_resume_last_app(bool(resume_enabled))  # type: ignore[attr-defined]
            server.launcher_home.set_display_preferences(launcher_settings)
            server.launcher_home.set_full_presentation(str(launcher_settings.get("fullLauncherPresentation", "app")))
            server.launcher_home.set_home_launch_mode(str(launcher_settings.get("homeLaunchMode", "split")))  # type: ignore[attr-defined]

            native_hook_enabled = config.get("input_hook_watchdog_enabled", False) is True
            server.input_hook_watchdog.set_enabled(native_hook_enabled)  # type: ignore[attr-defined]
            server.remote_broker_switch.restore()
            broker_enabled = server.remote_broker.enabled
            print(
                "TV launcher guard files synced; native Input Hook "
                + ("active" if native_hook_enabled else "disabled")
                + "; Remote Broker " + ("active" if broker_enabled else "disabled"),
                flush=True,
            )
        except Exception as error:
            print("TV supervisor setup failed: " + str(error), flush=True)
    threading.Thread(target=install_tv_supervisors, daemon=True).start()
    print(f"LGTV control listening on http://{listen_host}:{listen_port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
