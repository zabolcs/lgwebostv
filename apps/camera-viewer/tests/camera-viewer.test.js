'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var appRoot = path.resolve(__dirname, '..');
var core = require(path.join(appRoot, 'app.js'));

function validProfile(overrides) {
  var value = {
    id: 'profile-front',
    cameraId: 'front',
    name: 'Bejárat',
    scheme: 'http',
    host: '192.168.1.10',
    port: 1984,
    playerPort: 1985,
    playerPath: '/webos-player.html',
    audio: true,
    primarySource: 'front_h264',
    previewSource: 'front_preview'
  };
  Object.keys(overrides || {}).forEach(function (key) { value[key] = overrides[key]; });
  return value;
}

var appInfo = JSON.parse(fs.readFileSync(path.join(appRoot, 'appinfo.json'), 'utf8'));
var packageInfo = JSON.parse(fs.readFileSync(path.join(appRoot, 'packageinfo.json'), 'utf8'));
assert.strictEqual(appInfo.id, 'hu.szabi.cameraviewer');
assert.strictEqual(appInfo.version, '0.3.19');
assert.strictEqual(appInfo.type, 'web');
assert.strictEqual(appInfo.transparent, true);
assert.strictEqual(appInfo.defaultWindowType, 'popup');
assert.strictEqual(appInfo.noSplashOnLaunch, true);
assert.strictEqual(appInfo.handlesRelaunch, true);
assert.strictEqual(appInfo.disableBackHistoryAPI, true);
assert.strictEqual(packageInfo.id, appInfo.id);
assert.strictEqual(packageInfo.version, appInfo.version);
assert.strictEqual(packageInfo.package_format_version, 2);
assert.strictEqual(core.MAX_PROFILES, null);

assert.deepStrictEqual(core.DEFAULT_PROFILES, []);

assert.strictEqual(core.validateProfile(validProfile()).ok, true);
assert.strictEqual(core.validateProfile(validProfile({ cameraId: 'FrontDoor' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ cameraId: 'a23456789012345678901234567890123' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ host: '192.168.0.100' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ primarySource: '192.168.0.100' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ previewSource: 'proxy_192.168.0.100_cam' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ primarySource: '10.0.0.2' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ host: 'camera.local' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ host: '8.8.8.8' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ scheme: 'ftp' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ primarySource: '../front' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ previewSource: 'front?token=x' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ playerPath: 'http://192.168.1.10/player' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ playerPath: '/../player.html' })).ok, false);
assert.strictEqual(core.validateProfile(validProfile({ playerPath: '' })).ok, true);
assert.strictEqual(core.validateProfile(validProfile({ playerPort: 0 })).ok, false);

var profile = core.validateProfile(validProfile()).value;
assert.strictEqual(core.buildUrl(profile, 'mjpeg'), 'http://192.168.1.10:1984/api/stream.mjpeg?src=front_preview');
assert.strictEqual(
  core.buildUrl(core.validateProfile(validProfile({ cameraId: 'kapu', previewSource: 'camera_kapu_felso_h264' })).value, 'mjpeg'),
  'http://192.168.1.10:1984/api/stream.mjpeg?src=camera_kapu_felso_preview'
);
assert.strictEqual(
  core.buildUrl(core.validateProfile(validProfile({ cameraId: 'kapu2', previewSource: 'camera_kapu_also_h264' })).value, 'mjpeg'),
  'http://192.168.1.10:1984/api/stream.mjpeg?src=camera_kapu_also_preview'
);
assert.strictEqual(core.buildUrl(profile, 'snapshot'), 'http://192.168.1.10:1984/api/frame.jpeg?src=front_preview');
assert.strictEqual(core.buildSnapshotUrl(profile, '55s'), 'http://192.168.1.10:1984/api/frame.jpeg?src=front_preview&cache=55s');
assert.strictEqual(core.buildPlayerUrl(profile, '0123456789abcdef0123456789abcdef'),
  'http://192.168.1.10:1985/webos-player.html#src=front_h264&session=0123456789abcdef0123456789abcdef&audio=1');
assert.ok(/&audio=0$/.test(core.buildPlayerUrl(core.validateProfile(validProfile({ audio: false })).value, '0123456789abcdef0123456789abcdef')));
assert.deepStrictEqual(core.playbackPlan(profile), ['mjpeg', 'webrtc', 'snapshot']);
assert.deepStrictEqual(core.playbackPlan(profile, 'webrtc'), ['webrtc', 'mjpeg', 'snapshot']);
assert.deepStrictEqual(core.playbackPlan(profile, 'mjpeg'), ['mjpeg', 'webrtc', 'snapshot']);
assert.deepStrictEqual(core.playbackPlan(core.validateProfile(validProfile({ playerPath: '' })).value), ['mjpeg', 'snapshot']);
assert.deepStrictEqual(core.screenSaverResponsePayload({
  returnValue: true, state: 'Active', timestamp: '1388518297'
}), { clientName: 'hu.szabi.cameraviewer', ack: false, timestamp: '1388518297' });
assert.strictEqual(core.screenSaverResponsePayload({ returnValue: true, state: 'Inactive', timestamp: '1388518297' }), null);
assert.strictEqual(core.screenSaverResponsePayload({ returnValue: true, state: 'Active', timestamp: '../bad' }), null);
assert.strictEqual(core.SCREEN_SAVER_REGISTER_URI,
  'luna://com.webos.service.tvpower/power/registerScreenSaverRequest');
assert.strictEqual(core.SCREEN_SAVER_RESPONSE_URI,
  'luna://com.webos.service.tvpower/power/responseScreenSaverRequest');

var legacy = {
  id: 'profile-legacy',
  cameraId: 'legacy',
  name: 'Régi kamera',
  type: 'hls',
  scheme: 'http',
  host: '192.168.1.20',
  port: 1984,
  path: '/api/stream.m3u8?src=legacy_h264',
  snapshotPath: '/api/frame.jpeg?src=legacy_preview'
};
var migrated = core.migrateLegacyProfile(legacy);
assert.strictEqual(migrated.ok, true);
assert.strictEqual(migrated.value.primarySource, 'legacy_h264');
assert.strictEqual(migrated.value.previewSource, 'legacy_preview');
assert.strictEqual(migrated.value.playerPort, 1984);
assert.strictEqual(migrated.value.playerPath, '');
var migratedMjpeg = core.migrateLegacyProfile(validProfile({
  type: 'mjpeg', path: '/api/stream.mjpeg?src=legacy_preview', snapshotPath: '/api/frame.jpeg?src=legacy_preview'
}));
assert.strictEqual(migratedMjpeg.ok, true);
assert.strictEqual(migratedMjpeg.value.playerPath, '', 'A legacy MJPEG profil ne várjon WebRTC-re.');
var merged = core.migrateLegacyProfiles([legacy]);
assert.strictEqual(merged.length, 1);
assert.strictEqual(merged[0].cameraId, 'legacy');

var brokenLiveV2 = [
  validProfile({
    id: 'profile-legacy-gyerekszoba',
    cameraId: 'camera_gyerekszoba_preview',
    name: 'gyerekszoba',
    host: '192.168.0.150',
    port: 1984,
    playerPort: 1985,
    playerPath: '',
    primarySource: 'camera_gyerekszoba_preview',
    previewSource: 'camera_gyerekszoba_preview'
  }),
  validProfile({
    id: 'profile-legacy-kapu',
    cameraId: 'camera_kapu_felso_preview',
    name: 'kapu1',
    host: '192.168.0.150',
    port: 1984,
    playerPort: 1985,
    playerPath: '',
    primarySource: 'camera_kapu_felso_preview',
    previewSource: 'camera_kapu_felso_preview'
  })
];
var repairedLiveV2 = core.reconcileProfiles(brokenLiveV2);
assert.deepStrictEqual(repairedLiveV2.map(function (item) { return item.cameraId; }), ['camera_gyerekszoba_preview', 'camera_kapu_felso_preview']);

var customProfile = validProfile({
  id: 'profile-garazs',
  cameraId: 'garazs',
  name: 'Garázs',
  primarySource: 'garazs_h264',
  previewSource: 'garazs_preview'
});
var repairedWithCustom = core.reconcileProfiles(brokenLiveV2.concat([customProfile]));
assert.deepStrictEqual(repairedWithCustom.map(function (item) { return item.cameraId; }), ['camera_gyerekszoba_preview', 'camera_kapu_felso_preview', 'garazs']);
assert.deepStrictEqual(repairedWithCustom[2], core.validateProfile(customProfile).value);

var manyProfiles = [];
for (var manyIndex = 0; manyIndex < 18; manyIndex += 1) {
  manyProfiles.push(core.validateProfile(validProfile({
    id: 'profile-many-' + manyIndex,
    cameraId: 'camera-' + manyIndex,
    name: 'Kamera ' + manyIndex,
    primarySource: 'source-' + manyIndex,
    previewSource: 'preview-' + manyIndex
  })).value);
}
assert.strictEqual(core.normalizeProfileList(manyProfiles).length, 18, 'A tárolható kamerák száma nem korlátozott.');
var page3 = core.pageLayout(manyProfiles, { layoutSize: 3, featuredCameraId: '', preventScreenSaver: false }, 1);
assert.strictEqual(page3.pageCount, 2);
assert.strictEqual(page3.items.length, 9);
assert.strictEqual(page3.items[0].profile.cameraId, 'camera-9');
var featured3 = core.pageLayout(manyProfiles, { layoutSize: 3, featuredCameraId: 'camera-0', preventScreenSaver: true }, 1);
assert.strictEqual(featured3.pageCount, 4);
assert.strictEqual(featured3.items.length, 6);
assert.strictEqual(featured3.items[0].profile.cameraId, 'camera-0');
assert.strictEqual(featured3.items[0].featured, true);
var featured4 = core.pageLayout(manyProfiles, { layoutSize: 4, featuredCameraId: 'camera-0', preventScreenSaver: false }, 0);
assert.strictEqual(featured4.items.length, 13);
assert.strictEqual(core.normalizeConfig({ version: 3, settings: { layoutSize: 4, featuredCameraId: 'camera-0', preventScreenSaver: true }, profiles: manyProfiles }).profiles.length, 18);

var launch = core.extractLaunchCommand({
  v: 1,
  action: 'open',
  cameraId: 'front',
  view: 'full',
  requestId: '0123456789abcdef0123456789abcdef'
});
assert.strictEqual(launch.ok, true);
assert.strictEqual(launch.value.cameraId, 'front');
assert.strictEqual(core.extractLaunchCommand({
  launchParams: JSON.stringify({ v: 1, action: 'open', cameraId: 'front', view: 'full' })
}).ok, true);
assert.strictEqual(core.extractLaunchCommand({
  parameters: { v: 1, action: 'open', profileId: 'profile-front', view: 'full' }
}).ok, true);
assert.strictEqual(core.isPlainLauncherOpen({}), true);
assert.strictEqual(core.isPlainLauncherOpen({ storeCaller: 'home' }), true);
assert.strictEqual(core.isPlainLauncherOpen({ storeCaller: 'settings' }), false);
assert.strictEqual(core.isPlainLauncherOpen({ storeCaller: 'home', action: 'open' }), false);
assert.strictEqual(core.extractLaunchCommand({
  v: 1, action: 'open', cameraId: 'front', view: 'full', url: 'http://camera/live'
}).ok, false);
assert.strictEqual(core.extractLaunchCommand({
  v: 1, action: 'open', cameraId: 'Front', view: 'full'
}).ok, false);
assert.strictEqual(core.extractLaunchCommand({
  v: 1, action: 'open', cameraId: 'front', profileId: 'profile-front', view: 'full'
}).ok, false);
assert.strictEqual(core.extractLaunchCommand({
  v: 1, action: 'sync', syncUrl: 'http://192.168.0.223/api/tv-sync/camera-viewer'
}).ok, true);
assert.strictEqual(core.extractLaunchCommand({
  v: 1, action: 'configure', layoutSize: 4, featuredCameraId: 'front', preventScreenSaver: true
}).value.settings.layoutSize, 4);
assert.strictEqual(core.extractLaunchCommand(Object.assign({ v: 1, action: 'camera-save' }, validProfile())).ok, true);
assert.strictEqual(core.extractLaunchCommand({ v: 1, action: 'camera-delete', cameraId: 'front' }).ok, true);
var reordered = core.reorderProfiles([
  validProfile({ id: 'profile-a', cameraId: 'a' }),
  validProfile({ id: 'profile-b', cameraId: 'b' }),
  validProfile({ id: 'profile-c', cameraId: 'c' })
], ['c', 'a', 'b']);
assert.deepStrictEqual(reordered.map(function (item) { return item.cameraId; }), ['c', 'a', 'b']);
assert.throws(function () { core.reorderProfiles(reordered, ['a', 'a', 'c']); }, /ismétlődő/);
assert.throws(function () { core.reorderProfiles(reordered, ['a', 'b']); }, /minden kamerát/);
assert.deepStrictEqual(core.extractLaunchCommand({
  v: 1, action: 'camera-reorder', cameraIds: ['c', 'a', 'b']
}).value.cameraIds, ['c', 'a', 'b']);
assert.strictEqual(core.extractLaunchCommand({
  v: 1, action: 'camera-reorder', cameraIds: ['a', 'a']
}).ok, false);
assert.strictEqual(core.previewRefreshDelay(2, 1000, 1500), 1500,
  'A 2 mp-es érték kéréskezdetek közötti idő legyen, ne a betöltés utáni plusz várakozás.');
assert.strictEqual(core.previewRefreshDelay(2, 1000, 3500), 50,
  'Lassú snapshot után ne adódjon hozzá még egyszer a teljes beállított intervallum.');

var html = fs.readFileSync(path.join(appRoot, 'index.html'), 'utf8');
var script = fs.readFileSync(path.join(appRoot, 'app.js'), 'utf8');
var css = fs.readFileSync(path.join(appRoot, 'styles.css'), 'utf8');
assert.strictEqual(/PRESENCE_URL|192\.168\.0\.223/.test(script), false);
assert.ok(/presenceUrl = markerIndex > 0/.test(script));
assert.ok(/PRESENCE_INTERVAL_MS = 2500/.test(script));
assert.ok(/\.topbar-tools\s*\{[\s\S]*?column-gap:\s*26px/.test(css));
var hostedPlayer = fs.readFileSync(path.join(appRoot, 'webos-player.html'), 'utf8');
var hostedPlayerScript = fs.readFileSync(path.join(appRoot, 'webos-player.js'), 'utf8');
assert.strictEqual((html.match(/id="viewer-stage"/g) || []).length, 1);
assert.ok(/id="camera-id"[^>]*maxlength="32"/.test(html));
assert.ok(/id="layout-size"/.test(html));
assert.ok(/id="featured-camera"/.test(html));
assert.ok(/id="prevent-screensaver"/.test(html));
assert.strictEqual(/id="viewer-pip"/.test(html), false);
assert.strictEqual(/camera-pip|launchCameraPip|pipLaunchPending/.test(script + css), false);
assert.strictEqual(/class="brand"|id="app-title"/.test(html), false);
assert.ok(/id="settings-button"[^>]*aria-label="Beállítások"/.test(html));
assert.ok(/\.topbar\s*\{[\s\S]*?position:\s*absolute/.test(css));
assert.ok(/\.topbar\s*\{[\s\S]*?top:\s*12px;[\s\S]*?right:\s*48px/.test(css));
assert.ok(/DEFAULT_PREVIEW_INTERVAL_SECONDS\s*=\s*60/.test(script), 'A grid snapshot frissítés fixen 60 másodperc legyen.');
assert.ok(/gridSnapshotQueue:\s*\[\]/.test(script) && /gridSnapshotBusy:\s*false/.test(script), 'A grid snapshotok közös soros queue-t használjanak.');
assert.ok(/function pumpGridSnapshotQueue\(\)/.test(script) && /state\.gridSnapshotBusy = true/.test(script), 'Egyszerre legfeljebb egy snapshot töltődjön.');
assert.ok(/function pumpGridSnapshotQueue\(\)[\s\S]*?state\.activeGridLiveJob\) return;/.test(script), 'A snapshot queue álljon meg, amíg élő kamera fut.');
assert.ok(/GRID_SNAPSHOT_STAGGER_MS\s*=\s*9000/.test(script), 'A friss snapshotok kameránként 9 másodperces fáziseltolással induljanak.');
assert.ok(/GRID_CACHE_WARM_STAGGER_MS\s*=\s*150/.test(script), 'A cache-bemelegítés is sorosan, kis eltéréssel induljon.');
assert.ok(/SNAPSHOT_CACHE_MAX_AGE\s*=\s*'24h'/.test(script) && /SNAPSHOT_REFRESH_CACHE_MAX_AGE\s*=\s*'55s'/.test(script), 'Induláskor cache-elt kép, percenként pedig friss snapshot legyen.');
assert.ok(/function hardStopImage\(image\)/.test(script) && /image\.src = EMPTY_IMAGE_SRC/.test(script), 'Az MJPEG és snapshot kapcsolatok hard-stopot kapjanak.');
assert.strictEqual(/id="preview-interval-seconds"/.test(html), false, 'A percenkénti snapshot frissítés ne legyen külön állítható.');
assert.ok(/FLOATING_MESSAGE_TIMEOUT\s*=\s*5000/.test(script));
assert.ok(/\.camera-grid\s*\{[\s\S]*?height:\s*100%/.test(css));
assert.ok(/\.message:empty\s*\{[\s\S]*?display:\s*none/.test(css));
assert.ok(/id="screen-guard"/.test(html));
assert.ok(/registerScreenSaverRequest/.test(script));
assert.ok(/responseScreenSaverRequest/.test(script));
assert.ok(/ack:\s*false/.test(script));
assert.ok(/camera-feature/.test(script));
assert.ok(/toggleFeaturedCamera/.test(script));
assert.ok(/cellWidth \* 9 \/ 16/.test(script));
assert.ok(/\.camera-feature\.is-featured::after/.test(css));
assert.ok(/\.camera-tile:focus\s*\{[\s\S]*?outline:\s*0;/.test(css), 'A kijelölt kamerán ne legyen fehér szögletes outline.');
assert.ok(/\.camera-tile:focus\s*\{[\s\S]*?border-color:\s*rgba\(117, 216, 255/.test(css), 'A fókusz kapjon finom kékes lekerekített kiemelést.');
assert.ok(/buildUrl\(profile, 'mjpeg'\)/.test(script), 'A kijelölt grid kamera MJPEG-re váltson.');
assert.ok(/GRID_LIVE_FOCUS_DELAY_MS\s*=\s*800/.test(script), 'Gyors navigálás közben ne induljon minden átlépett csempén MJPEG stream.');
assert.ok(/addEventListener\('blur', job\.onBlur\)/.test(script), 'Fókuszvesztéskor álljon le a grid MJPEG stream.');
assert.ok(/GRID_LIVE_RETRY_DELAY_MS\s*=\s*1800/.test(script) && /liveImage\.onerror[\s\S]*?scheduleLivePreview\(0\)/.test(script), 'Transient MJPEG hiba esetén a kijelölt kamera próbálja újra az élő streamet.');
assert.ok(/camera-grid-live-badge/.test(script + css), 'A grid MJPEG kapjon látható LIVE jelzést.');
assert.ok(/camera-grid-live-badge::before[\s\S]*?margin-right:\s*7px/.test(css), 'A LIVE piros pontja ne lógjon bele a feliratba.');
assert.ok(/function directionalTileScore\(from, to, keyCode\)/.test(script) && /getBoundingClientRect\(\)/.test(script), 'A kiemelt 2×2 kamera navigációja vizuális geometriát használjon.');
assert.ok(/FULLSCREEN_HANDOFF_DELAY_MS\s*=\s*160/.test(script), 'Fullscreen előtt legyen rövid decoder-handoff.');
assert.strictEqual(/MJPEG_TIMEOUT/.test(script), false, 'A folyamatos MJPEG-et nem szabad onload alapú 9 mp-es timeouttal megszakítani.');
assert.ok(/▶ Videó/.test(script) && !/Valódi videó/.test(script), 'A módváltó felirata egyszerűen Videó legyen.');
assert.ok(/status\.textContent = ''/.test(script), 'Ne maradjon régi élő/kapcsolódás státusz a LIVE badge alatt.');
assert.ok(/right:\s*9px;[\s\S]*?bottom:\s*9px/.test(css), 'A LIVE jelzés a kamera jobb alsó sarkában legyen.');
assert.ok(/\.camera-tile\.is-live \.tile-state\{display:none!important\}/.test(css), 'LIVE közben a régi grid státusz ne takarja a LIVE jelzést.');
assert.strictEqual(/<iframe\b/i.test(html), false, 'A hosted player csak teljes nézetben jöjjön létre.');
assert.ok(/id="viewer-mode"/.test(html), 'A teljes nézetben legyen MJPEG/WebRTC váltó.');
assert.ok(script.includes(core.FULLSCREEN_TRANSPORT_KEY), 'A teljes nézet transport választása perzisztens legyen.');
assert.strictEqual((script.match(/createElement\('iframe'\)/g) || []).length, 1);
assert.strictEqual(/(^|[;{\s])gap\s*:/m.test(css), false, 'Chrome 79 miatt flex-gapre és rövid gap propertyre nem támaszkodunk.');
assert.ok(/minmax\(0, 1fr\)/.test(css));
assert.ok(/input,[\s\S]*select[\s\S]*width: 100%/.test(css));
assert.strictEqual(/<script(?![^>]*\bsrc=)/i.test(hostedPlayer), false, 'A gateway CSP miatt inline script nem lehet.');
assert.ok(/<script src="\/webos-player\.js"><\/script>/.test(hostedPlayer));
assert.strictEqual(/eval\s*\(|new Function\s*\(/.test(script + hostedPlayerScript), false);
assert.ok(/event\.origin !== expectedOrigin/.test(script));
assert.ok(/event\.source !== iframe\.contentWindow/.test(script));
assert.ok(/removeEventListener\('message'/.test(script));
assert.ok(/iframe\.removeAttribute\('src'\)|job\.node\.removeAttribute\('src'\)/.test(script));
assert.ok(/new WebSocket\(wsScheme \+ window\.location\.host \+ '\/api\/ws\?src='/.test(hostedPlayerScript));
assert.ok(/pc\.ontrack = attachTrack/.test(hostedPlayerScript));
assert.ok(/video\.srcObject = remoteStream/.test(hostedPlayerScript));
assert.strictEqual(/api\.origin|origin\s*:\s*['"]\*['"]/.test(script + hostedPlayerScript), false);
assert.ok(/document\.addEventListener\('webOSRelaunch'/.test(script));
assert.ok(/addEventListener\('pagehide'/.test(script));
assert.ok(/seenRequestIds/.test(script));
assert.ok(/viewerClosesApp/.test(script));
assert.ok(/openViewer\(profile, true\)/.test(script));
assert.ok(/closeViewer\(true\)/.test(script));
assert.ok(/html,[\s\S]*body\s*\{[\s\S]*background:\s*transparent/.test(css));

console.log('camera-viewer focused MJPEG stability tests: PASS');
