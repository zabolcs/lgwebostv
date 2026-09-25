(function (global) {
  'use strict';

  var state = null;
  var selectedCode = null;
  var apiBase = '';
  var requireArm = false;
  var confirmSave = false;
  var editingEnabled = true;
  var messageTimer = null;
  var mapperAppId = 'hu.szabi.remotemapper';
  var managedActions = ['launcherHome', 'overlayPreset', 'cameraOpen', 'appCommand', 'webhook'];
  var zones = ['top', 'numbers', 'rockers', 'navigation', 'middle', 'colors', 'apps', 'assistants'];

  function el(id) { return document.getElementById(id); }
  function byCode(code) {
    if (!state) return null;
    return state.buttons.filter(function (button) { return Number(button.keyCode) === Number(code); })[0] || null;
  }
  function isCritical(button) { return !!button && Number(button.keyCode) === 773; }
  function isLocked(button) { return !!button && (button.locked === true || button.locked === 1 || button.locked === 'true'); }
  function option(select, value, text) {
    var item = document.createElement('option');
    item.value = String(value);
    item.textContent = text;
    select.appendChild(item);
  }
  function ensureActionOption(value, text) {
    var select = el('rm-action');
    if (select.querySelector('option[value="' + value + '"]')) return;
    var item = document.createElement('option');
    item.value = value;
    item.textContent = text;
    var preserve = select.querySelector('option[value="preserve"]');
    select.insertBefore(item, preserve || null);
  }
  function ensureExtendedFields() {
    ensureActionOption('launcherHome', 'Rövid Home: gyorsindító · hosszú Home: teljes launcher');
    ensureActionOption('overlayPreset', 'PiP preset megnyitása');
    ensureActionOption('cameraOpen', 'Adott kamera megnyitása');
    ensureActionOption('appCommand', 'Egyéni app-parancs (paraméterezett indítás)');
    ensureActionOption('webhook', 'Home Assistant webhook meghívása');
    var grid = el('rm-action').closest('.rm-form-grid');
    if (!el('rm-home-warning')) {
      var homeWarning = document.createElement('div');
      homeWarning.id = 'rm-home-warning';
      homeWarning.className = 'rm-home-warning';
      homeWarning.hidden = true;
      homeWarning.textContent = 'Figyelem: a Home gomb felüldefiniálása elrejtheti a gyári kezdőképernyő gyors elérését. Bármikor visszaállíthatod a „Gyári működés vissza” gombbal.';
      el('rm-form').parentNode.insertBefore(homeWarning, el('rm-form'));
    }
    function addSelectField(id, labelText) {
      if (el(id)) return;
      var label = document.createElement('label');
      label.id = id + '-field';
      label.className = 'rm-field rm-wide';
      label.hidden = true;
      label.appendChild(document.createTextNode(labelText));
      var select = document.createElement('select');
      select.id = id;
      label.appendChild(select);
      grid.insertBefore(label, grid.querySelector('.rm-quick'));
    }
    addSelectField('rm-preset', 'PiP preset');
    addSelectField('rm-camera', 'Kamera');
    if (!el('rm-params')) {
      var paramsLabel = document.createElement('label');
      paramsLabel.id = 'rm-params-field';
      paramsLabel.className = 'rm-field rm-wide';
      paramsLabel.hidden = true;
      paramsLabel.appendChild(document.createTextNode('Indítási paraméterek (JSON)'));
      var params = document.createElement('textarea');
      params.id = 'rm-params';
      params.rows = 7;
      params.spellcheck = false;
      params.value = '{}';
      paramsLabel.appendChild(params);
      var hint = document.createElement('small');
      hint.className = 'rm-field-hint';
      hint.textContent = 'A TV-re telepített app kapja meg a JSON objektumot. Nyers shell-parancs nem futtatható.';
      paramsLabel.appendChild(hint);
      grid.insertBefore(paramsLabel, grid.querySelector('.rm-quick'));
    }
    if (!el('rm-webhook')) {
      var webhookLabel = document.createElement('label');
      webhookLabel.id = 'rm-webhook-field';
      webhookLabel.className = 'rm-field rm-wide';
      webhookLabel.hidden = true;
      webhookLabel.appendChild(document.createTextNode('Home Assistant webhook URL'));
      var webhook = document.createElement('input');
      webhook.id = 'rm-webhook';
      webhook.type = 'url';
      webhook.inputMode = 'url';
      webhook.autocomplete = 'off';
      webhook.spellcheck = false;
      webhook.placeholder = 'http://192.168.1.10:8123/api/webhook/azonosito';
      webhookLabel.appendChild(webhook);
      var webhookHint = document.createElement('small');
      webhookHint.className = 'rm-field-hint';
      webhookHint.textContent = 'A gomb lenyomásakor a TV üres POST kérést küld a helyi Home Assistant webhooknak. A teljes URL szükséges.';
      webhookLabel.appendChild(webhookHint);
      grid.insertBefore(webhookLabel, grid.querySelector('.rm-quick'));
    }
  }
  function showMessage(text, error) {
    var target = el('rm-status');
    if (!target) return;
    target.textContent = text || '';
    target.classList.toggle('rm-error', !!error);
    if (messageTimer) global.clearTimeout(messageTimer);
    if (text) messageTimer = global.setTimeout(function () { target.textContent = ''; }, 5000);
  }
  function request(path, method, body) {
    var crossOrigin = apiBase !== '';
    var options = { method: method || 'GET', cache: 'no-store' };
    if (body !== undefined) {
      options.headers = { 'Content-Type': crossOrigin ? 'text/plain' : 'application/json' };
      options.body = JSON.stringify(body);
    }
    return global.fetch(apiBase + path, options).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok || !data.ok) throw new Error(data.error || 'A kérés sikertelen.');
        return data;
      });
    });
  }
  function currentBinding() {
    return state && selectedCode !== null ? state.bindings[String(selectedCode)] : null;
  }
  function describeBinding(binding) {
    if (!binding) return { title: 'Eredeti működés', detail: 'A gomb a gyári funkcióját végzi.' };
    if (binding.action === 'launch') return { title: 'Alkalmazás indítása', detail: String(binding.id || 'Ismeretlen alkalmazás') };
    if (binding.action === 'ignore') return { title: 'Letiltva', detail: 'A Remote Broker nem továbbítja ezt a gombnyomást.' };
    if (binding.action === 'replace') {
      var target = byCode(binding.keycode);
      return { title: 'Másik gombként működik', detail: target ? target.name + ' · ' + target.keyCode : 'Keycode ' + binding.keycode };
    }
    if (binding.action === 'exec' && binding.managedBy === mapperAppId) {
      if (binding.bindingType === 'launcherHome') return { title: 'Launcher Home-kezelés', detail: 'Rövid: gyorsindító · hosszú: teljes launcher' };
      if (binding.bindingType === 'overlayPreset') return { title: 'PiP preset megnyitása', detail: String(binding.presetId || '') };
      if (binding.bindingType === 'cameraOpen') return { title: 'Kamera teljes nézetben', detail: String(binding.cameraId || '') };
      if (binding.bindingType === 'appCommand') return { title: 'Egyéni app-parancs', detail: String(binding.appId || '') };
      if (binding.bindingType === 'webhook') {
        var webhookUrl = String(binding.webhookUrl || '');
        return { title: 'Home Assistant webhook', detail: webhookUrl.replace(/(\/api\/webhook\/).+$/, '$1••••••') };
      }
    }
    return { title: 'Örökölt egyedi kötés', detail: 'A meglévő, nem strukturált kötést a felület változatlanul megőrzi.' };
  }
  function fillApps(binding) {
    var select = el('rm-app');
    var current = binding && binding.action === 'launch' ? String(binding.id || '') :
      (binding && binding.bindingType === 'appCommand' ? String(binding.appId || '') : '');
    select.textContent = '';
    option(select, '', 'Válassz telepített alkalmazást…');
    var found = false;
    state.apps.forEach(function (app) {
      option(select, app.id, app.title + ' · ' + app.id);
      if (app.id === current) found = true;
    });
    if (current && !found) option(select, current, 'Jelenlegi (nem listázott) · ' + current);
    select.value = current;
  }
  function fillTargets(binding) {
    var select = el('rm-target');
    var current = binding && binding.action === 'replace' ? Number(binding.keycode) : 0;
    select.textContent = '';
    state.buttons.forEach(function (button) {
      if (Number(button.keyCode) !== 116) option(select, button.keyCode, button.name + ' · ' + button.keyCode);
    });
    select.value = current ? String(current) : '398';
  }
  function fillShortcuts(binding) {
    var shortcuts = state.shortcuts || { presets: [], cameras: [] };
    var preset = el('rm-preset');
    var currentPreset = binding && binding.bindingType === 'overlayPreset' ? String(binding.presetId || '') : '';
    preset.textContent = '';
    option(preset, '', 'Válassz PiP presetet…');
    shortcuts.presets.forEach(function (item) { option(preset, item.id, item.id + (item.kind ? ' · ' + item.kind : '')); });
    preset.value = currentPreset;
    var camera = el('rm-camera');
    var currentCamera = binding && binding.bindingType === 'cameraOpen' ? String(binding.cameraId || '') : '';
    camera.textContent = '';
    option(camera, '', 'Válassz kamerát…');
    shortcuts.cameras.forEach(function (item) { option(camera, item.cameraId, item.name + ' · ' + item.cameraId); });
    camera.value = currentCamera;
  }
  function updateActionFields() {
    var action = el('rm-action').value;
    el('rm-app-field').hidden = action !== 'launch' && action !== 'appCommand';
    el('rm-target-field').hidden = action !== 'replace';
    el('rm-preset-field').hidden = action !== 'overlayPreset';
    el('rm-camera-field').hidden = action !== 'cameraOpen';
    el('rm-params-field').hidden = action !== 'appCommand';
    el('rm-webhook-field').hidden = action !== 'webhook';
    el('rm-save').disabled = !editingEnabled || action === 'preserve';
    el('rm-original').disabled = !editingEnabled;
    el('rm-action').disabled = !editingEnabled;
    el('rm-app').disabled = !editingEnabled;
    el('rm-target').disabled = !editingEnabled;
    el('rm-preset').disabled = !editingEnabled;
    el('rm-camera').disabled = !editingEnabled;
    el('rm-params').disabled = !editingEnabled;
    el('rm-webhook').disabled = !editingEnabled;
    el('rm-quick-overlay').disabled = !editingEnabled;
    el('rm-quick-camera').disabled = !editingEnabled;
    el('rm-restore-previous').disabled = !editingEnabled;
    el('rm-restore-original').disabled = !editingEnabled;
  }
  function setEditingEnabled(enabled) {
    editingEnabled = !!enabled;
    var arm = el('rm-arm');
    if (arm) {
      arm.disabled = editingEnabled;
      arm.textContent = editingEnabled ? 'Szerkesztés feloldva' : 'Szerkesztés feloldása';
    }
    if (state && selectedCode !== null) renderEditor();
  }
  function renderEditor() {
    var button = byCode(selectedCode);
    if (!button) return;
    var binding = currentBinding();
    var description = describeBinding(binding);
    el('rm-selected-name').textContent = button.name;
    var locked = isLocked(button);
    el('rm-selected-meta').textContent = locked ? 'Védett rendszerfunkció' : (isCritical(button) ? 'Kiemelt gomb · szabadon beállítható' : 'Szabadon beállítható gomb');
    el('rm-keycode').textContent = 'KEY ' + button.keyCode;
    el('rm-current-title').textContent = description.title;
    el('rm-current-detail').textContent = description.detail;
    el('rm-protected').hidden = !locked;
    var homeWarning = el('rm-home-warning');
    if (homeWarning) homeWarning.hidden = !isCritical(button);
    el('rm-form').hidden = locked;
    if (locked) return;

    var action = binding ? String(binding.action || '') : 'original';
    if (binding && binding.action === 'exec' && binding.managedBy === mapperAppId && managedActions.indexOf(binding.bindingType) !== -1) {
      action = binding.bindingType;
    }
    if (['launch', 'ignore', 'replace'].concat(managedActions).indexOf(action) < 0) action = binding ? 'preserve' : 'original';
    var launcherHomeOption = el('rm-action').querySelector('option[value="launcherHome"]');
    if (launcherHomeOption) launcherHomeOption.disabled = !isCritical(button);
    el('rm-action').value = action;
    fillApps(binding);
    fillTargets(binding);
    fillShortcuts(binding);
    el('rm-params').value = binding && binding.bindingType === 'appCommand'
      ? JSON.stringify(binding.params || {}, null, 2) : '{}';
    el('rm-webhook').value = binding && binding.bindingType === 'webhook' ? String(binding.webhookUrl || '') : '';
    updateActionFields();
  }
  function selectButton(code, focusEditor) {
    selectedCode = Number(code);
    Array.prototype.forEach.call(document.querySelectorAll('.rm-key'), function (key) {
      key.classList.toggle('rm-selected', Number(key.getAttribute('data-keycode')) === selectedCode);
      key.setAttribute('aria-pressed', Number(key.getAttribute('data-keycode')) === selectedCode ? 'true' : 'false');
    });
    renderEditor();
    if (focusEditor && global.innerWidth < 881) el('rm-selected-name').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  function renderRemote() {
    var remote = el('rm-remote');
    remote.textContent = '';
    var brand = document.createElement('div');
    brand.className = 'rm-brand';
    brand.textContent = 'LG · MAGIC REMOTE';
    remote.appendChild(brand);
    zones.forEach(function (zoneName) {
      var zone = document.createElement('div');
      zone.className = 'rm-zone rm-zone-' + zoneName;
      zone.setAttribute('data-zone', zoneName);
      state.buttons.filter(function (button) { return button.zone === zoneName; }).forEach(function (button) {
        var key = document.createElement('button');
        key.type = 'button';
        var locked = isLocked(button);
        key.className = 'rm-key' + (locked ? ' rm-locked' : '') + (isCritical(button) ? ' rm-critical' : '') + (state.bindings[String(button.keyCode)] ? ' rm-bound' : '');
        key.textContent = button.short || '●';
        key.title = button.name + ' · keycode ' + button.keyCode + (locked ? ' · védett' : '') + (isCritical(button) ? ' · kiemelt, felüldefiniálható' : '');
        key.setAttribute('data-keycode', button.keyCode);
        key.setAttribute('aria-label', key.title);
        key.setAttribute('aria-pressed', 'false');
        if (button.color) key.setAttribute('data-color', button.color);
        key.addEventListener('click', function () { selectButton(button.keyCode, true); });
        zone.appendChild(key);
      });
      remote.appendChild(zone);
    });
    if (selectedCode === null || !byCode(selectedCode)) {
      var boundEditable = state.buttons.filter(function (button) {
        return !isLocked(button) && state.bindings[String(button.keyCode)];
      })[0];
      var firstEditable = state.buttons.filter(function (button) { return !isLocked(button); })[0];
      selectedCode = Number((boundEditable || firstEditable || state.buttons[0]).keyCode);
    }
    selectButton(selectedCode, false);
  }
  function acceptState(data) {
    state = data;
    var badge = el('rm-hook-state');
    var runtime = data.runtime || {};
    badge.classList.remove('rm-hook-warning', 'rm-hook-danger');
    if (runtime.nativeHookLoaded === true) {
      badge.textContent = 'VESZÉLY · natív Input Hook betöltve';
      badge.classList.add('rm-hook-danger');
    } else if (runtime.active && runtime.mode === 'grab') {
      badge.textContent = '● Remote Broker aktív · fail-open';
    } else if (runtime.available) {
      badge.textContent = 'Remote Broker telepítve · nem aktív';
      badge.classList.add('rm-hook-warning');
    } else if (runtime.nativeHookLoaded === false) {
      badge.textContent = 'Remote Broker nincs telepítve · natív hook kikapcsolva';
      badge.classList.add('rm-hook-warning');
    } else {
      badge.textContent = 'A távirányító runtime állapota nem ellenőrizhető';
      badge.classList.add('rm-hook-danger');
    }
    renderRemote();
  }
  function refresh() {
    showMessage('Távirányító és kötések betöltése…');
    return request('/api/remote-mapper/state', 'GET').then(function (data) {
      acceptState(data);
      showMessage('A TV aktuális gombkötései betöltve.');
    }, function (error) {
      el('rm-hook-state').textContent = 'Távirányító runtime nem érhető el';
      el('rm-hook-state').classList.add('rm-hook-danger');
      showMessage(error.message, true);
    });
  }
  function saveBody(forceAction) {
    var action = forceAction || el('rm-action').value;
    var body = { keyCode: selectedCode, action: action };
    if (action === 'launch') body.appId = el('rm-app').value;
    if (action === 'replace') body.targetKeyCode = Number(el('rm-target').value);
    if (action === 'overlayPreset') body.presetId = el('rm-preset').value;
    if (action === 'cameraOpen') body.cameraId = el('rm-camera').value;
    if (action === 'appCommand') {
      body.appId = el('rm-app').value;
      body.params = JSON.parse(el('rm-params').value || '{}');
    }
    if (action === 'webhook') body.webhookUrl = el('rm-webhook').value.trim();
    return body;
  }
  function save(forceAction) {
    if (!editingEnabled) {
      showMessage('Előbb oldd fel a szerkesztést.', true);
      return;
    }
    var body;
    try { body = saveBody(forceAction); }
    catch (error) { showMessage('Az indítási paraméter nem szabályos JSON.', true); return; }
    if (body.action === 'launch' && !body.appId) {
      showMessage('Válassz alkalmazást.', true);
      return;
    }
    if (body.action === 'overlayPreset' && !body.presetId) { showMessage('Válassz PiP presetet.', true); return; }
    if (body.action === 'cameraOpen' && !body.cameraId) { showMessage('Válassz kamerát.', true); return; }
    if (body.action === 'appCommand' && (!body.appId || !body.params || typeof body.params !== 'object' || Array.isArray(body.params))) {
      showMessage('Válassz alkalmazást, és adj meg JSON objektumot.', true);
      return;
    }
    if (body.action === 'webhook' && !/^https?:\/\/[^/]+\/api\/webhook\/[A-Za-z0-9._~-]+$/.test(body.webhookUrl)) {
      showMessage('Add meg a teljes helyi Home Assistant webhook URL-t.', true);
      return;
    }
    var button = byCode(selectedCode);
    var confirmText = isCritical(button)
      ? 'Figyelem: a Home gomb gyári kezdőképernyő-funkcióját módosítod. Biztosan mented ezt a kötést?'
      : 'Biztosan módosítod ezt a gombot: ' + (button ? button.name : selectedCode) + '?';
    if (confirmSave && !global.confirm(confirmText)) return;
    showMessage('Gombkötés mentése…');
    request('/api/remote-mapper/bind', 'POST', body).then(function (data) {
      acceptState(data);
      if (requireArm) setEditingEnabled(false);
      if (data.runtimeSyncError) showMessage('A kötés elmentve, de a futó broker frissítése sikertelen: ' + data.runtimeSyncError, true);
      else showMessage(data.changed ? 'A gomb új működése elmentve.' : 'A gomb már így volt beállítva.');
    }, function (error) { showMessage(error.message, true); });
  }
  function restore(source) {
    if (!editingEnabled) {
      showMessage('Előbb oldd fel a szerkesztést.', true);
      return;
    }
    var label = source === 'previous' ? 'előző mentést' : 'első Remote Mapper előtti állapotot';
    if (!global.confirm('Biztosan visszaállítod az ' + label + '?')) return;
    showMessage('Biztonsági mentés visszaállítása…');
    request('/api/remote-mapper/restore', 'POST', { source: source }).then(function (data) {
      acceptState(data);
      if (requireArm) setEditingEnabled(false);
      if (data.runtimeSyncError) showMessage('A mentés visszaállt, de a futó broker frissítése sikertelen: ' + data.runtimeSyncError, true);
      else showMessage(data.changed ? 'A biztonsági mentés visszaállítva.' : 'Már ez az állapot volt aktív.');
    }, function (error) { showMessage(error.message, true); });
  }
  function quickLaunch(appId) {
    var exists = state.apps.some(function (app) { return app.id === appId; });
    if (!exists) {
      showMessage('Ez az alkalmazás nincs a TV telepített alkalmazásai között.', true);
      return;
    }
    el('rm-action').value = 'launch';
    fillApps({ action: 'launch', id: appId });
    updateActionFields();
  }
  function bindEvents() {
    el('rm-refresh').addEventListener('click', refresh);
    el('rm-action').addEventListener('change', updateActionFields);
    el('rm-save').addEventListener('click', function () { save(); });
    el('rm-original').addEventListener('click', function () { save('original'); });
    el('rm-restore-previous').addEventListener('click', function () { restore('previous'); });
    el('rm-restore-original').addEventListener('click', function () { restore('original'); });
    el('rm-quick-overlay').addEventListener('click', function () { quickLaunch('hu.szabi.mediaoverlay'); });
    el('rm-quick-camera').addEventListener('click', function () { quickLaunch('hu.szabi.cameraviewer'); });
    if (el('rm-arm')) el('rm-arm').addEventListener('click', function () {
      if (!global.confirm('Feloldod a gombkötések szerkesztését ehhez az egy mentéshez?')) return;
      setEditingEnabled(true);
      showMessage('Szerkesztés feloldva egy mentéshez.');
    });
  }
  function init(options) {
    options = options || {};
    apiBase = String(options.apiBase || '').replace(/\/$/, '');
    requireArm = options.requireArm === true;
    confirmSave = options.confirmSave === true;
    editingEnabled = !requireArm;
    ensureExtendedFields();
    bindEvents();
    setEditingEnabled(editingEnabled);
    refresh();
  }

  global.RemoteMapper = { init: init };
}(window));
