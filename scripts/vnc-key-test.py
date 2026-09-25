#!/usr/bin/env python3
"""Send a short, allowlisted VNC navigation sequence to the test TV."""

import importlib.util
import json
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path


KEYS = {
    "left": 0xFF51,
    "up": 0xFF52,
    "right": 0xFF53,
    "down": 0xFF54,
    "ok": 0xFF0D,
    "back": 0xFF1B,
}


def main() -> None:
    tokens = [token.casefold() for token in sys.argv[1:]]
    if not tokens or len(tokens) > 16 or any(token not in KEYS and token != "pointer" for token in tokens):
        raise SystemExit("usage: vnc-key-test.py [pointer] left|up|right|down|ok|back ... (max 16)")

    source = Path(__file__).resolve().parents[1] / "remote-control" / "server.py"
    spec = importlib.util.spec_from_file_location("lgtv_server", source)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    ssh = [
        "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "UserKnownHostsFile=/tmp/codex-lgtv-known", "-i", "/tmp/codex-lgtv-key",
        "root@192.168.0.240",
    ]
    raw = subprocess.check_output(ssh + ["cat", server.VNC_CONFIG], text=True, timeout=8)
    password = str(json.loads(raw).get("password") or "")
    if not password:
        raise RuntimeError("missing VNC password")

    with socket.create_connection(("192.168.0.240", 5900), timeout=5) as connection:
        connection.settimeout(8)
        server._recv_exact(connection, 12)
        connection.sendall(b"RFB 003.008\n")
        count = server._recv_exact(connection, 1)[0]
        types = server._recv_exact(connection, count)
        if 2 in types:
            connection.sendall(b"\x02")
            connection.sendall(server._vnc_response(password, server._recv_exact(connection, 16)))
            if struct.unpack("!I", server._recv_exact(connection, 4))[0] != 0:
                raise RuntimeError("VNC authentication failed")
        elif 1 in types:
            connection.sendall(b"\x01")
            if struct.unpack("!I", server._recv_exact(connection, 4))[0] != 0:
                raise RuntimeError("VNC security failed")
        else:
            raise RuntimeError("unsupported VNC security")
        connection.sendall(b"\x01")
        width, height = struct.unpack("!HH", server._recv_exact(connection, 4))
        server._recv_exact(connection, 16)
        name_length = struct.unpack("!I", server._recv_exact(connection, 4))[0]
        server._recv_exact(connection, name_length)
        for token in tokens:
            if token == "pointer":
                connection.sendall(struct.pack("!BBHH", 5, 0, min(width - 1, 980), min(height - 1, 330)))
            else:
                key = KEYS[token]
                connection.sendall(struct.pack("!BBxxI", 4, 1, key))
                connection.sendall(struct.pack("!BBxxI", 4, 0, key))
            time.sleep(0.6)
    print("VNC_KEY_TEST_PASS " + " ".join(tokens))


if __name__ == "__main__":
    main()
