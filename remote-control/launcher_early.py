#!/usr/bin/env python3
"""Native-network launcher accelerator; TV-local guard remains the fallback.

Reconnection is NOT a wake signal. Every takeover requires an observed native
off -> Active transition. SSAP cannot see every popup above a foreground card,
so ordinary Home visits remain solely the TV-local guard's responsibility.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

HOME = 'com.webos.app.home'
FULL = 'hu.szabi.launcher'
OWN = {FULL, FULL + '.quick', FULL + '.overlay'}
OFF = {'Active Standby', 'Suspend', 'Power Off', 'PowerOff', 'Standby'}
ACTIVE = 'Active'
TRANSIENT = ('com.webos.app.notification', 'com.webos.app.volume', 'com.webos.app.power',
             'com.webos.app.quicksettings', 'com.webos.app.spinner', 'com.webos.app.toast')


def eligible_input(app: str) -> bool:
    return app == 'com.webos.app.livetv' or app.startswith(('com.webos.app.hdmi', 'com.webos.app.externalinput'))


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        if os.name != 'nt': os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, separators=(',', ':'))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict): raise ValueError('Expected object')
    return value


def credential_stamp(path: Path) -> int | None:
    try: return path.stat().st_mtime_ns
    except OSError: return None


def pairing_paused(path: Path, now: float) -> bool:
    try: return float(read_json(path).get('until', 0)) > now
    except FileNotFoundError: return False
    except (OSError, ValueError, TypeError):
        # Fail closed for a newly corrupt marker, but a crashed writer must not
        # permanently disable acceleration. Normal markers expire in 95 sec.
        try: return now < path.stat().st_mtime + 120
        except OSError: return False


class CredentialLatch:
    """After a rejected key/certificate, only an explicit credential change retries."""
    def __init__(self):
        self.blocked = False
        self.rejected_stamp = None

    def reject(self, stamp: int | None) -> None:
        self.blocked = True
        self.rejected_stamp = stamp

    def ready(self, stamp: int | None, *, paused: bool) -> bool:
        if paused: return False
        if self.blocked:
            if stamp is None or stamp == self.rejected_stamp: return False
            self.blocked = False
        return True


class WakePolicy:
    """Deterministic, transport-independent safety gate (monotonic seconds)."""
    def __init__(self, *, off_observed: bool = False):
        self.power = ''
        self.off_observed = off_observed
        self.wake_until = 0.0
        self.last_app = ''
        self.dispatched = False
        self.attempts = 0
        self.retry_at = 0.0
        self.reason = 'waiting'

    def power_changed(self, state: str, now: float) -> None:
        if state in OFF:
            self.off_observed = True
            self.wake_until = 0
            self.dispatched = False
            self.attempts = 0
            self.retry_at = 0
        elif state == ACTIVE and self.off_observed:
            self.off_observed = False  # consume before any action/persist
            self.wake_until = now + 20
            self.dispatched = False
            self.attempts = 0
            self.retry_at = 0
        elif state != ACTIVE:
            self.wake_until = 0
        self.power = state

    def disconnected(self) -> None:
        # Do not manufacture standby from a WLAN interruption. In-flight
        # uncertainty is not grounds to repeat a launch after reconnect.
        self.power = ''
        self.wake_until = 0

    def pairing_started(self) -> None:
        # Pairing is an operator workflow, not a reason to open a launcher as
        # soon as its approval popup disappears.
        self.disconnected()
        self.off_observed = False
        self.dispatched = True
        self.reason = 'pairing-paused'

    def observe_foreground(self, app: str, now: float) -> None:
        if not app or app.startswith(TRANSIENT): return
        if app in OWN:
            self.wake_until = 0
            self.dispatched = True
            self.reason = 'launcher-already-running'
        elif app != HOME and not eligible_input(app):
            self.wake_until = 0
            self.dispatched = True
            self.reason = 'user-app-preserved'
        self.last_app = app

    def candidate(self, app: str, settings: dict, now: float) -> str | None:
        self.observe_foreground(app, now)
        if settings.get('defaultHomeEnabled') is not True:
            self.wake_until = 0
            self.reason = 'default-home-disabled'
            return None
        if settings.get('resumeLastAppOnPowerEnabled') is True:
            self.wake_until = 0
            self.reason = 'resume-last-app-delegated-to-tv'
            return None
        if self.power != ACTIVE or self.dispatched or now < self.retry_at:
            return None
        if self.wake_until > now and (app == HOME or eligible_input(app)):
            self.reason = 'verified-wake'
            return FULL + '.overlay' if settings.get('fullLauncherPresentation') == 'overlay' else FULL
        return None

    def mark_dispatch(self) -> None:
        self.dispatched = True  # even timeout is potentially accepted
        self.attempts += 1

    def explicit_rejection(self, now: float) -> None:
        # Only a definitive TV rejection permits one bounded retry. Unknown
        # transport outcome must stay consumed to prevent competing launches.
        if self.attempts < 2:
            self.dispatched = False
            self.retry_at = now + 3


def configuration(config_path: Path) -> tuple[str, str, dict]:
    config = read_json(config_path)
    connections = read_json(Path(config.get('connection_state_path', '/var/lib/lgtv-control/connections.json')))
    launcher = read_json(Path(config.get('launcher_state_path', '/var/lib/lgtv-control/launcher.json')))
    return str(connections.get('tvHost', config['tv_host'])), str(connections.get('controlOrigin', config['public_base_url'])), launcher['settings']


def tv_guard_busy(config_path: Path, host: str) -> bool:
    """Read existing TV state, without changing its fallback scripts/markers.

    Before root SSH is up the native route is free to launch. When it is up,
    preserve a recent guard request and any visible launcher popup. An
    inconclusive root read delegates this wake to the existing local guard.
    """
    try:
        with socket.create_connection((host, 22), timeout=.15): pass
    except OSError:
        return False
    try:
        config = read_json(config_path)
        command = "date +%s; cat /tmp/hu.szabi.launcher.last-launch 2>/dev/null; luna-send -t 1 -f -w 500 luna://com.webos.surfacemanager/getForegroundWindowInfo '{}' 2>&1"
        response = subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=1',
            '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(config['known_hosts']),
            '-i',str(config['ssh_key']),str(config.get('tv_user','root'))+'@'+host,command],
            capture_output=True, text=True, timeout=2)
        if response.returncode: return True
        return root_state_busy(response.stdout + response.stderr)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return True


def root_state_busy(output: str) -> bool:
    lines = output.splitlines()
    if not lines or not lines[0].isdigit(): return True
    now = int(lines[0])
    if len(lines)>1 and lines[1].isdigit() and 0 <= now-int(lines[1]) <= 15: return True
    try:
        response = json.JSONDecoder().raw_decode(output[output.index('{'):])[0]
        if response.get('returnValue') is not True: return True
        return any(row.get('appId') in OWN or row.get('windowType') in
                   {'_WEBOS_WINDOW_TYPE_ALERT','_WEBOS_WINDOW_TYPE_POPUP'}
                   for row in response.get('windows',[]) if isinstance(row,dict))
    except (ValueError, TypeError):
        return True


def main() -> None:
    from lg_ssap import SsapClient, SsapTimeout, PairingRequired, CertificateChanged, POWER_URI, FOREGROUND_URI, LAUNCH_URI
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--state', type=Path, default=Path('/var/lib/lgtv-control/launcher-early-state.json'))
    parser.add_argument('--status', type=Path, default=Path('/var/lib/lgtv-control/launcher-early-status.json'))
    parser.add_argument('--observe-only', action='store_true')
    args = parser.parse_args()
    host, origin, settings = configuration(args.config)
    try: saved = read_json(args.state)
    except (OSError, ValueError): saved = {}
    policy = WakePolicy(off_observed=saved.get('tvHost') == host and saved.get('offObserved') is True)
    last_saved = None
    status = {'transport':'native-lg-ssap', 'observeOnly':args.observe_only, 'launches':0}
    marker = args.credentials.with_name('launcher-pairing-active.json')
    latch = CredentialLatch()
    host_credential_stamp = credential_stamp(args.credentials)
    next_heartbeat = 0.0

    class ConnectionRefresh(Exception): pass

    def publish(event: str, **fields) -> None:
        nonlocal next_heartbeat
        status.update(fields, event=event, updatedAt=time.time())
        atomic_json(args.status, status)
        next_heartbeat = time.monotonic() + 5
        print(json.dumps({'time':time.time(), 'event':event, **fields}), flush=True)

    def heartbeat() -> None:
        nonlocal next_heartbeat
        if time.monotonic() >= next_heartbeat:
            status['updatedAt'] = time.time()
            atomic_json(args.status, status)
            next_heartbeat = time.monotonic() + 5

    def persist() -> None:
        nonlocal last_saved
        value = {'tvHost':host, 'offObserved':policy.off_observed}
        if value != last_saved:
            atomic_json(args.state, value)
            last_saved = value

    while True:
        client = None
        connection_stamp = credential_stamp(args.credentials)
        try:
            heartbeat()
            paused = pairing_paused(marker, time.time())
            if paused:
                policy.pairing_started()
                persist()
                if status.get('event') != 'pairing-paused':
                    publish('pairing-paused', connected=False, wakeArmed=False)
            if not latch.ready(connection_stamp, paused=paused):
                # No socket traffic while latched: not even repeated register
                # attempts that might reopen a firmware pairing prompt.
                if not paused and status.get('event') not in ('pairing-required', 'host-changed-repair-required'):
                    publish('pairing-required', connected=False)
                time.sleep(.5)
                continue
            current_host, origin, settings = configuration(args.config)
            if current_host != host:
                if connection_stamp is None or connection_stamp == host_credential_stamp:
                    latch.reject(connection_stamp)
                    publish('host-changed-repair-required', connected=False)
                    continue
                host = current_host
                policy = WakePolicy()
                persist()
            host_credential_stamp = connection_stamp
            client = SsapClient(host, args.credentials, timeout=2)
            client.connect()
            publish('connected', connected=True)
            power_id = client.subscribe(POWER_URI)
            foreground_id = client.subscribe(FOREGROUND_URI)
            next_poll = 0.0
            while True:
                heartbeat()
                if pairing_paused(marker, time.time()) or credential_stamp(args.credentials) != connection_stamp:
                    raise ConnectionRefresh()
                now = time.monotonic()
                if now >= next_poll:
                    current_host, origin, settings = configuration(args.config)
                    if current_host != host: raise PairingRequired('Configured TV changed')
                    power = client.request(POWER_URI, timeout=2)
                    heartbeat()
                    state = str(power.get('state', ''))
                    if state != policy.power:
                        policy.power_changed(state, now)
                        persist()
                        publish('power', power=state, wakeArmed=policy.wake_until > now)
                    foreground = client.request(FOREGROUND_URI, timeout=2)
                    heartbeat()
                    app = str(foreground.get('appId', ''))
                    target = policy.candidate(app, settings, time.monotonic())
                    if target and tv_guard_busy(args.config, host):
                        policy.mark_dispatch()
                        publish('tv-fallback-in-progress', reason='recent-local-launch-or-popup')
                        target = None
                    if target:
                        # Re-read BOTH immediately before dispatch; never act
                        # on stale subscription events or a last-known app.
                        fresh_power = client.request(POWER_URI, timeout=1)
                        fresh_app = client.request(FOREGROUND_URI, timeout=1)
                        heartbeat()
                        policy.power_changed(str(fresh_power.get('state', '')), time.monotonic())
                        persist()
                        _, origin, settings = configuration(args.config)
                        target = policy.candidate(str(fresh_app.get('appId', '')), settings, time.monotonic())
                        if target:
                            if pairing_paused(marker, time.time()) or credential_stamp(args.credentials) != connection_stamp:
                                raise ConnectionRefresh()
                            reason = policy.reason
                            policy.mark_dispatch()
                            if args.observe_only:
                                publish('would-launch', target=target, reason=reason)
                            else:
                                publish('launch-dispatch', target=target, reason=reason)
                                result = client.request(LAUNCH_URI, {'id':target, 'params':{
                                    'source':'native-early-home', 'controlOrigin':origin,
                                    'displayPreferences':{key:settings[key] for key in ('animationsEnabled','visualEffectsEnabled') if isinstance(settings.get(key),bool)}
                                }}, timeout=4)
                                if result.get('returnValue') is False:
                                    policy.explicit_rejection(time.monotonic())
                                    publish('launch-rejected', target=target)
                                else:
                                    status['launches'] += 1
                                    publish('launch-accepted', target=target)
                    next_poll = time.monotonic() + (0.35 if policy.wake_until > time.monotonic() else 5)
                try:
                    event = client.receive(timeout=min(.5, max(.05, next_poll-time.monotonic())))
                except SsapTimeout:
                    continue
                if event.get('type') == 'error': raise RuntimeError('Subscription rejected')
                payload = event.get('payload', {})
                if event.get('id') == power_id:
                    state = str(payload.get('state', ''))
                    if state and state != policy.power:
                        policy.power_changed(state, time.monotonic())
                        persist()
                        publish('power-event', power=state, wakeArmed=policy.wake_until > time.monotonic())
                    next_poll = 0
                elif event.get('id') == foreground_id:
                    # Useful to cancel wake immediately, never to authorize it.
                    policy.observe_foreground(str(payload.get('appId', '')), time.monotonic())
                    next_poll = 0
        except (PairingRequired, CertificateChanged) as error:
            latch.reject(connection_stamp)
            policy.pairing_started()
            persist()
            publish('pairing-required', connected=False, error=type(error).__name__)
            # Keep the process and its heartbeat alive; only a new credential
            # file after explicit web pairing can unlatch the next connection.
        except ConnectionRefresh:
            policy.pairing_started()
            persist()
            publish('connection-refresh', connected=False, wakeArmed=False)
        except Exception as error:
            policy.disconnected()
            if status.get('connected') is not False:
                publish('disconnected', connected=False, error=type(error).__name__)
            time.sleep(1)
        finally:
            if client is not None: client.close()


if __name__ == '__main__':
    main()
