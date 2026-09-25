import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lg_ssap as ssap


CERTIFICATE = b"test TV DER certificate"
SECRET = "private-test-client-key"
HOST = "192.0.2.42"


def response(identifier, payload=None, kind="response"):
    return {"id": identifier, "type": kind, "payload": payload or {}}


def handshake(*registration):
    return [response("hello", kind="hello"), response("info"), *registration]


class FakeWebSocket:
    def __init__(self, replies=(), certificate=CERTIFICATE):
        self.replies = list(replies)
        self.sent = []
        self.timeouts = []
        self.closed = False
        self.sock = self
        self.certificate = certificate

    def getpeercert(self, binary_form=False):
        assert binary_form
        return self.certificate

    def settimeout(self, value):
        self.timeouts.append(value)

    def send(self, message):
        self.sent.append(json.loads(message))

    def recv(self):
        if not self.replies:
            raise socket.timeout("sensitive transport diagnostic " + SECRET)
        item = self.replies.pop(0)
        return item if isinstance(item, str) else json.dumps(item)

    def close(self, timeout=None):
        self.closed = True


class SsapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.credentials = Path(self.directory.name) / "pair.json"
        self.client = ssap.SsapClient(HOST, self.credentials)
        self.addCleanup(self.client.close)

    def save(self, **changes):
        document = {"version": 1, "host": HOST, "client_key": SECRET,
                    "cert_sha256": hashlib.sha256(CERTIFICATE).hexdigest()}
        document.update(changes)
        ssap._save_credentials(self.credentials, document)

    def paired_socket(self, *after, **kwargs):
        return FakeWebSocket(handshake(response("register", {"client-key": SECRET}, "registered"), *after), **kwargs)

    def connect(self, ws):
        self.save()
        with patch.object(ssap, "_open_websocket", return_value=ws):
            self.client.connect()

    def test_pair_prompts_and_persists_only_minimal_permissions(self):
        ws = FakeWebSocket(handshake(
            response("register", {"pairingType": "PROMPT"}),
            response("register", {"client-key": SECRET}, "registered")))
        with patch.object(ssap, "_open_websocket", return_value=ws):
            self.client.connect(pair=True)
        payload = ws.sent[-1]["payload"]
        self.assertEqual(payload["pairingType"], "PROMPT")
        self.assertEqual(set(payload["manifest"]["permissions"]), {"LAUNCH", "READ_RUNNING_APPS", "READ_POWER_STATE", "CONTROL_POWER"})
        self.assertNotIn("signed", payload["manifest"])
        saved = ssap._load_credentials(self.credentials, HOST)
        self.assertEqual(saved["client_key"], SECRET)
        self.assertEqual(saved["cert_sha256"], hashlib.sha256(CERTIFICATE).hexdigest())
        self.assertTrue(all(0 < value <= 90 for value in ws.timeouts))
        self.assertEqual(list(Path(self.directory.name).glob(".ssap-*")), [])

    def test_reconnect_sends_key_only_and_does_not_rewrite_credentials(self):
        self.save()
        ws = self.paired_socket()
        with patch.object(ssap, "_open_websocket", return_value=ws), patch.object(ssap, "_save_credentials") as save:
            self.client.connect()
        self.assertEqual(ws.sent[-1]["payload"], {"forcePairing": False, "client-key": SECRET})
        save.assert_not_called()

    def test_attended_prompt_callback_fires_once_after_prompt(self):
        ws = FakeWebSocket(handshake(
            response("register", {"pairingType": "PROMPT"}),
            response("register", {"pairingType": "PROMPT"}),
            response("register", {"client-key": SECRET}, "registered")))
        called = []
        def on_prompt():
            called.append(len(ws.replies))
        with patch.object(ssap, "_open_websocket", return_value=ws):
            self.client.connect(pair=True, on_prompt=on_prompt)
        self.assertEqual(called, [2])

    def test_unattended_reconnect_never_calls_prompt_callback(self):
        self.save()
        ws = FakeWebSocket(handshake(response("register", {"pairingType": "PROMPT"})))
        with patch.object(ssap, "_open_websocket", return_value=ws), self.assertRaises(ssap.PairingRequired):
            self.client.connect(on_prompt=lambda: self.fail("Unexpected prompt callback"))

    def test_close_in_prompt_callback_cancels_without_saving(self):
        ws = FakeWebSocket(handshake(response("register", {"pairingType": "PROMPT"})))
        with patch.object(ssap, "_open_websocket", return_value=ws), self.assertRaises(ssap.SsapError):
            self.client.connect(pair=True, on_prompt=self.client.close)
        self.assertTrue(ws.closed)
        self.assertFalse(self.credentials.exists())

    def test_changed_certificate_never_sends_key_or_any_message(self):
        self.save()
        ws = self.paired_socket(certificate=b"other certificate")
        with patch.object(ssap, "_open_websocket", return_value=ws):
            with self.assertRaises(ssap.CertificateChanged):
                self.client.connect()
        self.assertEqual(ws.sent, [])
        self.assertTrue(ws.closed)

    def test_no_credentials_never_opens_socket(self):
        with patch.object(ssap, "_open_websocket") as opener:
            with self.assertRaises(ssap.PairingRequired):
                self.client.connect()
        opener.assert_not_called()

    def test_host_bound_credentials_never_open_socket(self):
        self.save(host="192.0.2.43")
        with patch.object(ssap, "_open_websocket") as opener:
            with self.assertRaises(ssap.PairingRequired):
                self.client.connect()
        opener.assert_not_called()

    @unittest.skipIf(os.name == "nt", "POSIX permission check")
    def test_owner_only_credentials(self):
        self.save()
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)
        self.credentials.chmod(0o644)
        with self.assertRaises(ssap.PairingRequired):
            self.client.connect()

    @unittest.skipIf(os.name == "nt", "POSIX symlink check")
    def test_symlink_credentials_rejected(self):
        self.save()
        linked = self.credentials.with_name("link.json")
        linked.symlink_to(self.credentials)
        with self.assertRaises(ssap.PairingRequired):
            ssap._load_credentials(linked, HOST)

    def test_unattended_pairing_request_closes_connection(self):
        ws = FakeWebSocket(handshake(response("register", {"pairingType": "PROMPT"})))
        with self.assertRaises(ssap.PairingRequired):
            self.connect(ws)
        self.assertTrue(ws.closed)
        self.assertEqual(len([msg for msg in ws.sent if msg["type"] == "register"]), 1)

    def test_rejected_key_response_is_not_leaked(self):
        ws = FakeWebSocket(handshake({"id": "register", "type": "error", "error": SECRET}))
        with self.assertRaises(ssap.PairingRequired) as captured:
            self.connect(ws)
        self.assertNotIn(SECRET, str(captured.exception))
        self.assertTrue(ws.closed)

    def test_key_not_silently_changed_on_reconnect(self):
        ws = FakeWebSocket(handshake(response("register", {"client-key": "another-key"}, "registered")))
        with self.assertRaises(ssap.PairingRequired):
            self.connect(ws)
        self.assertEqual(ssap._load_credentials(self.credentials, HOST)["client_key"], SECRET)

    def test_failed_pair_preserves_existing_credentials(self):
        self.save()
        before = self.credentials.read_bytes()
        ws = FakeWebSocket(handshake(response("register", {"pairingType": "PROMPT"})))
        with patch.object(ssap, "_open_websocket", return_value=ws):
            with self.assertRaises(ssap.SsapTimeout) as captured:
                self.client.connect(pair=True, pair_timeout=0.5)
        self.assertNotIn(SECRET, str(captured.exception))
        self.assertEqual(self.credentials.read_bytes(), before)

    def test_request_buffers_interleaved_subscription_update(self):
        ws = self.paired_socket(response("1", {"state": "Active"}),
                                response("unrelated", {"appId": "ignored"}),
                                response("2", {"appId": "com.webos.app.home"}))
        self.connect(ws)
        identifier = self.client.subscribe(ssap.POWER_URI)
        self.assertEqual(identifier, "1")
        foreground = self.client.request(ssap.FOREGROUND_URI)
        self.assertEqual(foreground["appId"], "com.webos.app.home")
        self.assertEqual(self.client.receive()["payload"], {"state": "Active"})

    def test_subscribed_error_is_sanitized(self):
        ws = self.paired_socket({"id": "1", "type": "error", "error": SECRET})
        self.connect(ws)
        self.client.subscribe(ssap.POWER_URI)
        self.assertEqual(self.client.receive(), {"id": "1", "type": "error", "payload": {}})

    def test_false_return_value_is_request_error(self):
        ws = self.paired_socket(response("1", {"returnValue": False, "errorText": SECRET}))
        self.connect(ws)
        with self.assertRaises(ssap.SsapError) as captured:
            self.client.request(ssap.FOREGROUND_URI)
        self.assertNotIn(SECRET, str(captured.exception))

    def test_timeout_is_safe_and_bounded(self):
        ws = self.paired_socket()
        self.connect(ws)
        with self.assertRaises(ssap.SsapTimeout) as captured:
            self.client.request(ssap.POWER_URI, timeout=0.25)
        self.assertNotIn(SECRET, str(captured.exception))
        self.assertLessEqual(ws.timeouts[-1], 0.25)

    def test_malformed_and_oversize_response_rejected(self):
        for malformed in ("not JSON " + SECRET, "[1,2]", "x" * (ssap.MAX_MESSAGE + 1), '{"type":"response","payload":[]}'):
            with self.subTest(malformed=malformed[:20]):
                ws = self.paired_socket(malformed)
                self.connect(ws)
                with self.assertRaises(ssap.SsapError) as captured:
                    self.client.request(ssap.POWER_URI)
                self.assertNotIn(SECRET, str(captured.exception))

    def test_unregistered_request_is_not_sent(self):
        with self.assertRaises(ssap.SsapError):
            self.client.request(ssap.LAUNCH_URI, {"id": "some-app"})

    def test_probe_prints_only_allowlisted_fields(self):
        self.save()
        ws = self.paired_socket(response("1", {"state": "Active", "client-key": SECRET}),
                                response("2", {"appId": "com.webos.app.home", "extra": SECRET}))
        output = io.StringIO()
        with patch.object(ssap, "_open_websocket", return_value=ws), contextlib.redirect_stdout(output):
            result = ssap.main(["probe", "--host", HOST, "--credentials", str(self.credentials)])
        self.assertEqual(result, 0)
        self.assertNotIn(SECRET, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["state"], "Active")

    def test_reject_urls_and_unbounded_timeouts(self):
        for invalid_host in ("https://example.com", "1.2.3.4/path", "host:3001", ""):
            with self.assertRaises(ValueError):
                ssap.SsapClient(invalid_host, self.credentials)
        for timeout in (0, -1, 121, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                ssap.SsapClient(HOST, self.credentials, timeout=timeout)


if __name__ == "__main__":
    unittest.main()
