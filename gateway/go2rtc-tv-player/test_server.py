#!/usr/bin/env python3
import importlib.util
import inspect
import socket
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("server.py")
SPEC = importlib.util.spec_from_file_location("go2rtc_tv_player_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


expect(SERVER.valid_source("/api/ws?src=camera_kapu_felso_h264"), "valid alias rejected")
expect(SERVER.valid_source("/api/ws?src=c210rtsp1"), "Gyerekszoba H264 alias rejected")
expect(SERVER.valid_source("/api/ws?src=camera1"), "arbitrary safe alias rejected")
for invalid in (
    "/api/ws",
    "/api/ws?src=",
    "/api/ws?src=http://192.168.0.100/x",
    "/api/ws?src=camera1&dst=camera2",
    "/api/config?src=camera1",
    "http://192.168.0.100/api/ws?src=camera1",
    "/api/ws?src=camera%2Fone",
    "/api/ws?src=camera1#fragment",
    "/api/ws?src=192.168.0.100",
):
    expect(not SERVER.valid_source(invalid), "invalid source accepted: " + invalid)

target, headers = SERVER.parse_request(
    b"GET /api/ws?src=camera1 HTTP/1.1\r\nHost: 192.168.0.150:1985\r\n"
    b"Origin: http://192.168.0.150:1985\r\nUpgrade: websocket\r\n\r\n"
)
expect(target == "/api/ws?src=camera1", "wrong target")
expect(headers["origin"] == "http://192.168.0.150:1985", "wrong origin")

left, right = socket.socketpair()
try:
    SERVER.send_response(left, 200, "OK", b"ok\n")
    response = right.recv(8192)
finally:
    left.close()
    right.close()
expect(b"Content-Length: 3" in response, "missing content length")
expect(b"X-Frame-Options" not in response, "file-origin iframe would be blocked")
expect(b"frame-ancestors file:" in response, "file-origin frame policy missing")
expect("/screen-guard.mp4" in SERVER.ASSETS, "screen guard asset missing")
handler_source = inspect.getsource(SERVER.Handler.handle)
expect("upstream.settimeout(None)" in handler_source, "upstream WebSocket must not inherit the connect timeout")

print("go2rtc TV-player proxy tests: PASS")
