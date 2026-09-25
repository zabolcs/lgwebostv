"""Run the actual Home script with fake Luna/TV paths; never talks to a TV."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lgtv_server", ROOT / "remote-control/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


@unittest.skipIf(os.name == "nt", "POSIX shell tests run on the PVE test fixture")
class HomeShellTests(unittest.TestCase):
    def exercise(self, mode, key_state, quick_visible=False, forbid_key_wait=False, presentation="app"):
        with tempfile.TemporaryDirectory(prefix="lgtv-home-test-") as temporary:
            root = Path(temporary)
            (root / "home-mode").write_text(mode)
            (root / "full-presentation").write_text(presentation)
            (root / "display-preferences.json").write_text('{"animationsEnabled":false,"visualEffectsEnabled":true}')
            (root / "control-origin").write_text("http://192.168.0.223:8765")
            (root / "key.log").write_text("773 => " + key_state + "\n")
            # Snapshot-restored legacy locks must not suppress a new key press.
            (root / "hu.szabi.launcher-home-key.lock").mkdir()
            if quick_visible:
                (root / "hu.szabi.launcher.quick-visible").touch()
                (root / "quick-running").touch()
            fake = root / "luna-send"
            fake.write_text("#!" + sys.executable + "\n" + """
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TV_TEST_ROOT"])
uri = sys.argv[-2]
payload = json.loads(sys.argv[-1])
with (root / "calls").open("a") as output:
    output.write(json.dumps({"uri":uri,"payload":payload}) + "\\n")
if uri.endswith("/listRunningApps"):
    print(json.dumps({"running":[{"id":"hu.szabi.launcher.quick"}] if (root / "quick-running").exists() else []}))
elif uri.endswith("/closeByAppId"):
    (root / "quick-running").unlink(missing_ok=True)
    print('{"returnValue":true}')
else:
    print('{"returnValue":true}')
""")
            fake.chmod(0o755)
            text = server.LauncherHomeManager.HOME_KEY_SCRIPT
            text = text.replace("DIR=/var/lib/webosbrew/launcher-home", "DIR=" + shlex.quote(str(root)))
            text = text.replace("/tmp/hu.szabi.", str(root) + "/hu.szabi.")
            text = text.replace("/usr/bin/luna-send-pub", shlex.quote(str(fake)))
            text = text.replace("/usr/bin/luna-send", shlex.quote(str(fake)))
            if forbid_key_wait:
                sleeper = root / "usleep"
                sleeper.write_text('#!/bin/sh\ntouch "' + str(root / "waited") + '"\n')
                sleeper.chmod(0o755)
                text = text.replace("/bin/usleep", shlex.quote(str(sleeper)))
            else:
                text = text.replace("/bin/usleep", "true")
            script = root / "home.sh"
            script.write_text(text)
            env = dict(os.environ, TV_TEST_ROOT=str(root), LAUNCHER_HOME_KEY_LOG=str(root / "key.log"),
                       PATH=str(root) + os.pathsep + os.environ["PATH"])
            subprocess.run(["sh", str(script)], env=env, check=True, capture_output=True, timeout=8)
            if forbid_key_wait:
                self.assertFalse((root / "waited").exists(), "Full Home must dispatch before waiting for release")
            return [json.loads(line) for line in (root / "calls").read_text().splitlines()]

    def test_short_long_and_user_mode_overrides(self):
        for mode, key, target in [
            ("split", "0", server.LAUNCHER_QUICK_APP_ID),
            ("split", "2", server.LAUNCHER_APP_ID),
            ("full", "0", server.LAUNCHER_APP_ID),
            ("full", "2", server.LAUNCHER_APP_ID),
            ("overlay", "0", server.LAUNCHER_QUICK_APP_ID),
            ("overlay", "2", server.LAUNCHER_QUICK_APP_ID),
        ]:
            with self.subTest(mode=mode, key=key):
                calls = self.exercise(mode, key)
                launches = [call for call in calls if call["uri"].endswith("/launch")]
                self.assertEqual(len(launches), 1)
                self.assertEqual(launches[0]["payload"]["id"], target)
                self.assertEqual(launches[0]["payload"]["params"]["controlOrigin"], "http://192.168.0.223:8765")
                self.assertEqual(launches[0]["payload"]["params"]["displayPreferences"],
                                 {"animationsEnabled": False, "visualEffectsEnabled": True})
                self.assertFalse(any(call["uri"].endswith("/listRunningApps") for call in calls),
                                 "Opening an absent launcher must not wait for an unnecessary WAM query")

    def test_short_home_delegates_toggle_to_retained_quick_instance(self):
        calls = self.exercise("split", "0", True)
        launches = [call["payload"] for call in calls if call["uri"].endswith("/launch")]
        self.assertEqual([call["id"] for call in launches], [server.LAUNCHER_QUICK_APP_ID])
        self.assertEqual(launches[0]["params"]["source"], "home-short-toggle")
        self.assertTrue(launches[0]["params"]["homeRequestId"])
        self.assertFalse(any(call["uri"].endswith("/closeByAppId") for call in calls))

    def test_full_presentation_is_independent_of_all_home_mappings(self):
        for mode, key, target in [("full", "1", server.LAUNCHER_OVERLAY_APP_ID),
                                  ("split", "2", server.LAUNCHER_OVERLAY_APP_ID),
                                  ("split", "0", server.LAUNCHER_QUICK_APP_ID),
                                  ("overlay", "1", server.LAUNCHER_QUICK_APP_ID)]:
            calls = self.exercise(mode, key, presentation="overlay", forbid_key_wait=mode != "split")
            launches = [c["payload"] for c in calls if c["uri"].endswith("/launch")]
            self.assertEqual([c["id"] for c in launches], [target])
            expected_host = "full-overlay" if target == server.LAUNCHER_OVERLAY_APP_ID else "quick"
            self.assertEqual(launches[0]["params"]["launcherHost"], expected_host)

    def test_full_home_dispatches_while_key_is_still_down(self):
        calls = self.exercise("full", "1", forbid_key_wait=True)
        launches = [call for call in calls if call["uri"].endswith("/launch")]
        self.assertEqual([call["payload"]["id"] for call in launches], [server.LAUNCHER_APP_ID])

    def test_long_home_closes_quick_then_opens_full(self):
        calls = self.exercise("split", "2", True)
        mutations = [call for call in calls if not call["uri"].endswith("/listRunningApps")]
        self.assertEqual([call["payload"]["id"] for call in mutations],
                         [server.LAUNCHER_QUICK_APP_ID, server.LAUNCHER_APP_ID])

    def test_guard_and_home_parse(self):
        for text in (server.LauncherHomeManager.HOME_KEY_SCRIPT, server.LauncherHomeManager.GUARD_SCRIPT,
                     server.LauncherHomeManager.PREWARM_SCRIPT, server.InputHookWatchdogManager.WATCHDOG_SCRIPT,
                     server.InputHookWatchdogManager.REPAIR_SCRIPT):
            subprocess.run(["sh", "-n"], input=text, text=True, check=True, capture_output=True)

    def test_guard_singleton_cleanup_and_stale_pid_are_safe(self):
        # Run the actual supervisor with inert subscriptions and Active/YouTube
        # answers. A second invocation must exit; stopping the guard must reap
        # its descendants while an unrelated process in the PID file survives.
        with tempfile.TemporaryDirectory(prefix="lgtv-supervisor-test-") as temporary:
            root = Path(temporary)
            (root / "enabled").touch()
            fake = root / "luna-send"
            fake.write_text("#!" + sys.executable + "\n" + '''
import json,os,pathlib,sys,time
root=pathlib.Path(os.environ['TV_TEST_ROOT'])
if '-i' in sys.argv:
    time.sleep(60)
else:
    uri=sys.argv[-2]
    if uri.endswith('/getPowerState'): print('{"state":"Active"}')
    elif uri.endswith('/getBootStatus'): print('{"powerStatus":"active","signals":{"boot-done":true}}')
    elif uri.endswith('/getForegroundAppInfo'): print('{"appId":"youtube.leanback.v4"}')
    else: print('{"returnValue":true}')
''')
            fake.chmod(0o755)
            (root / "luna-send-pub").symlink_to(fake)
            sleeper = root / "usleep"
            sleeper.write_text('#!/bin/sh\nsleep 0.1\n')
            sleeper.chmod(0o755)
            (root / "python").symlink_to(sys.executable)
            text = server.LauncherHomeManager.GUARD_SCRIPT
            text = text.replace('/var/lib/webosbrew/launcher-home', str(root))
            text = text.replace('/tmp/hu.szabi.', str(root) + '/hu.szabi.')
            text = text.replace('/bin/usleep', shlex.quote(str(sleeper)))
            script = root / 'guard.sh'
            script.write_text(text)
            env = dict(os.environ, TV_TEST_ROOT=str(root), PATH=str(root) + os.pathsep + os.environ['PATH'])
            unrelated = subprocess.Popen(['sleep', '60'])
            (root / 'hu.szabi.launcher-home.pid').write_text(str(unrelated.pid))
            guard = subprocess.Popen(['/bin/sh', str(script)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    pid = (root / 'hu.szabi.launcher-home.pid').read_text().strip()
                    if pid == str(guard.pid) and (root / 'hu.szabi.launcher.power-state').exists():
                        break
                    time.sleep(0.05)
                self.assertEqual(pid, str(guard.pid))
                duplicate = subprocess.run(['/bin/sh', str(script)], env=env, capture_output=True, timeout=3)
                self.assertEqual(duplicate.returncode, 0)
                self.assertIsNone(guard.poll())
                self.assertIsNone(unrelated.poll())
                # Exercise the same exact-command descendant stopper used by
                # configuration disable/deployment, with fixture paths only.
                stop = server.LauncherHomeManager.STOP_GUARD_PY.replace('/var/lib/webosbrew/launcher-home', str(root))
                subprocess.run([sys.executable, '-c', stop], check=True, timeout=5)
                guard.wait(timeout=5)
                self.assertIsNone(unrelated.poll())
                # A cleaned-up guard's kernel lock must be immediately reusable.
                lock = root / 'hu.szabi.launcher.guard-flock'
                subprocess.run(['flock', '-n', str(lock), 'true'], check=True, timeout=3)
                remaining = []
                for cmd in Path('/proc').glob('[0-9]*/cmdline'):
                    try:
                        value = cmd.read_bytes()
                        if str(root).encode() in value:
                            remaining.append(value)
                    except (FileNotFoundError, PermissionError):
                        pass
                self.assertEqual(remaining, [])
            finally:
                if guard.poll() is None:
                    guard.terminate()
                    guard.wait(timeout=5)
                unrelated.terminate()
                unrelated.wait(timeout=3)

    def test_native_prewarm_is_hidden_once_per_visit_and_skips_standby(self):
        with tempfile.TemporaryDirectory(prefix="lgtv-prewarm-test-") as temporary:
            root = Path(temporary)
            (root / "enabled").touch()
            (root / "home-mode").write_text("full")
            (root / "control-origin").write_text("http://192.168.0.223:8765")
            fake = root / "luna-send"
            fake.write_text("#!" + sys.executable + "\n" + '''
import json,os,pathlib,sys
root=pathlib.Path(os.environ['TV_TEST_ROOT'])
uri=sys.argv[-2]
payload=json.loads(sys.argv[-1])
if uri.endswith('/getPowerState'): print(json.dumps({'state':os.environ.get('TV_TEST_POWER','Active')}))
elif uri.endswith('/getForegroundAppInfo'): print(json.dumps({'appId':os.environ.get('TV_TEST_APP','cdp-30')}))
elif uri.endswith('/listRunningApps'): print(json.dumps({'running':[]}))
else:
 with (root/'calls').open('a') as f: f.write(json.dumps({'uri':uri,'payload':payload})+'\\n')
 print(json.dumps({'returnValue':True}))
''')
            fake.chmod(0o755)
            (root / "luna-send-pub").symlink_to(fake)
            text = server.LauncherHomeManager.PREWARM_SCRIPT
            text = text.replace("DIR=/var/lib/webosbrew/launcher-home", "DIR=" + shlex.quote(str(root)))
            text = text.replace("/tmp/hu.szabi.", str(root) + "/hu.szabi.").replace("\nsleep 1\n", "\ntrue\n")
            script = root / "prewarm.sh"
            script.write_text(text)
            env = dict(os.environ, TV_TEST_ROOT=str(root), PATH=str(root) + os.pathsep + os.environ["PATH"])
            def invoke(**changes):
                subprocess.run(["sh", str(script)], env=dict(env, **changes), check=True, capture_output=True, timeout=5)
            invoke(TV_TEST_POWER="Suspend")
            invoke(TV_TEST_APP=server.LAUNCHER_APP_ID)
            self.assertFalse((root / "calls").exists())
            invoke()
            invoke()
            calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()]
            self.assertEqual(len(calls), 1, "Memory reclamation must not cause a preload loop")
            self.assertEqual(calls[0]["payload"]["preload"], "full")
            self.assertEqual(calls[0]["payload"]["params"]["source"], "preload")
            self.assertEqual(calls[0]["payload"]["id"], server.LAUNCHER_APP_ID)

            (root / 'full-presentation').write_text('overlay')
            (root / 'hu.szabi.launcher.boot-ready').touch()
            (root / 'hu.szabi.launcher.active-since').write_text('2000')
            invoke(); invoke(TV_TEST_APP='youtube.leanback.v4')
            calls = [json.loads(line) for line in (root / 'calls').read_text().splitlines()]
            self.assertEqual(len(calls), 2, 'Overlay preload must be bounded to one attempt per wake')
            self.assertEqual(calls[1]['payload']['id'], server.LAUNCHER_OVERLAY_APP_ID)
            self.assertEqual(calls[1]['payload']['params']['launcherHost'], 'full-overlay')
            self.assertEqual(calls[1]['payload']['preload'], 'full')

    def test_quick_preload_is_native_hidden_once_per_wake_and_respects_power_memory(self):
        with tempfile.TemporaryDirectory(prefix='lgtv-quick-preload-test-') as temporary:
            root = Path(temporary)
            for name, value in [('enabled', ''), ('home-mode', 'split'),
                                ('hu.szabi.launcher.active-since', '1000'),
                                ('hu.szabi.launcher.quick-prewarm-after', '0'),
                                ('hu.szabi.launcher.boot-ready', ''),
                                ('memory', 'MemAvailable: 262144 kB\n')]:
                (root/name).write_text(value)
            fake=root/'luna-send'
            fake.write_text('#!'+sys.executable+'\n'+'''
import json,os,pathlib,sys
r=pathlib.Path(os.environ['TV_TEST_ROOT']);uri=sys.argv[-2]
if uri.endswith('/getPowerState'):
 print(json.dumps({'state':os.environ.get('TV_TEST_POWER','Active')}))
elif uri.endswith('/getForegroundAppInfo'):
 print(json.dumps({'appId':'hu.szabi.launcher'}))
 if os.environ.get('TV_TEST_INTERRUPT')=='1': (r/'hu.szabi.launcher.wake-signal').touch()
elif uri.endswith('/listRunningApps'):
 print(json.dumps({'running':[{'id':'hu.szabi.launcher.quick'}] if (r/'already-running').exists() else []}))
else:
 with (r/'launches').open('a') as f: f.write(json.dumps(json.loads(sys.argv[-1]))+'\\n')
 print('{"returnValue":true}')
''')
            fake.chmod(0o755)
            (root/'luna-send-pub').symlink_to(fake)
            text=server.LauncherHomeManager.PREWARM_SCRIPT.replace('/var/lib/webosbrew/launcher-home',str(root))
            text=text.replace('/tmp/hu.szabi.',str(root)+'/hu.szabi.').replace('/proc/meminfo',str(root/'memory'))
            text=text.replace('\nsleep 1\n','\ntrue\n')
            script=root/'prewarm.sh';script.write_text(text)
            env=dict(os.environ,TV_TEST_ROOT=str(root),PATH=str(root)+os.pathsep+os.environ['PATH'])
            def invoke(**values):
                subprocess.run(['/bin/sh',str(script),'quick'],env=dict(env,**values),check=True,capture_output=True,timeout=5)
            invoke(TV_TEST_POWER='Suspend')
            (root/'hu.szabi.launcher.power-startup').touch();invoke()
            (root/'hu.szabi.launcher.power-startup').unlink()
            (root/'hu.szabi.launcher.boot-ready').unlink();invoke()
            (root/'hu.szabi.launcher.boot-ready').touch()
            (root/'home-mode').write_text('full');invoke()
            (root/'home-mode').write_text('split')
            (root/'hu.szabi.launcher.quick-prewarm-after').write_text('9999999999');invoke()
            (root/'hu.szabi.launcher.quick-prewarm-after').write_text('0')
            (root/'memory').write_text('MemAvailable: 65536 kB\n');invoke()
            self.assertFalse((root/'launches').exists())
            # A rejected memory attempt is not repeated until another wake.
            (root/'memory').write_text('MemAvailable: 262144 kB\n');invoke()
            self.assertFalse((root/'launches').exists())
            (root/'hu.szabi.launcher.active-since').write_text('1001')
            invoke();invoke()
            calls=[json.loads(x) for x in (root/'launches').read_text().splitlines()]
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['id'],server.LAUNCHER_QUICK_APP_ID)
            self.assertEqual(calls[0]['preload'],'full')
            self.assertTrue(calls[0]['keepAlive'])
            self.assertEqual(calls[0]['params']['source'],'preload')
            self.assertEqual(calls[0]['params']['launcherHost'],'quick')
            (root/'hu.szabi.launcher.active-since').write_text('1002')
            (root/'already-running').touch();invoke()
            (root/'already-running').unlink()
            (root/'hu.szabi.launcher.active-since').write_text('1003')
            invoke(TV_TEST_INTERRUPT='1')
            self.assertEqual(len((root/'launches').read_text().splitlines()),1)

    def exercise_wake_guard(self, driver, resume_last=False, popup=""):
        """Use real guard functions, without its process scan or live loops."""
        with tempfile.TemporaryDirectory(prefix="lgtv-wake-test-") as temporary:
            root = Path(temporary)
            (root / "enabled").touch()
            (root / "control-origin").write_text("http://127.0.0.1:8765")
            (root / "current-popup").write_text(popup)
            (root / "clock").write_text("1000")
            (root / "current-app").write_text("")
            if resume_last:
                (root / "resume-last-app").touch()
            fake = root / "luna-send"
            fake.write_text("#!" + sys.executable + "\n" + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TV_TEST_ROOT"])
uri = sys.argv[-2]
payload = json.loads(sys.argv[-1])
with (root / "calls").open("a") as output:
    output.write(json.dumps({"uri":uri,"payload":payload}) + "\\n")
if uri.endswith("/getForegroundWindowInfo"):
    app = (root / "current-popup").read_text().strip() or (root / "current-app").read_text().strip()
    if (root / "no-surface").exists(): app = ""
    print(json.dumps({"appId":app}))
elif uri.endswith("/getForegroundAppInfo"):
    print(json.dumps({"appId":(root / "current-app").read_text().strip()}))
    if (root / "interrupt-foreground").exists():
        (root / "hu.szabi.launcher.wake-signal").touch()
elif uri.endswith("/getPowerState"):
    power = root / "current-power"
    print(json.dumps({"state":power.read_text().strip() if power.exists() else "Active"}))
elif uri.endswith("/getBootStatus"):
    status = root / "boot-status"
    print(status.read_text() if status.exists() else json.dumps({"powerStatus":"active", "signals":{"boot-done":not (root / "boot-pending").exists()}}))
elif uri.endswith("/launch"):
    print(json.dumps({"returnValue":not (root / "reject-launch").exists()}))
else:
    print('{"returnValue":true}')
''')
            fake.chmod(0o755)
            (root / "luna-send-pub").symlink_to(fake)
            guard = server.LauncherHomeManager.GUARD_SCRIPT
            declarations = guard.split('[ -f "$ENABLED" ] || exit 0', 1)[0]
            functions = guard.split("json_value() {", 1)[1].split(
                '\n# START WORKER', 1)[0]
            clock = '\ndate() { if [ "$1" = +%s ]; then cat "$DIR/clock"; else command date "$@"; fi; }\ntick() { echo "$1" >"$DIR/clock"; control_tick; }\n'
            text = declarations + "json_value() {" + functions + clock + "\n" + driver + "\ntrue\n"
            text = text.replace("DIR=/var/lib/webosbrew/launcher-home", "DIR=" + shlex.quote(str(root)))
            text = text.replace("/tmp/hu.szabi.", str(root) + "/hu.szabi.")
            script = root / "wake.sh"
            script.write_text(text)
            env = dict(os.environ, TV_TEST_ROOT=str(root), PATH=str(root) + os.pathsep + os.environ["PATH"])
            subprocess.run(["sh", str(script)], env=env, check=True, capture_output=True, timeout=8)
            calls_path = root / "calls"
            calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
            states_path = root / "states"
            states = states_path.read_text().splitlines() if states_path.exists() else []
            return calls, states

    def launches(self, calls):
        return [c['payload']['id'] for c in calls if c['uri'].endswith('/launch')]

    def test_power_event_wakes_worker_before_poll_and_is_consumed_once(self):
        calls, states = self.exercise_wake_guard('''
next_poll=2000
echo Suspend >"$POWER_STATE"
echo Active >"$DIR/current-power"
echo com.webos.app.home >"$DIR/current-app"
echo Active >"$POWER_EVENT"
run_pending_tick
cat "$POWER_STATE" >>"$DIR/states"
if [ -f "$POWER_STARTUP" ]; then echo armed >>"$DIR/states"; fi
if [ ! -f "$POWER_EVENT" ]; then echo consumed >>"$DIR/states"; fi
run_pending_tick
''')
        self.assertEqual(states, ['Active', 'armed', 'consumed'])
        self.assertEqual([c['uri'].rsplit('/', 1)[-1] for c in calls], ['getPowerState'],
                         'Power alone must wake the worker; consumed events must not spin it')
        self.assertEqual(self.launches(calls), [], 'The two-second wake readiness gate still applies')

    def test_quick_start_fast_lane_dispatches_once_before_boot_ready(self):
        calls, states = self.exercise_wake_guard('''
quick_fast_lane_safe() { return 0; }
echo Active >"$POWER_STATE"
echo Active >"$DIR/current-power"
handle_power_state 'Active Standby'
handle_power_state unknown
handle_power_state Active
if [ -f "$QUICK_FAST_ATTEMPT" ]; then echo attempted >>"$DIR/states"; fi
handle_power_state Active
''')
        self.assertEqual(states, ['attempted'])
        launches = [c for c in calls if c['uri'].endswith('/launch')]
        self.assertEqual([c['payload']['id'] for c in launches], [server.LAUNCHER_APP_ID])
        self.assertEqual(launches[0]['payload']['params']['source'], 'quick-start-fast-lane')

    def test_quick_start_fast_lane_ignores_unknown_glitch_and_cold_start(self):
        calls, _ = self.exercise_wake_guard('''
quick_fast_lane_safe() { return 0; }
echo Active >"$DIR/current-power"
handle_power_state unknown
handle_power_state Active
rm -f "$POWER_STATE"
handle_power_state Active
''')
        self.assertEqual(self.launches(calls), [])

    def test_quick_start_fast_lane_respects_resume_last_app_setting(self):
        calls, _ = self.exercise_wake_guard('''
quick_fast_lane_safe() { return 0; }
touch "$RESUME_LAST"
echo Active >"$POWER_STATE"
echo Active >"$DIR/current-power"
handle_power_state 'Active Standby'
handle_power_state Active
''', resume_last=True)
        self.assertEqual(self.launches(calls), [])

    def test_power_event_takes_precedence_over_foreground_fast_path(self):
        calls, states = self.exercise_wake_guard('''
next_poll=2000
echo Active >"$POWER_STATE"
touch "$BOOT_READY"
echo Suspend >"$DIR/current-power"
echo com.webos.app.home >"$DIR/current-app"
echo com.webos.app.home >"$FOREGROUND_EVENT"
echo Suspend >"$POWER_EVENT"
run_pending_tick
cat "$POWER_STATE" >>"$DIR/states"
if [ ! -f "$BOOT_READY" ]; then echo boot-invalidated >>"$DIR/states"; fi
if [ ! -f "$FOREGROUND_EVENT" ] && [ ! -f "$POWER_EVENT" ]; then echo consumed >>"$DIR/states"; fi
''')
        self.assertEqual(states, ['Suspend', 'boot-invalidated', 'consumed'])
        self.assertEqual([c['uri'].rsplit('/', 1)[-1] for c in calls], ['getPowerState'],
                         'A simultaneous Home event must not skip processing the power transition')
        self.assertEqual(self.launches(calls), [])

    def test_worker_keeps_power_event_arriving_during_control_tick(self):
        calls, states = self.exercise_wake_guard('''
next_poll=2000
echo Suspend >"$POWER_STATE"
echo Active >"$POWER_EVENT"
fresh_power() {
  if [ ! -f "$DIR/power-replied" ]; then
    touch "$DIR/power-replied"
    echo Suspend >"$POWER_EVENT"
    touch "$WAKE_SIGNAL"
    echo Active
  else
    echo Suspend
  fi
}
run_pending_tick
cat "$POWER_EVENT" >>"$DIR/states"
run_pending_tick
cat "$POWER_STATE" >>"$DIR/states"
if [ ! -f "$POWER_EVENT" ]; then echo consumed-new-event >>"$DIR/states"; fi
if [ ! -f "$POWER_STARTUP" ]; then echo no-pending-launch >>"$DIR/states"; fi
''')
        self.assertEqual(states, ['Suspend', 'Suspend', 'consumed-new-event', 'no-pending-launch'])
        self.assertEqual(self.launches(calls), [])

    def test_standby_unknown_and_boot_pending_never_launch(self):
        for power in ('Suspend', 'Screen Off', ''):
            for app in ('com.webos.app.home', 'com.webos.app.hdmi1', 'com.webos.app.livetv'):
                calls, _ = self.exercise_wake_guard('''
echo "''' + power + '''" >"$DIR/current-power"
echo "''' + app + '''" >"$DIR/current-app"
tick 1000; tick 1010
launch_custom || true
launch_id "$APP" test || true
''')
                self.assertEqual(self.launches(calls), [])
        calls, states = self.exercise_wake_guard('''
echo com.webos.app.home >"$DIR/current-app"
touch "$DIR/boot-pending"
tick 1000; tick 1002; tick 1005
if [ ! -f "$LAST_LAUNCH" ]; then echo blocked >>"$DIR/states"; fi
rm "$DIR/boot-pending"
tick 1006
''')
        self.assertEqual(states, ['blocked'])
        self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID])

    def test_delayed_hdmi_and_livetv_wake_waits_for_actual_visibility(self):
        for app in ('com.webos.app.home', 'com.webos.app.hdmi1', 'com.webos.app.livetv'):
            calls, states = self.exercise_wake_guard('''
echo youtube.leanback.v4 >"$FOREGROUND"
tick 1000; tick 1002
echo ''' + app + ''' >"$DIR/current-app"
tick 1003
if [ -f "$POWER_STARTUP" ]; then echo accepted-pending >>"$DIR/states"; fi
echo hu.szabi.launcher >"$DIR/current-app"
tick 1004
echo ''' + app + ''' >"$DIR/current-app"
tick 1011
if [ -f "$POWER_STARTUP" ]; then echo restored-input-pending >>"$DIR/states"; fi
echo hu.szabi.launcher >"$DIR/current-app"
tick 1012; tick 1014
if [ ! -f "$POWER_STARTUP" ]; then echo visible-settled >>"$DIR/states"; fi
echo com.webos.app.hdmi2 >"$DIR/current-app"
tick 1018
''')
            self.assertEqual(states, ['accepted-pending', 'restored-input-pending', 'visible-settled'])
            self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID] * 2)

    def test_accepted_failed_and_throttled_requests_remain_pending(self):
        for reject in (False, True):
            calls, states = self.exercise_wake_guard(('touch "$DIR/reject-launch"\n' if reject else '') + '''
echo com.webos.app.hdmi1 >"$DIR/current-app"
tick 1000; tick 1002; tick 1003; tick 1004; tick 1006
if [ -f "$POWER_STARTUP" ]; then echo pending >>"$DIR/states"; fi
tick 1010
''')
            self.assertEqual(states, ['pending'])
            self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID] * 2)

    def test_real_youtube_and_native_popups_are_preserved(self):
        for app, popup in [('youtube.leanback.v4', ''),
                           ('com.webos.app.home', server.LAUNCHER_QUICK_APP_ID),
                           ('com.webos.app.hdmi1', server.LAUNCHER_OVERLAY_APP_ID)]:
            calls, states = self.exercise_wake_guard('''
echo ''' + app + ''' >"$DIR/current-app"
tick 1000; tick 1002
if [ ! -f "$POWER_STARTUP" ]; then echo settled >>"$DIR/states"; fi
tick 1005
''', popup=popup)
            self.assertEqual(states, ['settled'])
            self.assertEqual(self.launches(calls), [])

    def test_screensaver_exit_keeps_manual_hdmi_selection(self):
        for initial in (True, False):
            calls, _ = self.exercise_wake_guard(('' if initial else '''
echo youtube.leanback.v4 >"$DIR/current-app"
tick 1000; tick 1002
''') + '''
echo 'Screen Saver' >"$DIR/current-power"
tick 1050
echo Active >"$DIR/current-power"
echo com.webos.app.hdmi1 >"$DIR/current-app"
tick 1051; tick 1053; tick 1060
''')
            self.assertEqual(self.launches(calls), [])

    def test_wake_expiry_does_not_take_over_later_user_input(self):
        calls, states = self.exercise_wake_guard('''
echo com.webos.app.hdmi1 >"$DIR/current-app"
tick 1000; tick 1002
cat "$WAKE_RETRY_UNTIL" >>"$DIR/states"
echo com.webos.app.hdmi2 >"$DIR/current-app"
tick 1042; tick 1050
if [ ! -f "$POWER_STARTUP" ]; then echo expired >>"$DIR/states"; fi
''')
        self.assertEqual(states, ['1042', 'expired'])
        self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID])

    def test_slow_boot_or_surface_starts_attempt_budget_only_when_ready(self):
        for pending in ('boot-pending', 'no-surface'):
            with self.subTest(pending=pending):
                calls, states = self.exercise_wake_guard('''
echo com.webos.app.livetv >"$DIR/current-app"
touch "$DIR/''' + pending + '''"
tick 1000; tick 1002; tick 1041; tick 1059
if [ ! -f "$WAKE_RETRY_UNTIL" ] && [ ! -f "$LAST_LAUNCH" ]; then echo waiting >>"$DIR/states"; fi
rm "$DIR/''' + pending + '''"
touch "$DIR/reject-launch"
tick 1060
cat "$WAKE_RETRY_UNTIL" >>"$DIR/states"
tick 1061; tick 1068
cat "$WAKE_RETRY_UNTIL" >>"$DIR/states"
echo com.webos.app.hdmi2 >"$DIR/current-app"
tick 1100; tick 1110
if [ ! -f "$POWER_STARTUP" ] && [ ! -f "$WAKE_WAIT_UNTIL" ] && [ ! -f "$WAKE_RETRY_UNTIL" ]; then echo expired >>"$DIR/states"; fi
''')
                self.assertEqual(states, ['waiting', '1100', '1100', 'expired'])
                self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID] * 2)

    def test_maximum_boot_wait_expires_once_without_late_hdmi_takeover(self):
        for ready_at in (1179, 1180, 1200):
            with self.subTest(ready_at=ready_at):
                calls, states = self.exercise_wake_guard('''
echo com.webos.app.hdmi1 >"$DIR/current-app"
touch "$DIR/boot-pending"
tick 1000; tick 1060
rm "$DIR/boot-pending"
tick ''' + str(ready_at) + '''
if [ -f "$WAKE_RETRY_UNTIL" ]; then cat "$WAKE_RETRY_UNTIL" >>"$DIR/states"; fi
tick 1220; tick 1230
if [ ! -f "$POWER_STARTUP" ]; then echo settled >>"$DIR/states"; fi
''')
                self.assertEqual(states, ['1219', 'settled'] if ready_at == 1179 else ['settled'])
                self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID] if ready_at == 1179 else [])

    def test_real_app_or_popup_seen_before_boot_ready_ends_wake_attempt(self):
        for app, popup in [('youtube.leanback.v4', ''),
                           ('com.webos.app.livetv', server.LAUNCHER_QUICK_APP_ID)]:
            with self.subTest(app=app, popup=popup):
                calls, states = self.exercise_wake_guard('''
touch "$DIR/boot-pending"
echo ''' + app + ''' >"$DIR/current-app"
tick 1000; tick 1002
if [ ! -f "$POWER_STARTUP" ]; then echo preserved >>"$DIR/states"; fi
rm "$DIR/boot-pending"
echo '' >"$DIR/current-popup"
echo com.webos.app.hdmi1 >"$DIR/current-app"
tick 1060; tick 1200
''', popup=popup)
                self.assertEqual(states, ['preserved'])
                self.assertEqual(self.launches(calls), [])

    def test_suspend_while_waiting_clears_both_deadlines_and_rearms_next_wake(self):
        calls, states = self.exercise_wake_guard('''
echo com.webos.app.livetv >"$DIR/current-app"
touch "$DIR/boot-pending"
tick 1000; tick 1060
echo Suspend >"$DIR/current-power"
tick 1061
if [ ! -f "$POWER_STARTUP" ] && [ ! -f "$WAKE_WAIT_UNTIL" ] && [ ! -f "$WAKE_RETRY_UNTIL" ]; then echo cleared >>"$DIR/states"; fi
rm "$DIR/boot-pending"
echo Active >"$DIR/current-power"
tick 1100; tick 1102
cat "$WAKE_RETRY_UNTIL" >>"$DIR/states"
''')
        self.assertEqual(states, ['cleared', '1142'])
        self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID])

    def test_slow_rpc_cannot_dispatch_after_readiness_or_attempt_deadline(self):
        for phase in ('waiting', 'attempt'):
            with self.subTest(phase=phase):
                calls, states = self.exercise_wake_guard('''
echo com.webos.app.hdmi1 >"$DIR/current-app"
tick 1000
''' + ('''tick 1002
fresh_power() {
  if [ -f "$DIR/power-polled" ]; then echo 1042 >"$DIR/clock"; else touch "$DIR/power-polled"; fi
  echo Active
}
tick 1010
''' if phase == 'attempt' else '''foreground_decision() { current=com.webos.app.hdmi1; echo 1180 >"$DIR/clock"; return 0; }
tick 1179
''') + '''
if [ ! -f "$POWER_STARTUP" ]; then echo expired >>"$DIR/states"; fi
''')
                self.assertEqual(states, ['expired'])
                self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID] if phase == 'attempt' else [])

    def test_full_launcher_requires_visible_native_surface_to_settle(self):
        calls, states = self.exercise_wake_guard('''
echo com.webos.app.livetv >"$DIR/current-app"
tick 1000; tick 1002
echo hu.szabi.launcher >"$DIR/current-app"
touch "$DIR/no-surface"
tick 1003; tick 1006
if [ -f "$POWER_STARTUP" ] && [ ! -f "$WAKE_VISIBLE_SINCE" ]; then echo not-visible >>"$DIR/states"; fi
rm "$DIR/no-surface"
tick 1007; tick 1009
if [ ! -f "$POWER_STARTUP" ]; then echo visible-settled >>"$DIR/states"; fi
''')
        self.assertEqual(states, ['not-visible', 'visible-settled'])
        self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID])

    def test_power_off_during_foreground_query_invalidates_dispatch(self):
        calls, _ = self.exercise_wake_guard('''
echo com.webos.app.home >"$DIR/current-app"
touch "$DIR/interrupt-foreground"
tick 1000; tick 1002
''')
        self.assertEqual(self.launches(calls), [])

    def test_fresh_power_recheck_blocks_old_active_marker(self):
        calls, _ = self.exercise_wake_guard('''
echo Active >"$POWER_STATE"
touch "$BOOT_READY"
echo Suspend >"$DIR/current-power"
launch_id "$APP" test || true
''')
        self.assertEqual(self.launches(calls), [])

    def test_missed_power_event_wall_gap_arms_new_hdmi_wake(self):
        calls, _ = self.exercise_wake_guard('''
echo youtube.leanback.v4 >"$DIR/current-app"
tick 1000; tick 1002
echo com.webos.app.hdmi1 >"$DIR/current-app"
touch "$WAKE_SIGNAL"
tick 1100; tick 1102
''')
        self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID])

    def test_last_app_resume_is_preserved_until_observed(self):
        calls, states = self.exercise_wake_guard('''
echo youtube.leanback.v4 >"$DIR/current-app"
tick 1000; tick 1002
echo Suspend >"$DIR/current-power"
tick 1005
echo Active >"$DIR/current-power"
echo com.webos.app.livetv >"$DIR/current-app"
tick 1100; tick 1102; tick 1103
if [ -f "$POWER_OFF_APP" ]; then echo saved >>"$DIR/states"; fi
echo youtube.leanback.v4 >"$DIR/current-app"
tick 1104
if [ ! -f "$POWER_STARTUP" ]; then echo settled >>"$DIR/states"; fi
''', resume_last=True)
        self.assertEqual(states, ['saved', 'settled'])
        self.assertEqual(self.launches(calls), ['youtube.leanback.v4'])

    def test_last_app_failure_falls_back_without_launch_storm(self):
        calls, _ = self.exercise_wake_guard('''
echo Active >"$POWER_STATE"
arm_power_startup
echo youtube.leanback.v4 >"$POWER_OFF_APP"
echo com.webos.app.livetv >"$DIR/current-app"
tick 1002; tick 1003; tick 1012
''', resume_last=True)
        self.assertEqual(self.launches(calls), ['youtube.leanback.v4', server.LAUNCHER_APP_ID])

    def test_slow_boot_keeps_full_last_app_resume_budget(self):
        calls, _ = self.exercise_wake_guard('''
echo Active >"$POWER_STATE"
arm_power_startup
echo youtube.leanback.v4 >"$POWER_OFF_APP"
echo com.webos.app.livetv >"$DIR/current-app"
touch "$DIR/boot-pending"
tick 1002; tick 1059
rm "$DIR/boot-pending"
tick 1060; tick 1061; tick 1070
''', resume_last=True)
        self.assertEqual(self.launches(calls), ['youtube.leanback.v4', server.LAUNCHER_APP_ID])

    def test_factory_home_replaces_old_escape_but_keeps_disabled_guard(self):
        for enabled in (True, False):
            calls, _ = self.exercise_wake_guard('''
echo Active >"$POWER_STATE"
touch "$BOOT_READY" "$ALLOW"
echo 2000 >"$FULL_CLOSE_SUPPRESS"
echo com.webos.app.home >"$DIR/current-app"
''' + ('' if enabled else 'rm "$ENABLED"\n') + '''
replace_visible_factory_home || true
''')
            self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID] if enabled else [])

    def test_prewarm_during_wake_quiet_period_is_not_started(self):
        calls, states = self.exercise_wake_guard('''
echo full >"$DIR/home-mode"
printf '#!/bin/sh\necho started >>"%s/states"\n' "$DIR" >"$DIR/prewarm.sh"
chmod +x "$DIR/prewarm.sh"
echo youtube.leanback.v4 >"$DIR/current-app"
tick 1000; tick 1002; tick 1007
tick 1008
''')
        self.assertEqual(states, ['started'])
        self.assertEqual(self.launches(calls), [])

    def test_ready_native_boot_can_dispatch_after_one_second(self):
        calls, _ = self.exercise_wake_guard('''
echo com.webos.app.hdmi1 >"$DIR/current-app"
tick 1000; tick 1001
''')
        self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID])

    def test_saved_lock_directories_do_not_block_new_wake(self):
        calls, _ = self.exercise_wake_guard('''
mkdir "$DIR/hu.szabi.launcher.launch-lock" "$DIR/hu.szabi.launcher.resume-claim"
echo com.webos.app.hdmi1 >"$DIR/current-app"
tick 1000; tick 1002
''')
        self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID])

    def test_minimal_boot_requires_first_app_and_native_surface(self):
        for minimal, first, active, visible in [(True, True, True, True), (False, True, True, True),
                                               (True, False, True, True), (True, True, False, True),
                                               (True, True, True, False)]:
            status = json.dumps({'powerStatus': 'active' if active else 'standby',
                                 'firstAppLaunched': first,
                                 'signals': {'boot-done': False, 'minimal-boot-done': minimal}})
            calls, _ = self.exercise_wake_guard('''
echo com.webos.app.home >"$DIR/current-app"
printf '%s' ''' + shlex.quote(status) + ''' >"$DIR/boot-status"
''' + ('' if visible else 'touch "$DIR/no-surface"\n') + '''
tick 1000; tick 1001; tick 1002
''')
            self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID] if all((minimal, first, active, visible)) else [])

    def test_new_home_visit_bypasses_cooldown_but_duplicate_does_not(self):
        calls, _ = self.exercise_wake_guard('''
echo Active >"$POWER_STATE"
touch "$BOOT_READY"
touch "$DIR/no-surface"
echo com.webos.app.home >"$DIR/current-app"
control_tick foreground-event
control_tick foreground-event
echo hu.szabi.launcher >"$DIR/current-app"
control_tick foreground-event
echo 1001 >"$DIR/clock"
echo com.webos.app.home >"$DIR/current-app"
control_tick foreground-event
control_tick foreground-event
''')
        self.assertEqual(self.launches(calls), [server.LAUNCHER_APP_ID] * 2)
        power_calls = [c for c in calls if c['uri'].endswith('/getPowerState')]
        self.assertEqual(len(power_calls), 2, 'Each dispatch checks fresh power, without another periodic query')

    def test_fast_home_event_still_checks_fresh_power_and_suspend_signal(self):
        for interruption in ('echo Suspend >"$DIR/current-power"', 'touch "$DIR/interrupt-foreground"'):
            calls, _ = self.exercise_wake_guard('''
echo Active >"$POWER_STATE"
touch "$BOOT_READY"
echo com.webos.app.home >"$DIR/current-app"
''' + interruption + '''
control_tick foreground-event
''')
            self.assertEqual(self.launches(calls), [])


@unittest.skipIf(os.name == 'nt', 'POSIX shell tests run on the PVE test fixture')
class HomeHookRepairTests(unittest.TestCase):
    def test_watchdog_runs_only_repair_once_and_keeps_its_singleton_lock(self):
        with tempfile.TemporaryDirectory(prefix='lgtv-watchdog-test-') as temporary:
            root = Path(temporary)
            helper = root / 'repair-home-hook.sh'
            helper.write_text('#!/bin/sh\n' + '''
echo repair >>"$TV_TEST_ROOT/calls"
touch "$TV_TEST_ROOT/ready"
while [ ! -f "$TV_TEST_ROOT/release" ]; do sleep 0.01; done
rm -f "$TV_TEST_ROOT/enabled"
''')
            helper.chmod(0o755)
            fake = root / 'luna-send'
            fake.write_text('#!/bin/sh\necho forbidden-luna >>"$TV_TEST_ROOT/calls"\n')
            fake.chmod(0o755)
            (root / 'luna-send-pub').symlink_to(fake)
            text = server.InputHookWatchdogManager.WATCHDOG_SCRIPT
            text = text.replace('/var/lib/webosbrew/inputhook-watchdog', str(root))
            text = text.replace('/tmp/hu.szabi.', str(root) + '/hu.szabi.')
            script = root / 'watchdog.sh'
            script.write_text(text)
            env = dict(os.environ, TV_TEST_ROOT=str(root), PATH=str(root) + os.pathsep + os.environ['PATH'])
            # Disabled means no helper or service calls at all.
            subprocess.run(['sh', str(script)], env=env, check=True, capture_output=True, timeout=3)
            self.assertFalse((root / 'calls').exists())
            (root / 'enabled').touch()
            process = subprocess.Popen(['sh', str(script)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                until = time.monotonic() + 3
                while not (root / 'ready').exists() and time.monotonic() < until:
                    time.sleep(0.01)
                self.assertTrue((root / 'ready').exists(), 'The repair helper must be reached')
                pidfile = root / 'hu.szabi.inputhook-watchdog.pid'
                self.assertEqual(pidfile.read_text().strip(), str(process.pid))
                subprocess.run(['sh', str(script)], env=env, check=True, capture_output=True, timeout=3)
                self.assertEqual(pidfile.read_text().strip(), str(process.pid), 'A duplicate must not replace the owner PID')
                (root / 'release').touch()
                process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0)
                self.assertFalse(pidfile.exists())
                self.assertEqual((root / 'calls').read_text().splitlines(), ['repair'])
            finally:
                (root / 'release').touch()
                if process.poll() is None:
                    process.terminate()
                    process.communicate(timeout=5)

    def exercise(self, scenario):
        with tempfile.TemporaryDirectory(prefix='lgtv-hook-test-') as temporary:
            root = Path(temporary)
            watchdog, launcher, assets = (root / name for name in ('watchdog', 'launcher', 'assets'))
            proc = root / 'proc/123'
            for folder in (watchdog, launcher, assets / 'libcrypt1', assets / 'libcrypt2', proc):
                folder.mkdir(parents=True)
            for marker in (watchdog / 'enabled', launcher / 'enabled', root / 'hu.szabi.launcher.boot-ready'):
                marker.touch()
            (root / 'hu.szabi.launcher.power-state').write_text('Active')
            (root / 'hu.szabi.launcher.active-since').write_text('100')
            (root / 'power').write_text('Active')
            (root / 'keybinds.json').write_text('{}')
            (proc / 'comm').write_text('lginput2')
            (proc / 'stat').write_text('123 (lginput2) S ' + '0 ' * 18 + '440255')
            (proc / 'maps').write_text('')
            for path in (assets / 'libcrypt1/libphp.so', assets / 'libcrypt2/libphp.so', assets / 'lginput-hook.php'):
                path.touch()
            pidof = root / 'pidof'
            pidof.write_text('#!/bin/sh\n[ "$1" = lginput2 ] && echo 123\n')
            pidof.chmod(0o755)
            fake = root / 'luna-send'
            fake.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib
root = pathlib.Path(os.environ['TV_TEST_ROOT'])
if (root / 'replace-pid').exists():
    stat = root / 'proc/123/stat'
    stat.write_text('123 (lginput2) S ' + '0 ' * 18 + str(int(stat.read_text().split()[-1]) + 1))
if (root / 'attach-during-query').exists():
    (root / 'proc/123/maps').write_text('libphp.so')
response = root / 'power-response'
print(response.read_text() if response.exists() else json.dumps({'state': (root / 'power').read_text()}))
''')
            fake.chmod(0o755)
            injector = assets / 'ezinject'
            injector.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TV_TEST_ROOT'])
with (root / 'calls').open('a') as stream: stream.write(json.dumps(sys.argv[1:]) + '\\n')
if not (root / 'fail-injection').exists(): (root / 'proc/123/maps').write_text('libphp.so')
''')
            injector.chmod(0o755)
            if scenario in ('already-attached', 'retained-two-wakes'): (proc / 'maps').write_text('libphp.so')
            elif scenario == 'cached-suspend': (root / 'hu.szabi.launcher.power-state').write_text('Suspend')
            elif scenario == 'fresh-suspend': (root / 'power').write_text('Suspend')
            elif scenario in ('active-idle', 'active-suspending', 'active-off', 'active-unknown-processing'):
                response = {'state': 'Active', 'processing': '', 'onOff': 'on'}
                if scenario == 'active-suspending': response['processing'] = 'Request Suspend'
                elif scenario == 'active-off': response['onOff'] = 'off'
                elif scenario == 'active-unknown-processing': response['processing'] = None
                (root / 'power-response').write_text(json.dumps(response))
            elif scenario in ('wake-signal', 'power-startup'): (root / ('hu.szabi.launcher.' + scenario)).touch()
            elif scenario == 'disabled': (watchdog / 'enabled').unlink()
            elif scenario == 'wrong-process': (proc / 'comm').write_text('micomservice')
            elif scenario in ('replace-pid', 'attach-during-query', 'fail-injection'): (root / scenario).touch()
            text = server.InputHookWatchdogManager.REPAIR_SCRIPT
            for original, replacement in [('/var/lib/webosbrew/inputhook-watchdog', watchdog),
                                           ('/var/lib/webosbrew/launcher-home', launcher),
                                           ('/media/developer/apps/usr/palm/services/org.webosbrew.inputhook.service/inputhook', assets),
                                           ('/tmp/hu.szabi.', str(root) + '/hu.szabi.'),
                                           ('/proc/', str(root) + '/proc/'),
                                           ('/home/root/.config/lginputhook/keybinds.json', root / 'keybinds.json')]:
                text = text.replace(original, str(replacement))
            text = text.replace('sleep 1', 'true')
            script = root / 'repair.sh'
            script.write_text(text)
            env = dict(os.environ, TV_TEST_ROOT=str(root), PATH=str(root) + os.pathsep + os.environ['PATH'])
            output = ''
            for iteration in range(4 if scenario == 'retained-two-wakes' else 2):
                if iteration == 2: (root / 'hu.szabi.launcher.active-since').write_text('200')
                output += subprocess.run(['sh', str(script)], env=env, check=True, capture_output=True, text=True, timeout=5).stdout
            calls = root / 'calls'
            if scenario == 'retained-two-wakes':
                self.assertFalse(calls.exists(), 'A retained hook must never be reinjected')
                self.assertEqual(output.count('keybind reload'), 2, 'Exactly one config reload per wake')
                self.assertTrue((root / 'hu.szabi.inputhook-reloaded').read_text().strip().endswith(':200'))
            return [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []

    def test_retained_hook_reloads_config_once_each_wake_without_reinjection(self):
        self.assertEqual(self.exercise('retained-two-wakes'), [])

    def test_repair_only_attaches_once_to_the_expected_native_process(self):
        for scenario in ('missing-hook', 'active-idle', 'fail-injection'):
            calls = self.exercise(scenario)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], '123')
            self.assertEqual(calls[0][-1], 'lginput2')
            self.assertTrue(calls[0][1].endswith('/libphp.so'))
            self.assertTrue(calls[0][2].endswith('/lginput-hook.php'))

    def test_repair_skips_unsafe_or_already_attached_processes(self):
        for scenario in ('already-attached', 'cached-suspend', 'fresh-suspend', 'wake-signal',
                         'power-startup', 'disabled', 'wrong-process', 'replace-pid', 'attach-during-query',
                         'active-suspending', 'active-off', 'active-unknown-processing'):
            with self.subTest(scenario=scenario):
                self.assertEqual(self.exercise(scenario), [])


@unittest.skipIf(os.name == 'nt', 'POSIX shell tests run on the PVE test fixture')
class ParkForegroundTests(unittest.TestCase):
    def test_delayed_full_park_cannot_launch_an_app_from_the_background(self):
        for foreground in ('hu.szabi.launcher', 'youtube.leanback.v4', 'hu.szabi.launcher.quick', ''):
            with self.subTest(foreground=foreground), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                probe = root / 'luna-send'
                probe.write_text('#!/bin/sh\nprintf \'%s\\n\' "$TV_WINDOW"\n')
                probe.chmod(0o755)
                launch = root / 'luna-send-pub'
                launch.write_text('#!/bin/sh\ntouch "$TV_TEST_ROOT/launched"\nprintf \'%s\\n\' \'{"returnValue":true}\'\n')
                launch.chmod(0o755)
                env = dict(os.environ, TV_TEST_ROOT=str(root), PATH=str(root)+os.pathsep+os.environ['PATH'],
                           TV_WINDOW=json.dumps({'returnValue':True,'windows':[{'appId':foreground}]}))
                manager = server.LauncherHomeManager({'tv_host':'192.168.0.240','ssh_key':'/test-key','known_hosts':'/test-known'})
                manager.last_app = lambda: 'youtube.leanback.v4'
                def execute(command):
                    command = command.replace('/tmp/hu.szabi.launcher.', str(root)+'/')
                    return subprocess.run(['sh','-c',command],env=env,check=True,capture_output=True,text=True).stdout
                manager._run_lifecycle = execute
                result = manager.park_launcher('full')
                expected = foreground == 'hu.szabi.launcher'
                self.assertEqual((root/'launched').exists(), expected)
                self.assertEqual((root/'allow-home').exists(), expected)
                self.assertEqual(result.get('ignored',False), not expected)


if __name__ == "__main__":
    unittest.main()
