(function () {
  'use strict';

  var toggle = document.getElementById('tv-power-toggle');
  var refreshButton = document.getElementById('tv-power-refresh');
  var statusNode = document.getElementById('tv-power-status');
  var busy = false;

  function decode(response) {
    return response.json().catch(function () { return {}; }).then(function (body) {
      if (!response.ok || !body.ok) throw new Error(body.error || 'A TV energiaállapota nem érhető el.');
      return body;
    });
  }

  function render(power) {
    var state = power && power.state ? power.state : 'unknown';
    var isOn = state === 'on' || state === 'turning_on';
    toggle.setAttribute('aria-checked', isOn ? 'true' : 'false');
    toggle.disabled = busy || state === 'unknown';
    if (state === 'on') {
      toggle.textContent = 'Bekapcsolva — kikapcsolás';
      statusNode.textContent = 'A TV be van kapcsolva' + (power.nativeState ? ' (' + power.nativeState + ').' : '.');
    } else if (state === 'off') {
      toggle.textContent = 'Kikapcsolva — bekapcsolás Wi-Fin';
      statusNode.textContent = 'A TV ki van kapcsolva. A bekapcsolás a Wi-Fi adapterét ébreszti.';
    } else if (state === 'turning_on') {
      toggle.textContent = 'Bekapcsolás folyamatban…';
      statusNode.textContent = 'A Wi-Fi ébresztőcsomag elküldve; várakozás a TV-re.';
    } else if (state === 'turning_off') {
      toggle.textContent = 'Kikapcsolás folyamatban…';
      statusNode.textContent = 'A TV leállítása folyamatban van.';
    } else {
      toggle.textContent = 'Állapot ismeretlen';
      statusNode.textContent = power && power.error ? power.error : 'A TV állapota most nem állapítható meg.';
    }
    statusNode.classList.toggle('error', state === 'unknown');
  }

  function refresh() {
    return fetch('/api/tv/power', { method: 'GET', cache: 'no-store' })
      .then(decode)
      .then(function (body) { render(body.power); })
      .catch(function (error) {
        toggle.disabled = true;
        toggle.textContent = 'Kapcsolódási hiba';
        statusNode.textContent = error.message;
        statusNode.classList.add('error');
      });
  }

  function setPower(state) {
    busy = true;
    toggle.disabled = true;
    statusNode.classList.remove('error');
    statusNode.textContent = state === 'on' ? 'Wi-Fi ébresztés küldése…' : 'Kikapcsolási parancs küldése…';
    fetch('/api/tv/power', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: state })
    }).then(decode).then(function (body) {
      busy = false;
      render(body.power);
    }).catch(function (error) {
      busy = false;
      statusNode.textContent = error.message;
      statusNode.classList.add('error');
      refresh();
    });
  }

  toggle.addEventListener('click', function () {
    if (busy) return;
    setPower(toggle.getAttribute('aria-checked') === 'true' ? 'off' : 'on');
  });
  refreshButton.addEventListener('click', refresh);
  refresh();
  window.setInterval(refresh, 7000);
}());
