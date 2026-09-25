"""Small synchronous LG SSAP client. One caller/thread owns each connection.

Protocol/endpoint references (not an official LG protocol specification):
https://github.com/home-assistant-libs/aiowebostv/blob/main/aiowebostv/handshake.py
https://github.com/home-assistant-libs/aiowebostv/blob/main/aiowebostv/endpoints.py

The TV uses a self-signed certificate. Explicit pairing establishes a certificate
pin; ordinary connections check it BEFORE transmitting the saved client key.
Run as the service account: credentials are owner-only, never a web API response.
"""

import argparse
from collections import deque
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import tempfile
import time


POWER_URI = "ssap://com.webos.service.tvpower/power/getPowerState"
FOREGROUND_URI = "ssap://com.webos.applicationManager/getForegroundAppInfo"
LAUNCH_URI = "ssap://system.launcher/launch"
# On the target TV, secondscreen.gateway/interfaces/com.webos.service.tvpower.interface
# requires CONTROL_POWER for /power/getPowerState (READ_POWER_STATE alone gives 401).
PERMISSIONS = ("LAUNCH", "READ_RUNNING_APPS", "READ_POWER_STATE", "CONTROL_POWER")
MAX_MESSAGE = 65536


class SsapError(Exception):
    """A safe-to-log message, never an untrusted TV response or credential."""


class SsapTimeout(SsapError):
    pass


class PairingRequired(SsapError):
    """Stop automatic retries; an explicit, attended pair is necessary."""


class CertificateChanged(PairingRequired):
    pass


def _duration(value):
    value = float(value)
    if not 0 < value <= 120:
        raise ValueError("Timeout must be between 0 and 120 seconds")
    return value


def _load_credentials(path, host):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("Not a regular file")
            if os.name != "nt" and (metadata.st_mode & 0o077):
                raise ValueError("Credentials must be owner-only")
            document = stream.read(16385)
            if len(document) > 16384:
                raise ValueError("Oversize credential file")
            data = json.loads(document)
        if (data.get("version") != 1 or data.get("host") != host
                or not isinstance(data.get("client_key"), str)
                or not 1 <= len(data["client_key"]) <= 512
                or not re.fullmatch(r"[a-f0-9]{64}", data.get("cert_sha256", ""))):
            raise ValueError("Invalid credentials")
        return data
    except (OSError, ValueError, TypeError, AttributeError):
        raise PairingRequired("SSAP credentials missing, unsafe, or invalid") from None


def _save_credentials(path, data):
    """Atomic 0600 replacement; the parent directory must be service-owned."""
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".ssap-", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            if os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            json.dump(data, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError:
        raise SsapError("Could not securely save SSAP credentials") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _open_websocket(host, timeout):
    try:
        import websocket
    except ImportError:
        raise SsapError("Install the websocket-client dependency") from None
    try:
        return websocket.create_connection(
            "wss://%s:3001/" % host, timeout=timeout,
            sslopt={"cert_reqs": ssl.CERT_NONE, "check_hostname": False},
            http_no_proxy=[host], suppress_origin=True,
        )
    except Exception:
        raise SsapError("SSAP TLS connection failed") from None


class SsapClient:
    def __init__(self, host, credentials_path, timeout=3):
        if not isinstance(host, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host):
            raise ValueError("Expected a TV IPv4 address or hostname")
        self.host = host
        self.credentials_path = Path(credentials_path)
        self.timeout = _duration(timeout)
        self._ws = None
        self._registered = False
        self._counter = 0
        self._subscriptions = set()
        self._events = deque(maxlen=128)

    def __enter__(self):
        return self.connect()

    def __exit__(self, *unused):
        self.close()

    def close(self):
        ws, self._ws = self._ws, None
        self._registered = False
        self._subscriptions.clear()
        self._events.clear()
        if ws is not None:
            try:
                ws.close(timeout=0.2)
            except Exception:
                pass

    def connect(self, pair=False, pair_timeout=90, on_prompt=None):
        """Pair ONLY in an attended operation. No downgrade to unencrypted WS.

        Reconnect supplies only an existing key, not a new pairing request. If
        firmware nevertheless requests pairing, disconnect and let the caller
        latch PairingRequired (do not retry automatically). SSAP has no verified
        universal no-prompt flag, so even that first rejected key can briefly
        display a firmware-generated prompt on some models.
        """
        self.close()
        duration = _duration(pair_timeout) if pair else self.timeout
        saved = None if pair else _load_credentials(self.credentials_path, self.host)
        deadline = time.monotonic() + duration
        try:
            self._ws = _open_websocket(self.host, min(self.timeout, duration))
            try:
                certificate = self._ws.sock.getpeercert(binary_form=True)
                if not certificate:
                    raise ValueError("Missing peer certificate")
                fingerprint = hashlib.sha256(certificate).hexdigest()
            except Exception:
                raise SsapError("Cannot read SSAP peer certificate") from None
            if saved and not hmac.compare_digest(saved["cert_sha256"], fingerprint):
                raise CertificateChanged("SSAP certificate changed; attended pairing required")

            # Newer LG firmware needs these two read-only messages pre-register.
            self._send({"id": "hello", "type": "hello", "payload": {}}, deadline)
            self._await("hello", deadline, expected="hello")
            self._send({"id": "info", "type": "request", "uri": "ssap://system/getSystemInfo", "payload": {}}, deadline)
            self._await("info", deadline)  # Unsupported system info is harmless.

            payload = {"forcePairing": False}
            if pair:
                payload.update({"pairingType": "PROMPT", "manifest": {
                    "manifestVersion": 1, "appVersion": "1.0",
                    "permissions": list(PERMISSIONS),
                }})
            else:
                payload["client-key"] = saved["client_key"]
            self._send({"id": "register", "type": "register", "payload": payload}, deadline)
            prompt_notified = False
            while True:
                reply = self._await("register", deadline, expected="registered")
                body = reply.get("payload", {})
                if reply["type"] == "registered":
                    key = body.get("client-key")
                    if not isinstance(key, str) or not 1 <= len(key) <= 512:
                        raise PairingRequired("SSAP registration did not return a key")
                    if pair:
                        _save_credentials(self.credentials_path, {
                            "version": 1, "host": self.host,
                            "client_key": key, "cert_sha256": fingerprint,
                        })
                    elif key != saved["client_key"]:
                        raise PairingRequired("SSAP registration unexpectedly changed key")
                    self._registered = True
                    return self
                if reply["type"] == "error" or not pair:
                    raise PairingRequired("SSAP key rejected; attended pairing required")
                if body.get("pairingType") != "PROMPT":
                    raise PairingRequired("SSAP pairing response was not recognized")
                if on_prompt is not None and not prompt_notified:
                    prompt_notified = True
                    try:
                        on_prompt()
                    except Exception:
                        raise SsapError("SSAP pairing prompt callback failed") from None
        except Exception:
            self.close()
            raise

    def _send(self, message, deadline):
        if self._ws is None:
            raise SsapError("SSAP is disconnected")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SsapTimeout("SSAP operation timed out")
        try:
            self._ws.settimeout(remaining)
            self._ws.send(json.dumps(message, separators=(",", ":")))
        except Exception:
            raise SsapError("SSAP send failed") from None

    def _read(self, deadline):
        if self._ws is None:
            raise SsapError("SSAP is disconnected")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SsapTimeout("SSAP operation timed out")
        try:
            self._ws.settimeout(remaining)
            raw = self._ws.recv()  # websocket-client handles fragmentation/ping.
        except Exception as error:
            if isinstance(error, (socket.timeout, TimeoutError)) or type(error).__name__ == "WebSocketTimeoutException":
                raise SsapTimeout("SSAP receive timed out") from None
            raise SsapError("SSAP receive failed") from None
        if not raw:
            raise SsapError("SSAP connection closed")
        try:
            if len(raw) > MAX_MESSAGE:
                raise ValueError("Oversize response")
            reply = json.loads(raw)
            if (not isinstance(reply, dict) or not isinstance(reply.get("type"), str)
                    or not isinstance(reply.get("payload", {}), dict)):
                raise ValueError("Malformed response")
            return reply
        except (ValueError, TypeError):
            raise SsapError("SSAP malformed response") from None

    def _await(self, identifier, deadline, expected=None):
        while True:
            reply = self._read(deadline)
            if str(reply.get("id", "")) == identifier or (expected and reply["type"] == expected):
                return reply
            if str(reply.get("id", "")) in self._subscriptions:
                self._events.append(self._event(reply))

    @staticmethod
    def _event(reply):
        failed = reply["type"] == "error" or reply.get("payload", {}).get("returnValue") is False
        return {"id": str(reply.get("id", "")), "type": "error" if failed else "response",
                "payload": {} if failed else reply.get("payload", {})}

    def _command(self, kind, uri, payload, timeout):
        if not self._registered:
            raise SsapError("SSAP is not registered")
        if not isinstance(uri, str) or not uri.startswith("ssap://"):
            raise ValueError("Expected an ssap:// endpoint")
        self._counter += 1
        identifier = str(self._counter)
        deadline = time.monotonic() + _duration(self.timeout if timeout is None else timeout)
        self._send({"id": identifier, "type": kind, "uri": uri, "payload": payload or {}}, deadline)
        return identifier, deadline

    def request(self, uri, payload=None, timeout=None):
        identifier, deadline = self._command("request", uri, payload, timeout)
        reply = self._await(identifier, deadline)
        if reply["type"] != "response" or reply.get("payload", {}).get("returnValue") is False:
            raise SsapError("SSAP request rejected")
        return reply.get("payload", {})

    def subscribe(self, uri, payload=None, timeout=None):
        """Send a subscription; receive() returns its first response and updates."""
        identifier, _ = self._command("subscribe", uri, payload, timeout)
        self._subscriptions.add(identifier)
        return identifier

    def receive(self, timeout=None):
        """Return a subscription event (including sanitized error events)."""
        if self._events:
            return self._events.popleft()
        deadline = time.monotonic() + _duration(self.timeout if timeout is None else timeout)
        while True:
            reply = self._read(deadline)
            if str(reply.get("id", "")) in self._subscriptions:
                return self._event(reply)


def main(argv=None):
    parser = argparse.ArgumentParser(description="LG SSAP attended pairing/read-only probe")
    parser.add_argument("command", choices=("pair", "probe"))
    parser.add_argument("--host", required=True)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--timeout", type=float, default=None)
    args = parser.parse_args(argv)
    client = None
    try:
        client = SsapClient(args.host, args.credentials, timeout=5)
        if args.command == "pair":
            print("Approve the pairing request on the TV (up to 90 seconds).", flush=True)
            client.connect(pair=True, pair_timeout=args.timeout or 90)
            print(json.dumps({"paired": True, "transport": "wss", "certificatePinned": True}))
        else:
            client.connect()
            power = client.request(POWER_URI, timeout=args.timeout or 5)
            foreground = client.request(FOREGROUND_URI, timeout=args.timeout or 5)
            print(json.dumps({"connected": True, "state": power.get("state"), "appId": foreground.get("appId")}))
        return 0
    except (SsapError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error), "pairingRequired": isinstance(error, PairingRequired)}))
        return 1
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
