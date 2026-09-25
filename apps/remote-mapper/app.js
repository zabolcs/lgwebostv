(function () {
  'use strict';

  var STORAGE_KEY = 'hu.szabi.remotemapper.controlOrigin.v1';
  var started = false;
  function launchParams() {
    try { return JSON.parse(window.PalmSystem && window.PalmSystem.launchParams || '{}'); }
    catch (ignore) { return {}; }
  }
  function normalizeOrigin(value) {
    var text = String(value || '').trim().replace(/\/$/, '');
    var match = /^(https?):\/\/(10\.[0-9]{1,3}(?:\.[0-9]{1,3}){2}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3})(?::([0-9]{1,5}))?$/.exec(text);
    if (!match || (match[3] && (Number(match[3]) < 1 || Number(match[3]) > 65535))) return '';
    return text;
  }
  function savedOrigin() {
    try { return normalizeOrigin(window.localStorage.getItem(STORAGE_KEY)); }
    catch (ignore) { return ''; }
  }
  function saveOrigin(value) {
    try { window.localStorage.setItem(STORAGE_KEY, value); } catch (ignore) {}
  }
  function start(origin) {
    if (started) return;
    started = true;
    window.RemoteMapper.init({ apiBase: origin, requireArm: true, confirmSave: true });
  }
  function connectionDialog(current, firstRun) {
    var overlay = document.getElementById('rm-connection-dialog');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'rm-connection-dialog';
      overlay.className = 'rm-connection-dialog';
      overlay.innerHTML = '<form class="rm-connection-card"><h2>Vezérlő kapcsolat</h2><p>Add meg annak a helyi NAS-szolgáltatásnak a címét, amely az lgtv-control felületet futtatja.</p><label class="rm-field">lgtv-control origin<input id="rm-control-origin" type="url" inputmode="url" autocomplete="off" placeholder="http://192.168.1.20:8765" required></label><div id="rm-connection-error" class="rm-status rm-error"></div><div class="rm-actions"><button class="rm-action" type="submit">Mentés</button><button id="rm-connection-cancel" class="rm-action rm-secondary" type="button">Mégse</button></div></form>';
      document.body.appendChild(overlay);
      overlay.querySelector('form').addEventListener('submit', function (event) {
        event.preventDefault();
        var origin = normalizeOrigin(document.getElementById('rm-control-origin').value);
        if (!origin) { document.getElementById('rm-connection-error').textContent = 'Teljes, privát IPv4-es HTTP/HTTPS címet adj meg.'; return; }
        saveOrigin(origin);
        if (!started) { overlay.hidden = true; start(origin); }
        else window.location.reload();
      });
      document.getElementById('rm-connection-cancel').addEventListener('click', function () {
        if (!firstRun) overlay.hidden = true;
      });
    }
    document.getElementById('rm-control-origin').value = current || '';
    document.getElementById('rm-connection-cancel').hidden = !!firstRun;
    document.getElementById('rm-connection-error').textContent = '';
    overlay.hidden = false;
    document.getElementById('rm-control-origin').focus();
  }
  function closeApp() {
    try { window.close(); } catch (ignore) {}
  }
  document.getElementById('rm-exit').addEventListener('click', closeApp);
  document.addEventListener('keydown', function (event) {
    if (event.keyCode === 461 || event.keyCode === 27) {
      event.preventDefault();
      closeApp();
    }
  });
  var connectionButton = document.createElement('button');
  connectionButton.className = 'rm-action rm-secondary';
  connectionButton.type = 'button';
  connectionButton.textContent = 'Kapcsolat';
  connectionButton.addEventListener('click', function () { connectionDialog(savedOrigin(), false); });
  document.querySelector('.rm-header-actions').insertBefore(connectionButton, document.getElementById('rm-exit'));
  var params = launchParams();
  var origin = normalizeOrigin(params.controlOrigin) || savedOrigin();
  if (normalizeOrigin(params.controlOrigin)) saveOrigin(origin);
  if (origin) start(origin); else connectionDialog('', true);
}());
