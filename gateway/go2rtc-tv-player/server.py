#!/usr/bin/env python3
"""Narrow same-origin bridge for the webOS Camera Viewer.

It serves only the bundled TV player assets and proxies only go2rtc's WebSocket
consumer endpoint.  It intentionally exposes no go2rtc administration API.
"""

import os
import socket
import socketserver
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


BIND_HOST = os.environ.get("PLAYER_BIND_HOST", "192.168.0.150")
BIND_PORT = int(os.environ.get("PLAYER_BIND_PORT", "1985"))
UPSTREAM_HOST = os.environ.get("GO2RTC_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("GO2RTC_PORT", "1984"))
ALLOWED_CLIENT = os.environ.get("PLAYER_ALLOWED_CLIENT", "192.168.0.240")
PUBLIC_HOST = os.environ.get("PLAYER_PUBLIC_HOST", "%s:%d" % (BIND_HOST, BIND_PORT))
EXPECTED_ORIGIN = "http://" + PUBLIC_HOST
ASSET_DIR = Path(os.environ.get("PLAYER_ASSET_DIR", "/opt/go2rtc-tv-player"))
MAX_HEADER_BYTES = 16 * 1024
SAFE_SOURCE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
ASSETS = {
    "/webos-player.html": ("webos-player.html", "text/html; charset=utf-8"),
    "/webos-player.js": ("webos-player.js", "application/javascript; charset=utf-8"),
    "/screen-guard.mp4": ("screen-guard.mp4", "video/mp4"),
}


def send_response(sock, status, reason, body=b"", content_type="text/plain; charset=utf-8"):
    headers = [
        "HTTP/1.1 %d %s" % (status, reason),
        "Content-Type: " + content_type,
        "Content-Length: %d" % len(body),
        "Cache-Control: no-store",
        "X-Content-Type-Options: nosniff",
        "Referrer-Policy: no-referrer",
        "Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; media-src blob:; connect-src 'self' ws://%s; frame-ancestors file:; base-uri 'none'; form-action 'none'" % PUBLIC_HOST,
        "Connection: close",
        "",
        "",
    ]
    sock.sendall("\r\n".join(headers).encode("ascii") + body)


def read_headers(sock):
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ValueError("connection closed before headers")
        data.extend(chunk)
        if len(data) > MAX_HEADER_BYTES:
            raise ValueError("headers too large")
    end = data.index(b"\r\n\r\n") + 4
    return bytes(data[:end]), bytes(data[end:])


def parse_request(raw):
    text = raw.decode("iso-8859-1")
    lines = text.split("\r\n")
    first = lines[0].split(" ")
    if len(first) != 3:
        raise ValueError("bad request line")
    method, target, version = first
    if method != "GET" or version != "HTTP/1.1":
        raise ValueError("unsupported request")
    headers = {}
    for line in lines[1:]:
        if not line:
            break
        if ":" not in line:
            raise ValueError("bad header")
        name, value = line.split(":", 1)
        key = name.strip().lower()
        if key in headers:
            raise ValueError("duplicate header")
        headers[key] = value.strip()
    return target, headers


def valid_source(target):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.path != "/api/ws" or parsed.fragment:
        return False
    try:
        values = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    if set(values) != {"src"} or len(values["src"]) != 1:
        return False
    source = values["src"][0]
    return (
        1 <= len(source) <= 64
        and all(ch in SAFE_SOURCE_CHARS for ch in source)
        and not (
            len(source.split(".")) == 4
            and all(part.isdigit() for part in source.split("."))
        )
    )


def relay(client, upstream, initial):
    if initial:
        upstream.sendall(initial)

    finished = threading.Event()

    def copy(source, destination):
        try:
            while not finished.is_set():
                data = source.recv(65536)
                if not data:
                    break
                destination.sendall(data)
        except OSError:
            pass
        finally:
            finished.set()
            for current in (source, destination):
                try:
                    current.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    upstream_to_client = threading.Thread(target=copy, args=(upstream, client), daemon=True)
    upstream_to_client.start()
    try:
        copy(client, upstream)
    finally:
        upstream_to_client.join(timeout=2)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        if self.client_address[0] not in (ALLOWED_CLIENT, BIND_HOST, "127.0.0.1", "::1"):
            send_response(self.request, 403, "Forbidden")
            return
        try:
            raw, extra = read_headers(self.request)
            target, headers = parse_request(raw)
        except (OSError, UnicodeError, ValueError):
            send_response(self.request, 400, "Bad Request")
            return

        parsed = urlsplit(target)
        if parsed.path == "/healthz" and not parsed.query:
            send_response(self.request, 200, "OK", b"ok\n")
            return

        asset = ASSETS.get(parsed.path)
        if asset and not parsed.query and not parsed.fragment:
            path = ASSET_DIR / asset[0]
            try:
                body = path.read_bytes()
            except OSError:
                send_response(self.request, 503, "Service Unavailable")
                return
            send_response(self.request, 200, "OK", body, asset[1])
            return

        if not valid_source(target):
            send_response(self.request, 404, "Not Found")
            return
        if headers.get("host") != PUBLIC_HOST or headers.get("origin") != EXPECTED_ORIGIN:
            send_response(self.request, 403, "Forbidden")
            return
        if headers.get("upgrade", "").lower() != "websocket":
            send_response(self.request, 400, "Bad Request")
            return

        try:
            upstream = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=5)
            # Limit only the TCP connect.  A healthy WebRTC signaling socket may
            # otherwise be idle for much longer than five seconds.
            upstream.settimeout(None)
            upstream.sendall(raw)
            relay(self.request, upstream, extra)
        except OSError:
            try:
                send_response(self.request, 502, "Bad Gateway")
            except OSError:
                pass
        finally:
            if "upstream" in locals():
                upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    if ALLOWED_CLIENT == "192.168.0.100":
        raise SystemExit("refusing forbidden client")
    with Server((BIND_HOST, BIND_PORT), Handler) as server:
        server.serve_forever(poll_interval=0.5)
