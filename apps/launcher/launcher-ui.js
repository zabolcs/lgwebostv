(function (global) {
  'use strict';

  function deepCopy(value) { return JSON.parse(JSON.stringify(value)); }
  function text(node, value) { node.textContent = String(value == null ? '' : value); return node; }
  function initial(label) { return String(label || '?').trim().charAt(0).toLocaleUpperCase() || '?'; }
  function cacheBust(url) { return url + (url.indexOf('?') < 0 ? '?' : '&') + '_launcher=' + Date.now(); }
  function wallpaperKey(value) {
    try {
      var parsed = new URL(String(value || ''));
      return parsed.protocol + '//' + parsed.host + parsed.pathname;
    } catch (ignore) { return String(value || '').split(/[?#]/)[0]; }
  }
  function optimizedWallpaperUrl(value) {
    var source = String(value || '');
    try {
      var parsed = new URL(source);
      var base = parsed.protocol + '//' + parsed.host + parsed.pathname;
      if (parsed.hostname === 'images.pexels.com') return base + '?auto=compress&cs=tinysrgb&w=1600&h=900&fit=crop';
      if (parsed.hostname === 'images.unsplash.com') return base + '?auto=format&fit=crop&w=1600&h=900&q=76';
    } catch (ignore) {}
    return source;
  }
  function localWallpaperUrl(value) {
    var cache = global.LauncherWallpaperCache || {};
    return String(cache[wallpaperKey(value)] || '');
  }
  function directPresetGo2rtc(preset, targetPath) {
    var sources = [
      String(preset && preset.content || ''),
      String(preset && preset.previewUrl || '')
    ];
    for (var index = 0; index < sources.length; index += 1) {
      try {
        var parsed = new URL(sources[index]);
        var host = parsed.hostname;
        var octets = host.split('.').map(function (value) { return Number(value); });
        var privateHost = octets.length === 4 && octets.every(function (value) { return value >= 0 && value <= 255; }) &&
          octets.join('.') === host &&
          (octets[0] === 10 || (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) || (octets[0] === 192 && octets[1] === 168));
        if (!privateHost || host === '192.168.0.100' || octets[3] === 0 || octets[3] === 255) continue;
        if ((parsed.protocol !== 'http:' && parsed.protocol !== 'https:') || parsed.username || parsed.password || parsed.hash) continue;
        if (parsed.port && (Number(parsed.port) < 1 || Number(parsed.port) > 65535)) continue;
        if (!/^\?src=[A-Za-z0-9][A-Za-z0-9._-]{0,47}$/.test(parsed.search)) continue;
        if (parsed.pathname !== '/api/frame.jpeg' && parsed.pathname !== '/api/stream.mjpeg') continue;
        parsed.pathname = targetPath;
        return parsed.protocol + '//' + parsed.host + parsed.pathname + parsed.search;
      } catch (ignore) {}
    }
    return '';
  }
  function directPresetPreview(preset) { return directPresetGo2rtc(preset, '/api/frame.jpeg'); }
  function directPresetMjpeg(preset) { return directPresetGo2rtc(preset, '/api/stream.mjpeg'); }

  function weatherIcon(code) {
    code = Number(code);
    if (code === 0) return '☀';
    if (code <= 3) return '⛅';
    if (code <= 48) return '🌫';
    if (code <= 67) return '🌧';
    if (code <= 77) return '🌨';
    if (code <= 82) return '🌦';
    return '⛈';
  }
  function formatKiB(value) {
    var mib = Number(value || 0) / 1024;
    return mib >= 1024 ? (mib / 1024).toFixed(1) + ' GiB' : Math.round(mib) + ' MiB';
  }
  var ICON_CATALOG = [
    { key: 'youtube', label: 'YouTube' }, { key: 'netflix', label: 'Netflix' },
    { key: 'disney', label: 'Disney+' }, { key: 'prime', label: 'Prime Video' },
    { key: 'plex', label: 'Plex' }, { key: 'spotify', label: 'Spotify' }, { key: 'moonlight', label: 'Moonlight' },
    { key: 'lyrion', label: 'Lyrion Music Server' }, { key: 'immich', label: 'Immich' },
    { key: 'camera', label: 'Camera Viewer' }, { key: 'overlay', label: 'Media Overlay / PiP' },
    { key: 'remote', label: 'Távirányító' }, { key: 'launcher', label: 'Launcher' },
    { key: 'tv', label: 'Élő TV' }, { key: 'hdmi', label: 'HDMI bemenet' }, { key: 'browser', label: 'Böngésző' },
    { key: 'home-assistant', label: 'Home Assistant' }, { key: 'apps', label: 'Összes app' },
    { key: 'settings', label: 'Beállítások' }, { key: 'info', label: 'Információ' },
    { key: 'weather', label: 'Időjárás' }, { key: 'clock', label: 'Óra' }, { key: 'web', label: 'Weboldal' }
  ];
  var ICON_BODIES = {
    favorite: '<path d="M256 55l61 124 137 20-99 96 23 136-122-64-122 64 23-136-99-96 137-20z" fill="#8ee7ff"/><path d="M256 104l43 88 97 14-70 68 17 96-87-45z" fill="#fff" opacity=".92"/>',
    resume: '<path d="M405 162A181 181 0 1 0 432 319" fill="none" stroke="#8ee7ff" stroke-width="42" stroke-linecap="round"/><path d="M401 75v105h-105" fill="none" stroke="#fff" stroke-width="42" stroke-linecap="round" stroke-linejoin="round"/>',
    youtube: '<rect x="52" y="128" width="408" height="256" rx="72" fill="#ff0033"/><path d="M224 190l132 66-132 66z" fill="#fff"/>',
    netflix: '<path d="M145 70h78l144 372h-78z" fill="#e50914"/><path d="M145 70h78v372h-78zM289 70h78v372h-78z" fill="#b20710"/>',
    disney: '<path d="M74 162c82-102 264-118 364-32" fill="none" stroke="#78d7ff" stroke-width="18" stroke-linecap="round"/><text x="256" y="326" text-anchor="middle" fill="#fff" font-family="Arial,sans-serif" font-size="118" font-style="italic" font-weight="700">Disney+</text>',
    prime: '<text x="256" y="248" text-anchor="middle" fill="#fff" font-family="Arial,sans-serif" font-size="120" font-weight="700">prime</text><path d="M125 314c82 62 184 65 272 3" fill="none" stroke="#39a9ff" stroke-width="22" stroke-linecap="round"/><path d="M368 299l45 5-25 38" fill="none" stroke="#39a9ff" stroke-width="18" stroke-linecap="round" stroke-linejoin="round"/>',
    plex: '<path d="M192 80h92l132 176-132 176h-92l132-176z" fill="#e5a00d"/>',
    spotify: '<circle cx="256" cy="256" r="202" fill="#1ed760"/><path d="M138 205c90-27 196-19 273 25M151 272c78-20 169-13 238 21M166 334c63-14 133-9 192 17" fill="none" stroke="#07150c" stroke-width="26" stroke-linecap="round"/>',
    moonlight: '<path d="M330 62c-89 26-142 117-116 206 25 88 117 140 205 114-45 72-136 107-220 76C91 418 36 298 76 190 113 89 222 33 330 62z" fill="#79ddff"/><path d="M178 294c18-38 47-57 86-57h44c39 0 68 19 86 57l31 69c13 28-16 56-43 41l-56-31H246l-56 31c-27 15-56-13-43-41z" fill="#fff"/><path d="M215 292v58M186 321h58" stroke="#17364a" stroke-width="18" stroke-linecap="round"/><circle cx="344" cy="305" r="11" fill="#17364a"/><circle cx="372" cy="335" r="11" fill="#17364a"/>',
    lyrion: '<rect x="38" y="38" width="436" height="436" rx="104" fill="#172722"/><g fill="#85d49a"><rect x="105" y="221" width="36" height="70" rx="18"/><rect x="164" y="172" width="36" height="168" rx="18"/><rect x="223" y="111" width="36" height="290" rx="18"/><rect x="282" y="151" width="36" height="210" rx="18"/><rect x="341" y="196" width="36" height="120" rx="18"/><rect x="400" y="229" width="36" height="54" rx="18"/></g>',
    immich: '<g transform="translate(58 58) scale(.5)"><path d="M375.48 267.63c38.64 34.21 69.78 70.87 89.82 105.42 34.42-61.56 57.42-134.71 57.71-181.3 0-68.94-68.77-95.77-128.01-95.77s-128.01 26.83-128.01 95.77c0 .94 0 2.2 0 3.72 33.02 14.67 72.16 40.9 108.49 73.06z" fill="#fa2921"/><path d="M164.7 455.63c24.15-26.87 61.2-55.99 103.01-80.61 44.48-26.18 88.97-44.47 128.02-52.84-47.91-51.76-110.37-96.24-154.6-110.91-65.57-21.3-112.34 35.81-130.64 92.15s-14.04 130.04 51.53 151.34c.89.29 1.69.55 2.68.87z" fill="#ed79b5"/><path d="M681.07 302.19c-18.3-56.34-65.07-113.45-130.64-92.15-.9.29-2.1.68-3.54 1.15-3.75 35.93-16.6 81.27-35.96 125.76-20.59 47.32-45.84 88.27-72.51 118 69.18 13.72 145.86 12.98 190.26-1.14 65.57-21.3 69.83-95 52.39-151.62z" fill="#ffb400"/><path d="M336.54 510.71c-11.15-50.39-14.8-98.36-10.7-138.08-64.03 29.57-125.63 75.23-153.26 112.76-40.52 55.78-.66 117.91 47.27 152.72 47.92 34.82 119.33 53.54 159.86-2.24.56-.76 1.1-1.51 1.66-2.28-18.09-31.27-34.35-75.51-44.83-122.88z" fill="#1e83f7"/><path d="M617.57 482.52c-35.33 7.54-82.42 9.33-130.72 4.66-51.37-4.96-98.11-16.32-134.63-32.5 8.33 70.03 32.73 142.73 59.88 180.6 40.52 55.78 111.93 37.06 159.86 2.24 47.92-34.82 87.79-96.95 47.27-152.72-.56-.76-1.1-1.51-1.66-2.28z" fill="#18c249"/></g>',
    camera: '<path d="M105 170h82l32-47h74l32 47h82c27 0 49 22 49 49v174c0 27-22 49-49 49H105c-27 0-49-22-49-49V219c0-27 22-49 49-49z" fill="none" stroke="#79ddff" stroke-width="28"/><circle cx="256" cy="300" r="82" fill="none" stroke="#fff" stroke-width="28"/>',
    overlay: '<rect x="60" y="88" width="392" height="294" rx="34" fill="none" stroke="#fff" stroke-width="24"/><rect x="252" y="235" width="174" height="122" rx="22" fill="#69dcff"/><path d="M105 424h302" stroke="#69dcff" stroke-width="24" stroke-linecap="round"/>',
    remote: '<rect x="164" y="34" width="184" height="444" rx="86" fill="none" stroke="#fff" stroke-width="22"/><circle cx="256" cy="147" r="54" fill="none" stroke="#70d9ff" stroke-width="20"/><circle cx="256" cy="147" r="18" fill="#70d9ff"/><path d="M215 263h82M256 222v82" stroke="#fff" stroke-width="22" stroke-linecap="round"/><circle cx="218" cy="363" r="15" fill="#ff4a5d"/><circle cx="256" cy="363" r="15" fill="#51df79"/><circle cx="294" cy="363" r="15" fill="#ffd84d"/>',
    launcher: '<rect x="66" y="72" width="174" height="152" rx="28" fill="#79ddff"/><rect x="272" y="72" width="174" height="152" rx="28" fill="#fff"/><rect x="66" y="256" width="174" height="184" rx="28" fill="#fff"/><rect x="272" y="256" width="174" height="184" rx="28" fill="#79ddff"/>',
    tv: '<rect x="52" y="98" width="408" height="286" rx="34" fill="none" stroke="#fff" stroke-width="26"/><path d="M181 437h150M256 384v53" stroke="#76dcff" stroke-width="26" stroke-linecap="round"/><path d="M223 184l108 57-108 57z" fill="#76dcff"/>',
    hdmi: '<rect x="72" y="96" width="368" height="320" rx="44" fill="none" stroke="#fff" stroke-width="25"/><path d="M151 205h210l-28 111H179z" fill="none" stroke="#73dcff" stroke-width="22" stroke-linejoin="round"/><path d="M196 205v-33h120v33M221 316v35M256 316v35M291 316v35" fill="none" stroke="#fff" stroke-width="17" stroke-linecap="round"/><text x="256" y="390" text-anchor="middle" fill="#73dcff" font-family="Arial,sans-serif" font-size="48" font-weight="700">HDMI</text>',
    browser: '<circle cx="256" cy="256" r="202" fill="none" stroke="#fff" stroke-width="24"/><path d="M54 256h404M256 54c70 65 70 339 0 404M256 54c-70 65-70 339 0 404M92 156h328M92 356h328" fill="none" stroke="#73dbff" stroke-width="18"/>',
    'home-assistant': '<path d="M58 238L256 62l198 176v210H306V321H206v127H58z" fill="none" stroke="#55d6ff" stroke-width="27" stroke-linejoin="round"/><circle cx="256" cy="242" r="24" fill="#fff"/><circle cx="173" cy="312" r="19" fill="#fff"/><circle cx="339" cy="312" r="19" fill="#fff"/><path d="M256 266v55M237 252l-49 48M275 252l49 48" stroke="#fff" stroke-width="17"/>',
    apps: '<g fill="#fff"><rect x="74" y="74" width="102" height="102" rx="24"/><rect x="205" y="74" width="102" height="102" rx="24"/><rect x="336" y="74" width="102" height="102" rx="24"/><rect x="74" y="205" width="102" height="102" rx="24"/><rect x="205" y="205" width="102" height="102" rx="24" fill="#72dcff"/><rect x="336" y="205" width="102" height="102" rx="24"/><rect x="74" y="336" width="102" height="102" rx="24"/><rect x="205" y="336" width="102" height="102" rx="24"/><rect x="336" y="336" width="102" height="102" rx="24"/></g>',
    settings: '<circle cx="256" cy="256" r="84" fill="none" stroke="#fff" stroke-width="30"/><circle cx="256" cy="256" r="25" fill="#76dcff"/><path d="M256 51v63M256 398v63M51 256h63M398 256h63M111 111l45 45M356 356l45 45M401 111l-45 45M156 356l-45 45" stroke="#76dcff" stroke-width="30" stroke-linecap="round"/>',
    info: '<circle cx="256" cy="256" r="200" fill="none" stroke="#76dcff" stroke-width="28"/><circle cx="256" cy="159" r="24" fill="#fff"/><path d="M256 231v150" stroke="#fff" stroke-width="34" stroke-linecap="round"/>',
    weather: '<circle cx="190" cy="190" r="82" fill="#ffd85a"/><g stroke="#ffd85a" stroke-width="22" stroke-linecap="round"><path d="M190 60v36M190 284v36M60 190h36M284 190h36M98 98l26 26M256 256l26 26M282 98l-26 26"/></g><path d="M148 375c-48 0-78-29-78-67 0-37 29-66 66-67 17-54 67-91 125-91 67 0 122 49 130 114 42 5 75 40 75 84 0 47-38 85-85 85H148z" fill="#eaf8ff" stroke="#76dcff" stroke-width="18"/>',
    clock: '<circle cx="256" cy="256" r="198" fill="none" stroke="#76dcff" stroke-width="28"/><path d="M256 130v139l92 55" fill="none" stroke="#fff" stroke-width="32" stroke-linecap="round" stroke-linejoin="round"/><circle cx="256" cy="256" r="20" fill="#76dcff"/>',
    web: '<circle cx="256" cy="256" r="202" fill="none" stroke="#77dcff" stroke-width="26"/><path d="M54 256h404M256 54c86 82 86 322 0 404M256 54c-86 82-86 322 0 404" fill="none" stroke="#fff" stroke-width="22"/>'
  };
  var ICON_DATA_CACHE = {};
  function iconData(key) {
    var body = ICON_BODIES[key];
    if (!body) return '';
    if (!ICON_DATA_CACHE[key]) ICON_DATA_CACHE[key] = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">' + body + '</svg>');
    return ICON_DATA_CACHE[key];
  }
  function suggestedIconKey(item, app) {
    if (item.type === 'allApps') return 'apps';
    if (item.type === 'settings') return 'settings';
    if (item.type === 'link' || item.type === 'preset') return '';
    var value = String((app && app.id) || item.targetId || '') + ' ' + String((app && app.title) || item.label || '');
    value = value.toLocaleLowerCase();
    if (value.indexOf('youtube') >= 0) return 'youtube';
    if (value.indexOf('netflix') >= 0) return 'netflix';
    if (value.indexOf('disney') >= 0) return 'disney';
    if (value.indexOf('prime') >= 0 || value.indexOf('amazon') >= 0) return 'prime';
    if (value.indexOf('plex') >= 0) return 'plex';
    if (value.indexOf('spotify') >= 0) return 'spotify';
    if (value.indexOf('moonlight') >= 0) return 'moonlight';
    if (value.indexOf('lyrion') >= 0 || value.indexOf('squeezebox') >= 0 || value.indexOf('slimserver') >= 0) return 'lyrion';
    if (value.indexOf('immich') >= 0) return 'immich';
    if (value.indexOf('cameraviewer') >= 0 || value.indexOf('kamera') >= 0) return 'camera';
    if (value.indexOf('mediaoverlay') >= 0 || value.indexOf('overlay') >= 0 || value.indexOf('pip') >= 0) return 'overlay';
    if (value.indexOf('remotemapper') >= 0 || value.indexOf('távirányító') >= 0) return 'remote';
    if (value.indexOf('hu.szabi.launcher') >= 0) return 'launcher';
    if (value.indexOf('com.webos.app.hdmi') >= 0 || value.indexOf('hdmi') >= 0) return 'hdmi';
    if (value.indexOf('livetv') >= 0 || value.indexOf('élő tv') >= 0) return 'tv';
    if (value.indexOf('browser') >= 0 || value.indexOf('böngésző') >= 0) return 'browser';
    if (value.indexOf('home assistant') >= 0 || value.indexOf('homeassistant') >= 0) return 'home-assistant';
    return '';
  }

  function init(root, options) {
    options = options || {};
    var QuickCore = global.LauncherQuickCore;
    var apiBase = String(options.apiBase || '').replace(/\/$/, '');
    var mode = options.mode === 'admin' ? 'admin' : 'tv';
    var viewMode = options.viewMode === 'overlay' ? 'overlay' : 'full';
    var data = null;
    var wallpaperTimer = null;
    var previewTimer = null;
    var previewJobs = [];
    var previewFocusTimer = null;
    var activeLivePreview = null;
    var fullWorkTimer = null;
    var clockTimer = null;
    var toastTimer = null;
    var previousFocus = null;
    var okHoldTimer = null;
    var okHeld = false;
    var backPressed = false;
    var backHeld = false;
    var resumeLoadingGeneration = 0;
    var resumeLoadingFailsafeTimer = null;
    var editingTileId = '';
    var editMode = null;
    var appPickerActive = false;
    var weatherData = null;
    var quickCategories = [];
    var quickState = QuickCore ? QuickCore.createState() : null;
    var quickDrilldown = null;
    var quickWeatherView = 'hourly';
    var quickWeatherTabFocused = false;
    var quickDiagnosticsCache = null;
    var quickSpecialLoadToken = 0;
    var quickFullOverlayReturn = false;
    var quickNeedsRender = true;
    var settingsPage = 'Indítás és Home';
    var quickClosing = false;
    var parked = options.initiallyParked === true;
    var parkRequested = false;
    var BOOT_PREFS_KEY = 'hu.szabi.launcher.boot-prefs.v1';
    var WALLPAPER_STATE_KEY = 'hu.szabi.launcher.wallpaper-state.v1';
    var WEATHER_CACHE_KEY = 'hu.szabi.launcher.weather-cache.v1';
    var WEATHER_CACHE_MS = 60 * 60 * 1000;
    var cachedBootPrefs = {};
    try { cachedBootPrefs = JSON.parse(global.localStorage.getItem(BOOT_PREFS_KEY) || '{}') || {}; } catch (ignore) {}
    var bootOverlayEnabled = cachedBootPrefs.enabled !== false;
    var bootMaxMs = Math.max(1000, Math.min(5000, Number(cachedBootPrefs.maxSeconds || 2) * 1000));
    var bootActive = mode === 'tv' && viewMode === 'full' && bootOverlayEnabled;
    var bootPending = 0;
    var bootRenderReady = false;
    var bootWallpaperReady = false;
    var bootTimer = null;
    var bootPaintQueued = false;
    var wallpaperActiveKey = '';
    var wallpaperLoadToken = 0;
    var wallpaperState = readWallpaperState();
    var lastClockDate = '';

    if (parked) {
      document.body.classList.add('launcher-parked');
      root.setAttribute('aria-hidden', 'true');
    }

    function protectedItem(item) {
      return !!item && (item.type === 'allApps' || item.type === 'settings' || String(item.id || '').indexOf('utility-com-webos-app-') === 0);
    }
    function bootCheck(forced) {
      if (!bootActive || !bootRenderReady || !bootWallpaperReady) return;
      bootActive = false;
      if (bootTimer) global.clearTimeout(bootTimer);
      var cover = document.getElementById('launcher-boot');
      if (cover) {
        if (forced || (data && data.config.settings.animationsEnabled === false)) cover.hidden = true;
        else { cover.classList.add('ready'); global.setTimeout(function () { cover.hidden = true; }, 180); }
      }
    }
    function setBootCoverState(active, resumeMode) {
      var cover = document.getElementById('launcher-boot');
      if (!cover) return;
      cover.hidden = !active;
      cover.classList.toggle('resume-loading', !!resumeMode);
      cover.classList.remove('ready');
      if (active) {
        cover.setAttribute('aria-hidden', 'false');
        document.body.classList.add('launcher-loading-active');
      } else {
        cover.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('launcher-loading-active');
      }
    }

    function forceHideLoadingCover() {
      if (resumeLoadingFailsafeTimer) {
        global.clearTimeout(resumeLoadingFailsafeTimer);
        resumeLoadingFailsafeTimer = null;
      }
      resumeLoadingGeneration += 1;
      setBootCoverState(false, false);
      var cover = document.getElementById('launcher-boot');
      if (cover) {
        cover.classList.remove('resume-loading', 'ready');
        cover.hidden = true;
        cover.setAttribute('aria-hidden', 'true');
      }
      document.body.classList.remove('launcher-loading-active');
    }
    function finishResumeLoading(generation, minimumMs, startedAt) {
      function finishFrame() {
        if (generation !== resumeLoadingGeneration) return;
        var elapsed = Date.now() - startedAt;
        var remaining = Math.max(0, minimumMs - elapsed);
        global.setTimeout(function () {
          if (generation !== resumeLoadingGeneration) return;
          var cover = document.getElementById('launcher-boot');
          document.body.classList.remove('launcher-loading-active');
          if (!cover) return;
          cover.classList.add('ready');
          global.setTimeout(function () {
            if (generation !== resumeLoadingGeneration) return;
            cover.hidden = true;
            cover.classList.remove('resume-loading', 'ready');
            cover.setAttribute('aria-hidden', 'true');
          }, 220);
        }, remaining);
      }
      if (typeof global.requestAnimationFrame === 'function') {
        global.requestAnimationFrame(function () { global.requestAnimationFrame(finishFrame); });
      } else global.setTimeout(finishFrame, 100);
    }
    function beginResumeLoading(minimumMs) {
      if (mode !== 'tv' || viewMode !== 'full') return;
      var generation = ++resumeLoadingGeneration;
      var startedAt = Date.now();
      setBootCoverState(true, true);
      if (resumeLoadingFailsafeTimer) global.clearTimeout(resumeLoadingFailsafeTimer);
      resumeLoadingFailsafeTimer = global.setTimeout(function () {
        if (generation !== resumeLoadingGeneration) return;
        forceHideLoadingCover();
      }, 5000);
      // A stalled renderer naturally delays this callback. That makes the
      // cover remain visible for the period in which input would not respond.
      global.setTimeout(function () {
        if (generation !== resumeLoadingGeneration) return;
        finishResumeLoading(generation, Math.max(700, Number(minimumMs || 1600)), startedAt);
      }, 0);
    }
    function cancelResumeLoading() {
      forceHideLoadingCover();
    }

    function bootTrack(image) {
      // Network images must never keep the launcher input-blocked.  Fallbacks
      // appear later if needed, while the UI becomes usable after first paint.
      return function () {};
    }
    function bootAfterFirstPaint() {
      if (!bootActive || bootPaintQueued) return;
      bootPaintQueued = true;
      function finish() {
        bootPaintQueued = false;
        bootPending = 0; bootWallpaperReady = true; bootCheck();
      }
      if (typeof global.requestAnimationFrame === 'function') {
        global.requestAnimationFrame(function () { global.requestAnimationFrame(finish); });
      } else global.setTimeout(finish, 80);
    }
    function bootFailsafe() {
      if (!bootActive || bootTimer) return;
      bootTimer = global.setTimeout(function () {
        bootPending = 0; bootWallpaperReady = true; bootRenderReady = true; bootCheck(true);
      }, bootMaxMs);
    }
    function applyBootPreferences(settings) {
      if (!settings) return;
      try { global.localStorage.setItem(BOOT_PREFS_KEY, JSON.stringify({ enabled: settings.bootOverlayEnabled !== false, maxSeconds: Number(settings.bootOverlayMaxSeconds || 2) })); } catch (ignore) {}
      if (settings.bootOverlayEnabled === false && bootActive) {
        bootPending = 0; bootWallpaperReady = true; bootRenderReady = true; bootCheck(true);
      }
    }

    function readWallpaperState() {
      try {
        var value = JSON.parse(global.localStorage.getItem(WALLPAPER_STATE_KEY) || 'null');
        if (!value || value.version !== 1 || !isFinite(Number(value.index)) ||
            !isFinite(Number(value.selectedAt)) || typeof value.key !== 'string') return null;
        return {
          version: 1,
          index: Math.max(0, Math.floor(Number(value.index))),
          key: value.key,
          selectedAt: Math.max(0, Number(value.selectedAt)),
          displayUrl: typeof value.displayUrl === 'string' ? value.displayUrl.slice(0, 4096) : ''
        };
      } catch (ignore) { return null; }
    }
    function matchingWallpaperState(settings) {
      if (!wallpaperState || !settings || !settings.wallpaperUrls || wallpaperState.index >= settings.wallpaperUrls.length) return null;
      var originalUrl = settings.wallpaperUrls[wallpaperState.index];
      var key = wallpaperState.index + '|' + wallpaperKey(originalUrl);
      return key === wallpaperState.key ? wallpaperState : null;
    }
    function rememberWallpaper(index, originalUrl, selectedAt, displayUrl) {
      var key = index + '|' + wallpaperKey(originalUrl);
      wallpaperState = {
        version: 1,
        index: index,
        key: key,
        selectedAt: selectedAt,
        // Never duplicate a potentially large data URL already held by the
        // dedicated local wallpaper cache.
        displayUrl: /^(data|blob):/.test(String(displayUrl || '')) ? '' : String(displayUrl || '').slice(0, 4096)
      };
      try { global.localStorage.setItem(WALLPAPER_STATE_KEY, JSON.stringify(wallpaperState)); } catch (ignore) {}
      return wallpaperState;
    }
    function rememberedWallpaperSource(settings, state) {
      if (!state) return '';
      var originalUrl = settings.wallpaperUrls[state.index];
      return localWallpaperUrl(originalUrl) || state.displayUrl || optimizedWallpaperUrl(originalUrl);
    }
    function applyRememberedWallpaper() {
      if (!data || !data.config || !data.config.settings) return;
      var settings = data.config.settings;
      var wallpaper = root.querySelector('.launcher-wallpaper');
      var state = matchingWallpaperState(settings);
      if (!wallpaper || !settings.wallpaperEnabled || !settings.wallpaperUrls.length || !state) return;
      // Initial restore is asynchronous; a broken or stale image never clears
      // the visible background. The scheduled loader supplies network fallback.
      var cache = global.LauncherImageCache;
      if (!cache) return;
      var token = wallpaperLoadToken;
      cache.getUrl('wallpaper:' + state.key, { source: optimizedWallpaperUrl(settings.wallpaperUrls[state.index]), allowStale: true }).then(function (url) {
        if (!url || token !== wallpaperLoadToken) return;
        var image = new Image();
        image.onload = function () {
          if (token !== wallpaperLoadToken) return;
          wallpaper.style.backgroundImage = 'url(' + JSON.stringify(url) + ')';
          wallpaperActiveKey = state.key;
        };
        image.onerror = function () { cache.remove('wallpaper:' + state.key); };
        image.src = url;
      });
    }
    function readWeatherCache(allowStale) {
      try {
        var cached = JSON.parse(global.localStorage.getItem(WEATHER_CACHE_KEY) || 'null');
        if (!cached || cached.version !== 1 || !cached.result || !cached.result.weather || !isFinite(Number(cached.savedAt))) return null;
        if (!allowStale && Date.now() - Number(cached.savedAt) > WEATHER_CACHE_MS) return null;
        return cached;
      } catch (ignore) { return null; }
    }
    function rememberWeather(result) {
      if (!result || !result.weather) return;
      weatherData = result.weather;
      try {
        global.localStorage.setItem(WEATHER_CACHE_KEY, JSON.stringify({ version: 1, savedAt: Date.now(), result: result }));
      } catch (ignore) {}
    }
    function requestWeatherCached() {
      var cached = readWeatherCache(false);
      if (cached) { weatherData = cached.result.weather; return Promise.resolve(cached.result); }
      return request('/api/launcher/weather', 'GET').then(function (result) {
        if (result.enabled && result.weather) rememberWeather(result);
        return result;
      }, function (error) {
        var stale = readWeatherCache(true);
        if (stale) { weatherData = stale.result.weather; return stale.result; }
        throw error;
      });
    }

    function request(path, method, body) {
      if (typeof options.request === 'function') return Promise.resolve().then(function () { return options.request(path, method || 'GET', body); });
      var cross = !!apiBase;
      var requestOptions = { method: method || 'GET', cache: 'no-store' };
      if (body !== undefined) {
        requestOptions.headers = { 'Content-Type': cross ? 'text/plain;charset=UTF-8' : 'application/json' };
        requestOptions.body = JSON.stringify(body);
      }
      return global.fetch(apiBase + path, requestOptions).then(function (response) {
        return response.json().then(function (json) {
          if (!response.ok || !json.ok) throw new Error(json.error || 'A kérés sikertelen.');
          return json;
        });
      });
    }
    function toast(message, error) {
      var node = root.querySelector('.launcher-toast');
      if (!node) return;
      node.textContent = message || '';
      node.classList.toggle('error', !!error);
      node.hidden = !message;
      if (toastTimer) global.clearTimeout(toastTimer);
      if (message) toastTimer = global.setTimeout(function () { node.hidden = true; }, 5000);
    }
    function closeOverlays() {
      var returnToQuick = quickFullOverlayReturn;
      quickFullOverlayReturn = false;
      Array.prototype.forEach.call(root.querySelectorAll('.launcher-overlay'), function (overlay) { overlay.hidden = true; });
      if (returnToQuick) {
        previousFocus = null;
        if (viewMode !== 'overlay') setViewMode('overlay'); else renderQuick();
        return;
      }
      if (previousFocus && document.documentElement.contains(previousFocus)) previousFocus.focus();
      previousFocus = null;
    }
    function openOverlay(id) {
      previousFocus = document.activeElement;
      Array.prototype.forEach.call(root.querySelectorAll('.launcher-overlay'), function (overlay) { overlay.hidden = true; });
      var overlay = root.querySelector('#' + id);
      if (overlay) { overlay.hidden = false; var focusable = overlay.querySelector('.launcher-settings-nav [aria-selected="true"]') || overlay.querySelector('button,input'); if (focusable) focusable.focus(); }
    }
    function handleSettingsKey(event) {
      var overlay = root.querySelector('#launcher-settings');
      if (!overlay || overlay.hidden) return false;
      var code = event.keyCode, active = document.activeElement;
      var nav = overlay.querySelector('.launcher-settings-nav');
      if (!nav) return false;
      var onNav = nav.contains(active);
      var selected = nav.querySelector('[aria-selected="true"]');
      var panel = overlay.querySelector('.launcher-settings-section:not([hidden])');
      var editing = active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA');
      if (editing && (code === 37 || code === 39 || code === 13)) return true;
      if ([8,13,27,37,38,39,40,461].indexOf(code) < 0) return false;
      event.preventDefault(); event.stopPropagation();
      if (code === 461 || code === 27 || code === 8) {
        if (onNav || active === overlay.querySelector('.launcher-close')) closeOverlays();
        else focusNode(selected);
        return true;
      }
      if (code === 13) { if (!event.repeat && active && active.click) active.click(); return true; }
      if ((code === 37 || code === 39) && active && active.__launcherChangeChoice) {
        active.__launcherChangeChoice(code === 37 ? -1 : 1); return true;
      }
      if (code === 37) { focusNode(selected); return true; }
      if (code === 39) { if (onNav && panel) focusNode(visibleFocusables(panel)[0]); return true; }
      var controls = visibleFocusables(onNav ? nav : (panel || overlay));
      var index = controls.indexOf(active);
      var next = controls[index + (code === 38 ? -1 : 1)];
      if (next) focusNode(next);
      else if (!onNav && code === 38) focusNode(selected);
      return true;
    }
    function visibleFocusables(scope) {
      return Array.prototype.filter.call(scope.querySelectorAll('button,input,select,textarea'), function (node) {
        if (node.disabled || node.hidden) return false;
        var rectangle = node.getBoundingClientRect();
        return rectangle.width > 0 && rectangle.height > 0;
      });
    }
    function hasUsableFocus() {
      var node = document.activeElement;
      return !!node && node !== root && root.contains(node) && !node.disabled &&
        !(node.closest && node.closest('[hidden]'));
    }
    function activeScope() {
      var visibleOverlay = Array.prototype.filter.call(root.querySelectorAll('.launcher-overlay'), function (overlay) { return !overlay.hidden; })[0];
      return visibleOverlay || root;
    }
    function pageSizeForRow(rowId) {
      return rowId === 'favorites' || rowId === 'cameras' ? 5 : (rowId === 'apps' ? 7 : 8);
    }
    function stripInset(strip) {
      var fallback = mode === 'tv' ? 22 : 0;
      if (global.getComputedStyle) {
        var value = parseFloat(global.getComputedStyle(strip).paddingLeft) || 0;
        var first = strip.querySelector && strip.querySelector('.launcher-tile');
        if (first) value += parseFloat(global.getComputedStyle(first).marginLeft) || 0;
        if (isFinite(value)) return value;
      }
      return fallback;
    }
    function scrollPageTop() {
      try { global.scrollTo(0, 0); } catch (ignore) {}
      if (document.documentElement) document.documentElement.scrollTop = 0;
      if (document.body) document.body.scrollTop = 0;
    }
    function belongsAtPageTop(node, row) {
      if (node.closest && node.closest('.launcher-top')) return true;
      if (!row) return false;
      // Hidden rows are omitted by renderRows; no layout query is needed.
      var rows = root.querySelectorAll('.launcher-row');
      return rows[0] === row || rows[1] === row;
    }
    function focusNode(node) {
      if (!node) return;
      try { node.focus({ preventScroll: true }); } catch (ignore) { node.focus(); }
      var strip = node.closest && node.closest('.launcher-strip');
      var row = node.closest && node.closest('.launcher-row');
      var pinTop = belongsAtPageTop(node, row);
      if (strip && row) {
        var tiles = Array.prototype.filter.call(strip.children, function (child) { return child.classList.contains('launcher-tile'); });
        var index = tiles.indexOf(node);
        if (pinTop && index === 0) { strip.scrollLeft = 0; scrollPageTop(); return; }
        var rowId = row.getAttribute('data-row');
        var pageSize = pageSizeForRow(rowId);
        var pageStart = Math.floor(Math.max(0, index) / pageSize) * pageSize;
        var stripPadding = stripInset(strip);
        if (!pinTop && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
        if (tiles[pageStart]) {
          var tileRectangle = tiles[pageStart].getBoundingClientRect();
          var stripRectangle = strip.getBoundingClientRect();
          strip.scrollLeft = Math.max(0, strip.scrollLeft + tileRectangle.left - stripRectangle.left - stripPadding);
        }
      } else if (!pinTop && node.scrollIntoView) node.scrollIntoView({ block: 'nearest', inline: 'nearest' });
      if (pinTop) {
        scrollPageTop();
        global.setTimeout(scrollPageTop, 0);
      }
    }
    function visibleRowTiles(row) {
      return visibleFocusables(row).filter(function (node) {
        return node.classList && node.classList.contains('launcher-tile');
      });
    }
    function moveFocus(direction) {
      var scope = activeScope();
      var candidates = visibleFocusables(scope);
      if (!candidates.length) return;
      var current = document.activeElement;
      if (candidates.indexOf(current) < 0) { focusNode(candidates[0]); return; }
      var currentRow = current.closest && current.closest('.launcher-row');
      if (currentRow && (direction === 'up' || direction === 'down')) {
        var rows = Array.prototype.filter.call(scope.querySelectorAll('.launcher-row'), function (row) {
          var rectangle = row.getBoundingClientRect();
          return rectangle.width > 0 && rectangle.height > 0 && visibleRowTiles(row).length > 0;
        });
        var rowIndex = rows.indexOf(currentRow);
        var nextRow = rows[rowIndex + (direction === 'up' ? -1 : 1)];
        if (nextRow) {
          focusNode(visibleRowTiles(nextRow)[0]);
          return;
        }
      }
      var currentStrip = current.closest && current.closest('.launcher-strip');
      if (currentStrip && current.classList.contains('launcher-tile') && (direction === 'left' || direction === 'right')) {
        var stripTiles = visibleRowTiles(currentStrip);
        var tileIndex = stripTiles.indexOf(current);
        var nextTile = stripTiles[tileIndex + (direction === 'left' ? -1 : 1)];
        if (nextTile) focusNode(nextTile);
        return;
      }
      var source = current.getBoundingClientRect();
      var sourceX = source.left + source.width / 2;
      var sourceY = source.top + source.height / 2;
      var best = null;
      var bestScore = Infinity;
      candidates.forEach(function (candidate) {
        if (candidate === current) return;
        var rectangle = candidate.getBoundingClientRect();
        var dx = rectangle.left + rectangle.width / 2 - sourceX;
        var dy = rectangle.top + rectangle.height / 2 - sourceY;
        var primary = direction === 'left' ? -dx : (direction === 'right' ? dx : (direction === 'up' ? -dy : dy));
        if (primary <= 4) return;
        var secondary = direction === 'left' || direction === 'right' ? Math.abs(dy) : Math.abs(dx);
        if ((direction === 'left' || direction === 'right') && secondary > Math.max(source.height, rectangle.height) * 0.75) return;
        var score = primary * 5 + secondary;
        if (score < bestScore) { bestScore = score; best = candidate; }
      });
      if (best) focusNode(best);
    }
    function findConfigItem(itemId, config) {
      var found = null;
      (config || data.config).rows.some(function (row) {
        return row.items.some(function (item) { if (item.id === itemId) { found = item; return true; } return false; });
      });
      return found;
    }
    function findConfigPosition(itemId, config) {
      var result = null;
      (config || data.config).rows.some(function (row) {
        var index = row.items.map(function (item) { return item.id; }).indexOf(itemId);
        if (index >= 0) { result = { row: row, index: index, item: row.items[index] }; return true; }
        return false;
      });
      return result;
    }
    function positionEditToolbar() {
      if (!editMode) return;
      var tile = root.querySelector('[data-item-id="' + editMode.itemId + '"]');
      var toolbar = root.querySelector('.launcher-edit-toolbar');
      if (!tile || !toolbar) return;
      var rectangle = tile.getBoundingClientRect();
      toolbar.hidden = false;
      toolbar.style.left = Math.max(14, rectangle.left + rectangle.width / 2 - toolbar.offsetWidth / 2) + 'px';
      toolbar.style.top = Math.max(14, rectangle.top - toolbar.offsetHeight - 12) + 'px';
      var remove = toolbar.querySelector('[data-edit-action="remove"]');
      var item = findConfigItem(editMode.itemId);
      remove.textContent = protectedItem(item) ? '◉' : '✕';
      remove.title = protectedItem(item) ? 'Elrejtés' : 'Törlés';
    }
    function enterEditMode(button) {
      var itemId = button.getAttribute('data-item-id');
      if (!itemId || !findConfigItem(itemId)) return;
      editMode = { itemId: itemId, original: deepCopy(data.config) };
      root.querySelector('.launcher-shell').classList.add('launcher-edit-mode');
      button.classList.add('launcher-editing');
      positionEditToolbar();
      toast('Szerkesztőmód: ← → mozgatás · ↓ mentés · ↑ műveletek · Vissza mégse');
    }
    function clearEditModeChrome() {
      var toolbar = root.querySelector('.launcher-edit-toolbar');
      if (toolbar) toolbar.hidden = true;
      var shell = root.querySelector('.launcher-shell');
      if (shell) shell.classList.remove('launcher-edit-mode');
      var editingTile = root.querySelector('.launcher-tile.launcher-editing');
      if (editingTile) editingTile.classList.remove('launcher-editing');
    }
    function leaveEditMode(save, message) {
      if (!editMode) return;
      var state = editMode; editMode = null;
      clearEditModeChrome();
      if (!save) { data.config = state.original; render(); toast(message || 'A rendezés visszavonva.'); return; }
      request('/api/launcher/config', 'POST', data.config).then(function (result) {
        data.config = result.config;
        var savedTile = root.querySelector('[data-item-id="' + state.itemId + '"]');
        if (savedTile) { savedTile.classList.remove('launcher-editing'); focusNode(savedTile); }
        else if (state.focusAfter && document.documentElement.contains(state.focusAfter)) focusNode(state.focusAfter);
        toast(message || 'Az új hely elmentve.');
      }, function (error) { data.config = state.original; render(); toast(error.message, true); });
    }
    function moveEditedTile(delta) {
      if (!editMode) return;
      var position = findConfigPosition(editMode.itemId);
      if (!position) return;
      var next = position.index + delta;
      if (next < 0 || next >= position.row.items.length) return;
      var item = position.row.items.splice(position.index, 1)[0]; position.row.items.splice(next, 0, item);
      var tile = root.querySelector('[data-item-id="' + editMode.itemId + '"]');
      var strip = tile && tile.closest ? tile.closest('.launcher-strip') : null;
      if (tile && strip) {
        var tiles = Array.prototype.filter.call(strip.children, function (child) { return child.classList.contains('launcher-tile'); });
        if (delta < 0 && tiles[position.index - 1]) strip.insertBefore(tile, tiles[position.index - 1]);
        if (delta > 0 && tiles[position.index + 1]) strip.insertBefore(tiles[position.index + 1], tile);
        focusNode(tile); positionEditToolbar();
      }
    }
    function removeOrHideEditedTile() {
      if (!editMode) return;
      var position = findConfigPosition(editMode.itemId);
      if (!position) return;
      var tile = root.querySelector('[data-item-id="' + editMode.itemId + '"]');
      var focusAfter = null;
      if (tile) {
        var siblings = Array.prototype.filter.call(tile.parentNode.children, function (child) { return child.classList.contains('launcher-tile') || child.classList.contains('launcher-add-tile'); });
        var tileIndex = siblings.indexOf(tile);
        focusAfter = siblings[tileIndex + 1] || siblings[tileIndex - 1] || null;
        tile.parentNode.removeChild(tile);
      }
      if (protectedItem(position.item)) position.item.visible = false;
      else position.row.items.splice(position.index, 1);
      editMode.focusAfter = focusAfter;
      leaveEditMode(true, protectedItem(position.item) ? 'A rendszer-csempe elrejtve.' : 'A csempe törölve.');
    }
    function addTypeForRow(rowId) {
      return rowId === 'links' ? 'link' : (rowId === 'cameras' ? 'preset' : 'app');
    }
    function fillAddTileTargets(rowId, type) {
      var target = root.querySelector('#launcher-add-tile-target');
      var targetField = root.querySelector('#launcher-add-tile-target-field');
      var appPickerField = root.querySelector('#launcher-add-tile-app-picker-field');
      var urlField = root.querySelector('#launcher-add-tile-url-field');
      target.textContent = '';
      targetField.hidden = type === 'app' || type === 'link' || type === 'allApps' || type === 'settings';
      appPickerField.hidden = type !== 'app';
      urlField.hidden = type !== 'link';
      if (type === 'app') data.apps.forEach(function (app) { var option = document.createElement('option'); option.value = app.id; option.textContent = app.title + ' · ' + app.id; target.appendChild(option); });
      if (type === 'preset') data.presets.forEach(function (preset) { var option = document.createElement('option'); option.value = preset.id; option.textContent = preset.id + ' · ' + preset.kind; target.appendChild(option); });
    }
    function updateAddTileFields() {
      var rowId = root.querySelector('#launcher-add-tile-row').value;
      fillAddTileTargets(rowId, root.querySelector('#launcher-add-tile-type').value);
    }
    function openAddTile(rowId) {
      var row = data.config.rows.filter(function (candidate) { return candidate.id === rowId; })[0];
      if (!row) return;
      var rowSelect = root.querySelector('#launcher-add-tile-row'); rowSelect.textContent = '';
      data.config.rows.forEach(function (candidate) { var option = document.createElement('option'); option.value = candidate.id; option.textContent = candidate.title; rowSelect.appendChild(option); });
      rowSelect.value = rowId;
      var typeSelect = root.querySelector('#launcher-add-tile-type'); typeSelect.textContent = '';
      var types = rowId === 'links' ? [['link', 'Webcím']] : (rowId === 'cameras' ? [['preset', 'Kamera-preset']] : (rowId === 'utilities' ? [['app', 'Alkalmazás'], ['allApps', 'Összes alkalmazás rács'], ['settings', 'Launcher beállítások']] : [['app', 'Alkalmazás']]));
      types.forEach(function (entry) { var option = document.createElement('option'); option.value = entry[0]; option.textContent = entry[1]; typeSelect.appendChild(option); });
      typeSelect.value = addTypeForRow(rowId);
      root.querySelector('#launcher-add-tile-label').value = '';
      root.querySelector('#launcher-add-tile-url').value = '';
      root.querySelector('#launcher-add-tile-app-picked').textContent = 'Nincs kiválasztva';
      updateAddTileFields();
      openOverlay('launcher-add-tile');
      root.querySelector('#launcher-add-tile-label').focus();
    }
    function saveAddTile(event) {
      event.preventDefault();
      var rowId = root.querySelector('#launcher-add-tile-row').value;
      var type = root.querySelector('#launcher-add-tile-type').value;
      var label = root.querySelector('#launcher-add-tile-label').value.trim();
      var target = type === 'link' ? root.querySelector('#launcher-add-tile-url').value.trim() : ((type === 'allApps' || type === 'settings') ? '' : root.querySelector('#launcher-add-tile-target').value);
      if (!label || ((type === 'app' || type === 'preset' || type === 'link') && !target)) { toast('A felirat és a cél kitöltése kötelező.', true); return; }
      var next = deepCopy(data.config); var row = next.rows.filter(function (candidate) { return candidate.id === rowId; })[0];
      if (!row) return;
      var id = 'item-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7);
      row.items.push({ id: id, type: type, targetId: target, label: label, visible: true, fit: type === 'preset' ? 'cover' : 'contain', iconKey: '', iconUrl: '', backgroundColor: '' });
      request('/api/launcher/config', 'POST', next).then(function (result) {
        data.config = result.config; closeOverlays(); render(); global.setTimeout(function () { focusNode(root.querySelector('[data-item-id="' + id + '"]')); }, 0); toast('Az új csempe elmentve.');
      }, function (error) { toast(error.message, true); });
    }
    function openTileSettings(button) {
      var item = findConfigItem(button.getAttribute('data-item-id'));
      if (!item) return;
      editingTileId = item.id;
      text(root.querySelector('.launcher-tile-settings-name'), item.label);
      root.querySelector('#launcher-tile-fit').value = item.fit === 'small' || item.fit === 'cover' ? item.fit : 'contain';
      root.querySelector('#launcher-tile-icon-key').value = item.iconKey || '';
      root.querySelector('#launcher-tile-icon-url').value = item.iconUrl || '';
      root.querySelector('#launcher-tile-background').value = item.backgroundColor || '';
      openOverlay('launcher-tile-settings');
      root.querySelector('#launcher-tile-fit').focus();
    }
    function saveTileSettings(event) {
      event.preventDefault();
      var next = deepCopy(data.config);
      var item = findConfigItem(editingTileId, next);
      if (!item) return;
      item.fit = root.querySelector('#launcher-tile-fit').value;
      item.iconKey = root.querySelector('#launcher-tile-icon-key').value;
      item.iconUrl = root.querySelector('#launcher-tile-icon-url').value.trim();
      if (item.iconUrl) item.iconKey = '';
      item.backgroundColor = root.querySelector('#launcher-tile-background').value.trim();
      request('/api/launcher/config', 'POST', next).then(function (result) {
        var itemId = editingTileId; editMode = null; clearEditModeChrome(); data.config = result.config; closeOverlays(); render();
        global.setTimeout(function () { focusNode(root.querySelector('[data-item-id="' + itemId + '"]')); }, 0);
        toast('A csempe beállításai elmentve.');
      }, function (error) { toast(error.message, true); });
    }
    function installTvNavigation() {
      if (mode !== 'tv') return;
      function loadingCoverActive() {
        var cover = document.getElementById('launcher-boot');
        return !!(cover && !cover.hidden);
      }
      function resetRemotePress() {
        if (okHoldTimer) global.clearTimeout(okHoldTimer);
        okHoldTimer = null; okHeld = false;
        backPressed = false; backHeld = false;
      }
      // Retained cards can receive stale input while their native surface is
      // hidden. Never let those events launch an app or return to the last app.
      document.addEventListener('visibilitychange', resetRemotePress);
      document.addEventListener('webOSRelaunch', resetRemotePress);
      document.addEventListener('keydown', function (event) {
        if (document.hidden || parked) { resetRemotePress(); return; }
        if (loadingCoverActive()) {
          event.preventDefault(); event.stopPropagation();
          resetRemotePress();
          return;
        }
        if (event.repeat && (event.keyCode === 461 || event.keyCode === 27)) {
          event.preventDefault(); event.stopPropagation();
          backHeld = true;
          return;
        }
        if (handleSettingsKey(event)) return;
        if (viewMode === 'overlay') { handleQuickKey(event); return; }
        var code = event.keyCode;
        var active = document.activeElement;
        var tag = active && active.tagName;
        if (editMode) {
          var toolbar = root.querySelector('.launcher-edit-toolbar');
          var onToolbar = toolbar && toolbar.contains(active);
          var editedTile = root.querySelector('[data-item-id="' + editMode.itemId + '"]');
          if (code === 461 || code === 27) { event.preventDefault(); leaveEditMode(false); return; }
          if (code === 37 || code === 39) {
            event.preventDefault();
            if (onToolbar) {
              var tools = Array.prototype.slice.call(toolbar.querySelectorAll('button'));
              focusNode(tools[(tools.indexOf(active) + (code === 37 ? tools.length - 1 : 1)) % tools.length]);
            } else moveEditedTile(code === 37 ? -1 : 1);
            return;
          }
          if (code === 38) { event.preventDefault(); focusNode(toolbar.querySelector('[data-edit-action="edit"]')); return; }
          if (code === 40) { event.preventDefault(); if (onToolbar) focusNode(editedTile); else leaveEditMode(true); return; }
        }
        if (tag === 'SELECT' && (code === 37 || code === 39)) {
          event.preventDefault();
          active.selectedIndex = Math.max(0, Math.min(active.options.length - 1, active.selectedIndex + (code === 37 ? -1 : 1)));
          return;
        }
        if ((tag === 'INPUT' || tag === 'TEXTAREA') && (code === 37 || code === 39)) return;
        if (code === 37 || code === 38 || code === 39 || code === 40) {
          event.preventDefault();
          moveFocus(code === 37 ? 'left' : (code === 38 ? 'up' : (code === 39 ? 'right' : 'down')));
          return;
        }
        if (code === 13 && active && tag === 'BUTTON') {
          event.preventDefault();
          if (event.repeat || okHoldTimer || okHeld) return;
          okHoldTimer = global.setTimeout(function () {
            okHoldTimer = null;
            if (document.hidden || parked) return;
            if (active.classList.contains('launcher-tile') && !active.classList.contains('launcher-page-spacer')) {
              okHeld = true; enterEditMode(active);
            }
          }, 700);
          return;
        }
        if (code === 461 || code === 27) {
          // Do not hide on key-down. A long Back generates repeat events on
          // webOS; hiding on the first down exposed LG Home for a visible beat.
          // Short Back is committed on key-up, while long Back stays consumed.
          event.preventDefault(); event.stopPropagation();
          if (!backPressed) backHeld = false;
          backPressed = true;
          return;
        }
      });
      document.addEventListener('keyup', function (event) {
        if (document.hidden || parked) { resetRemotePress(); return; }
        if (loadingCoverActive()) {
          event.preventDefault(); event.stopPropagation();
          resetRemotePress();
          return;
        }
        if (event.keyCode === 461 || event.keyCode === 27) {
          event.preventDefault(); event.stopPropagation();
          var commitBack = backPressed && !backHeld;
          backPressed = false; backHeld = false;
          if (!commitBack) return;
          var backOverlay = Array.prototype.filter.call(root.querySelectorAll('.launcher-overlay'), function (item) { return !item.hidden; })[0];
          if (backOverlay) closeOverlays(); else parkLauncher(true);
          return;
        }
        var settings = root.querySelector('#launcher-settings');
        if (settings && !settings.hidden && event.keyCode === 13) { event.preventDefault(); return; }
        if (viewMode === 'overlay') return;
        if (event.keyCode !== 13) return;
        event.preventDefault();
        if (okHoldTimer) {
          global.clearTimeout(okHoldTimer); okHoldTimer = null;
          if (document.activeElement && document.activeElement.tagName === 'BUTTON') document.activeElement.click();
        }
        okHeld = false;
      });
    }
    function iconForApp(appId) { return apiBase + '/api/apps/icon?appId=' + encodeURIComponent(appId); }
    function stopActiveLivePreview() {
      if (!activeLivePreview) return;
      var liveImage = activeLivePreview.image;
      var liveBadge = activeLivePreview.badge;
      activeLivePreview = null;
      if (liveImage && liveImage.parentNode) liveImage.parentNode.removeChild(liveImage);
      if (liveBadge && liveBadge.parentNode) liveBadge.parentNode.removeChild(liveBadge);
    }
    function localImageKey(kind, id) { return 'hu.szabi.launcher.image.' + kind + '.' + String(id || '').replace(/[^A-Za-z0-9._-]/g, '-'); }
    function readLocalImage(key) { try { return global.localStorage.getItem(key) || ''; } catch (ignore) { return ''; } }
    function removeLocalImage(key) { try { if (key) global.localStorage.removeItem(key); } catch (ignore) {} }
    var imageQueue = [];
    var imageQueueTimer = null;
    var imageQueueBusy = false;
    function pumpImages() {
      if (imageQueueTimer) global.clearTimeout(imageQueueTimer);
      imageQueueTimer = null;
      if (document.hidden || parked || imageQueueBusy || !imageQueue.length) return;
      var job = imageQueue.shift();
      if (!document.documentElement.contains(job.image)) { pumpImages(); return; }
      imageQueueBusy = true;
      var cache = global.LauncherImageCache;
      cache.fetchAndStore(job.key, job.source, 5000).then(function (url) {
        if (url) job.image.src = url;
      }, function () { job.image.src = job.source; }).then(function () {
        imageQueueBusy = false;
        cache.trim(64);
        imageQueueTimer = global.setTimeout(pumpImages, 100);
      });
    }
    function loadCachedIcon(image, key, source) {
      var cache = global.LauncherImageCache;
      if (!cache || !key) { image.src = source; return; }
      cache.getUrl(key, { source: source, allowStale: true }).then(function (url) {
        if (url) image.src = url;
        else {
          // Legacy data URLs are read-only migration fallbacks, never canvas
          // encoded or synchronously rewritten on the TV's render thread.
          var legacy = readLocalImage(key);
          if (legacy) image.src = legacy;
          imageQueue.push({ image: image, key: key, source: source });
          if (!imageQueueTimer) imageQueueTimer = global.setTimeout(pumpImages, 900);
        }
      });
    }
    function makeTile(item, app, preset, activate) {
      var button = document.createElement('button');
      button.type = 'button'; button.className = 'launcher-tile launcher-fit-' + (item.fit === 'small' || item.fit === 'cover' ? item.fit : 'contain');
      button.setAttribute('data-type', item.type); button.setAttribute('data-target', item.targetId || ''); button.setAttribute('data-item-id', item.id || '');
      var media = document.createElement('span'); media.className = 'launcher-tile-media';
      if (item.backgroundColor) media.style.background = item.backgroundColor;
      var fallback = text(document.createElement('span'), item.type === 'allApps' ? '▦' : (item.type === 'settings' ? '⚙' : initial(item.label)));
      fallback.className = 'launcher-fallback'; media.appendChild(fallback);
      var fallbackTimer = null;
      function armFallback() {
        if (fallbackTimer) global.clearTimeout(fallbackTimer);
        fallback.hidden = false;
      }
      var source = '';
      var isCameraPreview = false;
      var imageCacheKey = '';
      if (item.iconUrl) { source = item.iconUrl; imageCacheKey = localImageKey('custom', item.id || item.targetId); }
      else if (item.iconKey !== 'installed' && (item.iconKey || suggestedIconKey(item, app))) source = iconData(item.iconKey || suggestedIconKey(item, app));
      else if (item.type === 'app' && app) { source = iconForApp(app.id); imageCacheKey = localImageKey('app', app.id); }
      else if (item.type === 'link') {
        try { source = new URL(item.targetId).origin + '/favicon.ico'; } catch (ignore) {}
        imageCacheKey = localImageKey('link', item.id || item.targetId);
      } else if (item.type === 'preset' && preset && preset.previewAvailable && data.config.settings.cameraPreviewsEnabled) {
        // On the TV use go2rtc's single-frame endpoint directly.  This avoids
        // a hard NAS dependency and, unlike the old canvas path, works without
        // cross-origin pixel access.
        source = mode === 'tv' ? directPresetPreview(preset) : '';
        if (!source) source = apiBase + '/api/launcher/camera-preview?presetId=' + encodeURIComponent(item.targetId);
        isCameraPreview = true;
        imageCacheKey = localImageKey('camera', item.targetId);
      }
      if (source) {
        if (isCameraPreview) button.classList.add('launcher-camera-preview');
        var image = document.createElement('img'); image.alt = ''; image.hidden = true;
        if (imageCacheKey && !isCameraPreview) image.crossOrigin = 'anonymous';
        var bootDone = isCameraPreview ? function () {} : bootTrack(image);
        image.onload = function () { if (fallbackTimer) global.clearTimeout(fallbackTimer); fallback.hidden = true; image.hidden = false; bootDone(); };
        image.onerror = function () {
          image.hidden = true; fallback.hidden = false;
          if (!isCameraPreview && /^(blob|data):/.test(String(image.src)) && source !== image.src) {
            removeLocalImage(imageCacheKey);
            if (global.LauncherImageCache) global.LauncherImageCache.invalidate(imageCacheKey, source);
            image.src = source;
          }
          if (isCameraPreview) armFallback();
          bootDone();
        };
        if (isCameraPreview) {
          image.setAttribute('data-preview-url', source);
          image.__launcherArmFallback = armFallback;
          image.hidden = true; armFallback();
          if (global.LauncherImageCache && global.LauncherImageCache.bindPreview) {
            global.LauncherImageCache.bindPreview(image, imageCacheKey, source,
              apiBase + '/api/launcher/camera-preview?presetId=' + encodeURIComponent(item.targetId),
              function () { fallback.hidden = true; });
          } else image.__launcherRefresh = function () { image.src = cacheBust(source); };

          var liveMjpegUrl = mode === 'tv' ? directPresetMjpeg(preset) : '';
          if (liveMjpegUrl) {
            button.addEventListener('focus', function () {
              if (previewFocusTimer) global.clearTimeout(previewFocusTimer);
              previewFocusTimer = global.setTimeout(function () {
                previewFocusTimer = null;
                if (document.activeElement !== button || document.hidden || parked) return;
                stopActiveLivePreview();
                var liveImage = document.createElement('img');
                liveImage.alt = '';
                liveImage.className = 'launcher-camera-live';
                liveImage.setAttribute('data-live-mjpeg', liveMjpegUrl);
                var liveBadge = text(document.createElement('span'), 'LIVE');
                liveBadge.className = 'launcher-camera-live-badge';
                media.appendChild(liveImage);
                media.appendChild(liveBadge);
                activeLivePreview = { button: button, image: liveImage, badge: liveBadge };
                liveImage.onerror = function () {
                  if (activeLivePreview && activeLivePreview.image === liveImage) stopActiveLivePreview();
                };
                liveImage.src = liveMjpegUrl;
              }, 1000);
            });
            button.addEventListener('blur', function () {
              if (previewFocusTimer) { global.clearTimeout(previewFocusTimer); previewFocusTimer = null; }
              if (activeLivePreview && activeLivePreview.button === button) stopActiveLivePreview();
            });
          }
        } else {
          armFallback(); loadCachedIcon(image, imageCacheKey, source);
        }
        media.appendChild(image);
      } else armFallback();
      var label = text(document.createElement('span'), item.label); label.className = 'launcher-tile-label';
      button.appendChild(media); button.appendChild(label);
      button.addEventListener('click', function () {
        if (editMode) return;
        if (activate) { activate(item, app, preset); return; }
        if (item.type === 'allApps') { renderAllApps(''); openOverlay('launcher-all-apps'); return; }
        if (item.type === 'settings') { renderSettingsSummary(); openOverlay('launcher-settings'); return; }
        launch(item);
      });
      return button;
    }
    function launch(item, closeAfterLaunch) {
      toast(item.label + ' indítása…');
      request('/api/launcher/launch', 'POST', { type: item.type, targetId: item.targetId, label: item.label }).then(function (result) {
        if (result.lastUsed) { data.config.lastUsed = result.lastUsed; quickNeedsRender = true; }
        renderTopActions(); toast(item.label + ' elindult.');
        if (options.host === 'full-overlay') parkLauncher(true);
        else if (closeAfterLaunch) closeQuick();
      }, function (error) { toast(error.message, true); });
    }

    function stopFullViewWork() {
      if (imageQueueTimer) { global.clearTimeout(imageQueueTimer); imageQueueTimer = null; }
      if (fullWorkTimer) { global.clearTimeout(fullWorkTimer); fullWorkTimer = null; }
      if (wallpaperTimer) { global.clearTimeout(wallpaperTimer); wallpaperTimer = null; }
      stopPreviewWork();
      if (clockTimer) { global.clearInterval(clockTimer); clockTimer = null; }
      wallpaperLoadToken += 1;
    }

    function stopPreviewWork() {
      if (previewTimer) { global.clearTimeout(previewTimer); previewTimer = null; }
      previewJobs.forEach(function (timer) { global.clearTimeout(timer); }); previewJobs = [];
      if (previewFocusTimer) { global.clearTimeout(previewFocusTimer); previewFocusTimer = null; }
      stopActiveLivePreview();
    }

    var popupParkTimer = null;
    var popupParkGeneration = 0;
    var popupLifecycle = global.LauncherPopupLifecycle ? global.LauncherPopupLifecycle.create({
      system: global.PalmSystem || global.webOSSystem,
      document: document,
      setTimeout: function (callback, delay) { return global.setTimeout(callback, delay); },
      clearTimeout: function (timer) { global.clearTimeout(timer); }
    }) : null;

    function cancelPendingPopupPark() {
      popupParkGeneration += 1;
      if (popupParkTimer !== null) { global.clearTimeout(popupParkTimer); popupParkTimer = null; }
      if (popupLifecycle) popupLifecycle.cancel();
    }

    function closeApplicationFallback() {
      try { global.close(); } catch (ignore) {}
    }

    function parkLauncher(immediate) {
      if (parkRequested) return;
      parkRequested = true;
      parked = true;
      var parkGeneration = ++popupParkGeneration;
      stopFullViewWork();
      if (options.host === 'full') {
        // A normal card releases focus when backgrounded; retain DOM/images.
        Promise.resolve().then(function () { return options.onPark(); }).catch(function (error) {
          parked = false; parkRequested = false; scheduleFullViewWork(); toast(error.message, true);
        });
        return;
      }
      if (viewMode === 'overlay') {
        quickClosing = true;
        stopPreviewWork();
        if (!immediate) document.body.classList.add('launcher-quick-closing');
      }
      function concealAndPark() {
        // A close-animation callback may already be queued when native resume
        // thaws JavaScript; clearing the timer alone cannot invalidate it.
        if (parkGeneration !== popupParkGeneration || !parkRequested || !parked) return;
        popupParkTimer = null;
        document.body.classList.add('launcher-parked');
        root.setAttribute('aria-hidden', 'true');
        function forceClosePopup() {
          if (typeof options.onPark !== 'function') { closeApplicationFallback(); return; }
          try { Promise.resolve(options.onPark()).then(closeApplicationFallback, closeApplicationFallback); }
          catch (error) { closeApplicationFallback(); }
        }
        if (!popupLifecycle) { forceClosePopup(); return; }
        popupLifecycle.hide({
          beforeHide: function () {
            // Queue marker cleanup before native hide may suspend JavaScript.
            if (typeof options.onNativePark === 'function') {
              try { Promise.resolve(options.onNativePark()).catch(function () {}); } catch (ignore) {}
            }
          },
          onHidden: function () { global.__launcherNativeHiddenAt = Date.now(); },
          onFailure: forceClosePopup
        });
      }
      if (viewMode === 'overlay' && !immediate && data.config.settings.animationsEnabled !== false) popupParkTimer = global.setTimeout(concealAndPark, 170);
      else concealAndPark();
    }

    function closeQuick() {
      if (quickClosing || parked || viewMode !== 'overlay') return;
      parkLauncher(false);
    }

    function quickApp(item) {
      return (data.apps || []).filter(function (candidate) { return candidate.id === item.targetId; })[0] || null;
    }

    function quickPreset(item) {
      var presetId = item.previewPresetId || item.targetId;
      return (data.presets || []).filter(function (candidate) { return candidate.id === presetId; })[0] || null;
    }

    function quickFocusNode(node) {
      if (!node) return;
      try { node.focus({ preventScroll: true }); } catch (ignore) { node.focus(); }
      var viewport = node.closest && (node.closest('.launcher-quick-items') || node.closest('.launcher-quick-categories'));
      if (!viewport) return;
      var nodeRect = node.getBoundingClientRect();
      var viewportRect = viewport.getBoundingClientRect();
      var safe = 18;
      if (nodeRect.left < viewportRect.left + safe) viewport.scrollLeft += nodeRect.left - viewportRect.left - safe;
      else if (nodeRect.right > viewportRect.right - safe) viewport.scrollLeft += nodeRect.right - viewportRect.right + safe;
    }

    function focusQuickState() {
      if (!quickState || !quickCategories.length) return;
      var selector;
      if (quickDrilldown) {
        selector = '.launcher-quick-tile[data-quick-index="' + String(quickDrilldown.index || 0) + '"]';
      } else if (quickWeatherTabFocused) {
        selector = '.launcher-quick-tab.active';
      } else if (quickState.layer === 'items') {
        var category = quickCategories[quickState.categoryIndex];
        selector = '.launcher-quick-tile[data-quick-index="' + String(quickState.itemIndices[category.id] || 0) + '"]';
      } else selector = '.launcher-quick-category[data-quick-index="' + String(quickState.categoryIndex) + '"]';
      global.setTimeout(function () { if (activeScope() === root) quickFocusNode(root.querySelector(selector)); }, 0);
    }

    function buildQuickCategories() {
      var categories = QuickCore.buildCategories(data);
      if (data.config.lastUsed) {
        var favouriteCategory = categories.filter(function (category) { return category.id === 'favorites'; })[0] || categories[0];
        var resumeItem = deepCopy(data.config.lastUsed);
        var resumeApp = (data.apps || []).filter(function (candidate) { return candidate.id === resumeItem.targetId; })[0] || null;
        var resumeIconKey = suggestedIconKey(resumeItem, resumeApp) || (resumeItem.type === 'preset' ? 'camera' : 'resume');
        var resumeIconUrl = iconData(resumeIconKey);
        if (!resumeIconUrl && resumeApp) resumeIconUrl = readLocalImage(localImageKey('app', resumeApp.id)) || iconForApp(resumeApp.id);
        resumeItem.id = 'quick-resume-item'; resumeItem.visible = true; resumeItem.iconKey = resumeIconKey;
        if (favouriteCategory) {
          favouriteCategory.iconKey = resumeIconKey;
          favouriteCategory.iconUrl = resumeIconUrl;
          favouriteCategory.actionItem = resumeItem;
          favouriteCategory.resumeLabel = 'Folytatás: ' + resumeItem.label;
        }
      }
      categories.push({ id: 'quick-info', label: 'Info', iconKey: 'info', special: true, items: [{ id: 'quick-info-item', type: 'quickInfo', label: 'Rendszeradatok', visible: true }] });
      categories.push({ id: 'quick-weather', label: 'Időjárás', iconKey: 'weather', special: true, items: [{ id: 'quick-weather-item', type: 'quickWeather', label: 'Előrejelzés', visible: true }] });
      return categories;
    }

    function currentQuickCategory() {
      return quickCategories[quickState && quickState.categoryIndex || 0] || null;
    }

    function quickAllAppItems() {
      return (data.apps || []).map(function (app) {
        return { id: 'quick-all-' + app.id, type: 'app', targetId: app.id, label: app.title || app.id, visible: true, fit: 'contain', iconKey: '', iconUrl: '', backgroundColor: '' };
      });
    }

    function renderQuickContextTitle(value) {
      var tabs = root.querySelector('.launcher-quick-tabs');
      if (!tabs) return;
      tabs.textContent = ''; tabs.hidden = false;
      var title = text(document.createElement('strong'), value); title.className = 'launcher-quick-context-title'; tabs.appendChild(title);
    }

    function renderQuickWeatherTabs() {
      var tabs = root.querySelector('.launcher-quick-tabs');
      if (!tabs) return;
      tabs.textContent = ''; tabs.hidden = false;
      [['hourly', '36 óra'], ['weekly', 'Heti']].forEach(function (entry) {
        var button = text(document.createElement('button'), entry[1]);
        button.type = 'button'; button.className = 'launcher-quick-tab';
        if (quickWeatherView === entry[0]) button.classList.add('active');
        button.addEventListener('click', function () {
          quickWeatherView = entry[0]; quickWeatherTabFocused = true;
          renderQuickWeatherContent(weatherData); focusQuickState();
        });
        tabs.appendChild(button);
      });
    }

    function makeQuickDataTile(index, label, primary, secondary, symbol, variant, tertiary) {
      var button = document.createElement('button'); button.type = 'button';
      button.className = 'launcher-quick-tile launcher-quick-data-tile';
      if (variant) button.classList.add('launcher-quick-' + variant + '-tile');
      button.setAttribute('data-quick-index', String(index));
      var media = document.createElement('span'); media.className = 'launcher-quick-tile-media launcher-quick-data-media';
      var icon = text(document.createElement('span'), symbol || '•'); icon.className = 'launcher-quick-data-icon';
      var strong = text(document.createElement('strong'), primary); var small = text(document.createElement('small'), secondary || '');
      media.appendChild(icon); media.appendChild(strong); media.appendChild(small);
      if (tertiary) { var third = text(document.createElement('small'), tertiary); third.className = 'launcher-quick-data-tertiary'; media.appendChild(third); }
      var caption = text(document.createElement('span'), label); caption.className = 'launcher-quick-tile-label';
      button.appendChild(media); button.appendChild(caption);
      return button;
    }

    function renderQuickInfoContent(diagnostics) {
      var host = root.querySelector('.launcher-quick-items'); if (!host) return; host.textContent = '';
      diagnostics = diagnostics || {};
      var memory = diagnostics.memory || {};
      var entries = [
        ['CPU', diagnostics.cpuPercent == null ? 'n/a' : Number(diagnostics.cpuPercent).toFixed(1).replace('.0', '') + '%', 'Terhelés', 'CPU'],
        ['Memória', formatKiB(memory.usedKiB) + ' / ' + formatKiB(memory.totalKiB), 'Használt / teljes', 'RAM'],
        ['Load average', (diagnostics.load || []).slice(0, 3).join(' · ') || 'n/a', '1 · 5 · 15 perc', 'LOAD'],
        ['Hőmérséklet', diagnostics.temperatureC == null ? 'n/a' : diagnostics.temperatureC + ' °C', 'CPU', '°C'],
        ['Tárhely', (diagnostics.disks || []).map(function (disk) { return disk.mount + ' ' + disk.percent; }).join(' · ') || 'n/a', 'Foglalt terület', 'SSD']
      ];
      var infoCategory = currentQuickCategory();
      if (infoCategory) infoCategory.items = entries.map(function (entry, index) { return { id: 'quick-info-' + index, type: 'quickInfo', label: entry[0], visible: true }; });
      entries.forEach(function (entry, index) { host.appendChild(makeQuickDataTile(index, entry[0], entry[1], entry[2], entry[3], 'info')); });
      focusQuickState();
    }

    function loadQuickInfo(loadToken) {
      if (quickDiagnosticsCache && Date.now() - quickDiagnosticsCache.savedAt < 60000) {
        renderQuickInfoContent(quickDiagnosticsCache.data); return;
      }
      request('/api/launcher/diagnostics', 'GET').then(function (result) {
        if (loadToken !== quickSpecialLoadToken || !currentQuickCategory() || currentQuickCategory().id !== 'quick-info') return;
        quickDiagnosticsCache = { savedAt: Date.now(), data: result.diagnostics };
        renderQuickInfoContent(result.diagnostics);
      }, function (error) {
        if (loadToken !== quickSpecialLoadToken) return;
        var host = root.querySelector('.launcher-quick-items'); if (host) { host.textContent = ''; host.appendChild(makeQuickDataTile(0, 'Info', 'Nem elérhető', error.message, '!')); }
      });
    }

    function renderQuickWeatherContent(weather) {
      if (!weather || !currentQuickCategory() || currentQuickCategory().id !== 'quick-weather') return;
      renderQuickWeatherTabs();
      var host = root.querySelector('.launcher-quick-items'); if (!host) return; host.textContent = '';
      var entries = quickWeatherView === 'weekly' ? (weather.daily || []) : (weather.hourly || []).slice(0, 36);
      var weatherCategory = currentQuickCategory();
      if (weatherCategory) weatherCategory.items = (entries.length ? entries : [{}]).map(function (_entry, index) { return { id: 'quick-weather-' + quickWeatherView + '-' + index, type: 'quickWeather', label: 'Előrejelzés', visible: true }; });
      if (quickState && weatherCategory) quickState.itemIndices[weatherCategory.id] = Math.max(0, Math.min(entries.length - 1, quickState.itemIndices[weatherCategory.id] || 0));
      entries.forEach(function (entry, index) {
        if (quickWeatherView === 'weekly') {
          host.appendChild(makeQuickDataTile(index, dayLabel(entry.date), Math.round(Number(entry.min)) + '° – ' + Math.round(Number(entry.max)) + '°', dayLabel(entry.date) + ' · eső ' + Math.round(Number(entry.precipitationProbability || 0)) + '%', weatherIcon(entry.code), 'weather'));
        } else {
          host.appendChild(makeQuickDataTile(index, hourLabel(entry.time), Math.round(Number(entry.temperature)) + '°', hourLabel(entry.time) + ' · eső ' + Math.round(Number(entry.precipitationProbability || 0)) + '%', weatherIcon(entry.code), 'weather', 'Szél ' + Math.round(Number(entry.windSpeed || 0)) + ' km/h'));
        }
      });
      if (!entries.length) host.appendChild(makeQuickDataTile(0, 'Időjárás', 'Nincs adat', '', weatherIcon(weather.code)));
      focusQuickState();
    }

    function loadQuickWeather(loadToken) {
      var cached = readWeatherCache(false);
      if (cached) { weatherData = cached.result.weather; renderQuickWeatherContent(weatherData); return; }
      requestWeatherCached().then(function (result) {
        if (loadToken !== quickSpecialLoadToken || !currentQuickCategory() || currentQuickCategory().id !== 'quick-weather') return;
        if (!result.enabled || !result.weather) {
          var unavailable = root.querySelector('.launcher-quick-items'); if (unavailable) { unavailable.textContent = ''; unavailable.appendChild(makeQuickDataTile(0, 'Időjárás', 'Kikapcsolva', 'A teljes launcher beállításaiban kapcsolható be.', '○')); }
          return;
        }
        renderQuickWeatherContent(result.weather);
      }, function (error) {
        if (loadToken !== quickSpecialLoadToken) return;
        var host = root.querySelector('.launcher-quick-items'); if (host) { host.textContent = ''; host.appendChild(makeQuickDataTile(0, 'Időjárás', 'Nem elérhető', error.message, '!')); }
      });
    }

    function renderQuickClockValues() {
      var now = new Date();
      var hours = (now.getHours() < 10 ? '0' : '') + now.getHours();
      var minutes = (now.getMinutes() < 10 ? '0' : '') + now.getMinutes();
      Array.prototype.forEach.call(root.querySelectorAll('.launcher-quick-clock-value'), function (node) { node.textContent = hours + ':' + minutes; });
      Array.prototype.forEach.call(root.querySelectorAll('.launcher-quick-clock-main'), function (node) { node.textContent = hours + ':' + minutes; });
      Array.prototype.forEach.call(root.querySelectorAll('.launcher-quick-status-time'), function (node) { node.textContent = hours + ':' + minutes; });
      Array.prototype.forEach.call(root.querySelectorAll('.launcher-quick-clock-date,.launcher-quick-status-date'), function (node) { node.textContent = now.toLocaleDateString('hu-HU', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }); });
    }

    function startQuickClock() {
      renderQuickClockValues();
      if (!clockTimer) clockTimer = global.setInterval(renderQuickClockValues, 1000);
    }

    function renderQuickClockContent() {
      var host = root.querySelector('.launcher-quick-items'); if (!host) return; host.textContent = '';
      var tile = makeQuickDataTile(0, 'Dátum és idő', '', '', '◷');
      tile.querySelector('strong').classList.add('launcher-quick-clock-main');
      tile.querySelector('small').classList.add('launcher-quick-clock-date');
      host.appendChild(tile); renderQuickClockValues();
    }

    function activateQuickItem(item) {
      if (item.type === 'allApps') {
        quickDrilldown = { type: 'allApps', index: 0 }; quickWeatherTabFocused = false; renderQuick(); return;
      }
      if (item.type === 'settings') {
        quickFullOverlayReturn = true; renderSettingsSummary(); openOverlay('launcher-settings'); return;
      }
      if (item.type === 'quickInfo' || item.type === 'quickWeather' || item.type === 'quickClock') return;
      launch(item, true);
    }

    function makeQuickTile(item, index, categoryId, activateOverride) {
      var app = quickApp(item);
      var preset = quickPreset(item);
      var button = document.createElement('button');
      button.type = 'button'; button.className = 'launcher-quick-tile';
      button.setAttribute('data-quick-index', String(index));
      button.setAttribute('data-target', item.targetId || '');
      var media = document.createElement('span'); media.className = 'launcher-quick-tile-media';
      var iconKey = item.iconKey || suggestedIconKey(item, app);
      var source = item.iconUrl || iconData(iconKey);
      if (!source && item.type === 'app' && app) source = readLocalImage(localImageKey('app', app.id)) || iconForApp(app.id);
      var fallback = text(document.createElement('span'), initial(item.label));
      fallback.className = 'launcher-quick-fallback';
      if (categoryId === 'cameras' && preset && preset.previewAvailable && data.config.settings.cameraPreviewsEnabled) {
        var previewSource = mode === 'tv' ? directPresetPreview(preset) : '';
        if (!previewSource) previewSource = apiBase + '/api/launcher/camera-preview?presetId=' + encodeURIComponent(preset.id);
        if (previewSource) {
          button.classList.add('launcher-quick-camera-preview');
          fallback.textContent = '';
          var cameraIcon = document.createElement('img'); cameraIcon.alt = ''; cameraIcon.src = iconData('camera'); fallback.appendChild(cameraIcon);
          media.appendChild(fallback);
          var preview = document.createElement('img'); preview.alt = ''; preview.hidden = true;
          preview.setAttribute('data-preview-url', previewSource);
          preview.onload = function () { fallback.hidden = true; preview.hidden = false; };
          preview.onerror = function () { preview.hidden = true; fallback.hidden = false; };
          if (global.LauncherImageCache && global.LauncherImageCache.bindPreview) {
            global.LauncherImageCache.bindPreview(preview, localImageKey('camera', preset.id), previewSource,
              apiBase + '/api/launcher/camera-preview?presetId=' + encodeURIComponent(preset.id),
              function () { fallback.hidden = true; });
          } else preview.__launcherRefresh = function () { preview.src = cacheBust(previewSource); };
          media.appendChild(preview);
          source = '';
        }
      }
      if (source) {
        var image = document.createElement('img'); image.alt = ''; image.hidden = true;
        media.appendChild(fallback);
        image.onload = function () { image.hidden = false; fallback.hidden = true; };
        image.onerror = function () { image.hidden = true; fallback.hidden = false; };
        loadCachedIcon(image, localImageKey(item.iconUrl ? 'custom' : 'app', item.iconUrl || item.targetId || iconKey), source);
        media.appendChild(image);
      } else if (!media.firstChild) {
        media.appendChild(fallback);
      }
      var label = text(document.createElement('span'), item.label); label.className = 'launcher-quick-tile-label';
      button.appendChild(media); button.appendChild(label);
      button.addEventListener('click', function () {
        if (quickDrilldown) quickDrilldown.index = index;
        else {
          quickState.layer = 'items';
          var category = quickCategories[quickState.categoryIndex];
          quickState.itemIndices[category.id] = index;
        }
        (activateOverride || activateQuickItem)(item);
      });
      return button;
    }

    function renderQuick() {
      if (!QuickCore) throw new Error('A gyorsindító modell nem tölthető be.');
      stopPreviewWork();
      var localWeather = readWeatherCache(false);
      if (!weatherData && localWeather) weatherData = localWeather.result.weather;
      var previousCategory = currentQuickCategory();
      quickCategories = buildQuickCategories();
      if (previousCategory) {
        var restoredIndex = quickCategories.map(function (category) { return category.id; }).indexOf(previousCategory.id);
        if (restoredIndex >= 0) quickState.categoryIndex = restoredIndex;
      }
      quickState = QuickCore.normalizeState(quickState, quickCategories);
      var categoryHost = root.querySelector('.launcher-quick-categories');
      var itemHost = root.querySelector('.launcher-quick-items');
      if (!categoryHost || !itemHost) return;
      quickNeedsRender = false;
      var tabsHost = root.querySelector('.launcher-quick-tabs');
      categoryHost.textContent = ''; itemHost.textContent = ''; if (tabsHost) { tabsHost.textContent = ''; tabsHost.hidden = true; }
      var configuredCategoryCount = quickCategories.filter(function (category) { return !category.special; }).length;
      quickCategories.forEach(function (category, index) {
        var button = document.createElement('button');
        button.type = 'button'; button.className = 'launcher-quick-category';
        if (category.special) button.classList.add('launcher-quick-utility');
        if (index === configuredCategoryCount) button.classList.add('launcher-quick-utility-first');
        button.setAttribute('data-quick-index', String(index));
        button.setAttribute('aria-selected', index === quickState.categoryIndex ? 'true' : 'false');
        var categoryDisc = document.createElement('span');
        categoryDisc.className = 'launcher-quick-category-disc';
        if (category.id === 'quick-weather' && weatherData) {
          var currentWeather = weatherData.current || {};
          var weatherValue = text(document.createElement('span'), weatherIcon(currentWeather.code == null ? weatherData.code : currentWeather.code) + ' ' + Math.round(Number(currentWeather.temperature == null ? weatherData.max : currentWeather.temperature)) + '°');
          weatherValue.className = 'launcher-quick-weather-value'; categoryDisc.appendChild(weatherValue);
        } else {
          var categoryIcon = document.createElement('img');
          categoryIcon.className = 'launcher-quick-category-icon'; categoryIcon.alt = '';
          categoryIcon.src = category.iconUrl || iconData(category.iconKey); categoryDisc.appendChild(categoryIcon);
          if (category.actionItem) {
            var resumeBadge = document.createElement('span'); resumeBadge.className = 'launcher-quick-resume-badge'; resumeBadge.setAttribute('aria-hidden', 'true'); categoryDisc.appendChild(resumeBadge);
          }
        }
        var categoryLabel = text(document.createElement('span'), category.label);
        categoryLabel.className = 'launcher-quick-category-label';
        button.appendChild(categoryDisc); button.appendChild(categoryLabel);
        if (category.resumeLabel) button.setAttribute('aria-label', category.resumeLabel + ' · lefelé: Kedvencek');
        if (index === quickState.categoryIndex) button.classList.add('active');
        button.addEventListener('click', function () {
          if (category.actionItem) { launch(category.actionItem, true); return; }
          quickDrilldown = null; quickWeatherTabFocused = false; quickState.layer = 'categories'; quickState.categoryIndex = index; renderQuick();
        });
        categoryHost.appendChild(button);
      });
      var current = quickCategories[quickState.categoryIndex];
      var loadToken = ++quickSpecialLoadToken;
      if (quickDrilldown && quickDrilldown.type === 'allApps') {
        renderQuickContextTitle('Összes alkalmazás · Back: vissza a gyorsindítóhoz');
        var allApps = quickAllAppItems();
        allApps.forEach(function (item, index) { itemHost.appendChild(makeQuickTile(item, index, '', function (selected) { launch(selected, true); })); });
        if (!allApps.length) itemHost.appendChild(makeQuickDataTile(0, 'Összes alkalmazás', 'Nincs elérhető app', '', '▦'));
      } else if (current.id === 'quick-info') {
        itemHost.appendChild(makeQuickDataTile(0, 'Info', 'Adatok betöltése…', 'Csak most indul el a lekérés.', 'ⓘ')); loadQuickInfo(loadToken);
      } else if (current.id === 'quick-weather') {
        itemHost.appendChild(makeQuickDataTile(0, 'Időjárás', 'Előrejelzés betöltése…', '1 órás gyorsítótár', weatherIcon(0))); loadQuickWeather(loadToken);
      } else {
        current.items.forEach(function (item, index) { itemHost.appendChild(makeQuickTile(item, index, current.id)); });
      }
      if (!itemHost.children.length) {
        var empty = text(document.createElement('div'), 'Ebben a kategóriában még nincs elérhető elem.');
        empty.className = 'launcher-quick-empty'; itemHost.appendChild(empty);
      }
      focusQuickState();
      if (current.id === 'cameras') schedulePreviews(120);
      startQuickClock();
    }

    function handleQuickKey(event) {
      var code = event.keyCode;
      var visibleOverlay = Array.prototype.filter.call(root.querySelectorAll('.launcher-overlay'), function (item) { return !item.hidden; })[0];
      if (visibleOverlay) {
        event.preventDefault(); event.stopPropagation();
        if (code === 461 || code === 27 || code === 8) { closeOverlays(); return; }
        if (code === 37 || code === 38 || code === 39 || code === 40) {
          moveFocus(code === 37 ? 'left' : (code === 38 ? 'up' : (code === 39 ? 'right' : 'down'))); return;
        }
        if (code === 13 && !event.repeat && document.activeElement && typeof document.activeElement.click === 'function') document.activeElement.click();
        return;
      }
      if (code === 461 || code === 27 || code === 8) {
        event.preventDefault(); event.stopPropagation();
        if (quickDrilldown) { quickDrilldown = null; quickState.layer = 'items'; renderQuick(); return; }
        closeQuick(); return;
      }
      var intent = code === 37 ? 'left' : (code === 38 ? 'up' : (code === 39 ? 'right' : (code === 40 ? 'down' : '')));
      if (intent) {
        event.preventDefault(); event.stopPropagation();
        if (quickDrilldown) {
          var drilldownItems = quickAllAppItems();
          if (intent === 'left' || intent === 'right') quickDrilldown.index = Math.max(0, Math.min(drilldownItems.length - 1, quickDrilldown.index + (intent === 'left' ? -1 : 1)));
          else if (intent === 'up') { quickDrilldown = null; quickState.layer = 'categories'; renderQuick(); return; }
          focusQuickState(); return;
        }
        var activeCategory = currentQuickCategory();
        var weatherTabs = root.querySelector('.launcher-quick-tabs .launcher-quick-tab');
        if (activeCategory && activeCategory.id === 'quick-weather' && (weatherTabs || quickWeatherTabFocused)) {
          if (quickWeatherTabFocused) {
            if (intent === 'left' || intent === 'right') { quickWeatherView = quickWeatherView === 'hourly' ? 'weekly' : 'hourly'; renderQuickWeatherContent(weatherData); focusQuickState(); return; }
            if (intent === 'up') { quickWeatherTabFocused = false; quickState.layer = 'categories'; focusQuickState(); return; }
            if (intent === 'down') { quickWeatherTabFocused = false; quickState.layer = 'items'; quickState.itemIndices[activeCategory.id] = 0; focusQuickState(); return; }
          } else if (quickState.layer === 'categories' && intent === 'down' && weatherTabs) {
            quickWeatherTabFocused = true; focusQuickState(); return;
          } else if (quickState.layer === 'items' && intent === 'up' && weatherTabs) {
            quickWeatherTabFocused = true; focusQuickState(); return;
          }
        }
        if (quickState.layer === 'categories' && intent === 'down' && activeCategory) quickState.itemIndices[activeCategory.id] = 0;
        var previousCategoryIndex = quickState.categoryIndex;
        quickState = QuickCore.move(quickState, intent, quickCategories);
        if (quickState.categoryIndex !== previousCategoryIndex) renderQuick();
        else focusQuickState();
        return;
      }
      if (code === 13 && !event.repeat) {
        event.preventDefault(); event.stopPropagation();
        if (quickWeatherTabFocused) return;
        if (quickDrilldown) {
          var selectedApp = quickAllAppItems()[quickDrilldown.index || 0]; if (selectedApp) launch(selectedApp, true); return;
        }
        var selectedCategory = currentQuickCategory();
        if (quickState.layer === 'categories' && selectedCategory && selectedCategory.actionItem) { launch(selectedCategory.actionItem, true); return; }
        var item = QuickCore.currentItem(quickState, quickCategories);
        if (item) activateQuickItem(item);
      }
    }
    function renderRows() {
      var host = root.querySelector('.launcher-rows'); host.textContent = '';
      data.config.rows.forEach(function (row) {
        if (!row.visible) return;
        var section = document.createElement('section'); section.className = 'launcher-row'; section.setAttribute('data-row', row.id);
        section.appendChild(text(document.createElement('h2'), row.title));
        var strip = document.createElement('div'); strip.className = 'launcher-strip';
        var count = 0;
        row.items.forEach(function (item) {
          if (!item.visible) return;
          var app = data.apps.filter(function (candidate) { return candidate.id === item.targetId; })[0];
          var preset = data.presets.filter(function (candidate) { return candidate.id === item.targetId; })[0];
          var tile = makeTile(item, app, preset);
          if (editMode && editMode.itemId === item.id) tile.classList.add('launcher-editing');
          strip.appendChild(tile); count += 1;
        });
        if (!count) { var empty = text(document.createElement('div'), 'Ebben a sorban még nincs látható elem.'); empty.className = 'launcher-empty'; strip.appendChild(empty); }
        if (mode === 'tv' && data.config.settings.editorModeEnabled !== false) {
          var addTile = document.createElement('button'); addTile.type = 'button'; addTile.className = 'launcher-tile launcher-add-tile'; addTile.setAttribute('aria-label', row.title + ' – új elem'); addTile.title = 'Új elem hozzáadása';
          var addMedia = document.createElement('span'); addMedia.className = 'launcher-tile-media launcher-add-tile-media';
          addMedia.appendChild(text(document.createElement('span'), '+')).className = 'launcher-add-tile-symbol';
          addTile.appendChild(addMedia);
          addTile.appendChild(text(document.createElement('span'), 'Új elem')).className = 'launcher-tile-label';
          addTile.addEventListener('click', function () { openAddTile(row.id); }); strip.appendChild(addTile);
        }
        if (mode === 'tv' && count) {
          var pageSize = pageSizeForRow(row.id);
          var missing = (pageSize - (count % pageSize)) % pageSize;
          while (missing > 0) {
            var spacer = document.createElement('span');
            spacer.className = 'launcher-tile launcher-page-spacer';
            spacer.setAttribute('aria-hidden', 'true');
            strip.appendChild(spacer); missing -= 1;
          }
        }
        section.appendChild(strip); host.appendChild(section);
      });
      if (editMode) global.setTimeout(positionEditToolbar, 0);
    }
    function renderTopActions() {
      var host = root.querySelector('.launcher-top-actions'); if (!host) return; host.textContent = '';
      var last = data.config.lastUsed;
      if (last) {
        var resume = document.createElement('button'); resume.type = 'button'; resume.className = 'launcher-icon-action';
        resume.innerHTML = '<img class="launcher-resume-icon" alt=""><span></span>'; resume.querySelector('img').src = iconData('resume'); text(resume.querySelector('span'), 'Folytatás: ' + last.label);
        resume.addEventListener('click', function () { launch(last); }); host.appendChild(resume);
      }
      var diagnostics = document.createElement('button'); diagnostics.type = 'button'; diagnostics.className = 'launcher-icon-action launcher-round'; diagnostics.title = 'TV diagnosztika'; diagnostics.textContent = 'ⓘ';
      diagnostics.addEventListener('click', showDiagnostics); host.appendChild(diagnostics);
    }
    function renderClock() {
      if (document.hidden) return;
      var now = new Date();
      var clock = root.querySelector('.launcher-clock'); var date = root.querySelector('.launcher-date');
      function two(value) { return value < 10 ? '0' + value : String(value); }
      if (clock) {
        if (!clock.firstChild) clock.innerHTML = '<span></span><small></small>';
        clock.firstChild.textContent = two(now.getHours()) + ':' + two(now.getMinutes());
        clock.lastChild.textContent = two(now.getSeconds());
      }
      var dateKey = now.getFullYear() + '-' + now.getMonth() + '-' + now.getDate();
      if (date && dateKey !== lastClockDate) {
        lastClockDate = dateKey;
        date.textContent = now.toLocaleDateString('hu-HU', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
      }
    }
    function hourLabel(value) {
      var date = new Date(value);
      return date.toLocaleDateString('hu-HU', { weekday: 'short' }) + ' ' + date.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' });
    }
    function dayLabel(value) {
      return new Date(value + 'T12:00:00').toLocaleDateString('hu-HU', { weekday: 'short', month: 'short', day: 'numeric' });
    }
    function renderWeatherDetails(weather) {
      var body = root.querySelector('.launcher-weather-body');
      if (!body) return;
      body.textContent = '';
      var current = weather.current || {};
      var summary = document.createElement('section'); summary.className = 'launcher-weather-summary';
      summary.innerHTML = '<div class="launcher-weather-summary-icon">' + weatherIcon(current.code == null ? weather.code : current.code) + '</div><div><h3></h3><p></p></div>';
      text(summary.querySelector('h3'), (weather.label || 'Időjárás') + ' · ' + Math.round(Number(current.temperature == null ? weather.max : current.temperature)) + '°C');
      text(summary.querySelector('p'), 'Hőérzet: ' + Math.round(Number(current.apparentTemperature == null ? current.temperature : current.apparentTemperature)) + '° · Mai minimum / maximum: ' + Math.round(Number(weather.min)) + '° / ' + Math.round(Number(weather.max)) + '° · Szél: ' + Math.round(Number(current.windSpeed || 0)) + ' km/h');
      body.appendChild(summary);
      body.appendChild(text(document.createElement('h3'), 'Következő 36 óra'));
      var hourly = document.createElement('div'); hourly.className = 'launcher-hourly-strip';
      (weather.hourly || []).forEach(function (entry) {
        var card = document.createElement('button'); card.type = 'button'; card.className = 'launcher-hour-card';
        card.setAttribute('aria-label', hourLabel(entry.time) + ', ' + Math.round(Number(entry.temperature)) + ' fok');
        card.innerHTML = '<strong></strong><span class="launcher-hour-icon"></span><b></b><small></small>';
        text(card.querySelector('strong'), hourLabel(entry.time)); text(card.querySelector('.launcher-hour-icon'), weatherIcon(entry.code));
        text(card.querySelector('b'), Math.round(Number(entry.temperature)) + '°');
        text(card.querySelector('small'), 'Eső ' + Math.round(Number(entry.precipitationProbability || 0)) + '% · ' + Math.round(Number(entry.windSpeed || 0)) + ' km/h');
        hourly.appendChild(card);
      });
      body.appendChild(hourly);
      body.appendChild(text(document.createElement('h3'), 'Heti előrejelzés'));
      var weekly = document.createElement('div'); weekly.className = 'launcher-weekly-grid';
      (weather.daily || []).forEach(function (entry) {
        var card = document.createElement('button'); card.type = 'button'; card.className = 'launcher-day-card';
        card.setAttribute('aria-label', dayLabel(entry.date) + ', ' + Math.round(Number(entry.min)) + ' és ' + Math.round(Number(entry.max)) + ' fok között');
        card.innerHTML = '<strong></strong><span class="launcher-day-icon"></span><b></b><small></small>';
        text(card.querySelector('strong'), dayLabel(entry.date)); text(card.querySelector('.launcher-day-icon'), weatherIcon(entry.code));
        text(card.querySelector('b'), Math.round(Number(entry.min)) + '° / ' + Math.round(Number(entry.max)) + '°');
        text(card.querySelector('small'), 'Csapadék esélye: ' + Math.round(Number(entry.precipitationProbability || 0)) + '%');
        weekly.appendChild(card);
      });
      body.appendChild(weekly);
    }
    function loadWeather() {
      var host = root.querySelector('.launcher-weather');
      if (!data.config.settings.weatherEnabled) { host.hidden = true; return; }
      requestWeatherCached().then(function (result) {
        if (!result.enabled) { host.hidden = true; return; }
        weatherData = result.weather;
        host.hidden = false; host.textContent = '';
        var icon = text(document.createElement('span'), weatherIcon(result.weather.code)); icon.className = 'launcher-weather-icon'; host.appendChild(icon);
        var current = result.weather.current || {};
        host.appendChild(text(document.createElement('span'), (result.weather.label ? result.weather.label + ' · ' : '') + Math.round(Number(current.temperature == null ? result.weather.max : current.temperature)) + '° · min ' + Math.round(result.weather.min) + '° / max ' + Math.round(result.weather.max) + '°'));
      }, function () { host.hidden = true; });
    }
    function setWallpaper(retrySelection) {
      var settings = data.config.settings; var wallpaper = root.querySelector('.launcher-wallpaper');
      root.querySelector('.launcher-shell').style.setProperty('--launcher-dim', String(settings.wallpaperDimPercent / 100));
      if (wallpaperTimer) { global.clearTimeout(wallpaperTimer); wallpaperTimer = null; }
      if (!settings.wallpaperEnabled || !settings.wallpaperUrls.length) { wallpaper.style.backgroundImage = ''; wallpaperActiveKey = ''; return; }
      var now = Date.now();
      var intervalMs = Math.max(60000, Number(settings.wallpaperIntervalMinutes || 5) * 60000);
      var currentState = matchingWallpaperState(settings);
      var imageIndex = currentState ? currentState.index : 0;
      var selectedAt = currentState ? currentState.selectedAt : now;
      if (currentState && !retrySelection && settings.wallpaperUrls.length > 1 && now - selectedAt >= intervalMs) {
        imageIndex = (imageIndex + 1) % settings.wallpaperUrls.length;
        selectedAt = now;
        currentState = null;
      }
      var originalUrl = settings.wallpaperUrls[imageIndex];
      var nextKey = imageIndex + '|' + wallpaperKey(originalUrl);
      var previousDisplayUrl = currentState && currentState.key === nextKey ? currentState.displayUrl : '';
      currentState = rememberWallpaper(imageIndex, originalUrl, selectedAt, previousDisplayUrl);
      function scheduleNextWallpaper(retryFailed) {
        // Reloading the same single image every minute used to cost tens of
        // megabytes of decode memory for no visual change. A failed first load
        // still gets a bounded retry so a temporary outage is not permanent.
        if (settings.wallpaperUrls.length > 1 || retryFailed) {
          var remaining = Math.max(1000, selectedAt + intervalMs - Date.now());
          wallpaperTimer = global.setTimeout(function () { setWallpaper(retryFailed); }, retryFailed ? 60000 : remaining);
        }
      }
      if (wallpaperActiveKey === nextKey && wallpaper.style.backgroundImage) { scheduleNextWallpaper(false); return; }
      var wallpaperSources = [];
      function addWallpaperSource(value) { if (value && wallpaperSources.indexOf(value) < 0) wallpaperSources.push(value); }
      if (mode === 'tv') addWallpaperSource(localWallpaperUrl(originalUrl));
      addWallpaperSource(currentState.displayUrl);
      if (mode === 'tv' && apiBase) addWallpaperSource(apiBase + '/api/launcher/wallpaper?index=' + imageIndex + '&v=' + encodeURIComponent(wallpaperKey(originalUrl)));
      addWallpaperSource(optimizedWallpaperUrl(originalUrl));
      var loadToken = ++wallpaperLoadToken;
      function loadWallpaper(sourceIndex) {
        var wallpaperUrl = wallpaperSources[sourceIndex];
        if (loadToken !== wallpaperLoadToken) return;
        if (!wallpaperUrl) { scheduleNextWallpaper(true); return; }
        var preload = new Image();
        try { preload.decoding = 'async'; } catch (ignore) {}
        preload.onload = function () {
          if (loadToken !== wallpaperLoadToken) return;
          // Keep the currently displayed image until the next one is decoded;
          // changing backgroundImage before that caused a visible blank gap.
          wallpaper.style.backgroundImage = 'url(' + JSON.stringify(wallpaperUrl) + ')';
          wallpaperActiveKey = nextKey;
          rememberWallpaper(imageIndex, originalUrl, selectedAt, wallpaperUrl);
          if (global.LauncherImageCache && !/^(blob|data):/.test(wallpaperUrl)) {
            global.LauncherImageCache.fetchAndStore('wallpaper:' + nextKey, wallpaperUrl, 6000, { source: optimizedWallpaperUrl(originalUrl) }).then(function () { global.LauncherImageCache.trim(64); }, function () {});
          }
          scheduleNextWallpaper(false);
        };
        preload.onerror = function () { loadWallpaper(sourceIndex + 1); };
        preload.src = wallpaperUrl;
      }
      if (global.LauncherImageCache) {
        global.LauncherImageCache.getUrl('wallpaper:' + nextKey, { source: optimizedWallpaperUrl(originalUrl), allowStale: true }).then(function (url) {
          if (url) wallpaperSources.unshift(url);
          loadWallpaper(0);
        });
      } else loadWallpaper(0);
    }
    function applyDisplayPreferences(settings) {
      document.body.classList.toggle('launcher-motion-disabled', settings.animationsEnabled === false);
      document.body.classList.toggle('launcher-effects-disabled', settings.visualEffectsEnabled === false);
    }
    function setPresentation() {
      var percent = Number(data.config.settings.focusScalePercent || 10);
      var shellNode = root.querySelector('.launcher-shell');
      shellNode.style.setProperty('--launcher-focus-scale', String(1 + percent / 100));
      if (mode === 'tv') {
        // Matches the five-column TV CSS without forcing a layout measurement.
        var widest = Math.max(0, (global.innerWidth - 288) / 5);
        shellNode.style.setProperty('--launcher-focus-safe', Math.max(22, Math.ceil(widest * percent / 200) + 8) + 'px');
      }
      applyBootPreferences(data.config.settings);
    }
    function refreshPreviews() {
      if (previewTimer) { global.clearTimeout(previewTimer); previewTimer = null; }
      previewJobs.forEach(function (timer) { global.clearTimeout(timer); }); previewJobs = [];
      if (!data.config.settings.cameraPreviewsEnabled) return;
      if (document.hidden) { previewTimer = global.setTimeout(refreshPreviews, 60000); return; }
      Array.prototype.forEach.call(root.querySelectorAll('img[data-preview-url]'), function (image, index) {
        previewJobs.push(global.setTimeout(function () {
          if (document.documentElement.contains(image) && typeof image.__launcherRefresh === 'function') image.__launcherRefresh();
        }, index * 450));
      });
      previewTimer = global.setTimeout(refreshPreviews, 60000);
    }
    function schedulePreviews(delay) {
      stopPreviewWork();
      var startDelay = typeof delay === 'number' ? delay : (mode === 'tv' ? 900 : 0);
      previewTimer = global.setTimeout(refreshPreviews, startDelay);
    }
    function scheduleFullViewWork() {
      if (fullWorkTimer) global.clearTimeout(fullWorkTimer);
      fullWorkTimer = global.setTimeout(function () {
        fullWorkTimer = null;
        if (!data || viewMode !== 'full' || document.hidden || parked) return;
        setWallpaper(); loadWeather(); schedulePreviews();
      }, mode === 'tv' ? 120 : 0);
    }
    function renderAllApps(filter) {
      var grid = root.querySelector('.launcher-app-grid'); grid.textContent = '';
      var needle = String(filter || '').toLocaleLowerCase();
      data.apps.filter(function (app) { return !needle || app.title.toLocaleLowerCase().indexOf(needle) >= 0 || app.id.toLocaleLowerCase().indexOf(needle) >= 0; }).forEach(function (app) {
        grid.appendChild(makeTile({ type: 'app', targetId: app.id, label: app.title, visible: true }, app, null, appPickerActive ? function () {
          root.querySelector('#launcher-add-tile-target').value = app.id;
          root.querySelector('#launcher-add-tile-app-picked').textContent = app.title;
          if (!root.querySelector('#launcher-add-tile-label').value.trim()) root.querySelector('#launcher-add-tile-label').value = app.title;
          appPickerActive = false; openOverlay('launcher-add-tile'); root.querySelector('#launcher-add-tile-label').focus();
        } : null));
      });
    }
    function showDiagnostics() {
      openOverlay('launcher-diagnostics');
      var body = root.querySelector('.launcher-diagnostics-body'); body.textContent = 'TV-adatok lekérése…';
      request('/api/launcher/diagnostics', 'GET').then(function (result) {
        var diag = result.diagnostics; body.textContent = ''; body.className = 'launcher-diagnostics-body launcher-diag-grid';
        function card(title, value) { var item = document.createElement('div'); item.className = 'launcher-diag-card'; item.appendChild(text(document.createElement('strong'), title)); item.appendChild(text(document.createElement('span'), value)); body.appendChild(item); }
        card('CPU terhelés', diag.cpuPercent == null ? 'n/a' : Number(diag.cpuPercent).toFixed(1).replace('.0', '') + '%');
        card('Load average', (diag.load || []).join(' · ') || 'n/a');
        card('Memória', formatKiB(diag.memory.usedKiB) + ' / ' + formatKiB(diag.memory.totalKiB));
        card('CPU hőmérséklet', diag.temperatureC == null ? 'n/a' : diag.temperatureC + ' °C');
        card('Tárhely', (diag.disks || []).map(function (disk) { return disk.mount + ' ' + disk.percent; }).join(' · ') || 'n/a');
        var processes = document.createElement('section'); processes.className = 'launcher-diag-card launcher-processes';
        processes.appendChild(text(document.createElement('strong'), 'Leginkább terhelő folyamatok'));
        var table = document.createElement('table'); table.className = 'launcher-process-table';
        table.innerHTML = '<thead><tr><th>PID</th><th>Felhasználó</th><th>CPU</th><th>Memória</th><th>Folyamat</th></tr></thead><tbody></tbody>';
        var rows = diag.processRows || [];
        rows.forEach(function (process) {
          var row = document.createElement('tr');
          [process.pid, process.user, process.cpu ? process.cpu + '%' : '–', process.memory ? process.memory + '%' : '–', process.command].forEach(function (value) { row.appendChild(text(document.createElement('td'), value || '–')); });
          table.querySelector('tbody').appendChild(row);
        });
        if (!rows.length) { var emptyRow = document.createElement('tr'); var emptyCell = text(document.createElement('td'), 'Nincs elérhető folyamatadat.'); emptyCell.colSpan = 5; emptyRow.appendChild(emptyCell); table.querySelector('tbody').appendChild(emptyRow); }
        processes.appendChild(table); body.appendChild(processes);
      }, function (error) { body.textContent = error.message; });
    }
    function renderSettingsSummary() {
      var body = root.querySelector('.launcher-settings-body');
      var focused = body.contains(document.activeElement) && document.activeElement.getAttribute('data-settings-focus');
      body.textContent = '';
      var nav = document.createElement('nav'); nav.className = 'launcher-settings-nav'; nav.setAttribute('aria-label', 'Beállításcsoportok');
      var panels = document.createElement('div'); panels.className = 'launcher-settings-panels';
      body.appendChild(nav); body.appendChild(panels);
      var sections = [];
      function selectPage(title) {
        settingsPage = title;
        sections.forEach(function (entry) {
          var active = entry.title === title;
          entry.section.hidden = !active; entry.button.setAttribute('aria-selected', active ? 'true' : 'false');
        });
      }
      function saveConfig(next, message) {
        return request('/api/launcher/config', 'POST', next).then(function (result) { data.config = result.config; render(); toast(message || 'A beállítás elmentve.'); }, function (error) { toast(error.message, true); throw error; });
      }
      function settingSection(title) {
        var section = document.createElement('section'); section.className = 'launcher-settings-section';
        section.appendChild(text(document.createElement('h3'), title)); panels.appendChild(section);
        var button = text(document.createElement('button'), title); button.type = 'button';
        button.setAttribute('data-settings-focus', 'nav:' + title);
        button.addEventListener('focus', function () { selectPage(title); });
        button.addEventListener('click', function () { selectPage(title); focusNode(visibleFocusables(section)[0]); });
        nav.appendChild(button); sections.push({title:title, section:section, button:button});
        return section;
      }
      function addSelect(section, label, values, current, onChange) {
        var wrapper = document.createElement('label'); wrapper.className = 'launcher-setting-toggle'; wrapper.appendChild(text(document.createElement('span'), label));
        var select = document.createElement('select'); values.forEach(function (entry) { var option = document.createElement('option'); option.value = String(entry[0]); option.textContent = entry[1]; select.appendChild(option); }); select.value = String(current); select.addEventListener('change', function () { onChange(select.value); }); wrapper.appendChild(select); section.appendChild(wrapper);
      }
      var homeLaunchMode = data.config.settings.homeLaunchMode || 'split';
      var behaviorSection = settingSection('Indítás és Home');
      var editorLabel = document.createElement('label'); editorLabel.className = 'launcher-setting-toggle';
      var editorToggle = document.createElement('input'); editorToggle.type = 'checkbox'; editorToggle.checked = data.config.settings.editorModeEnabled !== false;
      editorLabel.appendChild(editorToggle); editorLabel.appendChild(text(document.createElement('span'), 'TV-szerkesztő mód (soronként + csempe)'));
      editorToggle.addEventListener('change', function () {
        var next = deepCopy(data.config); next.settings.editorModeEnabled = editorToggle.checked;
        request('/api/launcher/config', 'POST', next).then(function (result) { data.config = result.config; render(); toast(editorToggle.checked ? 'A TV-szerkesztő mód bekapcsolva.' : 'A TV-szerkesztő mód kikapcsolva.'); }, function (error) { editorToggle.checked = data.config.settings.editorModeEnabled !== false; toast(error.message, true); });
      });
      behaviorSection.appendChild(editorLabel);
      var homeLabel = document.createElement('label'); homeLabel.className = 'launcher-setting-toggle';
      var homeToggle = document.createElement('input'); homeToggle.type = 'checkbox'; homeToggle.checked = data.config.settings.defaultHomeEnabled === true;
      homeLabel.appendChild(homeToggle); homeLabel.appendChild(text(document.createElement('span'), 'Launcher legyen az alapértelmezett kezdőképernyő'));
      homeToggle.addEventListener('change', function () {
        var next = deepCopy(data.config); next.settings.defaultHomeEnabled = homeToggle.checked;
        request('/api/launcher/config', 'POST', next).then(function (result) { data.config = result.config; render(); toast(homeToggle.checked ? 'Az automatikus launcher bekapcsolva.' : 'Az automatikus launcher kikapcsolva.'); }, function (error) { homeToggle.checked = data.config.settings.defaultHomeEnabled === true; toast(error.message, true); });
      });
      behaviorSection.appendChild(homeLabel);
      addSelect(behaviorSection, 'Home gomb indítási módja', [
        ['split', 'Rövid Home: quick · hosszú Home: teljes'],
        ['full', 'Mindig teljes launcher'],
        ['overlay', 'Mindig quick launcher']
      ], homeLaunchMode, function (value) {
        var next = deepCopy(data.config); next.settings.homeLaunchMode = value;
        saveConfig(next, 'A Home gomb indítási módja elmentve.');
      });
      addSelect(behaviorSection, 'Teljes launcher megjelenítése', [
        ['app', 'Teljes alkalmazás (előre betölthető)'],
        ['overlay', 'Overlay (a mögöttes app megmarad)']
      ], data.config.settings.fullLauncherPresentation || 'app', function (value) {
        var next = deepCopy(data.config); next.settings.fullLauncherPresentation = value;
        saveConfig(next, 'A teljes launcher következő Home megnyitása már ezt a módot használja.');
      });
      function addSettingsToggle(key, label, enabledMessage, disabledMessage, targetSection) {
        var settingLabel = document.createElement('label'); settingLabel.className = 'launcher-setting-toggle';
        var settingToggle = document.createElement('input'); settingToggle.type = 'checkbox'; settingToggle.checked = data.config.settings[key] !== false;
        settingLabel.appendChild(settingToggle); settingLabel.appendChild(text(document.createElement('span'), label));
        settingToggle.addEventListener('change', function () {
          var next = deepCopy(data.config); next.settings[key] = settingToggle.checked;
          request('/api/launcher/config', 'POST', next).then(function (result) { data.config = result.config; render(); toast(settingToggle.checked ? enabledMessage : disabledMessage); }, function (error) { settingToggle.checked = data.config.settings[key] !== false; toast(error.message, true); });
        });
        (targetSection || behaviorSection).appendChild(settingLabel);
      }
      addSettingsToggle('bootOverlayEnabled', 'Fekete induló takarás', 'Az induló takarás bekapcsolva.', 'Az induló takarás kikapcsolva.');
      var bootMaxLabel = document.createElement('label'); bootMaxLabel.className = 'launcher-setting-toggle';
      bootMaxLabel.appendChild(text(document.createElement('span'), 'Induló takarás maximuma'));
      var bootMax = document.createElement('select');
      for (var second = 1; second <= 10; second += 1) { var secondOption = document.createElement('option'); secondOption.value = String(second); secondOption.textContent = second + ' mp'; bootMax.appendChild(secondOption); }
      bootMax.value = String(data.config.settings.bootOverlayMaxSeconds || 2);
      bootMax.addEventListener('change', function () {
        var next = deepCopy(data.config); next.settings.bootOverlayMaxSeconds = Number(bootMax.value);
        request('/api/launcher/config', 'POST', next).then(function (result) { data.config = result.config; render(); toast('Az induló takarás időkorlátja elmentve.'); }, function (error) { toast(error.message, true); });
      });
      bootMaxLabel.appendChild(bootMax); behaviorSection.appendChild(bootMaxLabel);
      var displaySection = settingSection('Megjelenés');
      addSettingsToggle('animationsEnabled', 'Animációk és átmenetek', 'Az animációk bekapcsolva.', 'Az animációk kikapcsolva.', displaySection);
      addSettingsToggle('visualEffectsEnabled', 'Látványeffektek (panelek áttetszősége, elmosás, árnyék)', 'A látványeffektek bekapcsolva.', 'A látványeffektek kikapcsolva. A háttérkép és az átlátszó csempefelirat megmarad.', displaySection);
      var resumeLabel = document.createElement('label'); resumeLabel.className = 'launcher-setting-toggle';
      var resumeToggle = document.createElement('input'); resumeToggle.type = 'checkbox'; resumeToggle.checked = data.config.settings.resumeLastAppOnPowerEnabled === true;
      resumeLabel.appendChild(resumeToggle); resumeLabel.appendChild(text(document.createElement('span'), 'Bekapcsoláskor az utolsó app folytatása'));
      resumeToggle.addEventListener('change', function () {
        var next = deepCopy(data.config); next.settings.resumeLastAppOnPowerEnabled = resumeToggle.checked;
        request('/api/launcher/config', 'POST', next).then(function (result) { data.config = result.config; render(); toast(resumeToggle.checked ? 'Bekapcsoláskor az utolsó app folytatódik.' : 'Bekapcsoláskor a launcher indul.'); }, function (error) { resumeToggle.checked = data.config.settings.resumeLastAppOnPowerEnabled === true; toast(error.message, true); });
      });
      behaviorSection.appendChild(resumeLabel);
      var appearanceSection = settingSection('Háttér és kamerák');
      addSelect(displaySection, 'Kijelölt csempe nagyítása', [[5,'5%'],[10,'10%'],[15,'15%'],[20,'20%']], data.config.settings.focusScalePercent || 10, function (value) { var next = deepCopy(data.config); next.settings.focusScalePercent = Number(value); saveConfig(next, 'A nagyítás elmentve.'); });
      addSelect(appearanceSection, 'Háttérkép váltási ideje', [[1,'1 perc'],[2,'2 perc'],[3,'3 perc'],[4,'4 perc'],[5,'5 perc'],[6,'6 perc'],[7,'7 perc'],[8,'8 perc'],[9,'9 perc'],[10,'10 perc']], data.config.settings.wallpaperIntervalMinutes, function (value) { var next = deepCopy(data.config); next.settings.wallpaperIntervalMinutes = Number(value); saveConfig(next, 'A háttérkép ideje elmentve.'); });
      addSelect(appearanceSection, 'Háttér sötétítése', [[0,'0%'],[15,'15%'],[30,'30%'],[42,'42%'],[55,'55%'],[70,'70%'],[85,'85%']], data.config.settings.wallpaperDimPercent, function (value) { var next = deepCopy(data.config); next.settings.wallpaperDimPercent = Number(value); saveConfig(next, 'A háttér fényereje elmentve.'); });
      function addAppearanceToggle(key, label, targetSection) {
        var wrapper = document.createElement('label'); wrapper.className = 'launcher-setting-toggle'; var input = document.createElement('input'); input.type = 'checkbox'; input.checked = data.config.settings[key] === true; wrapper.appendChild(input); wrapper.appendChild(text(document.createElement('span'), label));
        input.addEventListener('change', function () { var next = deepCopy(data.config); next.settings[key] = input.checked; saveConfig(next, label + ': ' + (input.checked ? 'bekapcsolva' : 'kikapcsolva') + '.'); }); (targetSection || appearanceSection).appendChild(wrapper);
      }
      addAppearanceToggle('wallpaperEnabled', 'Háttérképváltás'); addAppearanceToggle('cameraPreviewsEnabled', 'Kamera-előnézetek'); var weatherSection = settingSection('Időjárás'); addAppearanceToggle('weatherEnabled', 'Időjárás', weatherSection);
      var wallpaperLabel = document.createElement('label'); wallpaperLabel.className = 'launcher-settings-field'; wallpaperLabel.appendChild(text(document.createElement('span'), 'Háttérkép URL-ek · soronként egy')); var wallpaperUrls = document.createElement('textarea'); wallpaperUrls.rows = 5; wallpaperUrls.value = data.config.settings.wallpaperUrls.join('\n'); wallpaperLabel.appendChild(wallpaperUrls); appearanceSection.appendChild(wallpaperLabel);
      var wallpaperSave = text(document.createElement('button'), 'Háttérkép-lista mentése'); wallpaperSave.type = 'button'; wallpaperSave.className = 'launcher-icon-action'; wallpaperSave.addEventListener('click', function () { var next = deepCopy(data.config); next.settings.wallpaperUrls = wallpaperUrls.value.split(/\r?\n/).map(function (value) { return value.trim(); }).filter(Boolean); saveConfig(next, 'A háttérkép-lista elmentve.'); }); appearanceSection.appendChild(wallpaperSave);
      var weatherGrid = document.createElement('div'); weatherGrid.className = 'launcher-settings-grid';
      [['Hely neve','text','weatherLabel'],['Szélesség','number','latitude'],['Hosszúság','number','longitude']].forEach(function (entry) { var label = document.createElement('label'); label.className = 'launcher-settings-field'; label.appendChild(text(document.createElement('span'), entry[0])); var input = document.createElement('input'); input.type = entry[1]; input.value = data.config.settings[entry[2]]; input.setAttribute('data-setting', entry[2]); label.appendChild(input); weatherGrid.appendChild(label); }); weatherSection.appendChild(weatherGrid);
      var weatherSave = text(document.createElement('button'), 'Időjárási hely mentése'); weatherSave.type = 'button'; weatherSave.className = 'launcher-icon-action'; weatherSave.addEventListener('click', function () { var next = deepCopy(data.config); Array.prototype.forEach.call(weatherGrid.querySelectorAll('input'), function (input) { next.settings[input.getAttribute('data-setting')] = input.type === 'number' ? Number(input.value) : input.value.trim(); }); saveConfig(next, 'Az időjárási hely elmentve.'); }); weatherSection.appendChild(weatherSave);
      var rowsSection = settingSection('Sorok és csempék'); rowsSection.appendChild(editorLabel);
      data.config.rows.forEach(function (row, index) {
        var card = document.createElement('div'); card.className = 'launcher-settings-row'; var visible = document.createElement('input'); visible.type = 'checkbox'; visible.checked = row.visible; card.appendChild(visible); card.appendChild(text(document.createElement('strong'), row.title));
        var up = text(document.createElement('button'), '↑'); var down = text(document.createElement('button'), '↓'); up.type = down.type = 'button'; up.disabled = index === 0; down.disabled = index === data.config.rows.length - 1; card.appendChild(up); card.appendChild(down);
        visible.addEventListener('change', function () { var next = deepCopy(data.config); next.rows[index].visible = visible.checked; saveConfig(next, row.title + (visible.checked ? ' megjelenítve.' : ' elrejtve.')); });
        function moveRow(delta) { var next = deepCopy(data.config); var moved = next.rows.splice(index, 1)[0]; next.rows.splice(index + delta, 0, moved); saveConfig(next, 'A sor új helye elmentve.'); }
        up.addEventListener('click', function () { moveRow(-1); }); down.addEventListener('click', function () { moveRow(1); }); rowsSection.appendChild(card);
      });
      var hidden = [];
      data.config.rows.forEach(function (row) { row.items.forEach(function (item) { if (!item.visible) hidden.push(item); }); });
      if (hidden.length) {
        var hiddenSection = rowsSection; hiddenSection.appendChild(text(document.createElement('h3'), 'Elrejtett csempék'));
        var heading = text(document.createElement('p'), 'A rendszer-csempék itt újra megjeleníthetők.'); hiddenSection.appendChild(heading);
        var list = document.createElement('div'); list.className = 'launcher-hidden-items';
        hidden.forEach(function (item) {
          var button = text(document.createElement('button'), item.label + ' · megjelenítés'); button.type = 'button'; button.className = 'launcher-icon-action';
          button.addEventListener('click', function () {
            var next = deepCopy(data.config); var target = findConfigItem(item.id, next); if (target) target.visible = true;
            request('/api/launcher/config', 'POST', next).then(function (result) { data.config = result.config; render(); toast(item.label + ' újra látható.'); }, function (error) { toast(error.message, true); });
          });
          list.appendChild(button);
        });
        hiddenSection.appendChild(list);
      }
      var actionsSection = settingSection('Karbantartás');
      if (options.onConnection) { var button = text(document.createElement('button'), 'NAS-kapcsolat módosítása'); button.className = 'launcher-icon-action'; button.addEventListener('click', options.onConnection); actionsSection.appendChild(button); }
      if (mode === 'tv') {
        var restartButton = text(document.createElement('button'), 'Launcher alkalmazás teljes újraindítása');
        restartButton.type = 'button'; restartButton.className = 'launcher-icon-action launcher-settings-restart';
        restartButton.title = 'Leállítja a launcher WAM-folyamatát, majd tisztán újraindítja a teljes nézetet';
        restartButton.addEventListener('click', function () {
          if (restartButton.disabled) return;
          restartButton.disabled = true; restartButton.textContent = 'Újraindítás…';
          toast('A launcher teljesen újraindul…');
          request('/api/launcher/restart', 'POST', {}).catch(function (error) {
            restartButton.disabled = false; restartButton.textContent = 'Launcher alkalmazás teljes újraindítása'; toast(error.message, true);
          });
        });
        actionsSection.appendChild(restartButton);
      }
      var exitButton = text(document.createElement('button'), 'Kilépés az LG Home menübe');
      exitButton.type = 'button'; exitButton.className = 'launcher-icon-action launcher-settings-exit';
      exitButton.disabled = data.config.settings.defaultHomeEnabled === true;
      exitButton.title = exitButton.disabled ? 'Előbb kapcsold ki az Alapértelmezett kezdőképernyő beállítást.' : 'Visszatérés a gyári webOS kezdőképernyőre';
      exitButton.addEventListener('click', function () {
        request('/api/launcher/system-home', 'POST', {}).then(function () { toast('Az LG Home menü megnyitva.'); }, function (error) { toast(error.message, true); });
      });
      actionsSection.appendChild(exitButton);
      actionsSection.appendChild(text(document.createElement('p'), 'A kapcsolók és választók azonnal mentődnek. A szöveges mezők alatt külön Mentés gomb található.'));
      sections.forEach(function (entry) {
        // Native select popups and tiny checkboxes are awkward on a TV remote.
        // Keep the same change handlers, expose a single large focus target.
        Array.prototype.forEach.call(entry.section.querySelectorAll('select,input[type="checkbox"]'), function (input) {
          var choice = text(document.createElement('button'), ''); choice.type = 'button'; choice.className = 'launcher-setting-choice';
          var label = input.parentNode.querySelector('span,strong');
          if (label) choice.setAttribute('aria-label', label.textContent);
          function updateLabel() {
            if (input.tagName === 'SELECT') choice.textContent = '‹  ' + input.options[input.selectedIndex].textContent + '  ›';
            else { choice.textContent = input.checked ? 'Bekapcsolva' : 'Kikapcsolva'; choice.setAttribute('role', 'switch'); choice.setAttribute('aria-checked', input.checked ? 'true' : 'false'); }
          }
          choice.__launcherChangeChoice = function (delta) {
            if (input.tagName === 'SELECT') input.selectedIndex = (input.selectedIndex + delta + input.options.length) % input.options.length;
            else input.checked = !input.checked;
            updateLabel();
            var changed = document.createEvent('HTMLEvents'); changed.initEvent('change', true, false); input.dispatchEvent(changed);
          };
          choice.addEventListener('click', function () { choice.__launcherChangeChoice(1); });
          input.hidden = true; input.parentNode.insertBefore(choice, input); updateLabel();
        });
        Array.prototype.forEach.call(entry.section.querySelectorAll('button,input:not([hidden]),textarea'), function (control, index) {
          control.setAttribute('data-settings-focus', entry.title + ':' + index);
        });
      });
      if (!sections.some(function (entry) { return entry.title === settingsPage; })) settingsPage = sections[0].title;
      selectPage(settingsPage);
      var help = text(document.createElement('p'), '↑↓ Lépkedés · ← Csoportok · → / OK Választás · Back Vissza');
      help.className = 'launcher-settings-help'; body.appendChild(help);
      if (focused) {
        var restored = Array.prototype.filter.call(body.querySelectorAll('[data-settings-focus]'), function (node) { return node.getAttribute('data-settings-focus') === focused; })[0];
        focusNode(restored || nav.querySelector('[aria-selected="true"]'));
      }
    }
    function fullShell() {
      document.body.classList.remove('launcher-quick-mode', 'launcher-quick-closing');
      quickClosing = false;
      root.innerHTML = '<section class="launcher-shell"><div class="launcher-wallpaper"></div><div class="launcher-shade"></div><div class="launcher-content"><header class="launcher-top"><div><div class="launcher-clock"></div><div class="launcher-date"></div><button type="button" class="launcher-weather" hidden title="Részletes időjárás"></button></div><div class="launcher-top-actions"></div></header><div class="launcher-rows"></div></div><div id="launcher-all-apps" class="launcher-overlay" hidden><section class="launcher-modal launcher-all-apps-modal"><header class="launcher-modal-head"><h2>Összes telepített alkalmazás</h2><button class="launcher-close" type="button">×</button></header><input class="launcher-app-search" type="search" placeholder="Keresés az alkalmazások között…"><div class="launcher-app-grid"></div></section></div><div id="launcher-weather-detail" class="launcher-overlay" hidden><section class="launcher-modal launcher-weather-modal"><header class="launcher-modal-head"><h2>Részletes időjárás</h2><button class="launcher-close" type="button">×</button></header><div class="launcher-weather-body"></div></section></div><div id="launcher-diagnostics" class="launcher-overlay" hidden><section class="launcher-modal"><header class="launcher-modal-head"><h2>TV diagnosztika</h2><button class="launcher-close" type="button">×</button></header><div class="launcher-diagnostics-body"></div></section></div><div id="launcher-settings" class="launcher-overlay" hidden><section class="launcher-modal launcher-settings-modal"><header class="launcher-modal-head"><h2>Launcher beállítások</h2><button class="launcher-close" type="button">×</button></header><div class="launcher-settings-body"></div></section></div><div id="launcher-tile-settings" class="launcher-overlay" hidden><section class="launcher-modal launcher-tile-settings-modal"><header class="launcher-modal-head"><div><h2>Csempe beállításai</h2><p class="launcher-tile-settings-name"></p></div><button class="launcher-close" type="button">×</button></header><form id="launcher-tile-settings-form" class="launcher-tile-settings-form"><label>Ikon / kép mérete<select id="launcher-tile-fit"><option value="small">Kicsi, középen</option><option value="contain">Arányosan, teljes ikon</option><option value="cover">Teljes csempe kitöltése</option></select></label><label>Saját ikon vagy kép URL (opcionális)<input id="launcher-tile-icon-url" type="url" placeholder="https://…"></label><label>Háttérszín (opcionális)<input id="launcher-tile-background" maxlength="7" placeholder="#123456"></label><p class="launcher-admin-small">Rövid OK: indítás · hosszú OK: ez a beállító.</p><div class="launcher-admin-actions"><button type="submit">Mentés</button><button id="launcher-tile-settings-cancel" class="secondary" type="button">Mégse</button></div></form></section></div><div id="launcher-add-tile" class="launcher-overlay" hidden><section class="launcher-modal launcher-tile-settings-modal"><header class="launcher-modal-head"><h2>Csempe hozzáadása</h2><button class="launcher-close" type="button">×</button></header><form id="launcher-add-tile-form" class="launcher-tile-settings-form"><label>Sor<select id="launcher-add-tile-row"></select></label><label>Típus<select id="launcher-add-tile-type"></select></label><label>Felirat<input id="launcher-add-tile-label" maxlength="64" required></label><label id="launcher-add-tile-target-field">Cél<select id="launcher-add-tile-target"></select></label><label id="launcher-add-tile-app-picker-field"><span>Kiválasztott alkalmazás: <b id="launcher-add-tile-app-picked">Nincs kiválasztva</b></span><button id="launcher-add-tile-app-picker" type="button">Alkalmazás kiválasztása</button></label><label id="launcher-add-tile-url-field">Webcím<input id="launcher-add-tile-url" type="url" placeholder="https://…"></label><p class="launcher-admin-small">A sorhoz illő célok jelennek meg; a csempe a sor végére kerül.</p><div class="launcher-admin-actions"><button type="submit">Hozzáadás</button><button id="launcher-add-tile-cancel" class="secondary" type="button">Mégse</button></div></form></section></div><div class="launcher-toast" hidden></div></section>';
      applyRememberedWallpaper();
      var editToolbar = document.createElement('div'); editToolbar.className = 'launcher-edit-toolbar'; editToolbar.hidden = true;
      editToolbar.innerHTML = '<button type="button" data-edit-action="edit" title="Szerkesztés">✎</button><button type="button" data-edit-action="remove" title="Törlés">✕</button>';
      root.querySelector('.launcher-shell').appendChild(editToolbar);
      editToolbar.querySelector('[data-edit-action="edit"]').addEventListener('click', function () { var tile = editMode && root.querySelector('[data-item-id="' + editMode.itemId + '"]'); if (tile) openTileSettings(tile); });
      editToolbar.querySelector('[data-edit-action="remove"]').addEventListener('click', removeOrHideEditedTile);
      var iconKeyLabel = document.createElement('label'); iconKeyLabel.appendChild(document.createTextNode('Beépített, átlátszó ikon'));
      var iconKeySelect = document.createElement('select'); iconKeySelect.id = 'launcher-tile-icon-key';
      var autoOption = document.createElement('option'); autoOption.value = ''; autoOption.textContent = 'Automatikus (egységes, ha ismert)'; iconKeySelect.appendChild(autoOption);
      var installedOption = document.createElement('option'); installedOption.value = 'installed'; installedOption.textContent = 'Gyári alkalmazásikon'; iconKeySelect.appendChild(installedOption);
      ICON_CATALOG.forEach(function (entry) { var option = document.createElement('option'); option.value = entry.key; option.textContent = entry.label; iconKeySelect.appendChild(option); });
      iconKeyLabel.appendChild(iconKeySelect);
      var iconUrlLabel = root.querySelector('#launcher-tile-icon-url').parentNode;
      iconUrlLabel.parentNode.insertBefore(iconKeyLabel, iconUrlLabel);
      iconKeySelect.addEventListener('change', function () { root.querySelector('#launcher-tile-icon-url').value = ''; });
      root.querySelector('#launcher-tile-icon-url').addEventListener('input', function () { if (this.value.trim()) iconKeySelect.value = ''; });
      Array.prototype.forEach.call(root.querySelectorAll('.launcher-close'), function (button) { button.addEventListener('click', closeOverlays); });
      Array.prototype.forEach.call(root.querySelectorAll('.launcher-overlay'), function (overlay) { overlay.addEventListener('click', function (event) { if (event.target === overlay) closeOverlays(); }); });
      root.querySelector('.launcher-app-search').addEventListener('input', function () { renderAllApps(this.value); });
      root.querySelector('.launcher-weather').addEventListener('click', function () { if (weatherData) { renderWeatherDetails(weatherData); openOverlay('launcher-weather-detail'); } });
      root.querySelector('#launcher-tile-settings-form').addEventListener('submit', saveTileSettings);
      root.querySelector('#launcher-tile-settings-cancel').addEventListener('click', closeOverlays);
      root.querySelector('#launcher-add-tile-form').addEventListener('submit', saveAddTile);
      root.querySelector('#launcher-add-tile-cancel').addEventListener('click', closeOverlays);
      root.querySelector('#launcher-add-tile-app-picker').addEventListener('click', function () { appPickerActive = true; renderAllApps(''); openOverlay('launcher-all-apps'); });
      root.querySelector('#launcher-add-tile-row').addEventListener('change', function () { openAddTile(this.value); });
      root.querySelector('#launcher-add-tile-type').addEventListener('change', updateAddTileFields);
    }
    function quickShell() {
      stopFullViewWork();
      quickClosing = false;
      quickFullOverlayReturn = false;
      document.body.classList.add('launcher-quick-mode');
      document.body.classList.remove('launcher-quick-closing');
      var cover = document.getElementById('launcher-boot'); if (cover) cover.hidden = true;
      root.innerHTML = '<section class="launcher-quick-shell" aria-label="Gyorsindító"><header class="launcher-quick-upper"><nav class="launcher-quick-categories" aria-label="Kategóriák"></nav><aside class="launcher-quick-status" aria-label="Pontos idő és dátum"><strong class="launcher-quick-status-time">--:--</strong><span class="launcher-quick-status-date"></span></aside></header><section class="launcher-quick-lower" aria-label="Kategóriatartalom"><div class="launcher-quick-tabs" hidden></div><div class="launcher-quick-items" aria-label="Az aktuális kategória elemei"></div></section><div id="launcher-settings" class="launcher-overlay" hidden><section class="launcher-modal launcher-settings-modal"><header class="launcher-modal-head"><h2>Launcher beállítások</h2><button class="launcher-close" type="button">×</button></header><div class="launcher-settings-body"></div></section></div><div class="launcher-toast" hidden></div></section>';
      root.querySelector('.launcher-close').addEventListener('click', closeOverlays);
      root.querySelector('#launcher-settings').addEventListener('click', function (event) { if (event.target === this) closeOverlays(); });
    }
    function shell() {
      if (viewMode === 'overlay') quickShell(); else fullShell();
      // Place the full-screen settings outside the animated/blurred quick panel.
      var settings = root.querySelector('#launcher-settings'); if (settings) root.appendChild(settings);
    }
    function render() {
      applyDisplayPreferences(data.config.settings);
      if (viewMode === 'overlay') renderQuick();
      else { renderRows(); renderTopActions(); setPresentation(); scheduleFullViewWork(); }
      var settingsOverlay = root.querySelector('#launcher-settings');
      if (settingsOverlay && !settingsOverlay.hidden) renderSettingsSummary();
      if (bootActive) { bootRenderReady = true; bootFailsafe(); bootAfterFirstPaint(); }
      if (mode === 'tv' && !hasUsableFocus()) {
        global.setTimeout(function () { focusNode(root.querySelector('.launcher-tile')); }, 0);
      }
    }
    function reload() {
      return request('/api/launcher/state', 'GET').then(function (result) {
        data = { config: result.config, apps: result.apps || [], presets: result.presets || [] };
        applyBootPreferences(data.config.settings);
        shell(); render();
        if (viewMode === 'full') {
          renderClock();
          if (clockTimer) global.clearInterval(clockTimer); clockTimer = global.setInterval(renderClock, 1000);
        }
        if (typeof options.onReady === 'function') options.onReady(controller);
        return controller;
      }, function (error) {
        root.innerHTML = '<div class="launcher-connect"><p>' + String(error.message).replace(/[<>]/g, '') + '</p></div>';
        bootPending = 0; bootWallpaperReady = true; bootRenderReady = true; bootCheck(); throw error;
      });
    }
    function setViewMode(nextMode) {
      var next = nextMode === 'overlay' ? 'overlay' : 'full';
      if (!data) { viewMode = next; return; }
      if (next === viewMode) return;
      stopFullViewWork();
      viewMode = next;
      bootActive = false;
      shell(); render();
      if (viewMode === 'full') {
        renderClock();
        clockTimer = global.setInterval(renderClock, 1000);
      }
    }
    var controller = {
      prepareResume: function () { cancelPendingPopupPark(); },
      beginResumeLoading: beginResumeLoading,
      cancelResumeLoading: cancelResumeLoading,
      setDisplayPreferences: function (preferences) {
        if (!data || !data.config) return;
        ['animationsEnabled', 'visualEffectsEnabled'].forEach(function (key) {
          if (typeof preferences[key] === 'boolean') data.config.settings[key] = preferences[key];
        });
        applyDisplayPreferences(data.config.settings);
      },
      reload: reload,
      useState: function (result) {
        if (!result || !result.config) return;
        data = { config: deepCopy(result.config), apps: deepCopy(result.apps || []), presets: deepCopy(result.presets || []) };
        applyBootPreferences(data.config.settings); render();
        if (viewMode === 'full') renderClock();
      },
      resume: function () {
        cancelPendingPopupPark();
        // A real launch may arrive while a hidden preload is still reading its
        // initial state. Remember the activation even before there is a UI to
        // resume; reload() will render using this state when the data arrives.
        parked = false; parkRequested = false; quickClosing = false;
        document.body.classList.remove('launcher-parked', 'launcher-quick-closing');
        root.removeAttribute('aria-hidden');
        if (!data) return;
        if (!imageQueueTimer) imageQueueTimer = global.setTimeout(pumpImages, 500);
        if (viewMode === 'overlay') {
          if (quickNeedsRender) renderQuick();
          else {
            focusQuickState(); startQuickClock();
            var category = currentQuickCategory();
            if (category && category.id === 'cameras') schedulePreviews(120);
          }
          return;
        }
        renderClock();
        scheduleFullViewWork();
        if (!clockTimer) clockTimer = global.setInterval(renderClock, 1000);
        if (mode === 'tv' && !hasUsableFocus()) {
          global.setTimeout(function () { focusNode(root.querySelector('.launcher-tile')); }, 0);
        }
      },
      setViewMode: setViewMode,
      suspend: stopFullViewWork,
      viewMode: function () { return viewMode; },
      isQuickOpen: function () { return viewMode === 'overlay' && !quickClosing && !parked; },
      isParked: function () { return parked; },
      park: parkLauncher,
      closeQuick: closeQuick,
      snapshot: function () { var result = deepCopy(data); result.icons = deepCopy(ICON_CATALOG); return result; },
      preview: function (config) { data.config = deepCopy(config); render(); },
      save: function (config) { return request('/api/launcher/config', 'POST', config).then(function (result) { data.config = result.config; render(); return deepCopy(data.config); }); },
      toast: toast
    };
    root.__launcherController = controller;
    root.addEventListener('click', function (event) {
      if (viewMode === 'overlay' && event.target === root) closeQuick();
    });
    installTvNavigation();
    if (!bootActive) { var initialCover = document.getElementById('launcher-boot'); if (initialCover) initialCover.hidden = true; }
    else bootFailsafe();
    reload();
    return controller;
  }

  global.LauncherUI = { init: init };
}(window));
