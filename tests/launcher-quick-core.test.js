'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const core = require('../apps/launcher/launcher-quick-core');

const data = {
  config: {
    rows: [
      { id: 'utilities', title: 'Eszközök', visible: true, items: [
        { id: 'live-tv', type: 'app', targetId: 'com.webos.app.livetv', label: 'Élő TV', visible: true },
        { id: 'settings', type: 'settings', targetId: '', label: 'Beállítások', visible: true }
      ] },
      { id: 'favorites', title: 'Kedvencek', visible: true, items: [
        { id: 'fav-plex', type: 'app', targetId: 'cdp-30', label: 'Plex', visible: true },
        { id: 'fav-link', type: 'link', targetId: 'http://192.168.0.2', label: 'Link', visible: true },
        { id: 'fav-hidden', type: 'app', targetId: 'hidden', label: 'Rejtett', visible: false }
      ] },
      { id: 'cameras', title: 'Kamerák', visible: true, items: [
        { id: 'camera-child', type: 'preset', targetId: 'gyerekszoba', label: 'Gyerekszoba', visible: true }
      ] },
      { id: 'links', title: 'Web', visible: false, items: [] }
    ]
  },
  apps: [
    { id: 'cdp-30', title: 'Plex' },
    { id: 'com.webos.app.hdmi2', title: 'HDMI 2' },
    { id: 'com.webos.app.livetv', title: 'Live TV' },
    { id: 'com.webos.app.browser', title: 'Böngésző' }
  ],
  presets: [
    { id: 'gyerekszoba', kind: 'image', content: 'http://192.168.0.150/camera.mjpeg' }
  ]
};

const categories = core.buildCategories(data);
assert.deepStrictEqual(categories.map(category => category.id), ['utilities', 'favorites', 'cameras'],
  'Quick categories exactly follow visible full-launcher row order');
assert.deepStrictEqual(categories.map(category => category.label), ['Eszközök', 'Kedvencek', 'Kamerák']);
assert.deepStrictEqual(categories.map(category => category.iconKey), ['settings', 'favorite', 'camera']);
assert.deepStrictEqual(categories[0].items.map(item => item.id), ['live-tv', 'settings'],
  'Quick options exactly follow the configured full-launcher row');
assert.strictEqual(categories[1].items.length, 2, 'Every visible configured favorite remains available');
assert.strictEqual(categories[1].items[0].targetId, 'cdp-30');
assert.strictEqual(categories[2].items[0].type, 'overlayPreset');
assert.strictEqual(categories[2].items[0].previewPresetId, 'gyerekszoba');
assert.strictEqual(categories[2].items[0].label, 'Gyerekszoba');
assert.strictEqual(Object.prototype.hasOwnProperty.call(categories[2].items[0], 'content'), false,
  'Quick camera tiles must not initialize stream URLs');

let state = core.createState();
state = core.move(state, 'left', categories);
assert.strictEqual(state.categoryIndex, 2, 'Category navigation wraps');
state = core.move(state, 'down', categories);
assert.strictEqual(state.layer, 'items');
assert.strictEqual(core.currentItem(state, categories).targetId, 'gyerekszoba');
state = core.move(state, 'up', categories);
assert.strictEqual(state.layer, 'categories');
state = core.move(state, 'right', categories);
assert.strictEqual(state.categoryIndex, 0);

state = core.move(state, 'down', categories);
state = core.move(state, 'right', categories);
assert.strictEqual(state.itemIndices.utilities, 1, 'Item navigation follows the configured row items');

assert.strictEqual(core.isInputId('com.webos.app.hdmi4'), true);
assert.strictEqual(core.isInputId('com.webos.app.hdmi5'), false);

const launcherDir = path.join(__dirname, '..', 'apps', 'launcher');
const manifest = JSON.parse(fs.readFileSync(path.join(launcherDir, 'appinfo.json'), 'utf8'));
const quickManifest = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'apps', 'launcher-quick', 'appinfo.json'), 'utf8'));
const indexSource = fs.readFileSync(path.join(launcherDir, 'index.html'), 'utf8');
const appSource = fs.readFileSync(path.join(launcherDir, 'app.js'), 'utf8');
const uiSource = fs.readFileSync(path.join(launcherDir, 'launcher-ui.js'), 'utf8');
const serverSource = fs.readFileSync(path.join(__dirname, '..', 'remote-control', 'server.py'), 'utf8');
const pythonBuildSource = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'build-all.py'), 'utf8');
const shellBuildSource = fs.readFileSync(path.join(__dirname, '..', 'scripts', 'build-all.sh'), 'utf8');
assert.strictEqual(manifest.id, 'hu.szabi.launcher');
assert.strictEqual(manifest.transparent, false);
assert.strictEqual(manifest.defaultWindowType, 'card');
assert.strictEqual(quickManifest.id, 'hu.szabi.launcher.quick');
assert.strictEqual(quickManifest.version, manifest.version);
assert.strictEqual(quickManifest.transparent, true);
assert.strictEqual(quickManifest.defaultWindowType, 'popup');
assert.strictEqual(manifest.noSplashOnLaunch, false);
assert.strictEqual(quickManifest.noSplashOnLaunch, true);
assert.ok(indexSource.includes('launcher-quick-core.js'));
assert.ok(appSource.includes("launcherHost === 'quick' ? 'overlay' : 'full'"), 'Unparameterized launches remain full');
assert.ok(appSource.includes("{ v: 1, action: 'show', presetId: overlayPreset.id }"), 'Camera tiles reuse Media Overlay presets');
assert.ok(uiSource.includes("code === 461") && uiSource.includes('closeQuick()'), 'Back closes the quick overlay');
assert.ok(uiSource.includes("event.target === root") && uiSource.includes('closeQuick: closeQuick'), 'Transparent backdrop closes the quick overlay');
assert.ok(appSource.includes("nextLaunch.source === 'home-short-toggle'") && appSource.includes('controller.isQuickOpen()') && appSource.includes('controller.closeQuick()'), 'Only an explicit short-Home toggle closes a visibly open quick overlay');
assert.ok(appSource.includes('requestId && requestId === lastHomeRequestId'), 'Duplicate warm webOS events share one Home request ID');
assert.ok(uiSource.includes("isQuickOpen: function () { return viewMode === 'overlay' && !quickClosing && !parked; }"), 'A warm but parked popup can reopen');
assert.ok(uiSource.includes('parkLauncher') && uiSource.includes('launcher-parked'), 'Closing hides the launcher immediately before releasing its popup process');
assert.ok(uiSource.includes('then(closeApplicationFallback, closeApplicationFallback)'), 'A completed park request also asks the popup to close itself');
assert.ok(appSource.includes("'/api/launcher/park'") && appSource.includes("'/api/launcher/restart'") && appSource.includes("'/api/launcher/visible'"), 'TV lifecycle actions use the fixed launcher endpoints');
assert.ok(appSource.indexOf('window.PalmSystem.activate()') < appSource.indexOf('window.webOSSystem.activate()'), 'Older TV firmware uses PalmSystem activation first');
assert.ok(appSource.indexOf('window.PalmSystem && window.PalmSystem.launchParams') < appSource.indexOf('window.webOSSystem && window.webOSSystem.launchParams'), 'Cold popup parameters prefer the working PalmSystem bridge');
assert.ok(uiSource.includes('Launcher alkalmazás teljes újraindítása'), 'Full settings expose a real launcher restart');
assert.ok(uiSource.includes('preventScroll: true'), 'Quick focus remains visible without browser auto-scroll races');
assert.ok(uiSource.includes('previousCategoryIndex') && uiSource.includes('else focusQuickState()'), 'Item navigation moves focus without rebuilding the quick DOM');
assert.ok(uiSource.includes("current.id === 'cameras'") && uiSource.includes('schedulePreviews(120)'), 'Quick camera previews start lazily only for the active camera category');
assert.ok(uiSource.includes("item.type === 'allApps'") && uiSource.includes("item.type === 'settings'"), 'Full-launcher utility options remain usable from quick mode');
assert.ok(uiSource.includes("id: 'quick-info'") && uiSource.includes("id: 'quick-weather'") && !uiSource.includes("id: 'quick-clock'"), 'Quick mode appends lazy Info and weather utilities while the clock remains non-navigable');
assert.ok(uiSource.includes('launcher-quick-status-time') && uiSource.includes('launcher-quick-status-date'), 'Quick mode keeps a visible non-navigable clock and full weekday date');
assert.ok(uiSource.includes('favouriteCategory.actionItem = resumeItem') && !uiSource.includes("id: 'quick-resume',"), 'Continue shares the existing Favorites category');
assert.ok(uiSource.includes('quickState.itemIndices[activeCategory.id] = 0'), 'Down from every quick category starts on its first tile');
assert.ok(uiSource.includes('quickFullOverlayReturn = true; renderSettingsSummary()') && !uiSource.includes("quickFullOverlayReturn = true; setViewMode('full')"), 'Quick settings open above the quick surface without rendering the full launcher behind them');
assert.ok(uiSource.includes('WEATHER_CACHE_MS = 60 * 60 * 1000') && uiSource.includes('readWeatherCache(false)'), 'Quick weather uses a one-hour local cache before any request');
assert.ok(uiSource.includes("weatherCategory.items = (entries.length ? entries : [{}]).map") && uiSource.includes("quick-weather-' + quickWeatherView + '-' + index"), 'Every rendered weather card participates in remote navigation');
assert.ok(uiSource.includes("'Szél ' + Math.round") && uiSource.includes('launcher-quick-data-tertiary'), 'Hourly weather places wind on a readable third line');
assert.ok(uiSource.includes("resumeBadge.setAttribute('aria-hidden', 'true')") && !uiSource.includes("text(document.createElement('span'), '↻')"), 'Continue uses the CSS-drawn circular arrow badge');
assert.ok(uiSource.includes('homeLaunchMode') && serverSource.includes('LAUNCHER_HOME_MODE'), 'The three-state Home launch mode is stored and synchronized to the TV key handler');
assert.ok(uiSource.includes("quickDrilldown = { type: 'allApps'") && uiSource.includes("if (quickDrilldown) { quickDrilldown = null"), 'All apps stays inside quick mode and Back returns to its category');
assert.ok(uiSource.includes('launcher-quick-lower') && uiSource.includes('launcher-quick-tabs'), 'Quick categories and tile content have separate presentation surfaces');
assert.ok(uiSource.includes('scheduleFullViewWork') && uiSource.includes("mode === 'tv' ? 120 : 0"), 'Decorative full-view work starts after the interactive frame');
assert.ok(uiSource.includes('hu.szabi.launcher.wallpaper-state.v1') && uiSource.includes('applyRememberedWallpaper()'), 'Full mode restores the last wallpaper before deferred work');
assert.ok(uiSource.includes('selectedAt + intervalMs - Date.now()') && !uiSource.includes('wallpaperIndex ='), 'Wallpaper rotation follows persisted elapsed time instead of render count');
assert.ok(uiSource.includes("preview.setAttribute('data-preview-url'") && uiSource.includes('preview.__launcherRefresh'), 'Quick camera network loading is deferred to the preview scheduler');
assert.ok(pythonBuildSource.includes('"launcher-quick-core.js"'));
assert.ok(pythonBuildSource.includes('"launcher-cache.js"'));
assert.ok(pythonBuildSource.includes('"launcher-host.js"'));
assert.ok(pythonBuildSource.includes('"launcher-quick"') && pythonBuildSource.includes('"hu.szabi.launcher.quick"'));
assert.ok(shellBuildSource.includes('build-all.py'), 'The shell entry point delegates to the canonical deterministic builder');
console.log('launcher quick core tests passed');
