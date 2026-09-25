(function () {
  'use strict';

  var connections = null;
  function el(id) { return document.getElementById(id); }
  function showPage(name) {
    Array.prototype.forEach.call(document.querySelectorAll('.page'), function (page) { page.hidden = page.id !== 'page-' + name; });
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (button) { button.classList.toggle('active', button.getAttribute('data-page') === name); });
  }
  function status(text, error) {
    el('connections-status').textContent = text || '';
    el('connections-status').classList.toggle('error', !!error);
  }
  function request(method, body) {
    var options = { method: method, cache: 'no-store' };
    if (body) { options.headers = { 'Content-Type': 'application/json' }; options.body = JSON.stringify(body); }
    return fetch('/api/connections', options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) throw new Error(data.error || 'A kérés sikertelen.');
        return data.connections;
      });
    });
  }
  function fill(value) {
    connections = value;
    el('connection-control-origin').value = value.controlOrigin;
    el('connection-tv-host').value = value.tvHost;
    el('connection-gateway-scheme').value = value.gatewayScheme;
    el('connection-gateway-host').value = value.gatewayHost;
    el('connection-media-port').value = value.mediaPort;
    el('connection-player-port').value = value.playerPort;
    el('connection-player-path').value = value.playerPath;
  }
  function applyCameraDefaults() {
    if (!connections) return;
    var selected = el('camera-list');
    if (selected && selected.value) return;
    el('camera-scheme').value = connections.gatewayScheme;
    el('camera-host').value = connections.gatewayHost;
    el('camera-port').value = connections.mediaPort;
    el('player-port').value = connections.playerPort;
    el('player-path').value = connections.playerPath;
  }
  function createUi() {
    var tab = document.createElement('button');
    tab.className = 'tab'; tab.type = 'button'; tab.setAttribute('data-page', 'connections'); tab.textContent = 'Kapcsolatok';
    document.querySelector('.tabs').appendChild(tab);
    tab.addEventListener('click', function () { showPage('connections'); });
    var page = document.createElement('section');
    page.id = 'page-connections'; page.className = 'page'; page.hidden = true;
    page.innerHTML = '<form id="connections-form" class="card"><h2>Kapcsolati beállítások</h2><p class="note">Ezekből a címekből dolgozik a NAS-szolgáltatás és ezeket adja át a TV-appoknak. A TV-cím módosításakor az SSH-kulcsnak az új TV-n is működnie kell.</p><div class="grid"><label class="wide">lgtv-control nyilvános origin<input id="connection-control-origin" type="url" placeholder="http://192.168.1.20:8765" required></label><label>TV privát IPv4-címe<input id="connection-tv-host" inputmode="decimal" maxlength="15" required></label><label>Kameraátjáró séma<select id="connection-gateway-scheme"><option value="http">HTTP</option><option value="https">HTTPS</option></select></label><label>Kameraátjáró host<input id="connection-gateway-host" inputmode="decimal" maxlength="15" required></label><label>Média port<input id="connection-media-port" type="number" min="1" max="65535" required></label><label>Player port<input id="connection-player-port" type="number" min="1" max="65535" required></label><label class="wide">Player útvonal<input id="connection-player-path" required></label></div><div class="actions"><button type="submit">Kapcsolatok mentése</button><button id="connections-refresh" class="secondary" type="button">Újratöltés</button></div><p id="connections-status" class="status"></p></form>';
    document.querySelector('main').appendChild(page);
    el('connections-form').addEventListener('submit', function (event) {
      event.preventDefault(); status('Mentés…');
      request('POST', {
        controlOrigin: el('connection-control-origin').value.trim(), tvHost: el('connection-tv-host').value.trim(),
        gatewayScheme: el('connection-gateway-scheme').value, gatewayHost: el('connection-gateway-host').value.trim(),
        mediaPort: Number(el('connection-media-port').value), playerPort: Number(el('connection-player-port').value),
        playerPath: el('connection-player-path').value.trim()
      }).then(function (data) { fill(data); status('A kapcsolati beállítások elmentve.'); }, function (error) { status(error.message, true); });
    });
    el('connections-refresh').addEventListener('click', load);
    el('new-camera').addEventListener('click', function () { window.setTimeout(applyCameraDefaults, 0); });
  }
  function load() {
    status('Kapcsolatok betöltése…');
    request('GET').then(function (data) { fill(data); applyCameraDefaults(); status(''); }, function (error) { status(error.message, true); });
  }
  createUi();
  load();
}());
