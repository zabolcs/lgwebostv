'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var ROOT = path.resolve(__dirname, '..');
var Core = require(path.join(ROOT, 'core.js'));

function rejects(fn, pattern) {
  assert.throws(fn, pattern);
}

assert.strictEqual(Core.BLOCKED_HOST, '192.168.0.100');
assert.strictEqual(Core.privateIPv4('192.168.0.125'), '192.168.0.125');
assert.strictEqual(Core.privateIPv4('10.2.3.4'), '10.2.3.4');
assert.strictEqual(Core.privateIPv4('192.168.0.100'), null);
assert.strictEqual(Core.privateIPv4('8.8.8.8'), null);
assert.strictEqual(Core.privateIPv4('192.168.000.125'), null);

assert.strictEqual(
  Core.normalizeMediaUrl('http://192.168.0.125:1984/api/stream.m3u8?src=front_sub'),
  'http://192.168.0.125:1984/api/stream.m3u8?src=front_sub'
);
assert.strictEqual(
  Core.normalizeMediaUrl('https://10.0.0.2:8443/live/camera.m3u8?camera=front'),
  'https://10.0.0.2:8443/live/camera.m3u8?camera=front'
);
assert.strictEqual(
  Core.normalizeMediaUrl('http://192.168.0.125/image.jpg?quality=high'),
  'http://192.168.0.125/image.jpg?quality=high'
);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.100:8080/live'); }, /nem engedélyezett/);
rejects(function () { Core.normalizeMediaUrl('http://camera.local:8080/live'); }, /formátuma/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/live?token=secret'); }, /Titkot/);
rejects(function () { Core.normalizeMediaUrl('http://user:pass@192.168.0.2:8080/live'); }, /formátuma/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/192.168.0.100/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/live?src=192.168.0.100'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/192.168.000.100/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/0192.168.0.100/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/3232235620/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/0xc0a80064/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/192.168.100/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/192.11010148/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/0xc0.0xa8.0x0.0x64/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/0000300.0000250.0000.0000144/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/proxy/0000000000300.0000000000250.00000000000.0000000000144/live'); }, /tiltott/);
rejects(function () { Core.normalizeMediaUrl('http://192.168.0.2:8080/%252e%252e/admin'); }, /kódolt|útvonala/);

var defaults = Core.defaultConfig();
assert.strictEqual(defaults.layout.corner, 'top-left');
assert.strictEqual(defaults.layout.width, 640);
assert.strictEqual(defaults.layout.height, 360);
assert.strictEqual(defaults.layout.ttlMs, 15000);
assert.deepStrictEqual(defaults.presets.map(function (preset) { return preset.id; }), ['welcome']);
assert.strictEqual(defaults.presets.some(function (preset) { return /192\.168\./.test(preset.content); }), false);

var savedLayout = Core.normalizeLayout({ corner: 'bottom-right', width: 800, height: 450, marginX: 21, marginY: 22, ttlMs: 0 });
assert.deepStrictEqual(Core.resolveLayoutRequest({ width: 900, margin: 15 }, savedLayout), {
  corner: 'bottom-right', width: 900, height: 450, marginX: 15, marginY: 15, ttlMs: 0
});
assert.deepStrictEqual(Core.resolveLayoutRequest({ margin: 15, marginX: 25, ttlMs: 30000 }, savedLayout), {
  corner: 'bottom-right', width: 800, height: 450, marginX: 25, marginY: 15, ttlMs: 30000
});
var savedCustomPreset = Core.normalizePreset({ id: 'custom', kind: 'text', content: 'Saját', fit: 'contain' });
var supplemented = Core.parseStored(JSON.stringify({ version: 1, layout: savedLayout, presets: [savedCustomPreset] }));
assert.deepStrictEqual(supplemented.layout, savedLayout);
assert.deepStrictEqual(supplemented.presets[0], savedCustomPreset);
assert.strictEqual(supplemented.presets.length, 1);

var savedKapuPreview = Core.normalizePreset({
  id: 'kapu-preview',
  kind: 'image',
  content: 'http://10.0.0.2:8080/custom.jpeg?src=sajat_kapu',
  fit: 'contain',
  clickAction: 'openCamera',
  cameraId: 'sajat-kapu'
});
var preserved = Core.parseStored(JSON.stringify({ version: 1, layout: savedLayout, presets: [savedKapuPreview] }));
assert.deepStrictEqual(preserved.layout, savedLayout);
assert.deepStrictEqual(preserved.presets, [savedKapuPreview]);

var fullUserPresetList = [];
for (var presetIndex = 0; presetIndex < 32; presetIndex++) {
  fullUserPresetList.push(Core.normalizePreset({
    id: 'user-' + presetIndex,
    kind: 'text',
    content: 'User preset ' + presetIndex,
    fit: 'contain'
  }));
}
var fullPreserved = Core.parseStored(JSON.stringify({ version: 1, layout: savedLayout, presets: fullUserPresetList }));
assert.deepStrictEqual(fullPreserved.presets, fullUserPresetList);

assert.strictEqual(Core.keyIntent('SELECT', 37), 'select');
assert.strictEqual(Core.keyIntent('SELECT', 39), 'select');
assert.strictEqual(Core.keyIntent('SELECT', 38), 'focus');
assert.strictEqual(Core.keyIntent('SELECT', 40), 'focus');
assert.strictEqual(Core.keyIntent('INPUT', 37), 'native');
assert.strictEqual(Core.keyIntent('INPUT', 39), 'native');
assert.strictEqual(Core.keyIntent('INPUT', 38), 'focus');
assert.strictEqual(Core.keyIntent('TEXTAREA', 40), 'focus');
assert.strictEqual(Core.keyIntent('BUTTON', 37), 'focus');
assert.strictEqual(Core.keyIntent('SELECT', 13), 'other');

var cameraPreset = Core.normalizePreset({
  id: 'doorbell',
  kind: 'image',
  content: 'http://192.168.0.125:1984/api/frame.jpeg?camera=front',
  fit: 'cover',
  clickAction: 'openCamera',
  cameraId: 'front'
});
assert.strictEqual(cameraPreset.clickAction, 'openCamera');
assert.strictEqual(cameraPreset.cameraId, 'front');
var dismissPreset = Core.normalizePreset({
  id: 'quiet-camera', kind: 'image', content: 'http://192.168.0.125/frame.jpg',
  fit: 'cover', clickAction: 'dismiss'
});
assert.strictEqual(dismissPreset.clickAction, 'dismiss');
assert.strictEqual(dismissPreset.cameraId, '');
rejects(function () {
  Core.normalizePreset({ id: 'bad', kind: 'text', content: 'x', clickAction: 'openCamera', cameraId: '../front' });
}, /kamera-ID/);
rejects(function () {
  Core.normalizePreset({ id: 'bad', kind: 'text', content: 'x', clickAction: 'launchApp', cameraId: 'front' });
}, /kattintási/);

var remotelyManagedPreset = Core.resolvePresetRequest({
  presetId: 'udvar-web',
  kind: 'image',
  url: 'http://192.168.0.150:1984/api/stream.mjpeg?src=camera_udvar_felso_preview',
  fit: 'cover',
  clickAction: 'openCamera',
  cameraId: 'udvar'
});
assert.strictEqual(remotelyManagedPreset.id, 'udvar-web');
assert.strictEqual(remotelyManagedPreset.clickAction, 'openCamera');
assert.strictEqual(remotelyManagedPreset.cameraId, 'udvar');
rejects(function () {
  Core.resolvePresetRequest({ presetId: 'bad-camera', kind: 'text', text: 'x', clickAction: 'openCamera', cameraId: '../front' });
}, /kamera-ID/);

var config = {
  version: 1,
  layout: defaults.layout,
  presets: [cameraPreset]
};
var resolved = Core.resolveShowRequest({ presetId: 'doorbell', mode: 'fullscreen' }, config);
assert.strictEqual(resolved.preset.cameraId, 'front');
assert.strictEqual(resolved.fullscreen, true);
assert.deepStrictEqual(resolved.layout, defaults.layout);

var directImage = Core.resolveShowRequest({
  kind: 'image',
  url: 'http://192.168.0.125:1984/api/frame.jpeg?camera=front&quality=high',
  fit: 'cover',
  corner: 'bottom-right',
  width: 800,
  height: 450,
  marginX: 20,
  marginY: 30,
  ttlMs: 0
}, config);
assert.strictEqual(directImage.preset.kind, 'image');
assert.strictEqual(directImage.preset.fit, 'cover');
assert.strictEqual(directImage.preset.content, 'http://192.168.0.125:1984/api/frame.jpeg?camera=front&quality=high');
assert.deepStrictEqual(directImage.layout, {
  corner: 'bottom-right', width: 800, height: 450, marginX: 20, marginY: 30, ttlMs: 0
});
assert.strictEqual(directImage.ttlMs, 0);

var directVideo = Core.resolveShowRequest({
  kind: 'video',
  src: 'http://10.0.0.2/live/video.mp4',
  margin: 12
}, config);
assert.strictEqual(directVideo.preset.kind, 'video');
assert.strictEqual(directVideo.layout.marginX, 12);
assert.strictEqual(directVideo.layout.marginY, 12);

rejects(function () {
  Core.resolveShowRequest({ kind: 'video', text: 'x' }, config);
}, /text/);
rejects(function () {
  Core.resolveShowRequest({ kind: 'image', url: 'http://192.168.0.125/x.jpg', src: 'http://192.168.0.125/y.jpg' }, config);
}, /Egyszerre/);
rejects(function () {
  Core.resolveShowRequest({ presetId: 'doorbell', url: 'http://192.168.0.125/x.jpg' }, config);
}, /Preset indításnál/);
rejects(function () {
  Core.resolveShowRequest({ presetId: 'doorbell', mode: 'preview' }, config);
}, /mód/);
rejects(function () {
  Core.resolveShowRequest({ presetId: 'doorbell', kind: 'text', text: 'ignored' }, config);
}, /Preset indításnál/);
assert.strictEqual(Core.normalizeAction({ v: 1, action: 'show', presetId: 'doorbell' }), 'show');
assert.strictEqual(Core.normalizeAction({
  v: 1, action: 'show', kind: 'image', url: 'http://192.168.0.125/x.jpg',
  corner: 'top-right', width: 640, height: 360, margin: 16, marginX: 20, marginY: 10,
  fit: 'cover', ttlMs: 0
}), 'show');
assert.strictEqual(Core.normalizeAction({ v: 1, action: 'close' }), 'dismiss');
assert.strictEqual(Core.normalizeAction({
  v: 1, action: 'configure', corner: 'bottom-left', width: 700, height: 394,
  marginX: 20, marginY: 25, ttlMs: 0
}), 'configure');
assert.strictEqual(Core.normalizeAction({ v: 1, action: 'defaults', margin: 16 }), 'configure');
assert.strictEqual(Core.normalizeAction({
  v: 1, action: 'preset-save', presetId: 'udvar-web', kind: 'image',
  url: 'http://192.168.0.150:1984/live', fit: 'cover', clickAction: 'openCamera', cameraId: 'udvar'
}), 'preset-save');
assert.strictEqual(Core.normalizeAction({ v: 1, action: 'savePreset', presetId: 'x', kind: 'text', text: 'x' }), 'preset-save');
assert.strictEqual(Core.normalizeAction({ v: 1, action: 'preset-delete', presetId: 'udvar-web' }), 'preset-delete');
assert.strictEqual(Core.normalizeAction({ v: 1, action: 'deletePreset', presetId: 'x' }), 'preset-delete');
rejects(function () {
  Core.normalizeAction({ v: 1, action: 'configure', url: 'http://192.168.0.125/x.jpg' });
}, /tiltott mezőt/);
assert.strictEqual(Core.normalizeAction({
  v: 1, action: 'show', kind: 'image', url: 'http://192.168.0.125/x.jpg',
  clickAction: 'openCamera', cameraId: 'front'
}), 'show');
assert.strictEqual(Core.normalizeAction({ v: 1, action: 'show', presetId: 'doorbell', cameraId: 'front' }), 'show');
rejects(function () {
  Core.resolveShowRequest({ presetId: 'doorbell', cameraId: 'front' }, config);
}, /Preset indításnál|kattint/);
assert.strictEqual(Core.normalizeAction({
  v: 1, action: 'sync', syncUrl: 'http://192.168.0.223/api/tv-sync/media-overlay'
}), 'sync');
rejects(function () {
  Core.normalizeAction({ action: 'settings', url: 'http://192.168.0.125:1984/x' });
}, /tiltott mezőt/);
assert.strictEqual(
  Core.resolveShowRequest({ kind: 'text', text: '<img src=x onerror=alert(1)>' }, config).preset.content,
  '<img src=x onerror=alert(1)>'
);

var appInfo = JSON.parse(fs.readFileSync(path.join(ROOT, 'appinfo.json'), 'utf8'));
var packageInfo = JSON.parse(fs.readFileSync(path.join(ROOT, 'packageinfo.json'), 'utf8'));
assert.strictEqual(appInfo.id, 'hu.szabi.mediaoverlay');
assert.strictEqual(appInfo.version, '0.3.7');
assert.strictEqual(appInfo.transparent, true);
assert.strictEqual(appInfo.defaultWindowType, 'popup');
assert.strictEqual(appInfo.handlesRelaunch, true);
assert.strictEqual(appInfo.icon, 'icon.png');
assert.strictEqual(appInfo.largeIcon, 'icon-large.png');
assert.strictEqual(packageInfo.id, appInfo.id);
assert.strictEqual(packageInfo.version, appInfo.version);
assert.strictEqual(Object.prototype.hasOwnProperty.call(appInfo, 'requiredPermissions'), false);

var appSource = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
var css = fs.readFileSync(path.join(ROOT, 'style.css'), 'utf8');
assert.ok(/CAMERA_APP_ID = 'hu\.szabi\.cameraviewer'/.test(appSource));
assert.ok(/LAST_SHOW_KEY = 'hu\.szabi\.mediaoverlay\.last-show\.v1'/.test(appSource));
assert.ok(/keys\.length === 1 && keys\[0\] === 'storeCaller' && params\.storeCaller === 'home'/.test(appSource));
assert.strictEqual(/CAMERA_PRESENCE_URL|192\.168\.0\.223/.test(appSource), false);
assert.ok(/function cameraPresenceUrl\(\)/.test(appSource));
assert.ok(/state === 'VISIBLE' \|\| state === 'LOADING' \|\| state === 'CHECKING_FOREGROUND'/.test(appSource));
assert.ok(/\{ v: 1, action: 'open', cameraId: cameraId, view: 'full', requestId: newRequestId\(\) \}/.test(appSource));
assert.strictEqual(/params\.appId|params\.url|params\.src/.test(appSource), false);
assert.strictEqual(fs.existsSync(path.join(ROOT, 'service')), false);
assert.strictEqual(fs.existsSync(path.join(ROOT, 'services.json')), false);
assert.strictEqual(fs.existsSync(path.join(ROOT, 'assets', 'icon-source.svg')), true);
assert.strictEqual(/(^|[;{\s])gap\s*:/m.test(css), false, 'Chrome 79 miatt flex-gapre és rövid gap propertyre nem támaszkodunk.');
assert.ok(/#overlay-controls button \+ button\s*\{\s*margin-left:\s*10px/.test(css));
assert.ok(/\.preset-row > \* \+ \*[\s\S]*margin-left:\s*16px/.test(css));
assert.ok(/label > input,[\s\S]*margin-top:\s*7px/.test(css));

console.log('media overlay tests: PASS');
