import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class FakeBroker:
    def __init__(self):
        self.enabled = False
        self.mode = 'passive'
        self.calls = []
        self.failure = None
        self.live = {'enabled': False, 'active': False, 'compatible': True, 'nativeHookLoaded': False}

    def status(self): return dict(self.live)

    def set_enabled(self, enabled, bindings=None):
        self.calls.append((enabled, bindings))
        if self.failure == enabled: raise RuntimeError('SSH unavailable')
        self.enabled = enabled
        self.live.update(enabled=enabled, active=enabled)


class BrokerSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'switch.json'
        self.broker = FakeBroker()
        self.hook = Mock()
        self.hook.read_config.return_value = {'398': {'action': 'ignore'}}
        self.switch = server.RemoteBrokerSwitch(self.path, self.broker, self.hook)

    def tearDown(self): self.temp.cleanup()

    def test_enable_loads_saved_bindings_and_persists(self):
        result = self.switch.set_enabled({'enabled': True})
        self.assertTrue(result['active'])
        self.assertEqual(self.broker.mode, 'grab')
        self.assertEqual(self.broker.calls, [(True, self.hook.read_config.return_value)])
        self.assertEqual(json.loads(self.path.read_text()), {'enabled': True})

    def test_off_does_not_need_binding_or_app_catalog(self):
        self.hook.read_config.side_effect = RuntimeError('hook unavailable')
        self.switch.set_enabled({'enabled': False})
        self.hook.read_config.assert_not_called()
        self.assertEqual(self.broker.calls, [(False, None)])

    def test_off_survives_unreachable_tv(self):
        self.broker.failure = False
        with self.assertRaises(RuntimeError): self.switch.set_enabled({'enabled': False})
        self.assertEqual(json.loads(self.path.read_text()), {'enabled': False})
        self.assertFalse(self.switch.requested)

    def test_failed_enable_rolls_back(self):
        self.broker.failure = True
        with self.assertRaises(RuntimeError): self.switch.set_enabled({'enabled': True})
        self.assertEqual(json.loads(self.path.read_text()), {'enabled': False})
        self.assertFalse(self.broker.enabled)
        self.assertEqual(self.broker.calls[-1], (False, None))

    def test_old_binary_or_native_hook_cannot_enable(self):
        for key, value in [('compatible', False), ('nativeHookLoaded', True)]:
            previous = self.broker.live[key]
            self.broker.live[key] = value
            with self.assertRaises(RuntimeError): self.switch.set_enabled({'enabled': True})
            self.broker.live[key] = previous
        self.assertEqual(self.broker.calls, [])

    def test_emergency_off_stops_even_if_nas_state_cannot_be_saved(self):
        self.switch._write = Mock(side_effect=OSError('disk full'))
        with self.assertRaises(OSError): self.switch.set_enabled({'enabled': False})
        self.assertEqual(self.broker.calls, [(False, None)])

    def test_validation(self):
        for raw in [None, {}, {'enabled': 1}, {'enabled': 'false'}, {'enabled': True, 'extra': 1}]:
            with self.assertRaises(server.RequestError): self.switch.set_enabled(raw)
        self.assertEqual(self.broker.calls, [])

    def test_restart_respects_saved_off(self):
        self.switch.set_enabled({'enabled': False})
        self.broker.calls.clear()
        fresh = server.RemoteBrokerSwitch(self.path, self.broker, self.hook)
        fresh.restore()
        self.assertEqual(self.broker.calls, [(False, None)])

    def test_restart_does_not_rearm_crash_circuit(self):
        self.switch.set_enabled({'enabled': True})
        self.broker.live.update(enabled=False, active=False)
        self.broker.calls.clear()
        fresh = server.RemoteBrokerSwitch(self.path, self.broker, self.hook)
        fresh.restore()
        self.assertEqual(self.broker.calls, [])
        self.assertFalse(self.broker.enabled)

    def test_restart_restores_still_enabled_engine(self):
        self.switch.set_enabled({'enabled': True})
        self.broker.calls.clear()
        fresh = server.RemoteBrokerSwitch(self.path, self.broker, self.hook)
        fresh.restore()
        self.assertEqual(self.broker.calls, [(True, self.hook.read_config.return_value)])


if __name__ == '__main__': unittest.main()
