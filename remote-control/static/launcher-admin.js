(function () {
  'use strict';
  var controller = null;
  var metadata = null;
  var working = null;
  var selectedItemId = '';
  var draggedItem = null;
  var previewResizeTimer = null;
  function el(id) { return document.getElementById(id); }
  function showPage(name) {
    Array.prototype.forEach.call(document.querySelectorAll('.page'), function (page) { page.hidden = page.id !== 'page-' + name; });
    Array.prototype.forEach.call(document.querySelectorAll('.tab'), function (button) { button.classList.toggle('active', button.getAttribute('data-page') === name); });
    if (name === 'launcher') window.setTimeout(fitPreviewForViewport, 0);
  }
  function setStatus(message, error) { el('launcher-admin-status').textContent = message || ''; el('launcher-admin-status').classList.toggle('error', !!error); }
  function move(list, index, delta) { var next = index + delta; if (next < 0 || next >= list.length) return; var value = list.splice(index, 1)[0]; list.splice(next, 0, value); }
  function option(select, value, label) { var item = document.createElement('option'); item.value = value; item.textContent = label; select.appendChild(item); }
  function preview() { controller.preview(working); window.setTimeout(fitPreviewForViewport, 0); }
  function makeButton(label, className, fn) { var button = document.createElement('button'); button.type = 'button'; button.textContent = label; if (className) button.className = className; button.addEventListener('click', fn); return button; }
  function isProtected(item) { return item.type === 'allApps' || item.type === 'settings' || String(item.id || '').indexOf('utility-com-webos-app-') === 0; }
  function findItem(itemId) {
    var found = null;
    working.rows.some(function (row) { var index = row.items.map(function (item) { return item.id; }).indexOf(itemId); if (index >= 0) { found = { row: row, index: index, item: row.items[index] }; return true; } return false; });
    return found;
  }
  function openItemEditor(itemId) {
    var found = findItem(itemId); if (!found) return;
    var item = found.item; el('launcher-admin-item-id').value = item.id; el('launcher-admin-item-name').textContent = item.label;
    el('launcher-admin-item-label').value = item.label; el('launcher-admin-item-fit').value = item.fit === 'small' || item.fit === 'cover' ? item.fit : 'contain';
    el('launcher-admin-item-icon-key').value = item.iconKey || ''; el('launcher-admin-item-icon-url').value = item.iconUrl || ''; el('launcher-admin-item-background').value = item.backgroundColor || ''; el('launcher-admin-item-visible').checked = item.visible;
    el('launcher-admin-item-overlay').hidden = false; el('launcher-admin-item-label').focus();
  }
  function closeItemEditor() { el('launcher-admin-item-overlay').hidden = true; }
  function saveItemEditor(event) {
    event.preventDefault(); var found = findItem(el('launcher-admin-item-id').value); if (!found) return;
    var item = found.item; item.label = el('launcher-admin-item-label').value.trim() || item.label; item.fit = el('launcher-admin-item-fit').value;
    item.iconKey = el('launcher-admin-item-icon-key').value; item.iconUrl = el('launcher-admin-item-icon-url').value.trim(); if (item.iconUrl) item.iconKey = '';
    item.backgroundColor = el('launcher-admin-item-background').value.trim(); item.visible = el('launcher-admin-item-visible').checked;
    closeItemEditor(); renderRowsEditor(); preview(); setStatus('A csempe módosítása bekerült az előnézetbe; a véglegesítéshez mentsd el.');
  }
  function changeItemVisibilityOrDelete(itemId) {
    var found = findItem(itemId); if (!found) return;
    if (isProtected(found.item)) found.item.visible = !found.item.visible;
    else found.row.items.splice(found.index, 1);
    selectedItemId = ''; renderRowsEditor(); preview();
    setStatus(isProtected(found.item) ? (found.item.visible ? 'A rendszer-csempe ismét látható.' : 'A rendszer-csempe elrejtve.') : 'A csempe törölve az előnézetből. Mentéssel véglegesíthető.');
  }
  function reorderItem(itemId, delta) {
    var found = findItem(itemId); if (!found) return; var next = found.index + delta;
    if (next < 0 || next >= found.row.items.length) return;
    move(found.row.items, found.index, delta); renderRowsEditor(); preview();
    window.setTimeout(function () { var card = document.querySelector('[data-admin-item-id="' + itemId + '"]'); if (card) card.focus(); }, 0);
  }
  function renderRowsEditor() {
    var host = el('launcher-row-editor'); host.textContent = '';
    working.rows.forEach(function (row, rowIndex) {
      var wrapper = document.createElement('section'); wrapper.className = 'launcher-admin-row-card';
      var header = document.createElement('header'); header.className = 'launcher-admin-row-head';
      var fields = document.createElement('div'); fields.className = 'launcher-admin-row-title';
      var title = document.createElement('input'); title.value = row.title; title.maxLength = 48; title.setAttribute('aria-label', row.id + ' sor címe');
      title.addEventListener('input', function () { row.title = title.value; preview(); }); fields.appendChild(title);
      var visibleLabel = document.createElement('label'); visibleLabel.className = 'launcher-admin-small';
      var visible = document.createElement('input'); visible.type = 'checkbox'; visible.checked = row.visible; visible.addEventListener('change', function () { row.visible = visible.checked; preview(); }); visibleLabel.appendChild(visible); visibleLabel.appendChild(document.createTextNode(' Sor megjelenítése')); fields.appendChild(visibleLabel);
      var buttons = document.createElement('div'); buttons.className = 'launcher-admin-row-actions';
      buttons.appendChild(makeButton('↑', 'secondary', function () { move(working.rows, rowIndex, -1); renderRowsEditor(); preview(); }));
      buttons.appendChild(makeButton('↓', 'secondary', function () { move(working.rows, rowIndex, 1); renderRowsEditor(); preview(); }));
      header.appendChild(fields); header.appendChild(buttons); wrapper.appendChild(header);
      var items = document.createElement('div'); items.className = 'launcher-admin-tile-strip';
      row.items.forEach(function (item, itemIndex) {
        var card = document.createElement('div'); card.className = 'launcher-admin-tile-card'; card.setAttribute('role', 'button'); card.tabIndex = 0; card.setAttribute('data-admin-item-id', item.id); card.setAttribute('draggable', 'true');
        if (!item.visible) card.classList.add('is-hidden'); if (selectedItemId === item.id) card.classList.add('is-selected');
        var thumb = document.createElement('span'); thumb.className = 'launcher-admin-tile-thumb' + (item.type === 'preset' ? ' launcher-admin-camera-thumb' : ''); if (item.backgroundColor) thumb.style.background = item.backgroundColor;
        var fallback = document.createElement('span'); fallback.textContent = (item.label || '?').charAt(0).toLocaleUpperCase(); fallback.hidden = true; thumb.appendChild(fallback);
        var fallbackTimer = window.setTimeout(function () { fallback.hidden = false; }, 1800);
        var thumbSource = item.iconUrl || (item.type === 'app' && item.targetId ? '/api/apps/icon?appId=' + encodeURIComponent(item.targetId) : (item.type === 'preset' ? '/api/launcher/camera-preview?presetId=' + encodeURIComponent(item.targetId) : ''));
        if (thumbSource) { var image = document.createElement('img'); image.src = thumbSource; image.alt = ''; image.onload = function () { window.clearTimeout(fallbackTimer); fallback.hidden = true; }; image.onerror = function () { image.hidden = true; }; thumb.appendChild(image); }
        var label = document.createElement('strong'); label.textContent = item.label; var meta = document.createElement('small'); meta.textContent = item.visible ? item.type : 'elrejtve';
        card.appendChild(thumb); card.appendChild(label); card.appendChild(meta);
        if (selectedItemId === item.id) {
          var tools = document.createElement('span'); tools.className = 'launcher-admin-tile-tools';
          var edit = makeButton('✎', '', function (event) { event.stopPropagation(); openItemEditor(item.id); }); edit.title = 'Szerkesztés';
          var remove = makeButton(isProtected(item) ? (item.visible ? '◉' : '●') : '✕', isProtected(item) ? 'secondary' : 'danger', function (event) { event.stopPropagation(); changeItemVisibilityOrDelete(item.id); }); remove.title = isProtected(item) ? (item.visible ? 'Elrejtés' : 'Megjelenítés') : 'Törlés';
          tools.appendChild(edit); tools.appendChild(remove); card.appendChild(tools);
        }
        var holdTimer = null; var held = false;
        function startHold() { held = false; holdTimer = window.setTimeout(function () { held = true; selectedItemId = item.id; renderRowsEditor(); }, 550); }
        function cancelHold() { if (holdTimer) { window.clearTimeout(holdTimer); holdTimer = null; } }
        card.addEventListener('mousedown', startHold); card.addEventListener('mouseup', cancelHold); card.addEventListener('mouseleave', cancelHold);
        card.addEventListener('touchstart', startHold); card.addEventListener('touchend', cancelHold);
        card.addEventListener('click', function () { if (held) { held = false; return; } selectedItemId = selectedItemId === item.id ? '' : item.id; renderRowsEditor(); });
        card.addEventListener('keydown', function (event) { if (selectedItemId !== item.id) return; if (event.keyCode === 37 || event.keyCode === 39) { event.preventDefault(); reorderItem(item.id, event.keyCode === 37 ? -1 : 1); } else if (event.keyCode === 40) { event.preventDefault(); selectedItemId = ''; renderRowsEditor(); setStatus('A csempe helye rögzítve az előnézetben; mentéssel véglegesíthető.'); } });
        card.addEventListener('dragstart', function () { draggedItem = { rowId: row.id, itemId: item.id }; });
        card.addEventListener('dragover', function (event) { event.preventDefault(); });
        card.addEventListener('drop', function (event) { event.preventDefault(); if (!draggedItem || draggedItem.rowId !== row.id || draggedItem.itemId === item.id) return; var source = findItem(draggedItem.itemId); if (!source) return; var moved = source.row.items.splice(source.index, 1)[0]; var destination = row.items.map(function (entry) { return entry.id; }).indexOf(item.id); row.items.splice(destination, 0, moved); selectedItemId = moved.id; draggedItem = null; renderRowsEditor(); preview(); });
        items.appendChild(card);
      });
      wrapper.appendChild(items); host.appendChild(wrapper);
    });
    fillAddTargets();
  }
  function targetType(rowId) {
    if (rowId === 'links') return 'link';
    if (rowId === 'cameras') return 'preset';
    if (rowId === 'utilities') return el('launcher-add-type').value || 'app';
    return 'app';
  }
  function fillAddTargets() {
    var rowId = el('launcher-add-row').value; var type = targetType(rowId); var select = el('launcher-add-target');
    el('launcher-add-type-field').hidden = rowId !== 'utilities';
    el('launcher-add-url-field').hidden = type !== 'link'; select.parentNode.hidden = type === 'link' || type === 'allApps' || type === 'settings';
    select.textContent = '';
    if (type === 'app') metadata.apps.forEach(function (app) { option(select, app.id, app.title + ' · ' + app.id); });
    if (type === 'preset') metadata.presets.forEach(function (preset) { option(select, preset.id, preset.id + ' · ' + preset.kind); });
  }
  function addItem() {
    var row = working.rows.filter(function (candidate) { return candidate.id === el('launcher-add-row').value; })[0];
    var type = targetType(row.id); var target = type === 'link' ? el('launcher-add-url').value.trim() : ((type === 'allApps' || type === 'settings') ? '' : el('launcher-add-target').value);
    var label = el('launcher-add-label').value.trim();
    if (!label || ((type === 'app' || type === 'preset' || type === 'link') && !target)) { setStatus('A felirat és a cél kitöltése kötelező.', true); return; }
    var id = 'item-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
    row.items.push({ id: id, type: type, targetId: target, label: label, visible: true, fit: type === 'preset' ? 'cover' : 'contain', iconKey: '', iconUrl: '', backgroundColor: '' });
    el('launcher-add-label').value = ''; el('launcher-add-url').value = ''; renderRowsEditor(); preview(); setStatus('Az elem bekerült az előnézetbe; a véglegesítéshez mentsd a beállításokat.');
  }
  function readSettings() {
    working.settings.wallpaperEnabled = el('launcher-wallpaper-enabled').checked;
    working.settings.wallpaperIntervalMinutes = Number(el('launcher-wallpaper-interval').value);
    working.settings.wallpaperDimPercent = Number(el('launcher-wallpaper-dim').value);
    working.settings.focusScalePercent = Number(el('launcher-focus-scale').value);
    working.settings.defaultHomeEnabled = el('launcher-default-home').checked;
    working.settings.bootOverlayEnabled = el('launcher-boot-overlay').checked;
    working.settings.bootOverlayMaxSeconds = Number(el('launcher-boot-max').value);
    working.settings.animationsEnabled = el('launcher-animations').checked;
    working.settings.visualEffectsEnabled = el('launcher-visual-effects').checked;
    working.settings.homeLaunchMode = el('launcher-home-mode').value;
    working.settings.fullLauncherPresentation = el('launcher-full-presentation').value;
    working.settings.resumeLastAppOnPowerEnabled = el('launcher-resume-last').checked;
    working.settings.wallpaperUrls = el('launcher-wallpaper-urls').value.split(/\r?\n/).map(function (value) { return value.trim(); }).filter(Boolean);
    working.settings.cameraPreviewsEnabled = el('launcher-camera-previews').checked;
    working.settings.weatherEnabled = el('launcher-weather-enabled').checked;
    working.settings.weatherLabel = el('launcher-weather-label').value.trim();
    working.settings.latitude = Number(el('launcher-weather-latitude').value);
    working.settings.longitude = Number(el('launcher-weather-longitude').value);
  }
  function fillSettings() {
    var settings = working.settings;
    el('launcher-wallpaper-enabled').checked = settings.wallpaperEnabled; el('launcher-wallpaper-interval').value = settings.wallpaperIntervalMinutes;
    el('launcher-wallpaper-dim').value = settings.wallpaperDimPercent; el('launcher-focus-scale').value = settings.focusScalePercent || 10; el('launcher-wallpaper-urls').value = settings.wallpaperUrls.join('\n');
    el('launcher-default-home').checked = settings.defaultHomeEnabled === true;
    el('launcher-boot-overlay').checked = settings.bootOverlayEnabled !== false;
    el('launcher-boot-max').value = settings.bootOverlayMaxSeconds || 2;
    el('launcher-animations').checked = settings.animationsEnabled !== false;
    el('launcher-visual-effects').checked = settings.visualEffectsEnabled !== false;
    el('launcher-home-mode').value = settings.homeLaunchMode || 'split';
    el('launcher-full-presentation').value = settings.fullLauncherPresentation || 'app';
    el('launcher-resume-last').checked = settings.resumeLastAppOnPowerEnabled === true;
    el('launcher-camera-previews').checked = settings.cameraPreviewsEnabled; el('launcher-weather-enabled').checked = settings.weatherEnabled;
    el('launcher-weather-label').value = settings.weatherLabel; el('launcher-weather-latitude').value = settings.latitude; el('launcher-weather-longitude').value = settings.longitude;
  }
  function modalizeEditorSections(host) {
    var sections = Array.prototype.slice.call(host.querySelectorAll(':scope > .launcher-admin-panel'));
    var definitions = [
      ['Csempék és sorok', 'Sorok sorrendje, láthatósága és csempék rendezése.'],
      ['Új elem', 'Alkalmazás, kamera, webcím vagy rendszer-csempe hozzáadása.'],
      ['Megjelenés és időjárás', 'Háttérképek, előnézetek, nagyítás és időjárás.'],
      ['Indítás és teljesítmény', 'Kezdőképernyő, folytatás, takarás, animációk és látványeffektek.'],
      ['Mentés és hordozhatóság', 'Mentés, import, export és visszatöltés.']
    ];
    var hub = document.createElement('section'); hub.className = 'launcher-admin-hub';
    var heading = document.createElement('div'); heading.className = 'launcher-admin-hub-head'; heading.innerHTML = '<div><h2>Launcher beállításai</h2><p class="launcher-admin-small">A részletes blokkok külön ablakban nyílnak meg, így az oldal átlátható marad.</p></div><button id="launcher-hub-save" type="button">Minden mentése</button>'; hub.appendChild(heading);
    var grid = document.createElement('div'); grid.className = 'launcher-admin-category-grid'; hub.appendChild(grid); host.insertBefore(hub, host.firstChild);
    sections.forEach(function (section, index) {
      var overlay = document.createElement('div'); overlay.className = 'launcher-overlay launcher-admin-section-overlay'; overlay.hidden = true;
      var modal = document.createElement('section'); modal.className = 'launcher-modal launcher-admin-section-modal';
      var header = document.createElement('header'); header.className = 'launcher-modal-head'; header.innerHTML = '<div><h2></h2><p class="launcher-admin-small"></p></div><button class="launcher-close" type="button">×</button>';
      header.querySelector('h2').textContent = definitions[index][0]; header.querySelector('p').textContent = definitions[index][1];
      modal.appendChild(header); modal.appendChild(section); overlay.appendChild(modal); host.appendChild(overlay);
      var open = document.createElement('button'); open.type = 'button'; open.className = 'launcher-admin-category'; open.innerHTML = '<strong></strong><span></span><b>Megnyitás ›</b>'; open.querySelector('strong').textContent = definitions[index][0]; open.querySelector('span').textContent = definitions[index][1];
      open.addEventListener('click', function () { overlay.hidden = false; var first = section.querySelector('button,input,select,textarea'); if (first) first.focus(); });
      header.querySelector('button').addEventListener('click', function () { overlay.hidden = true; });
      overlay.addEventListener('click', function (event) { if (event.target === overlay) overlay.hidden = true; });
      grid.appendChild(open);
    });
    var status = el('launcher-admin-status'); if (status) hub.appendChild(status);
    el('launcher-hub-save').addEventListener('click', function () { el('launcher-save').click(); });
  }
  function buildEditor() {
    var host = el('launcher-editor');
    host.innerHTML = '<section class="launcher-admin-panel"><h2>Launcher szerkesztése</h2><p class="launcher-admin-small">Válassz ki egy csempét kattintással vagy nyomva tartással. A megjelenő két ikonnal szerkesztheted, törölheted vagy elrejtheted; húzással és a ← → billentyűkkel rendezheted.</p><div id="launcher-row-editor" class="launcher-admin-list"></div></section><section class="launcher-admin-panel"><h3>Új elem</h3><div class="launcher-admin-grid"><label>Sor<select id="launcher-add-row"></select></label><label id="launcher-add-type-field" hidden>Típus<select id="launcher-add-type"><option value="app">Alkalmazás</option><option value="allApps">Összes alkalmazás rács</option><option value="settings">Launcher beállítások</option></select></label><label>Felirat<input id="launcher-add-label" maxlength="64"></label><label>Cél<select id="launcher-add-target"></select></label><label id="launcher-add-url-field" hidden>Webcím<input id="launcher-add-url" type="url" placeholder="https://…"></label></div><div class="launcher-admin-actions"><button id="launcher-add-button" type="button">Elem hozzáadása</button></div></section><section class="launcher-admin-panel"><h3>Háttér, kamerák és időjárás</h3><div class="launcher-admin-grid"><label><span><input id="launcher-wallpaper-enabled" type="checkbox"> Háttérképváltás</span></label><label>Váltási idő (1–10 perc)<input id="launcher-wallpaper-interval" type="number" min="1" max="10"></label><label>Háttér sötétítése (0–85%)<input id="launcher-wallpaper-dim" type="range" min="0" max="85"></label><label><span><input id="launcher-camera-previews" type="checkbox"> Kamera-előnézetek</span></label><label class="wide">Háttérkép URL-ek, soronként egy<textarea id="launcher-wallpaper-urls"></textarea></label><label><span><input id="launcher-weather-enabled" type="checkbox"> Mai időjárás</span></label><label>Hely neve<input id="launcher-weather-label" maxlength="64" placeholder="Budapest"></label><label>Szélesség<input id="launcher-weather-latitude" type="number" min="-90" max="90" step="0.0001"></label><label>Hosszúság<input id="launcher-weather-longitude" type="number" min="-180" max="180" step="0.0001"></label></div></section><section class="launcher-admin-panel"><h3>Kezdőképernyő és sebesség</h3><div class="launcher-admin-grid"><label class="wide"><span><input id="launcher-default-home" type="checkbox"> A launcher legyen az alapértelmezett kezdőképernyő</span><small class="launcher-admin-small">Bekapcsolva újraindításkor, gyors ébredéskor és egy alkalmazás bezárásakor a launcher nyílik meg. A gyári Home nem kerül lecserélésre.</small></label><label><span><input id="launcher-boot-overlay" type="checkbox"> Fekete induló takarás</span></label><label>Induló takarás legfeljebb (1–10 mp)<input id="launcher-boot-max" type="number" min="1" max="10" step="1"></label><label><span><input id="launcher-animations" type="checkbox"> Animációk és átmenetek</span><small class="launcher-admin-small">Kikapcsolva a kijelölés és az overlayek azonnal váltanak.</small></label><label><span><input id="launcher-visual-effects" type="checkbox"> Látványeffektek (panelek áttetszősége, elmosás, árnyék)</span><small class="launcher-admin-small">Kikapcsolva egyszerűbb panelek jelennek meg. A háttérkép és az átlátszó csempefelirat megmarad.</small></label><label><span><input id="launcher-resume-last" type="checkbox"> Bekapcsoláskor az utolsó app folytatása</span><small class="launcher-admin-small">Csak valódi TV-bekapcsoláskor vagy gyors ébredéskor; normál appkilépéskor továbbra is a launcher tér vissza.</small></label></div><div class="launcher-admin-actions"><button id="launcher-system-home" class="secondary" type="button">Kilépés az LG Home menübe</button></div></section><section class="launcher-admin-panel"><h3>Mentés és hordozhatóság</h3><div class="launcher-admin-actions"><button id="launcher-save" type="button">Minden beállítás mentése</button><button id="launcher-export" class="secondary" type="button">JSON export</button><button id="launcher-import-button" class="secondary" type="button">JSON import</button><input id="launcher-import" type="file" accept="application/json,.json" hidden><button id="launcher-reload" class="secondary" type="button">Mentett állapot újratöltése</button></div><p id="launcher-admin-status" class="launcher-admin-status"></p></section><div id="launcher-admin-item-overlay" class="launcher-overlay" hidden><section class="launcher-modal launcher-admin-item-modal"><header class="launcher-modal-head"><div><h2>Csempe szerkesztése</h2><p id="launcher-admin-item-name" class="launcher-admin-small"></p></div><button id="launcher-admin-item-close" class="launcher-close" type="button">×</button></header><form id="launcher-admin-item-form" class="launcher-admin-item-form"><input id="launcher-admin-item-id" type="hidden"><label>Felirat<input id="launcher-admin-item-label" maxlength="64"></label><label>Ikon / kép mérete<select id="launcher-admin-item-fit"><option value="small">Kicsi, középen</option><option value="contain">Arányosan, teljes ikon</option><option value="cover">Teljes csempe kitöltése</option></select></label><label>Beépített ikon<select id="launcher-admin-item-icon-key"><option value="">Automatikus</option><option value="installed">Gyári alkalmazásikon</option></select></label><label>Saját ikon vagy kép URL<input id="launcher-admin-item-icon-url" type="url" placeholder="https://…"></label><label>Háttérszín<input id="launcher-admin-item-background" maxlength="7" placeholder="#123456"></label><label class="launcher-admin-visible"><input id="launcher-admin-item-visible" type="checkbox"> Látható</label><div class="launcher-admin-actions"><button type="submit">Alkalmazás</button><button id="launcher-admin-item-cancel" class="secondary" type="button">Mégse</button></div></form></section></div>';
    modalizeEditorSections(host);
    (metadata.icons || []).forEach(function (entry) { option(el('launcher-admin-item-icon-key'), entry.key, entry.label); });
    el('launcher-admin-item-close').addEventListener('click', closeItemEditor); el('launcher-admin-item-cancel').addEventListener('click', closeItemEditor); el('launcher-admin-item-form').addEventListener('submit', saveItemEditor);
    el('launcher-admin-item-icon-key').addEventListener('change', function () { if (this.value) el('launcher-admin-item-icon-url').value = ''; });
    el('launcher-admin-item-icon-url').addEventListener('input', function () { if (this.value.trim()) el('launcher-admin-item-icon-key').value = ''; });
    var presentationFields = document.createElement('div');
    presentationFields.innerHTML = '<label>Home gomb indítási módja<select id="launcher-home-mode"><option value="split">Rövid: gyorsmenü · hosszú: teljes</option><option value="full">Mindig teljes launcher</option><option value="overlay">Mindig gyorsmenü</option></select></label><label>Teljes launcher megjelenítése<select id="launcher-full-presentation"><option value="app">Teljes alkalmazás (előre betölthető)</option><option value="overlay">Overlay (a mögöttes app megmarad)</option></select></label>';
    el('launcher-animations').closest('.launcher-admin-panel').appendChild(presentationFields);
    var focusLabel = document.createElement('label');
    focusLabel.innerHTML = 'Kijelölt csempe nagyítása<select id="launcher-focus-scale"><option value="5">5%</option><option value="10">10%</option><option value="15">15%</option><option value="20">20%</option></select>';
    var cameraPreviewLabel = el('launcher-camera-previews').parentNode.parentNode;
    cameraPreviewLabel.parentNode.insertBefore(focusLabel, cameraPreviewLabel);
    working.rows.forEach(function (row) { option(el('launcher-add-row'), row.id, row.title); });
    el('launcher-add-row').addEventListener('change', fillAddTargets); el('launcher-add-type').addEventListener('change', fillAddTargets); el('launcher-add-button').addEventListener('click', addItem);
    ['launcher-wallpaper-enabled','launcher-wallpaper-interval','launcher-wallpaper-dim','launcher-focus-scale','launcher-wallpaper-urls','launcher-camera-previews','launcher-weather-enabled','launcher-weather-label','launcher-weather-latitude','launcher-weather-longitude','launcher-default-home','launcher-boot-overlay','launcher-boot-max','launcher-animations','launcher-visual-effects','launcher-resume-last','launcher-home-mode','launcher-full-presentation'].forEach(function (id) { el(id).addEventListener('input', function () { readSettings(); preview(); }); });
    el('launcher-system-home').addEventListener('click', function () {
      setStatus('Átváltás az LG Home menüre…');
      fetch('/api/launcher/system-home', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).then(function (response) { return response.json().then(function (body) { if (!response.ok || !body.ok) throw new Error(body.error || 'A TV nem válaszolt.'); return body; }); }).then(function () { setStatus('A gyári LG Home menü megnyitva. A védelem a következő alkalmazásindítás után újra aktív lesz.'); }, function (error) { setStatus(error.message, true); });
    });
    el('launcher-save').addEventListener('click', function () { readSettings(); setStatus('Mentés…'); controller.save(working).then(function (saved) { working = saved; fillSettings(); renderRowsEditor(); setStatus('A launcher beállításai elmentve.'); }, function (error) { setStatus(error.message, true); }); });
    el('launcher-export').addEventListener('click', function () { readSettings(); var blob = new Blob([JSON.stringify(working, null, 2)], { type: 'application/json' }); var link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'lgtv-launcher-settings.json'; link.click(); window.setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000); });
    el('launcher-import-button').addEventListener('click', function () { el('launcher-import').click(); });
    el('launcher-import').addEventListener('change', function () { var file = this.files && this.files[0]; if (!file) return; var reader = new FileReader(); reader.onload = function () { try { working = JSON.parse(reader.result); fillSettings(); renderRowsEditor(); preview(); setStatus('Az import betöltve az előnézetbe. Ellenőrzés után mentsd el.'); } catch (error) { setStatus('A JSON import nem olvasható.', true); } }; reader.readAsText(file); });
    el('launcher-reload').addEventListener('click', function () { controller.reload(); });
    fillSettings(); renderRowsEditor();
  }
  function ready(nextController) {
    controller = nextController; metadata = controller.snapshot(); working = metadata.config; buildEditor(); window.setTimeout(fitPreviewForViewport, 0);
  }
  function fitPreviewForViewport() {
    var host = el('launcher-preview'); if (!host) return; var shell = host.querySelector('.launcher-shell'); if (!shell) return;
    if (window.innerWidth <= 760) {
      var hostWidth = host.clientWidth; if (!hostWidth) return;
      host.classList.add('launcher-preview-scaled'); host.style.height = ''; shell.style.width = '1280px'; shell.style.transform = 'none';
      var scale = Math.min(1, hostWidth / 1280); var naturalHeight = shell.offsetHeight || 720;
      shell.style.transform = 'scale(' + scale + ')'; host.style.height = Math.ceil(naturalHeight * scale) + 'px';
    } else {
      host.classList.remove('launcher-preview-scaled'); host.style.height = ''; shell.style.width = ''; shell.style.transform = '';
    }
  }
  function createPage() {
    document.body.classList.add('launcher-admin-enabled');
    var tab = document.createElement('button'); tab.className = 'tab'; tab.type = 'button'; tab.setAttribute('data-page', 'launcher'); tab.textContent = 'Launcher'; document.querySelector('.tabs').appendChild(tab);
    tab.addEventListener('click', function () { showPage('launcher'); });
    var page = document.createElement('section'); page.id = 'page-launcher'; page.className = 'page'; page.hidden = true;
    page.innerHTML = '<section class="launcher-admin-panel launcher-screen-toolbar"><div class="launcher-screen-heading"><h2>Launcher előnézet és TV</h2><p class="launcher-admin-small">Az élő kép ugyanitt váltja fel a szimulációt, és csak bekapcsolt állapotban frissül.</p></div><div class="launcher-screen-actions"><label class="launcher-view-switch"><span>Szimuláció</span><input id="launcher-live-enabled" type="checkbox" role="switch" aria-label="Élő TV-kép bekapcsolása"><i aria-hidden="true"></i><span>Élő TV</span></label><button id="launcher-remote-button" class="secondary" type="button" aria-haspopup="dialog" aria-expanded="false">⌁ Távirányító</button><button id="launcher-tv-screen-button" class="secondary" type="button">Egyszeri nagy kép</button></div></section><div class="launcher-preview-stage"><section id="launcher-preview" class="launcher-preview-surface"></section><figure id="launcher-live-stage" class="launcher-live-stage" hidden><div class="launcher-live-placeholder" aria-hidden="true"><b>TV</b><span>Az élő képre várunk…</span></div><img id="launcher-live-image" class="launcher-live-image" alt="A TV élő képe" hidden><figcaption id="launcher-live-status">Élő nézet kikapcsolva</figcaption></figure></div><section id="launcher-editor" class="launcher-admin"></section><div id="launcher-remote-overlay" class="launcher-overlay launcher-remote-overlay" hidden><section class="launcher-modal launcher-remote-modal" role="dialog" aria-modal="true" aria-labelledby="launcher-remote-title"><header class="launcher-modal-head"><div><h2 id="launcher-remote-title">TV távirányító</h2><p class="launcher-admin-small">A gomb csak kattintásra küld parancsot a TV-nek.</p></div><button id="launcher-remote-close" class="launcher-close" type="button" aria-label="Távirányító bezárása">×</button></header><div class="launcher-remote-device"><div class="launcher-remote-brand"><span>LG TV</span><small>Hálózati távirányító</small></div><div class="launcher-remote-utility"><button type="button" data-tv-key="home"><b>⌂</b><span>Home</span></button><button type="button" data-tv-key="back"><b>↶</b><span>Vissza</span></button></div><div class="launcher-remote-navigation" aria-label="Navigáció"><button type="button" data-tv-key="up" class="launcher-remote-up" aria-label="Fel">▲</button><button type="button" data-tv-key="left" class="launcher-remote-left" aria-label="Balra">◀</button><button type="button" data-tv-key="ok" class="launcher-remote-ok">OK</button><button type="button" data-tv-key="right" class="launcher-remote-right" aria-label="Jobbra">▶</button><button type="button" data-tv-key="down" class="launcher-remote-down" aria-label="Le">▼</button></div><div class="launcher-remote-media"><button type="button" data-tv-key="playPause"><b>▶Ⅱ</b><span>Lejátszás</span></button><button type="button" data-tv-key="stop"><b>■</b><span>Stop</span></button></div></div><p id="launcher-remote-status" class="launcher-remote-status" role="status" aria-live="polite">A távirányító használatra kész.</p></section></div><div id="launcher-tv-screen-overlay" class="launcher-overlay" hidden><section class="launcher-modal"><header class="launcher-modal-head"><h2>TV aktuális képe</h2><button id="launcher-tv-screen-close" class="launcher-close" type="button">×</button></header><p id="launcher-tv-screen-status" class="launcher-admin-small">Képkocka lekérése…</p><img id="launcher-tv-screen-image" class="launcher-tv-screen-image" alt="A TV aktuális képernyőképe"><div class="launcher-admin-actions"><button id="launcher-tv-screen-refresh" type="button">Kép frissítése</button></div></section></div>';
    document.querySelector('main').appendChild(page);
    window.addEventListener('resize', function () { if (previewResizeTimer) window.clearTimeout(previewResizeTimer); previewResizeTimer = window.setTimeout(fitPreviewForViewport, 80); });
    function loadScreen() { var image = el('launcher-tv-screen-image'); el('launcher-tv-screen-status').textContent = 'Képkocka lekérése…'; image.hidden = true; image.onload = function () { image.hidden = false; el('launcher-tv-screen-status').textContent = 'Egyszeri 1920 × 1080 képkocka · ' + new Date().toLocaleTimeString('hu-HU'); }; image.onerror = function () { el('launcher-tv-screen-status').textContent = 'A TV-kép most nem kérhető le.'; }; image.src = '/api/tv-screen?_=' + Date.now(); }
    el('launcher-tv-screen-button').addEventListener('click', function () { el('launcher-tv-screen-overlay').hidden = false; loadScreen(); });
    el('launcher-tv-screen-close').addEventListener('click', function () { el('launcher-tv-screen-overlay').hidden = true; });
    el('launcher-tv-screen-refresh').addEventListener('click', loadScreen);
    function closeRemote() { el('launcher-remote-overlay').hidden = true; el('launcher-remote-button').setAttribute('aria-expanded', 'false'); el('launcher-remote-button').focus(); }
    el('launcher-remote-button').addEventListener('click', function () { el('launcher-remote-overlay').hidden = false; this.setAttribute('aria-expanded', 'true'); el('launcher-remote-close').focus(); });
    el('launcher-remote-close').addEventListener('click', closeRemote);
    el('launcher-remote-overlay').addEventListener('click', function (event) { if (event.target === this) closeRemote(); });
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape' && !el('launcher-remote-overlay').hidden) closeRemote(); });
    var liveTimer = null; var livePending = false;
    function scheduleLive(delay) { if (liveTimer) window.clearTimeout(liveTimer); if (el('launcher-live-enabled').checked) liveTimer = window.setTimeout(loadLive, delay); }
    function loadLive() {
      if (!el('launcher-live-enabled').checked || livePending) return;
      livePending = true; var image = el('launcher-live-image');
      image.onload = function () { livePending = false; image.hidden = false; el('launcher-live-status').textContent = 'Élő TV-kép · ' + new Date().toLocaleTimeString('hu-HU'); scheduleLive(1500); };
      image.onerror = function () { livePending = false; image.hidden = true; el('launcher-live-status').textContent = 'A VNC-kép most nem érhető el, újrapróbáljuk…'; scheduleLive(3500); };
      image.src = '/api/tv-screen?_=' + Date.now();
    }
    el('launcher-live-enabled').addEventListener('change', function () { var enabled = this.checked; el('launcher-preview').hidden = enabled; el('launcher-live-stage').hidden = !enabled; if (enabled) { el('launcher-live-status').textContent = 'Élő képkocka lekérése…'; loadLive(); } else { if (liveTimer) window.clearTimeout(liveTimer); liveTimer = null; livePending = false; el('launcher-live-image').hidden = true; el('launcher-live-status').textContent = 'Élő nézet kikapcsolva'; } });
    Array.prototype.forEach.call(page.querySelectorAll('[data-tv-key]'), function (button) {
      button.addEventListener('click', function () {
        var key = button.getAttribute('data-tv-key'); el('launcher-remote-status').textContent = 'Küldés: ' + key + '…';
        fetch('/api/tv-key', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: key }) }).then(function (response) { return response.json().then(function (body) { if (!response.ok || !body.ok) throw new Error(body.error || 'A TV nem válaszolt.'); }); }).then(function () { el('launcher-remote-status').textContent = 'Elküldve: ' + key; if (el('launcher-live-enabled').checked) scheduleLive(250); }, function (error) { el('launcher-remote-status').textContent = error.message; });
      });
    });
    window.LauncherUI.init(el('launcher-preview'), { mode: 'admin', apiBase: '', onReady: ready });
  }
  createPage();
}());
