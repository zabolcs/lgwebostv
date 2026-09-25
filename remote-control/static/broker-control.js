(function () {
  'use strict';
  var toggle = document.getElementById('broker-toggle');
  var stop = document.getElementById('broker-stop');
  var status = document.getElementById('broker-status');
  var live = null, busy = false, reading = false, revision = 0;
  function api(method, enabled) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, 45000);
    var options = {method: method, cache: 'no-store', signal: controller.signal};
    if (method === 'POST') {
      options.headers = {'Content-Type': 'application/json'};
      options.body = JSON.stringify({enabled: enabled});
    }
    return fetch('/api/remote-mapper/runtime', options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) throw new Error(data.error || 'A kapcsolás sikertelen.');
        return data.runtime;
      });
    }).finally(function () { clearTimeout(timer); });
  }
  function render(value) {
    live = value;
    var on = !!(value.enabled || value.active);
    toggle.setAttribute('aria-checked', String(on));
    toggle.textContent = on ? 'BE — kikapcsolás' : 'KI — bekapcsolás';
    toggle.disabled = busy || !!value.error || (!on && !value.compatible);
    stop.disabled = busy;
    var waiting = value.enabled && ['standby', 'waiting-for-tv', 'waiting-for-input'].indexOf(value.lifecycle) !== -1;
    status.classList.toggle('error', !!value.error || (value.enabled && !value.active && !waiting) || !!value.disabledReason);
    status.textContent = value.error ? 'A TV állapota nem ellenőrizhető. A Vészleállítás továbbra is kérhető.' :
      value.active ? 'Aktív · mentett gombkiosztás · automatikus indulás bekapcsolva' :
      waiting ? 'Automatikus indulás engedélyezve · ' + (value.lifecycle === 'standby' ? 'a TV készenlétben van' : 'várakozás a TV és a távirányító készenlétére') :
      value.requestedEnabled && value.disabledReason ? 'Hiba miatt leállítva · a kívánt állapot továbbra is BE. A fenti gombbal újra engedélyezhető.' :
      value.enabled ? 'Engedélyezve, de a kezelő nem fut. Kapcsold ki, majd szükség esetén újra be.' :
      'Kikapcsolva · gyári gombkezelés · automatikus indulás kikapcsolva';
    if (!value.active && value.disabledReason) status.textContent += ' · ' + value.disabledReason;
  }
  function refresh() {
    if (busy || reading) return;
    reading = true;
    var current = revision;
    api('GET').then(function (value) { if (current === revision) render(value); })
      .catch(function () { if (current === revision) render({error: true}); })
      .finally(function () { reading = false; });
  }
  function change(enabled) {
    if (busy) return;
    busy = true; revision++;
    toggle.disabled = true; stop.disabled = true;
    status.classList.remove('error');
    status.textContent = enabled ? 'Bekapcsolás és a mentett kiosztás betöltése…' : 'Leállítás és az automatikus indulás kikapcsolása…';
    api('POST', enabled).then(function (value) {
      busy = false; render(value);
    }).catch(function (error) {
      busy = false; live = null;
      toggle.disabled = true; stop.disabled = false;
      status.classList.add('error');
      status.textContent = 'Nem igazolt állapot: ' + error.message + ' A Vészleállítás újra megpróbálható.';
    });
  }
  toggle.addEventListener('click', function () { if (live) change(!(live.enabled || live.active)); });
  stop.addEventListener('click', function () { change(false); });
  document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
  setInterval(function () { if (!document.hidden) refresh(); }, 15000);
  refresh();
}());
