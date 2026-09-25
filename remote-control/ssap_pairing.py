"""Explicit, bounded, repeatable SSAP pairing; never exposes client credentials."""
import json
import os
from pathlib import Path
import secrets
import threading
import time

from lg_ssap import SsapClient, POWER_URI, FOREGROUND_URI
from launcher_early import atomic_json

PENDING = {'connecting', 'waiting', 'approving'}


class PairingManager:
    def __init__(self, host, credentials, approve, dialog_visible, client_factory=SsapClient):
        self.host = host
        self.credentials = Path(credentials)
        self.marker = self.credentials.with_name('launcher-pairing-active.json')
        self.early_status = self.credentials.with_name('launcher-early-status.json')
        self.approve_button = approve
        self.dialog_visible = dialog_visible
        self.client_factory = client_factory
        self.lock = threading.RLock()
        self.client = None
        self.worker = None
        self.state = {'id':'', 'state':'idle', 'deadline':0, 'error':''}

    def snapshot(self):
        with self.lock:
            value = dict(self.state, paired=self.credentials.is_file(),
                         canApprove=self.state['state'] == 'waiting' and time.time() < self.state['deadline'])
        try:
            early = json.loads(self.early_status.read_text(encoding='utf-8'))
            early = {key:early[key] for key in ('event','updatedAt','connected','power','observeOnly','launches','reason') if key in early}
        except (OSError, ValueError, TypeError):
            early = {'event':'not-started'}
        return {'pairing':value, 'earlyLauncher':early}

    def _matching(self, identifier):
        return isinstance(identifier, str) and secrets.compare_digest(identifier, self.state['id'])

    def start(self):
        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise ValueError('Egy párosítás már folyamatban van.')
            identifier = secrets.token_hex(16)
            self.state = {'id':identifier, 'state':'connecting', 'deadline':time.time()+90, 'error':''}
            # The accelerator pauses during pairing; this also expires after a
            # NAS crash instead of leaving a permanent stop marker behind.
            try:
                atomic_json(self.marker, {'id':identifier, 'until':self.state['deadline']+5})
                self.worker = threading.Thread(target=self._pair, args=(identifier,), daemon=True, name='lg-tv-pairing')
                self.worker.start()
            except Exception:
                self.state.update(state='error', deadline=0, error='A párosítás nem indítható. A korábbi kulcs megmaradt.')
                try: self.marker.unlink(missing_ok=True)
                except OSError: pass
                raise RuntimeError(self.state['error']) from None
        return self.snapshot()

    def _pair(self, identifier):
        candidate = self.credentials.with_name('.lg-ssap-pair-'+identifier+'.json')
        client = None
        try:
            client = self.client_factory(self.host(), candidate, timeout=5)
            with self.lock:
                if not self._matching(identifier) or self.state['state'] not in PENDING: return
                self.client = client
            def prompt():
                with self.lock:
                    if not self._matching(identifier) or self.state['state'] not in PENDING:
                        raise RuntimeError('Pairing cancelled')
                    if self._matching(identifier) and self.state['state'] == 'connecting':
                        self.state['state'] = 'waiting'
            client.connect(pair=True, pair_timeout=85, on_prompt=prompt)
            # Do not replace a working key with a registration that cannot read
            # the state required by the accelerator.
            client.request(POWER_URI, timeout=5)
            client.request(FOREGROUND_URI, timeout=5)
            with self.lock:
                if self._matching(identifier) and self.state['state'] in PENDING and time.time() < self.state['deadline']:
                    os.replace(candidate, self.credentials)
                    self.state.update(state='paired', error='', deadline=0)
                elif self._matching(identifier) and self.state['state'] in PENDING:
                    self.state.update(state='expired', error='A párosítási kérés ideje lejárt. A korábbi kulcs megmaradt.', deadline=0)
        except Exception as error:
            with self.lock:
                if self._matching(identifier) and self.state['state'] in PENDING:
                    # Never expose firmware replies, certificates, client keys,
                    # arbitrary exception text or filesystem paths via HTTP.
                    self.state.update(state='error', deadline=0,
                        error='A párosítás nem sikerült ('+type(error).__name__+'). A korábbi kulcs megmaradt.')
        finally:
            if client is not None:
                try: client.close()
                except Exception: pass
            try: candidate.unlink(missing_ok=True)
            except OSError: pass
            with self.lock:
                if self._matching(identifier):
                    self.client = None
                    try: self.marker.unlink(missing_ok=True)
                    except OSError: pass  # expires automatically even if cleanup fails

    def approve(self, identifier):
        with self.lock:
            if not self._matching(identifier) or self.state['state'] != 'waiting' or time.time() >= self.state['deadline']:
                raise ValueError('Nincs jóváhagyásra váró, érvényes párosítás.')
            # User reviewed the screenshot. Still require a native dialog and
            # an outstanding matching SSAP prompt immediately before OK.
            if not self.dialog_visible():
                raise ValueError('A TV jóváhagyó ablaka már nem látható. Frissítsd a képet.')
            if self.state['state'] != 'waiting' or time.time() >= self.state['deadline']:
                raise ValueError('A párosítási kérés lejárt.')
            self.state['state'] = 'approving'
            try: self.approve_button()
            except Exception:
                self.state['state'] = 'waiting'
                raise RuntimeError('A TV gombnyomása nem sikerült; a képen ellenőrizhető és újrapróbálható.') from None
        return self.snapshot()

    def cancel(self, identifier):
        with self.lock:
            if not self._matching(identifier) or self.state['state'] not in PENDING:
                raise ValueError('Nincs ilyen folyamatban lévő párosítás.')
            self.state.update(state='cancelled', deadline=0, error='')
            client = self.client
        if client is not None: client.close()
        return self.snapshot()

    def command(self, value):
        if not isinstance(value, dict): raise ValueError('Érvénytelen párosítási kérés.')
        if value == {'action':'start'}: return self.start()
        if set(value) != {'action','id'}: raise ValueError('Érvénytelen párosítási kérés.')
        if value['action'] == 'approve': return self.approve(value['id'])
        if value['action'] == 'cancel': return self.cancel(value['id'])
        raise ValueError('Ismeretlen párosítási művelet.')
