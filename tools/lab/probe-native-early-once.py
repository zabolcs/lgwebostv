#!/usr/bin/env python3
"""One attended reboot diagnostic: read-only except at most one app launch.

The caller owns reboot, guard inhibition, and restoration. This process never
changes services, TV files, credentials, or pairing; an existing pinned key is
mandatory. Output deliberately excludes protocol payloads and exception text.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import sys
import threading
import time

sys.path.insert(0, '/opt/lgtv-control')
import lg_ssap
from launcher_early import ACTIVE, FULL, HOME, OWN, TRANSIENT, configuration, eligible_input


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path('/etc/lgtv-control/config.json'))
    parser.add_argument('--credentials', type=Path, default=Path('/var/lib/lgtv-control/lg-ssap.json'))
    parser.add_argument('--duration', type=float, default=100)
    args = parser.parse_args()
    if not 5 <= args.duration <= 100:
        parser.error('duration must be between 5 and 100 seconds')

    started = time.monotonic()
    deadline = started + args.duration
    output_lock = threading.RLock()
    state_lock = threading.Lock()
    stop = threading.Event()
    down_seen = threading.Event()
    ports = {}
    down_at = None
    baseline_ready = False
    launch_sent = False
    launch_blocked = False
    attempts = 0
    client = None

    def emit(event: str, **fields) -> None:
        now = time.monotonic()
        with output_lock:
            print(json.dumps({'event': event, 't': round(now-started, 3),
                              'epoch': round(time.time(), 3),
                              'bootT': None if down_at is None else round(now-down_at, 3),
                              **fields}, separators=(',', ':')), flush=True)

    def remaining(limit: float = 5) -> float:
        value = min(limit, deadline-time.monotonic())
        if value <= 0:
            raise lg_ssap.SsapTimeout('Diagnostic deadline reached')
        return value

    host, origin, settings = configuration(args.config)
    emit('start', duration=args.duration, target=FULL)

    def monitor(port: int) -> None:
        nonlocal down_at
        previous = None
        while not stop.is_set() and time.monotonic() < deadline:
            tick = time.monotonic()
            try:
                with socket.create_connection((host, port), timeout=.15):
                    opened = True
            except OSError:
                opened = False
            with state_lock:
                ports[port] = opened
                if port == 3001 and previous is True and not opened and baseline_ready and down_at is None:
                    down_at = time.monotonic()
                    down_seen.set()
                    emit('boot-disconnect')
            if opened != previous:
                emit('port', port=port, opened=opened)
                previous = opened
            stop.wait(max(0, .25-(time.monotonic()-tick)))

    original_open = lg_ssap._open_websocket

    def traced_open(hostname, timeout):
        began = time.monotonic()
        emit('tls-open-start')
        try:
            connection = original_open(hostname, min(timeout, remaining()))
        except Exception as error:
            emit('tls-open-failed', elapsed=round(time.monotonic()-began, 3), error=type(error).__name__)
            raise
        emit('tls-open-done', elapsed=round(time.monotonic()-began, 3))
        return connection

    class TraceClient(lg_ssap.SsapClient):
        def _send(self, message, phase_deadline):
            # Only locally generated message types and correlation IDs.
            if not str(message.get('id','')).isdigit():
                emit('send', kind=message.get('type'), id=message.get('id'))
            return super()._send(message, min(phase_deadline, deadline))

        def _await(self, identifier, phase_deadline, expected=None):
            began = time.monotonic()
            try:
                result = super()._await(identifier, min(phase_deadline, deadline), expected)
            except Exception as error:
                emit('await-failed', id=identifier, elapsed=round(time.monotonic()-began, 3), error=type(error).__name__)
                raise
            if not str(identifier).isdigit():
                emit('await-done', id=identifier, elapsed=round(time.monotonic()-began, 3), kind=result.get('type'))
            return result

    lg_ssap._open_websocket = traced_open
    workers = [threading.Thread(target=monitor, args=(port,), daemon=True) for port in (3000, 3001, 22)]
    for worker in workers:
        worker.start()

    last_snapshot = None
    def snapshot(current):
        nonlocal last_snapshot
        power = current.request(lg_ssap.POWER_URI, timeout=remaining(2))
        foreground = current.request(lg_ssap.FOREGROUND_URI, timeout=remaining(2))
        # App IDs and native state are the only TV fields logged.
        state = str(power.get('state', ''))[:80]
        app = str(foreground.get('appId', ''))[:160]
        if (state, app) != last_snapshot:
            emit('state', state=state, appId=app)
            last_snapshot = (state, app)
        stable = state == ACTIVE and power.get('processing', '') == '' and power.get('onOff') != 'off'
        return stable, app

    def connect():
        nonlocal attempts
        attempts += 1
        current = TraceClient(host, args.credentials, timeout=remaining(5))
        emit('connect-start', attempt=attempts)
        try:
            current.connect(pair=False)
        except Exception:
            current.close()
            raise
        emit('registered', attempt=attempts)
        return current

    def safe_foreground(app: str) -> bool:
        nonlocal launch_blocked
        if app == HOME or eligible_input(app):
            return True
        if not app or app.startswith(TRANSIENT + ('com.webos.app.boot', 'com.webos.app.splash')):
            return False
        if not launch_blocked:
            emit('launch-preserved', reason='own-app-present' if app in OWN else 'real-app-present', appId=app)
        launch_blocked = True
        return False

    try:
        client = connect()
        stable, app = snapshot(client)
        if not stable:
            emit('abort', reason='baseline-not-active')
            return 2
        # A successful TLS connection alone is not enough: require the monitor
        # to have recorded open before it may recognize a falling edge.
        while time.monotonic() < deadline and ports.get(3001) is not True:
            stop.wait(.05)
        if ports.get(3001) is not True:
            emit('abort', reason='baseline-port-not-open')
            return 2
        with state_lock:
            baseline_ready = True
        emit('ready', appId=app)
        client.close()
        client = None
        while not down_seen.is_set() and time.monotonic() < deadline:
            down_seen.wait(min(.25, max(0, deadline-time.monotonic())))
        if not down_seen.is_set():
            emit('abort', reason='no-observed-disconnect')
            return 2

        while time.monotonic() < deadline:
            try:
                if client is None:
                    if ports.get(3001) is not True:
                        stop.wait(.1)
                        continue
                    client = connect()
                stable, app = snapshot(client)
                eligible = safe_foreground(app) if not launch_sent else False
                if stable and eligible and not launch_sent and not launch_blocked:
                    current_host, origin, settings = configuration(args.config)
                    if current_host != host:
                        emit('abort', reason='configured-host-changed')
                        return 2
                    # A second fresh read closes the gap between readiness and
                    # dispatch. A real app is permanently preserved this run.
                    stable, app = snapshot(client)
                    eligible = safe_foreground(app)
                    if stable and eligible and not launch_blocked:
                        launch_sent = True  # before any write; never retry
                        emit('launch-dispatch', target=FULL)
                        try:
                            client.request(lg_ssap.LAUNCH_URI, {
                                'id': FULL, 'noSplash': True, 'params': {
                                    'source': 'native-probe', 'launcherHost': 'full',
                                    'controlOrigin': origin,
                                    'displayPreferences': {key: settings[key] for key in ('animationsEnabled', 'visualEffectsEnabled')
                                                           if isinstance(settings.get(key), bool)}
                                }}, timeout=remaining(5))
                            emit('launch-accepted', target=FULL)
                        except lg_ssap.PairingRequired:
                            raise
                        except Exception as error:
                            emit('launch-outcome-unknown-no-retry', error=type(error).__name__)
                            client.close()
                            client = None
                stop.wait(min(.5, max(0, deadline-time.monotonic())))
            except lg_ssap.PairingRequired as error:
                emit('abort', reason='pairing-required', error=type(error).__name__)
                return 3
            except Exception as error:
                emit('connection-error', error=type(error).__name__)
                if client is not None:
                    client.close()
                    client = None
                stop.wait(min(.25, max(0, deadline-time.monotonic())))
        return 0
    except lg_ssap.PairingRequired as error:
        emit('abort', reason='pairing-required', error=type(error).__name__)
        return 3
    except Exception as error:
        emit('abort', reason='baseline-error', error=type(error).__name__)
        return 2
    finally:
        stop.set()
        if client is not None:
            client.close()
        for worker in workers:
            worker.join(timeout=.3)
        lg_ssap._open_websocket = original_open
        emit('finished', launchSent=launch_sent, launchBlocked=launch_blocked, attempts=attempts)


if __name__ == '__main__':
    raise SystemExit(main())
