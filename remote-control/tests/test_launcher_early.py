import sys
import unittest
import tempfile
import json
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from launcher_early import WakePolicy, FULL, HOME, CredentialLatch, pairing_paused, credential_stamp, atomic_json

SETTINGS={'defaultHomeEnabled':True,'fullLauncherPresentation':'app'}

class WakePolicyTests(unittest.TestCase):
    def test_no_wake_on_startup_or_network_reconnect(self):
        p=WakePolicy(); p.power_changed('Active',0)
        self.assertIsNone(p.candidate('com.webos.app.hdmi2',SETTINGS,1))
        p.disconnected();p.power_changed('Active',100)
        self.assertIsNone(p.candidate('com.webos.app.hdmi2',SETTINGS,101))

    def test_home_without_verified_wake_is_delegated_to_tv_guard(self):
        p=WakePolicy();p.power_changed('Active',0)
        self.assertIsNone(p.candidate(HOME,SETTINGS,1))
        p.disconnected();p.power_changed('Active',20)
        self.assertIsNone(p.candidate(HOME,SETTINGS,21))

    def test_home_is_accelerated_once_in_verified_wake_window(self):
        p=WakePolicy(off_observed=True);p.power_changed('Active',0)
        self.assertEqual(p.candidate(HOME,SETTINGS,1),FULL)
        p.mark_dispatch()
        self.assertIsNone(p.candidate(HOME,SETTINGS,10))

    def test_real_off_active_arms_once(self):
        p=WakePolicy();p.power_changed('Active Standby',0);p.disconnected()
        p.power_changed('Active',100)
        self.assertEqual(p.candidate('com.webos.app.hdmi1',SETTINGS,101),FULL)
        p.mark_dispatch();p.power_changed('Active',102)
        self.assertIsNone(p.candidate('com.webos.app.hdmi1',SETTINGS,110))

    def test_user_app_cancels_wake_including_later_hdmi(self):
        p=WakePolicy(off_observed=True);p.power_changed('Active',0)
        self.assertIsNone(p.candidate('cdp-30',SETTINGS,1))
        self.assertIsNone(p.candidate('com.webos.app.hdmi2',SETTINGS,2))
        self.assertIsNone(p.candidate(HOME,SETTINGS,3))

    def test_native_own_popup_prevents_competing_guard_launch(self):
        for app in (FULL,FULL+'.quick',FULL+'.overlay'):
            p=WakePolicy(off_observed=True);p.power_changed('Active',0)
            self.assertIsNone(p.candidate(app,SETTINGS,1))
            self.assertIsNone(p.candidate('com.webos.app.hdmi2',SETTINGS,2))

    def test_timeout_and_unknown_power_fail_closed(self):
        p=WakePolicy(off_observed=True);p.power_changed('Active',0)
        self.assertIsNone(p.candidate('com.webos.app.hdmi2',SETTINGS,21))
        self.assertIsNone(p.candidate(HOME,SETTINGS,21))
        p.power_changed('',22)
        self.assertIsNone(p.candidate(HOME,SETTINGS,23))

    def test_screensaver_is_not_a_power_cycle(self):
        p=WakePolicy();p.power_changed('Screen Saver',0);p.power_changed('Active',1)
        self.assertIsNone(p.candidate('com.webos.app.hdmi1',SETTINGS,2))

    def test_user_settings_and_selected_presentation(self):
        for settings in ({'defaultHomeEnabled':False},{'defaultHomeEnabled':True,'resumeLastAppOnPowerEnabled':True}):
            p=WakePolicy(off_observed=True);p.power_changed('Active',0)
            self.assertIsNone(p.candidate(HOME,settings,1))
        p=WakePolicy(off_observed=True);p.power_changed('Active',0)
        self.assertEqual(p.candidate(HOME,{**SETTINGS,'fullLauncherPresentation':'overlay'},1),FULL+'.overlay')

    def test_explicit_rejection_retries_once_but_timeout_never_does(self):
        p=WakePolicy(off_observed=True);p.power_changed('Active',0)
        self.assertEqual(p.candidate(HOME,SETTINGS,1),FULL)
        p.mark_dispatch();p.explicit_rejection(1)
        self.assertIsNone(p.candidate(HOME,SETTINGS,2))
        self.assertEqual(p.candidate(HOME,SETTINGS,4),FULL)
        p.mark_dispatch();p.explicit_rejection(4)
        self.assertIsNone(p.candidate(HOME,SETTINGS,8))
        p.disconnected();p.power_changed('Active',9)
        self.assertIsNone(p.candidate(HOME,SETTINGS,10))

    def test_new_home_visit_cannot_rearm_accelerator(self):
        p=WakePolicy(off_observed=True);p.power_changed('Active',0)
        p.candidate(HOME,SETTINGS,1);p.mark_dispatch()
        p.candidate('youtube.leanback.v4',SETTINGS,2)
        self.assertIsNone(p.candidate(HOME,SETTINGS,3))

    def test_pairing_cancels_even_persisted_off_signal(self):
        p=WakePolicy(off_observed=True);p.pairing_started()
        p.power_changed('Active',0)
        self.assertIsNone(p.candidate(HOME,SETTINGS,1))

    def test_second_real_wake_is_still_supported(self):
        p=WakePolicy(off_observed=True);p.power_changed('Active',0)
        p.candidate(HOME,SETTINGS,1);p.mark_dispatch()
        p.power_changed('Active Standby',50);p.power_changed('Active',100)
        self.assertEqual(p.candidate(HOME,SETTINGS,101),FULL)

    def test_unknown_request_outcome_stays_consumed_even_after_home_change(self):
        p=WakePolicy(off_observed=True);p.power_changed('Active',0)
        p.candidate(HOME,SETTINGS,1);p.mark_dispatch()
        p.candidate('com.webos.app.hdmi1',SETTINGS,2)
        self.assertIsNone(p.candidate(HOME,SETTINGS,3))


class CredentialLatchTests(unittest.TestCase):
    def test_unchanged_bad_credentials_never_retry(self):
        gate=CredentialLatch();gate.reject(100)
        for _ in range(20): self.assertFalse(gate.ready(100,paused=False))

    def test_changed_key_waits_for_pairing_marker_to_expire(self):
        gate=CredentialLatch();gate.reject(100)
        self.assertFalse(gate.ready(101,paused=True))
        self.assertTrue(gate.ready(101,paused=False))
        self.assertTrue(gate.ready(101,paused=False))

    def test_missing_and_deleted_credentials_do_not_unlatch(self):
        gate=CredentialLatch();gate.reject(None)
        self.assertFalse(gate.ready(None,paused=False))
        self.assertTrue(gate.ready(100,paused=False))
        gate.reject(100)
        self.assertFalse(gate.ready(None,paused=False))
        self.assertFalse(gate.ready(100,paused=False))

    def test_pairing_pauses_even_valid_connection(self):
        self.assertFalse(CredentialLatch().ready(100,paused=True))


class FileStateTests(unittest.TestCase):
    def test_atomic_state_is_readable_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            atomic_json(path,{'test':True})
            self.assertEqual(json.loads(path.read_text()),{'test':True})
            self.assertIsNotNone(credential_stamp(path))
            if os.name!='nt': self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(list(Path(directory).iterdir()),[path])

    def test_pairing_marker_expiry_and_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'marker.json'
            self.assertFalse(pairing_paused(path,100))
            atomic_json(path,{'until':120})
            self.assertTrue(pairing_paused(path,119))
            self.assertFalse(pairing_paused(path,120))
            self.assertFalse(pairing_paused(path,121))

    def test_corrupt_marker_fails_closed_then_expires(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'marker.json'
            atomic_json(path,{'until':[]})
            modified=path.stat().st_mtime
            self.assertTrue(pairing_paused(path,modified+119))
            self.assertFalse(pairing_paused(path,modified+120))

    def test_absent_credentials_have_no_stamp(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(credential_stamp(Path(directory)/'absent.json'))

class FallbackCooperationTests(unittest.TestCase):
    def test_recent_launch_and_visible_popup_delegate_to_tv(self):
        from launcher_early import root_state_busy
        home='{"returnValue":true,"windows":[{"appId":"com.webos.app.home","windowType":"_WEBOS_WINDOW_TYPE_CARD"}]}'
        self.assertTrue(root_state_busy('100\n99\npayload '+home))
        self.assertFalse(root_state_busy('100\n80\npayload '+home))
        self.assertFalse(root_state_busy('100\npayload '+home))
        self.assertTrue(root_state_busy('100\npayload '+home.replace('com.webos.app.home',FULL+'.quick')))
        self.assertTrue(root_state_busy('100\npayload '+home.replace('_WEBOS_WINDOW_TYPE_CARD','_WEBOS_WINDOW_TYPE_ALERT')))
        self.assertTrue(root_state_busy('100\nunparseable'))

if __name__=='__main__':unittest.main()
