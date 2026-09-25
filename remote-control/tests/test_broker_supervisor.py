"""Execute the actual supervisor shell with a fake broker, isolated from TV input."""
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("broker_test_server", ROOT / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

FAKE = '''#!/usr/bin/env python3
import os, signal, sys, time
from pathlib import Path
r = Path(__file__).parent
if '--check-config' in sys.argv: sys.exit(0)
if '--check-devices' in sys.argv: sys.exit(2 if (r / 'no-devices').exists() else 0)
if '--recover-output' in sys.argv:
    (r / 'recovered').touch(); sys.exit(0)
with (r / 'starts').open('a') as f: f.write('start\\n')
(r / 'fake.pid').write_text(str(os.getpid()))
signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
if (r / 'crash').exists():
    print('simulated device failure', file=sys.stderr, flush=True); sys.exit(7)
hb = Path(sys.argv[sys.argv.index('--heartbeat') + 1])
while True:
    if not (r / 'stale').exists():
        t = hb.with_suffix('.new')
        t.write_text(str(int(float(Path('/proc/uptime').read_text().split()[0]))))
        t.replace(hb)
    time.sleep(.05)
'''

@unittest.skipUnless(os.name == 'posix' and shutil.which('flock'), 'Linux shell test')
class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='codex-supervisor-test-')
        self.root = Path(self.temp.name)
        self.processes = []
        script = server.RemoteBrokerManager.SUPERVISOR_SCRIPT
        script = script.replace('/var/lib/webosbrew/remote-broker', str(self.root))
        script = script.replace('/tmp/hu.szabi.remote-broker', str(self.root / 'state'))
        script = script.replace('/bin/usleep 100000', 'sleep 0.1')
        (self.root / 'supervisor.sh').write_text(script)
        (self.root / 'remote-broker').write_text(FAKE)
        (self.root / 'remote-broker').chmod(0o700)
        (self.root / 'enabled').touch()
        (self.root / 'bindings.conf').touch()
        (self.root / 'power').write_text('Active')
        luna = self.root / 'luna-send'
        # This firmware prints timing-mode Luna payloads on stderr.
        luna.write_text('#!/bin/sh\nprintf \'{"returnValue":true,"state":"%s"}\\n\' "$(cat "' + str(self.root / 'power') + '")" >&2\n')
        luna.chmod(0o700)

    def start(self):
        p = subprocess.Popen(['sh', str(self.root / 'supervisor.sh')], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env=dict(os.environ, PATH=str(self.root) + os.pathsep + os.environ['PATH']))
        self.processes.append(p)
        return p

    def wait_file(self, name):
        for _ in range(250):
            if (self.root / name).exists(): return
            time.sleep(.02)
        self.fail('file not created: ' + name)

    def tearDown(self):
        for p in self.processes:
            if p.poll() is None: p.terminate()
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        self.temp.cleanup()

    def test_term_exits_and_does_not_restart_child(self):
        p = self.start(); self.wait_file('fake.pid')
        child = int((self.root / 'fake.pid').read_text())
        p.terminate(); self.assertEqual(p.wait(timeout=5), 0)
        self.assertEqual((self.root / 'starts').read_text().count('start'), 1)
        with self.assertRaises(ProcessLookupError): os.kill(child, 0)
        self.assertFalse((self.root / 'recovered').exists())

    def test_duplicate_supervisor_cannot_touch_first(self):
        first = self.start(); self.wait_file('fake.pid')
        second = self.start(); self.assertEqual(second.wait(timeout=3), 0)
        self.assertIsNone(first.poll())
        self.assertEqual((self.root / 'starts').read_text().count('start'), 1)
        self.assertTrue((self.root / 'state-supervisor.pid').exists())

    def test_crash_disables_without_retry_and_recovers_output(self):
        (self.root / 'crash').touch()
        p = self.start(); self.assertEqual(p.wait(timeout=9), 1)
        self.assertFalse((self.root / 'enabled').exists())
        self.assertTrue((self.root / 'recovered').exists())
        self.assertEqual((self.root / 'starts').read_text().count('start'), 1)
        failure = (self.root / 'last-failure.log').read_text()
        self.assertIn('exit=7', failure)
        self.assertIn('simulated device failure', failure)

    def wait_state(self, expected):
        for _ in range(250):
            state = self.root / 'state.state'
            if state.exists() and state.read_text().strip() == expected: return
            time.sleep(.02)
        self.fail('supervisor state not reached: ' + expected)

    def test_standby_releases_child_but_preserves_autostart_and_wakes(self):
        p = self.start(); self.wait_file('fake.pid')
        child = int((self.root / 'fake.pid').read_text())
        (self.root / 'power').write_text('Active Standby')
        self.wait_state('standby')
        self.assertTrue((self.root / 'enabled').exists())
        with self.assertRaises(ProcessLookupError): os.kill(child, 0)
        (self.root / 'power').write_text('Active')
        self.wait_state('active')
        time.sleep(.1)
        self.assertEqual((self.root / 'starts').read_text().count('start'), 2)
        self.assertIsNone(p.poll())

    def test_boot_waits_for_luna_and_devices_without_disabling(self):
        (self.root / 'power').write_text('')
        p = self.start(); self.wait_state('waiting-for-tv')
        self.assertFalse((self.root / 'starts').exists())
        (self.root / 'no-devices').touch()
        (self.root / 'power').write_text('Active')
        self.wait_state('waiting-for-input')
        self.assertFalse((self.root / 'starts').exists())
        self.assertTrue((self.root / 'enabled').exists())
        (self.root / 'no-devices').unlink()
        self.wait_file('fake.pid')
        self.assertIsNone(p.poll())

    def test_shutdown_child_exit_before_power_event_is_not_a_crash(self):
        p = self.start(); self.wait_file('fake.pid')
        os.kill(int((self.root / 'fake.pid').read_text()), signal.SIGTERM)
        time.sleep(.25)
        (self.root / 'power').write_text('Active Standby')
        self.wait_state('standby')
        self.assertTrue((self.root / 'enabled').exists())
        self.assertFalse((self.root / 'disabled-reason').exists())
        self.assertIsNone(p.poll())

    def test_stale_heartbeat_stops_and_disables(self):
        (self.root / 'stale').touch()
        p = self.start(); self.wait_file('fake.pid')
        self.assertEqual(p.wait(timeout=12), 1)
        self.assertFalse((self.root / 'enabled').exists())
        self.assertIn('stale heartbeat', (self.root / 'disabled-reason').read_text())
        self.assertEqual((self.root / 'starts').read_text().count('start'), 1)

    def test_disable_marker_stops_child(self):
        p = self.start(); self.wait_file('fake.pid')
        (self.root / 'enabled').unlink()
        self.assertEqual(p.wait(timeout=5), 0)
        self.assertEqual((self.root / 'starts').read_text().count('start'), 1)

if __name__ == '__main__': unittest.main()
