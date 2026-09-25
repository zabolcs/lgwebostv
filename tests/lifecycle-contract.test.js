'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var vm = require('vm');

var ROOT = path.resolve(__dirname, '..');

function ClassList() { this.names = {}; }
ClassList.prototype.add = function () { for (var i = 0; i < arguments.length; i++) this.names[arguments[i]] = true; };
ClassList.prototype.remove = function () { for (var i = 0; i < arguments.length; i++) delete this.names[arguments[i]]; };
ClassList.prototype.contains = function (name) { return !!this.names[name]; };
ClassList.prototype.toggle = function (name, force) {
  var enabled = force === undefined ? !this.contains(name) : !!force;
  if (enabled) this.add(name); else this.remove(name);
  return enabled;
};

function Element(document, id, tagName) {
  this.ownerDocument = document;
  this.id = id || '';
  this.tagName = String(tagName || 'DIV').toUpperCase();
  this.hidden = false;
  this.disabled = false;
  this.value = '';
  this.checked = false;
  this.tabIndex = -1;
  this.children = [];
  this.options = [];
  this.selectedIndex = 0;
  this.listeners = {};
  this.classList = new ClassList();
  this.style = { setProperty: function () {} };
  this.attributes = {};
  this._text = '';
  this.src = '';
  this.srcObject = null;
}
Object.defineProperty(Element.prototype, 'firstChild', { get: function () { return this.children[0] || null; } });
Object.defineProperty(Element.prototype, 'className', {
  get: function () { return Object.keys(this.classList.names).join(' '); },
  set: function (value) {
    this.classList.names = {};
    String(value || '').split(/\s+/).forEach(function (name) { if (name) this.classList.add(name); }, this);
  }
});
Object.defineProperty(Element.prototype, 'textContent', {
  get: function () { return this._text; },
  set: function (value) { this._text = String(value == null ? '' : value); this.children = []; this.options = []; }
});
Element.prototype.addEventListener = function (name, handler) { (this.listeners[name] || (this.listeners[name] = [])).push(handler); };
Element.prototype.dispatchEvent = function (event) {
  event = event || {};
  event.target = event.target || this;
  event.currentTarget = this;
  var list = this.listeners[event.type] || [];
  for (var i = 0; i < list.length; i++) list[i](event);
};
Element.prototype.appendChild = function (child) {
  this.children.push(child);
  if (child.tagName === 'OPTION') this.options.push(child);
  return child;
};
Element.prototype.removeChild = function (child) {
  var index = this.children.indexOf(child);
  if (index >= 0) this.children.splice(index, 1);
  var optionIndex = this.options.indexOf(child);
  if (optionIndex >= 0) this.options.splice(optionIndex, 1);
  return child;
};
Element.prototype.setAttribute = function (name, value) { this.attributes[name] = String(value); };
Element.prototype.getAttribute = function (name) { return this.attributes[name] || null; };
Element.prototype.removeAttribute = function (name) { delete this.attributes[name]; if (name === 'src') this.src = ''; };
Element.prototype.focus = function () { this.ownerDocument.activeElement = this; };
Element.prototype.closest = function (selector) { return selector === '.hidden' && this.classList.contains('hidden') ? this : null; };
Element.prototype.querySelector = function (selector) { var all = this.querySelectorAll(selector); return all[0] || null; };
Element.prototype.querySelectorAll = function (selector) {
  var result = [];
  function visit(node) {
    for (var i = 0; i < node.children.length; i++) {
      var child = node.children[i];
      if (selector.charAt(0) === '.' && selector.indexOf(' ') === -1 && child.classList.contains(selector.slice(1))) result.push(child);
      if (selector.indexOf('button') !== -1 && ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].indexOf(child.tagName) !== -1 && !child.disabled) result.push(child);
      visit(child);
    }
  }
  visit(this);
  return result;
};
Element.prototype.pause = function () {};
Element.prototype.load = function () {};
Element.prototype.play = function () { return { catch: function () {} }; };
Element.prototype.click = function () { this.dispatchEvent({ type: 'click', preventDefault: function () {}, stopPropagation: function () {} }); };

function makeEnvironment(ids, savedStorage) {
  var documentListeners = {};
  var windowListeners = {};
  var elements = {};
  var documentStyle = {};
  var document = {
    hidden: false,
    readyState: 'complete',
    activeElement: null,
    documentElement: { style: { setProperty: function (name, value) { documentStyle[name] = value; } } },
    addEventListener: function (name, handler) { (documentListeners[name] || (documentListeners[name] = [])).push(handler); },
    emit: function (name, event) { var list = documentListeners[name] || []; for (var i = 0; i < list.length; i++) list[i](event || {}); },
    getElementById: function (id) { return elements[id] || null; },
    createElement: function (tag) { return new Element(document, '', tag); },
    createEvent: function () { return { type: '', initEvent: function (name) { this.type = name; } }; },
    querySelectorAll: function () { return []; }
  };
  for (var i = 0; i < ids.length; i++) elements[ids[i]] = new Element(document, ids[i], inferTag(ids[i]));
  var storage = savedStorage || {};
  var timers = {};
  var nextTimer = 1;
  var root = {
    document: document,
    localStorage: {
      getItem: function (key) { return Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : null; },
      setItem: function (key, value) { storage[key] = String(value); }
    },
    addEventListener: function (name, handler) { (windowListeners[name] || (windowListeners[name] = [])).push(handler); },
    emit: function (name, event) { var list = windowListeners[name] || []; for (var i = 0; i < list.length; i++) list[i](event || {}); },
    setTimeout: function (handler) { var id = nextTimer++; timers[id] = handler; return id; },
    clearTimeout: function (id) { delete timers[id]; },
    closeCount: 0,
    close: function () { root.closeCount += 1; },
    webOSSystem: { launchParams: null, activateCount: 0, activate: function () { this.activateCount += 1; } },
    PalmSystem: null,
    crypto: require('crypto').webcrypto,
    URL: URL,
    Date: Date,
    Math: Math,
    JSON: JSON,
    Object: Object,
    Array: Array,
    Number: Number,
    String: String,
    RegExp: RegExp,
    Error: Error,
    Uint8Array: Uint8Array,
    console: console
  };
  root.window = root;
  root.globalThis = root;
  return { root: root, document: document, elements: elements, storage: storage, timers: timers, documentStyle: documentStyle };
}

function inferTag(id) {
  if (/button|close|new-profile|delete-profile|cancel-settings|settings-button|viewer-audio|page-previous|page-next|save-view-settings/.test(id)) return 'BUTTON';
  if (/select|type|scheme|corner/.test(id)) return 'SELECT';
  if (/content/.test(id)) return 'TEXTAREA';
  if (/name|camera-id|source|host|port|path|width|height|margin|seconds/.test(id)) return 'INPUT';
  if (/form/.test(id)) return 'FORM';
  return 'DIV';
}

function runCameraLifecycle() {
  var ids = [
    'grid-screen', 'viewer-screen', 'viewer-stage', 'viewer-title', 'viewer-status', 'viewer-close',
    'viewer-transport', 'camera-grid', 'empty-state', 'message', 'settings-button', 'settings-panel',
    'profile-select', 'profile-name', 'camera-id', 'primary-source', 'preview-source', 'stream-scheme',
    'stream-host', 'stream-port', 'player-port', 'player-path', 'settings-error', 'empty-settings-button', 'settings-close',
    'cancel-settings', 'new-profile', 'delete-profile', 'settings-form', 'viewer-audio',
    'screen-guard', 'page-controls', 'page-previous', 'page-next', 'page-indicator', 'camera-audio',
    'layout-size', 'featured-camera', 'prevent-screensaver', 'preview-interval-seconds', 'save-view-settings'
  ];
  var profile = [{
    id: 'profile-front', cameraId: 'front', name: 'Bejárat', type: 'hls', scheme: 'http',
    host: '192.168.1.10', port: 1984, path: '/api/stream.m3u8?src=front',
    snapshotPath: '/api/frame.jpeg?src=front'
  }];
  var currentProfile = {
    id: 'profile-front', cameraId: 'front', name: 'Bejárat', scheme: 'http', host: '192.168.1.10',
    port: 1984, playerPort: 1985, playerPath: '/webos-player.html', audio: true,
    primarySource: 'front', previewSource: 'front'
  };
  var env = makeEnvironment(ids, { 'hu.szabi.cameraviewer.config.v3': JSON.stringify({ version: 3, settings: { layoutSize: 2, featuredCameraId: '', preventScreenSaver: false, previewIntervalSeconds: 5 }, profiles: [currentProfile] }) });
  env.elements['grid-screen'].appendChild(env.elements['camera-grid']);
  env.elements['settings-panel'].appendChild(env.elements['profile-select']);
  env.elements['settings-panel'].appendChild(env.elements['stream-scheme']);
  var context = vm.createContext(env.root);
  var source = fs.readFileSync(path.join(ROOT, 'apps', 'camera-viewer', 'app.js'), 'utf8');
  vm.runInContext(source, context, { filename: 'camera-viewer/app.js' });

  var featureButtons = env.elements['camera-grid'].querySelectorAll('.camera-feature');
  assert.strictEqual(featureButtons.length, 1, 'every preview must have a featured-camera eye button');
  featureButtons[0].click();
  var featuredStored = JSON.parse(env.storage['hu.szabi.cameraviewer.config.v3']);
  assert.strictEqual(featuredStored.settings.featuredCameraId, 'front');
  featureButtons = env.elements['camera-grid'].querySelectorAll('.camera-feature');
  assert.strictEqual(featureButtons[0].classList.contains('is-featured'), true, 'the selected eye must be crossed');
  featureButtons[0].click();
  featuredStored = JSON.parse(env.storage['hu.szabi.cameraviewer.config.v3']);
  assert.strictEqual(featuredStored.settings.featuredCameraId, '', 'clicking the crossed eye must clear the feature');

  env.elements.message.textContent = 'Régi figyelmeztetés';
  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify({ storeCaller: 'home' }) } });
  assert.strictEqual(env.root.webOSSystem.activateCount, 1, 'Home launcher open must foreground the app');
  assert.strictEqual(env.elements.message.textContent, '', 'Home launcher metadata must not produce a warning');

  var request = { v: 1, action: 'open', cameraId: 'front', view: 'full', requestId: '0123456789abcdef0123456789abcdef' };
  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(request) } });
  assert.strictEqual(env.root.webOSSystem.activateCount, 2, 'warm relaunch must activate the app');
  assert.strictEqual(env.elements['viewer-screen'].classList.contains('hidden'), false);
  assert.strictEqual(env.elements['viewer-stage'].children.length, 1);
  assert.strictEqual(env.elements['viewer-stage'].children[0].tagName, 'IFRAME');

  env.elements['viewer-close'].click();
  assert.strictEqual(env.root.closeCount, 1, 'an externally opened full-screen camera must close the popup back to the underlying app');

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(Object.assign({}, request, { requestId: '1123456789abcdef0123456789abcdef' })) } });
  assert.strictEqual(env.elements['viewer-screen'].classList.contains('hidden'), false);
  assert.strictEqual(env.root.webOSSystem.activateCount, 3, 'reopening the popup must activate it');

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(Object.assign({}, request, { requestId: '1123456789abcdef0123456789abcdef' })) } });
  assert.strictEqual(env.root.webOSSystem.activateCount, 4, 'duplicate relaunch must still foreground');
  assert.strictEqual(env.elements['viewer-stage'].children.length, 1, 'duplicate request must not create another decoder');

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify({ v: 1, action: 'open', cameraId: 'missing', view: 'full' }) } });
  assert.strictEqual(env.root.webOSSystem.activateCount, 5, 'invalid target must still foreground the visible error');
  assert.ok(/Ismeretlen kamera/.test(env.elements.message.textContent));

  env.root.emit('pagehide', {});
  assert.strictEqual(env.elements['viewer-stage'].children.length, 0, 'pagehide must release the active media node');
}

function runOverlayLifecycle() {
  var ids = [
    'overlay', 'overlay-frame', 'media-host', 'overlay-status', 'overlay-controls', 'fullscreen-button',
    'close-button', 'settings', 'settings-close-button', 'corner', 'width', 'height', 'margin-x',
    'margin-y', 'ttl-seconds', 'save-layout-button', 'preset-list', 'new-preset-button',
    'delete-preset-button', 'preset-id', 'preset-kind', 'preset-fit', 'preset-content',
    'preset-click-action', 'preset-camera-id', 'save-preset-button', 'show-preset-button',
    'settings-status', 'content-label'
  ];
  var env = makeEnvironment(ids, {});
  env.elements.overlay.appendChild(env.elements['overlay-frame']);
  env.elements['overlay-frame'].appendChild(env.elements['media-host']);
  env.elements['overlay-frame'].appendChild(env.elements['overlay-status']);
  env.elements['overlay-frame'].appendChild(env.elements['overlay-controls']);
  env.elements['overlay-controls'].appendChild(env.elements['fullscreen-button']);
  env.elements['overlay-controls'].appendChild(env.elements['close-button']);
  env.elements['content-label'].appendChild({ nodeValue: '' });
  env.elements.overlay.hidden = true;
  env.elements.settings.hidden = false;
  env.root.MediaOverlayCore = require(path.join(ROOT, 'apps', 'media-overlay', 'core.js'));
  var directImage = {
    v: 1,
    action: 'show',
    kind: 'image',
    url: 'http://192.168.0.150:1984/api/frame.jpeg?src=front',
    fit: 'cover',
    corner: 'bottom-right',
    width: 800,
    height: 450,
    marginX: 20,
    marginY: 30,
    ttlMs: 0
  };
  env.root.webOSSystem.launchParams = JSON.stringify(directImage);
  var context = vm.createContext(env.root);
  var source = fs.readFileSync(path.join(ROOT, 'apps', 'media-overlay', 'app.js'), 'utf8');
  vm.runInContext(source, context, { filename: 'media-overlay/app.js' });
  assert.strictEqual(env.elements.overlay.hidden, false);
  assert.strictEqual(env.elements['media-host'].children.length, 1);
  assert.strictEqual(env.elements['media-host'].children[0].tagName, 'IMG');
  assert.strictEqual(env.elements['media-host'].children[0].src, directImage.url);
  assert.strictEqual(env.documentStyle['--overlay-width'], '800px');
  assert.strictEqual(env.documentStyle['--overlay-height'], '450px');
  assert.strictEqual(env.documentStyle['--margin-x'], '20px');
  assert.strictEqual(env.documentStyle['--margin-y'], '30px');
  assert.strictEqual(env.elements.overlay.classList.contains('corner-bottom-right'), true);
  var liveImage = env.elements['media-host'].children[0];
  liveImage.onload();
  assert.strictEqual(Object.keys(env.timers).length, 0, 'ttlMs:0 must not arm an expiry timer');
  liveImage.onerror();
  assert.ok(/újracsatlakozás/.test(env.elements['overlay-status'].textContent));
  assert.strictEqual(env.root.closeCount, 0, 'a late MJPEG error must not close a ttlMs:0 overlay');
  var retryIds = Object.keys(env.timers);
  assert.strictEqual(retryIds.length, 1, 'a late MJPEG error must arm exactly one reconnect');
  var retryId = retryIds[0];
  var retry = env.timers[retryId];
  delete env.timers[retryId];
  retry();
  assert.ok(/_overlay_retry=/.test(liveImage.src));
  liveImage.onload();
  assert.strictEqual(Object.keys(env.timers).length, 0, 'successful reconnect must clear its load timer');
  assert.strictEqual(env.elements['overlay-status'].textContent, '');

  var relaunch = { v: 1, action: 'show', kind: 'text', text: 'Második', ttlMs: 0, requestId: '1123456789abcdef0123456789abcdef' };
  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(relaunch) } });
  assert.strictEqual(env.root.webOSSystem.activateCount, 1);
  assert.strictEqual(env.elements['media-host'].children[0], liveImage, 'a futó PiP-et új show nem írhatja felül');

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(relaunch) } });
  assert.strictEqual(env.root.webOSSystem.activateCount, 2, 'duplicate overlay request must still foreground');
  assert.strictEqual(env.elements['media-host'].children.length, 1);

  var replacementImage = Object.assign({}, directImage, {
    url: 'http://192.168.0.150:1984/api/frame.jpeg?src=back',
    requestId: '2123456789abcdef0123456789abcdef'
  });
  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(replacementImage) } });
  assert.strictEqual(env.root.webOSSystem.activateCount, 3);
  assert.strictEqual(env.elements['media-host'].children[0], liveImage, 'másik show requestId sem cserélheti le az aktív PiP-et');

  var configure = {
    v: 1, action: 'configure', corner: 'top-right', width: 720, height: 405,
    marginX: 18, marginY: 24, ttlMs: 0
  };
  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(configure) } });
  var stored = JSON.parse(env.storage['hu.szabi.mediaoverlay.config.v1']);
  assert.deepStrictEqual(stored.layout, {
    corner: 'top-right', width: 720, height: 405, marginX: 18, marginY: 24, ttlMs: 0
  });
  assert.strictEqual(env.root.closeCount, 1, 'configure must persist defaults and close without showing media');
  assert.strictEqual(env.root.webOSSystem.activateCount, 3, 'configure must not foreground a closing app');

  var savePreset = {
    v: 1, action: 'preset-save', presetId: 'web-kapu', kind: 'image',
    url: 'http://192.168.0.150:1984/api/stream.mjpeg?src=camera_kapu_felso_preview',
    fit: 'cover', clickAction: 'openCamera', cameraId: 'kapu'
  };
  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(savePreset) } });
  stored = JSON.parse(env.storage['hu.szabi.mediaoverlay.config.v1']);
  var webPreset = stored.presets.filter(function (preset) { return preset.id === 'web-kapu'; })[0];
  assert.strictEqual(webPreset.cameraId, 'kapu');
  assert.strictEqual(webPreset.clickAction, 'openCamera');
  assert.strictEqual(env.root.closeCount, 2);

  savePreset.kind = 'text';
  savePreset.text = 'Módosítva';
  delete savePreset.url;
  delete savePreset.fit;
  delete savePreset.clickAction;
  delete savePreset.cameraId;
  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify(savePreset) } });
  stored = JSON.parse(env.storage['hu.szabi.mediaoverlay.config.v1']);
  var matching = stored.presets.filter(function (preset) { return preset.id === 'web-kapu'; });
  assert.strictEqual(matching.length, 1, 'saving an existing id must update instead of duplicate');
  assert.strictEqual(matching[0].content, 'Módosítva');
  assert.strictEqual(env.root.closeCount, 3);

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify({ v: 1, action: 'preset-delete', presetId: 'web-kapu' }) } });
  stored = JSON.parse(env.storage['hu.szabi.mediaoverlay.config.v1']);
  assert.strictEqual(stored.presets.some(function (preset) { return preset.id === 'web-kapu'; }), false);
  assert.strictEqual(env.root.closeCount, 4);
  assert.strictEqual(env.root.webOSSystem.activateCount, 3, 'preset management must not foreground a closing app');

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify({ v: '1', action: 'show', kind: 'text', text: 'tiltott' }) } });
  assert.strictEqual(env.root.webOSSystem.activateCount, 4);
  assert.ok(/verziója/.test(env.elements['overlay-status'].textContent));

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify({ v: 1, action: 'dismiss' }) } });
  assert.strictEqual(env.root.closeCount, 5, 'dismiss relaunch must close the overlay app');
  assert.strictEqual(env.root.webOSSystem.activateCount, 4, 'dismiss must not foreground a closing app');
}

function runOverlayRememberedLaunch() {
  var ids = [
    'overlay', 'overlay-frame', 'media-host', 'overlay-status', 'overlay-controls', 'fullscreen-button',
    'close-button', 'settings', 'settings-close-button', 'corner', 'width', 'height', 'margin-x',
    'margin-y', 'ttl-seconds', 'save-layout-button', 'preset-list', 'new-preset-button',
    'delete-preset-button', 'preset-id', 'preset-kind', 'preset-fit', 'preset-content',
    'preset-click-action', 'preset-camera-id', 'save-preset-button', 'show-preset-button',
    'settings-status', 'content-label'
  ];
  var env = makeEnvironment(ids, {});
  env.elements.overlay.appendChild(env.elements['overlay-frame']);
  env.elements['overlay-frame'].appendChild(env.elements['media-host']);
  env.elements['overlay-frame'].appendChild(env.elements['overlay-status']);
  env.elements['overlay-frame'].appendChild(env.elements['overlay-controls']);
  env.elements['overlay-controls'].appendChild(env.elements['fullscreen-button']);
  env.elements['overlay-controls'].appendChild(env.elements['close-button']);
  env.elements['content-label'].appendChild({ nodeValue: '' });
  env.elements.overlay.hidden = true;
  env.elements.settings.hidden = false;
  env.root.MediaOverlayCore = require(path.join(ROOT, 'apps', 'media-overlay', 'core.js'));
  env.root.webOSSystem.launchParams = JSON.stringify({
    v: 1, action: 'show', kind: 'text', text: 'Megjegyzett PiP', corner: 'bottom-left',
    width: 700, height: 394, marginX: 30, marginY: 40, ttlMs: 0
  });
  var context = vm.createContext(env.root);
  var source = fs.readFileSync(path.join(ROOT, 'apps', 'media-overlay', 'app.js'), 'utf8');
  vm.runInContext(source, context, { filename: 'media-overlay/app.js' });

  var remembered = JSON.parse(env.storage['hu.szabi.mediaoverlay.last-show.v1']);
  assert.strictEqual(remembered.text, 'Megjegyzett PiP');
  assert.strictEqual(remembered.corner, 'bottom-left');
  assert.strictEqual(remembered.ttlMs, 0);
  assert.strictEqual(Object.prototype.hasOwnProperty.call(remembered, 'requestId'), false);

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify({ v: 1, action: 'dismiss' }) } });
  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify({ storeCaller: 'home' }) } });
  assert.strictEqual(env.elements['media-host'].children[0].textContent, 'Megjegyzett PiP');
  assert.strictEqual(env.documentStyle['--overlay-width'], '700px');
  assert.strictEqual(env.elements.overlay.classList.contains('corner-bottom-left'), true);
  var replayed = env.elements['media-host'].children[0];

  env.document.emit('webOSRelaunch', { detail: { launchParams: '{}' } });
  assert.strictEqual(env.elements['media-host'].children[0], replayed, 'az aktív PiP-et az üres relaunch sem írhatja felül');

  env.document.emit('webOSRelaunch', { detail: { launchParams: JSON.stringify({ action: 'settings' }) } });
  assert.strictEqual(env.elements.settings.hidden, false, 'az explicit settings továbbra is a beállítófelületet nyitja');
  assert.strictEqual(env.elements.overlay.hidden, true);

  var empty = makeEnvironment(ids, {});
  empty.elements.overlay.appendChild(empty.elements['overlay-frame']);
  empty.elements['overlay-frame'].appendChild(empty.elements['media-host']);
  empty.elements['overlay-frame'].appendChild(empty.elements['overlay-status']);
  empty.elements['overlay-frame'].appendChild(empty.elements['overlay-controls']);
  empty.elements['overlay-controls'].appendChild(empty.elements['fullscreen-button']);
  empty.elements['overlay-controls'].appendChild(empty.elements['close-button']);
  empty.elements['content-label'].appendChild({ nodeValue: '' });
  empty.elements.overlay.hidden = true;
  empty.elements.settings.hidden = false;
  empty.root.MediaOverlayCore = env.root.MediaOverlayCore;
  empty.root.webOSSystem.launchParams = JSON.stringify({ storeCaller: 'home' });
  vm.runInContext(source, vm.createContext(empty.root), { filename: 'media-overlay/app.js' });
  assert.strictEqual(empty.elements.settings.hidden, false);
  assert.ok(/nincs visszajátszható/.test(empty.elements['settings-status'].textContent));
}

runCameraLifecycle();
runOverlayLifecycle();
runOverlayRememberedLaunch();
console.log('lifecycle contract tests: PASS');
