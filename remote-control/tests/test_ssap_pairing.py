"""Pairing lifecycle tests with in-memory clients: no network or TV actions."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ssap_pairing
from lg_ssap import FOREGROUND_URI, POWER_URI


class FakeClient:
    def __init__(self, factory, host, candidate, timeout):
        self.factory = factory
        self.host = host
        self.candidate = Path(candidate)
        self.timeout = timeout
        self.closed = False
        self.requests = []

    def connect(self, *, pair, pair_timeout, on_prompt):
        self.factory.connect_args = (pair, pair_timeout)
        on_prompt()
        self.factory.prompted.set()
        if not self.factory.release.wait(3):
            raise TimeoutError('Fake client was not released by test')
        if self.closed:
            raise ConnectionError('Fake client cancelled')
        if self.factory.connect_error:
            raise self.factory.connect_error
        self.candidate.write_text(json.dumps(self.factory.new_key), encoding='utf-8')
        return self

    def request(self, uri, timeout):
        self.requests.append(uri)
        self.factory.keys_during_validation.append(self.factory.credentials.read_bytes())
        if uri == self.factory.reject_uri:
            raise RuntimeError('untrusted firmware text: client-key=new-secret')
        if self.factory.on_request:
            self.factory.on_request(uri)
        return {'returnValue': True, 'state': 'Active', 'appId': 'com.webos.app.home'}

    def close(self):
        self.closed = True
        self.factory.release.set()


class FakeFactory:
    def __init__(self, credentials):
        self.credentials = credentials
        self.prompted = threading.Event()
        self.release = threading.Event()
        self.clients = []
        self.keys_during_validation = []
        self.connect_error = None
        self.reject_uri = None
        self.on_request = None
        self.new_key = {'version': 1, 'host': '192.0.2.20', 'client_key': 'new-secret', 'cert_sha256': 'a' * 64}

    def __call__(self, host, candidate, timeout):
        client = FakeClient(self, host, candidate, timeout)
        self.clients.append(client)
        return client


class PairingManagerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.credentials = self.root / 'lg-ssap.json'
        self.old_key = b'{"client_key":"old-secret"}'
        self.credentials.write_bytes(self.old_key)
        self.factory = FakeFactory(self.credentials)
        self.button = mock.Mock()
        self.dialog = mock.Mock(return_value=True)
        self.manager = ssap_pairing.PairingManager(
            lambda: '192.0.2.20', self.credentials, self.button, self.dialog,
            client_factory=self.factory,
        )
        self.addCleanup(self.stop_worker)

    def stop_worker(self):
        self.factory.release.set()
        if self.manager.worker:
            self.manager.worker.join(4)

    def begin(self):
        result = self.manager.start()
        self.assertTrue(self.factory.prompted.wait(2), 'Fake pairing prompt was not reached')
        self.assertEqual(self.manager.snapshot()['pairing']['state'], 'waiting')
        return result['pairing']['id']

    def finish(self):
        self.factory.release.set()
        self.manager.worker.join(4)
        self.assertFalse(self.manager.worker.is_alive(), 'Pairing worker did not stop')
        return self.manager.snapshot()['pairing']

    def assert_old_key(self):
        self.assertEqual(self.credentials.read_bytes(), self.old_key)

    def assert_cleaned(self):
        self.assertFalse(self.manager.marker.exists())
        self.assertEqual(list(self.root.glob('.lg-ssap-pair-*')), [])
        self.assertIsNone(self.manager.client)

    def test_success_atomically_replaces_only_after_both_validation_reads(self):
        original_replace = os.replace
        commits = []

        def replace(source, destination):
            if Path(destination) == self.credentials:
                self.assert_old_key()
                self.assertEqual(self.factory.clients[0].requests, [POWER_URI, FOREGROUND_URI])
                self.assertEqual(json.loads(Path(source).read_text()), self.factory.new_key)
                commits.append((source, destination))
            return original_replace(source, destination)

        with mock.patch.object(ssap_pairing.os, 'replace', side_effect=replace):
            identifier = self.begin()
            self.assertTrue(self.manager.marker.exists())
            self.assert_old_key()
            state = self.finish()
        self.assertEqual(state['id'], identifier)
        self.assertEqual(state['state'], 'paired')
        self.assertEqual(len(commits), 1)
        self.assertEqual(json.loads(self.credentials.read_text()), self.factory.new_key)
        self.assertEqual(self.factory.keys_during_validation, [self.old_key, self.old_key])
        self.assertTrue(state['paired'])
        self.assertFalse(state['canApprove'])
        self.button.assert_not_called()
        self.assert_cleaned()

    def test_connection_failure_retains_old_key_and_sanitizes_errors(self):
        self.factory.connect_error = RuntimeError('client-key=new-secret /private/path')
        self.begin()
        state = self.finish()
        self.assertEqual(state['state'], 'error')
        self.assertIn('RuntimeError', state['error'])
        self.assertNotIn('new-secret', json.dumps(state))
        self.assertNotIn('/private/path', json.dumps(state))
        self.assert_old_key()
        self.assert_cleaned()

    def test_rejected_foreground_read_does_not_commit_candidate(self):
        self.factory.reject_uri = FOREGROUND_URI
        self.begin()
        state = self.finish()
        self.assertEqual(state['state'], 'error')
        self.assertNotIn('new-secret', json.dumps(state))
        self.assert_old_key()
        self.assert_cleaned()

    def test_cancel_retains_old_key_and_closes_connection(self):
        identifier = self.begin()
        result = self.manager.cancel(identifier)
        self.assertEqual(result['pairing']['state'], 'cancelled')
        self.assertTrue(self.factory.clients[0].closed)
        state = self.finish()
        self.assertEqual(state['state'], 'cancelled')
        self.assert_old_key()
        self.button.assert_not_called()
        self.assert_cleaned()

    def test_cancel_during_validation_cannot_commit_new_key(self):
        identifier = self.begin()
        self.factory.on_request = lambda uri: self.manager.cancel(identifier) if uri == FOREGROUND_URI else None
        state = self.finish()
        self.assertEqual(state['state'], 'cancelled')
        self.assert_old_key()
        self.assert_cleaned()

    def test_only_one_concurrent_pairing_session(self):
        identifier = self.begin()
        with self.assertRaises(ValueError):
            self.manager.start()
        self.assertEqual(len(self.factory.clients), 1)
        self.assertEqual(self.manager.snapshot()['pairing']['id'], identifier)
        self.assertEqual(json.loads(self.manager.marker.read_text())['id'], identifier)

    def test_stale_session_cannot_approve_or_cancel(self):
        self.begin()
        with self.assertRaises(ValueError):
            self.manager.approve('stale-session')
        with self.assertRaises(ValueError):
            self.manager.cancel('stale-session')
        self.button.assert_not_called()
        self.dialog.assert_not_called()
        self.assertEqual(self.manager.snapshot()['pairing']['state'], 'waiting')

    def test_nonvisible_dialog_sends_no_ok(self):
        identifier = self.begin()
        self.dialog.return_value = False
        with self.assertRaises(ValueError):
            self.manager.approve(identifier)
        self.button.assert_not_called()
        self.dialog.assert_called_once_with()
        self.assertEqual(self.manager.snapshot()['pairing']['state'], 'waiting')

    def test_exactly_one_explicit_approval_is_sent(self):
        identifier = self.begin()
        self.button.assert_not_called()
        state = self.manager.approve(identifier)['pairing']
        self.assertEqual(state['state'], 'approving')
        self.button.assert_called_once_with()
        with self.assertRaises(ValueError):
            self.manager.approve(identifier)
        self.button.assert_called_once_with()
        self.dialog.assert_called_once_with()
        self.assertEqual(self.finish()['state'], 'paired')

    def test_expired_request_sends_no_ok(self):
        identifier = self.begin()
        with self.manager.lock:
            self.manager.state['deadline'] = time.time() - 1
        with self.assertRaises(ValueError):
            self.manager.approve(identifier)
        self.button.assert_not_called()
        self.dialog.assert_not_called()

    def test_validation_finishing_after_deadline_becomes_terminal(self):
        self.begin()
        with self.manager.lock:
            self.manager.state['deadline'] = time.time() - 1
        state = self.finish()
        self.assertNotIn(state['state'], ssap_pairing.PENDING)
        self.assert_old_key()
        self.assert_cleaned()

    def test_public_snapshot_never_exposes_credentials_or_private_status(self):
        self.manager.early_status.write_text(json.dumps({
            'event': 'connected', 'connected': True, 'updatedAt': time.time(),
            'client_key': 'private-key', 'certificate': 'private-cert', 'path': '/private/path',
        }))
        snapshot = self.manager.snapshot()
        text = json.dumps(snapshot)
        for secret in ('private-key', 'private-cert', '/private/path', 'old-secret'):
            self.assertNotIn(secret, text)
        self.assertTrue(snapshot['pairing']['paired'])
        self.assertEqual(snapshot['earlyLauncher']['event'], 'connected')

    def test_command_rejects_extra_fields_unknown_actions_and_nonobjects(self):
        for value in (None, [], 'start', {'action': 'start', 'id': 'unexpected'},
                      {'action': 'unknown', 'id': 'x'}, {'action': 'approve'},
                      {'action': 'approve', 'id': 'x', 'force': True}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.manager.command(value)
        self.button.assert_not_called()
        self.assertEqual(self.factory.clients, [])


if __name__ == '__main__':
    unittest.main()
