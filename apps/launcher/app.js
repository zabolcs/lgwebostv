(function () {
  'use strict';

  window.__launcherStartAt = Date.now();

  var ORIGIN_KEY = 'hu.szabi.launcher.control-origin.v1';
  var STATE_KEY = 'hu.szabi.launcher.offline-state.v1';
  var DIRTY_KEY = 'hu.szabi.launcher.offline-config-dirty.v1';
  var LAUNCH_URI = 'luna://com.webos.applicationManager/launch';
  var CAMERA_APP = 'hu.szabi.cameraviewer';
  var OVERLAY_APP = 'hu.szabi.mediaoverlay';
  var bridges = [];
  var controller = null;
  var cachedStateSerialized = loadText(STATE_KEY);
  var cachedState = parseJson(cachedStateSerialized);
  var nasSyncTimer = null;
  var nasSyncActive = false;
  function recordPaint(name) {
    if (typeof window.requestAnimationFrame !== 'function') return;
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { window[name] = Date.now(); });
    });
  }

  function launcherId(value) {
    return value === 'hu.szabi.launcher' || value === 'hu.szabi.launcher.quick' || value === 'hu.szabi.launcher.overlay' || value === 'hu.szabi.launcher.fasttest';
  }

  function parseLaunchEnvelope(raw) {
    try {
      var parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
      for (var depth = 0; parsed && typeof parsed === 'object' && depth < 6; depth += 1) {
        if (Object.prototype.hasOwnProperty.call(parsed, 'launchParams')) parsed = typeof parsed.launchParams === 'string' ? JSON.parse(parsed.launchParams) : parsed.launchParams;
        else if (Object.prototype.hasOwnProperty.call(parsed, 'parameters')) parsed = typeof parsed.parameters === 'string' ? JSON.parse(parsed.parameters) : parsed.parameters;
        else if (parsed.payload && typeof parsed.payload === 'object' && (launcherId(parsed.payload.id) || parsed.payload.params)) parsed = parsed.payload;
        else if (parsed.params && typeof parsed.params === 'object' && (launcherId(parsed.id) || Object.keys(parsed).length === 1)) parsed = parsed.params;
        else break;
      }
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (ignore) { return {}; }
  }
  function params() {
    // This TV exposes webOSSystem.launchParams but leaves it stale/empty on
    // popup cold starts. PalmSystem carries the actual Home mode payload.
    var raw = window.PalmSystem && window.PalmSystem.launchParams;
    if (!raw) raw = window.webOSSystem && window.webOSSystem.launchParams;
    return parseLaunchEnvelope(raw);
  }
  function currentApplicationId() {
    try {
      return String(window.__LAUNCHER_HOST__ && window.__LAUNCHER_HOST__.appId ||
        window.PalmSystem && window.PalmSystem.identifier ||
        window.webOSSystem && window.webOSSystem.identifier || '');
    } catch (ignore) { return ''; }
  }
  function resolveHost(value) {
    var packaged = window.__LAUNCHER_HOST__ && window.__LAUNCHER_HOST__.host;
    if (packaged === 'quick' || packaged === 'full' || packaged === 'full-overlay') return packaged;
    var appId = currentApplicationId();
    if (appId === 'hu.szabi.launcher.overlay') return 'full-overlay';
    if (appId === 'hu.szabi.launcher.quick') return 'quick';
    if (appId === 'hu.szabi.launcher' || appId === 'hu.szabi.launcher.fasttest') return 'full';
    return value && value.host === 'quick' ? 'quick' : 'full';
  }
  function deepCopy(value) { return JSON.parse(JSON.stringify(value)); }
  function loadText(key) { try { return localStorage.getItem(key) || ''; } catch (ignore) { return ''; } }
  function parseJson(value) { try { return JSON.parse(value || 'null'); } catch (ignore) { return null; } }
  function normalize(value) {
    var text = String(value || '').trim().replace(/\/$/, '');
    var match = /^https?:\/\/(10\.[0-9]{1,3}(?:\.[0-9]{1,3}){2}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3})(?::([0-9]{1,5}))?$/.exec(text);
    return match && (!match[2] || (Number(match[2]) > 0 && Number(match[2]) <= 65535)) ? text : '';
  }
  function loadOrigin() { try { return normalize(localStorage.getItem(ORIGIN_KEY)); } catch (ignore) { return ''; } }
  function saveOrigin(value) { try { localStorage.setItem(ORIGIN_KEY, value); } catch (ignore) {} }
  function isDirty() { try { return localStorage.getItem(DIRTY_KEY) === '1'; } catch (ignore) { return false; } }
  function setDirty(value) { try { if (value) localStorage.setItem(DIRTY_KEY, '1'); else localStorage.removeItem(DIRTY_KEY); } catch (ignore) {} }
  function validState(value) { return !!value && typeof value === 'object' && value.config && Array.isArray(value.config.rows) && Array.isArray(value.apps) && Array.isArray(value.presets); }
  if (!validState(cachedState)) { cachedState = null; cachedStateSerialized = ''; }

  function applyLaunchDisplayPreferences(envelope) {
    var preferences = envelope && envelope.displayPreferences;
    if (!preferences || typeof preferences !== 'object') return;
    var checked = {};
    ['animationsEnabled', 'visualEffectsEnabled'].forEach(function (key) {
      if (typeof preferences[key] === 'boolean') {
        checked[key] = preferences[key];
        if (cachedState && cachedState.config && cachedState.config.settings) cachedState.config.settings[key] = preferences[key];
      }
    });
    if (controller && controller.setDisplayPreferences) controller.setDisplayPreferences(checked);
  }
  var launch = params();
  applyLaunchDisplayPreferences(launch);
  var launcherHost = resolveHost(launch);
  var viewMode = launcherHost === 'quick' ? 'overlay' : 'full';
  var prewarmLaunch = launch.source === 'preload';
  var readySignalLaunch = prewarmLaunch || launch.source === 'power-warm';
  var initialHomeRequestId = String(launch.homeRequestId || '');
  var lastHomeRequestId = '';
  var lifecycleParkArmed = false;
  var lifecycleArmTimer = null;
  var backgroundParkTimer = null;
  var backgroundParkGeneration = 0;
  var origin = normalize(launch.controlOrigin) || loadOrigin();
  if (normalize(launch.controlOrigin)) saveOrigin(origin);
  document.documentElement.classList.add(launcherHost === 'quick' ? 'launcher-host-quick' : 'launcher-host-full');
  document.body.classList.add(launcherHost === 'quick' ? 'launcher-quick-host' : 'launcher-full-host');
  if (cachedState && cachedState.config.settings && cachedState.config.settings.animationsEnabled === false) document.body.classList.add('launcher-motion-disabled');
  if (cachedState && cachedState.config.settings && cachedState.config.settings.visualEffectsEnabled === false) document.body.classList.add('launcher-effects-disabled');

  function lifecyclePayload() { return { host: launcherHost, mode: viewMode }; }

  function setup(current) {
    var root = document.getElementById('launcher-root');
    root.innerHTML = '<section class="launcher-connect"><form><h1>Launcher kapcsolat</h1><p>A NAS-cím csak a kényelmes beállításhoz és szinkronhoz kell. A launcher az első sikeres szinkron után NAS nélkül is működik.</p><input id="launcher-origin" type="url" inputmode="url" placeholder="http://192.168.1.20:8765"><div id="launcher-origin-error"></div><button type="submit">Mentés és szinkronizálás</button></form></section>';
    document.getElementById('launcher-origin').value = current || '';
    root.querySelector('form').addEventListener('submit', function (event) {
      event.preventDefault(); var next = normalize(document.getElementById('launcher-origin').value);
      if (!next) { document.getElementById('launcher-origin-error').textContent = 'Teljes, privát IPv4-es HTTP/HTTPS címet adj meg.'; return; }
      origin = next; saveOrigin(origin); window.location.reload();
    });
  }

  function remoteJson(path, method, body, timeoutMs) {
    if (!origin) return Promise.reject(new Error('A NAS-kapcsolat nincs beállítva.'));
    var options = { method: method || 'GET', cache: 'no-store' };
    // A system-level long Back can background the popup before the response
    // arrives.  Keep the tiny park request alive so the TV-side manager can
    // really close the WAM window instead of leaving a transparent focus trap.
    if (path === '/api/launcher/park' || path === '/api/launcher/hidden') options.keepalive = true;
    if (body !== undefined) { options.headers = { 'Content-Type': 'text/plain;charset=UTF-8' }; options.body = JSON.stringify(body); }
    var timeout = null;
    var request = window.fetch(origin + path, options).then(function (response) {
      return response.json().then(function (json) {
        if (!response.ok || !json.ok) throw new Error(json.error || 'A NAS-kérés sikertelen.');
        return json;
      });
    });
    // Keep the deadline active until response.json() consumed the body, then
    // clear it so completed calls do not leave hundreds of pending timers.
    var deadline = new Promise(function (_, reject) {
      timeout = window.setTimeout(function () { reject(new Error('A NAS nem érhető el.')); }, timeoutMs || 3500);
    });
    return Promise.race([request, deadline]).then(function (result) {
      if (timeout) window.clearTimeout(timeout);
      return result;
    }, function (error) {
      if (timeout) window.clearTimeout(timeout);
      throw error;
    });
  }

  function lunaLaunch(appId, appParams) {
    return new Promise(function (resolve, reject) {
      if (typeof window.PalmServiceBridge !== 'function') { reject(new Error('A helyi webOS alkalmazásindító nem érhető el.')); return; }
      var bridge = new window.PalmServiceBridge(); bridges.push(bridge); var done = false;
      function finish(error, result) {
        if (done) return; done = true; window.clearTimeout(timer); bridges.splice(bridges.indexOf(bridge), 1);
        if (error) reject(error); else resolve(result || { returnValue: true });
      }
      bridge.onservicecallback = function (message) {
        try { var result = JSON.parse(message || '{}'); if (result.returnValue === false) finish(new Error(result.errorText || 'A webOS elutasította az indítást.')); else finish(null, result); }
        catch (error) { finish(error); }
      };
      var timer = window.setTimeout(function () { finish(new Error('Az alkalmazásindítás nem válaszolt.')); }, 8000);
      try { bridge.call(LAUNCH_URI, JSON.stringify({ id: appId, params: appParams || {} })); } catch (error) { finish(error); }
    });
  }

  function findPreset(id) {
    var presets = cachedState && cachedState.presets || [];
    for (var index = 0; index < presets.length; index += 1) if (presets[index].id === id) return presets[index];
    return null;
  }
  function persistState(serialized) {
    if (!validState(cachedState)) return false;
    try {
      var next = serialized || JSON.stringify(cachedState);
      if (next === cachedStateSerialized) return false;
      localStorage.setItem(STATE_KEY, next);
      cachedStateSerialized = next;
      return true;
    } catch (ignore) { return false; }
  }
  function recordLast(body) {
    if (!cachedState || !cachedState.config) return null;
    cachedState.config.lastUsed = { type: body.type, targetId: body.targetId, label: body.label };
    persistState(); return deepCopy(cachedState.config.lastUsed);
  }

  var WEBHOOK_MODE_KEY = '__sl_mode';
  var WEBHOOK_METHOD_KEY = '__sl_method';
  var WEBHOOK_BODY_KEY = '__sl_body';

  function encodeLinkForNas(item) {
    if (!item || item.type !== 'link') return item;
    var next = deepCopy(item);
    if (next.linkMode === 'webhook') {
      var url;
      try { url = new URL(next.targetId); } catch (error) { throw new Error('A webhook URL érvénytelen.'); }
      url.searchParams.set(WEBHOOK_MODE_KEY, 'webhook');
      url.searchParams.set(WEBHOOK_METHOD_KEY, next.webhookMethod === 'POST' ? 'POST' : 'GET');
      if (next.webhookMethod === 'POST' && next.webhookBody) url.searchParams.set(WEBHOOK_BODY_KEY, String(next.webhookBody));
      else url.searchParams.delete(WEBHOOK_BODY_KEY);
      next.targetId = url.toString();
      if (next.targetId.length > 2000) throw new Error('A webhook URL és body együtt túl hosszú.');
    }
    delete next.linkMode;
    delete next.webhookMethod;
    delete next.webhookBody;
    return next;
  }

  function decodeLinkFromNas(item) {
    if (!item || item.type !== 'link') return item;
    var next = deepCopy(item);
    var url;
    try { url = new URL(next.targetId); } catch (ignore) {
      next.linkMode = 'website'; next.webhookMethod = 'GET'; next.webhookBody = ''; return next;
    }
    if (url.searchParams.get(WEBHOOK_MODE_KEY) !== 'webhook') {
      next.linkMode = 'website'; next.webhookMethod = 'GET'; next.webhookBody = ''; return next;
    }
    next.linkMode = 'webhook';
    next.webhookMethod = url.searchParams.get(WEBHOOK_METHOD_KEY) === 'POST' ? 'POST' : 'GET';
    next.webhookBody = next.webhookMethod === 'POST' ? (url.searchParams.get(WEBHOOK_BODY_KEY) || '') : '';
    url.searchParams.delete(WEBHOOK_MODE_KEY);
    url.searchParams.delete(WEBHOOK_METHOD_KEY);
    url.searchParams.delete(WEBHOOK_BODY_KEY);
    next.targetId = url.toString();
    return next;
  }

  function encodeConfigForNas(config) {
    var next = deepCopy(config);
    (next.rows || []).forEach(function (row) {
      row.items = (row.items || []).map(encodeLinkForNas);
    });
    return next;
  }

  function decodeConfigFromNas(config) {
    var next = deepCopy(config);
    (next.rows || []).forEach(function (row) {
      row.items = (row.items || []).map(decodeLinkFromNas);
    });
    return next;
  }

  function decodeStateFromNas(state) {
    var next = deepCopy(state);
    if (next && next.config) next.config = decodeConfigFromNas(next.config);
    return next;
  }

  function sendWebhook(body) {
    var method = body.webhookMethod === 'POST' ? 'POST' : 'GET';
    var options = { method: method, cache: 'no-store', mode: 'no-cors' };
    if (method === 'POST') options.body = String(body.webhookBody || '');
    var timer = null;
    var request = window.fetch(String(body.targetId || ''), options).then(function () {
      return { ok: true, lastUsed: null, webhookStatus: null, direct: true };
    });
    var timeout = new Promise(function (_, reject) {
      timer = window.setTimeout(function () { reject(new Error('A webhook nem érhető el.')); }, 5000);
    });
    return Promise.race([request, timeout]).then(function (result) {
      if (timer) window.clearTimeout(timer);
      return result;
    }, function (error) {
      if (timer) window.clearTimeout(timer);
      throw error;
    });
  }
  function localLaunch(body) {
    var action;
    if (body.type === 'app') action = lunaLaunch(body.targetId, {});
    else if (body.type === 'link' && body.linkMode === 'webhook') {
      return sendWebhook(body);
    } else if (body.type === 'link') action = lunaLaunch('com.webos.app.browser', { target: body.targetId });
    else if (body.type === 'preset') {
      var preset = findPreset(body.targetId);
      if (!preset) return Promise.reject(new Error('A kamera- vagy PiP-preset nincs a TV helyi másolatában.'));
      if (preset.clickAction === 'openCamera' && preset.cameraId) action = lunaLaunch(CAMERA_APP, { v: 1, action: 'open', cameraId: preset.cameraId, view: 'full' });
      else {
        var overlayParams = { v: 1, action: 'show', kind: preset.kind, fit: preset.fit || 'cover' };
        if (preset.kind === 'text') overlayParams.text = preset.content || preset.text || '';
        else overlayParams.url = preset.content || preset.url || '';
        action = lunaLaunch(OVERLAY_APP, overlayParams);
      }
    } else if (body.type === 'overlayPreset') {
      var overlayPreset = findPreset(body.targetId);
      if (!overlayPreset) return Promise.reject(new Error('A PiP-preset nincs a TV helyi másolatában.'));
      action = lunaLaunch(OVERLAY_APP, { v: 1, action: 'show', presetId: overlayPreset.id });
    } else return Promise.reject(new Error('Ez a launcher-művelet helyben nem indítható.'));
    return action.then(function () {
      return { ok: true, lastUsed: body.type === 'app' || body.type === 'preset' ? recordLast(body) : null };
    });
  }

  function weatherRequest() {
    var settings = cachedState && cachedState.config && cachedState.config.settings;
    if (!settings || !settings.weatherEnabled) return Promise.resolve({ ok: true, enabled: false });
    if (Math.abs(Number(settings.latitude || 0)) < 0.0001 && Math.abs(Number(settings.longitude || 0)) < 0.0001) {
      return Promise.reject(new Error('Az időjárási koordináta 0,0; állítsd be a település valódi koordinátáit.'));
    }
    var url = 'https://api.open-meteo.com/v1/forecast?latitude=' + encodeURIComponent(settings.latitude) + '&longitude=' + encodeURIComponent(settings.longitude)
      + '&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,is_day'
      + '&hourly=temperature_2m,apparent_temperature,precipitation_probability,weather_code,wind_speed_10m'
      + '&daily=temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max,sunrise,sunset'
      + '&timezone=auto&forecast_days=7&forecast_hours=36';
    return window.fetch(url, { cache: 'no-store' }).then(function (response) { if (!response.ok) throw new Error('Az időjárási szolgáltatás nem válaszolt.'); return response.json(); }).then(function (raw) {
      var daily = raw.daily || {}; var hourly = raw.hourly || {}; var current = raw.current || {};
      function at(object, key, index, fallback) { var values = object[key] || []; return index < values.length ? values[index] : fallback; }
      var days = (daily.time || []).slice(0, 7).map(function (date, index) { return { date: date, min: at(daily, 'temperature_2m_min', index, 0), max: at(daily, 'temperature_2m_max', index, 0), code: at(daily, 'weather_code', index, 0), precipitationProbability: at(daily, 'precipitation_probability_max', index, 0), sunrise: at(daily, 'sunrise', index, ''), sunset: at(daily, 'sunset', index, '') }; });
      if (!days.length) throw new Error('Az időjárási szolgáltatás nem adott napi adatot.');
      var hours = (hourly.time || []).slice(0, 36).map(function (time, index) { return { time: time, temperature: at(hourly, 'temperature_2m', index, 0), apparentTemperature: at(hourly, 'apparent_temperature', index, 0), precipitationProbability: at(hourly, 'precipitation_probability', index, 0), code: at(hourly, 'weather_code', index, 0), windSpeed: at(hourly, 'wind_speed_10m', index, 0) }; });
      var weather = { label: settings.weatherLabel, timezone: raw.timezone || '', min: days[0].min, max: days[0].max, code: current.weather_code == null ? days[0].code : current.weather_code, current: { time: current.time || '', temperature: current.temperature_2m == null ? days[0].max : current.temperature_2m, apparentTemperature: current.apparent_temperature == null ? current.temperature_2m : current.apparent_temperature, code: current.weather_code == null ? days[0].code : current.weather_code, windSpeed: current.wind_speed_10m || 0, isDay: !!current.is_day }, hourly: hours, daily: days };
      return { ok: true, enabled: true, weather: weather };
    });
  }

  function localRequest(path, method, body) {
    if (path === '/api/launcher/state') {
      if (validState(cachedState)) return Promise.resolve(deepCopy(cachedState));
      return remoteJson(path, 'GET', undefined, 6000).then(function (state) {
        cachedState = decodeStateFromNas(state); persistState(); return deepCopy(cachedState);
      });
    }
    if (path === '/api/launcher/config' && method === 'POST') {
      var nasConfig;
      try { nasConfig = encodeConfigForNas(body); } catch (error) { return Promise.reject(error); }
      cachedState.config = deepCopy(body); persistState(); setDirty(true);
      remoteJson(path, 'POST', nasConfig).then(function (result) {
        cachedState.config = decodeConfigFromNas(result.config); persistState(); setDirty(false);
      }, function () {});
      return Promise.resolve({ ok: true, config: deepCopy(cachedState.config), offline: true });
    }
    if (path === '/api/launcher/launch' && method === 'POST') return localLaunch(body);
    if (path === '/api/launcher/weather') return weatherRequest();
    if (path === '/api/launcher/system-home' && method === 'POST') {
      return remoteJson(path, 'POST', body, 1800).catch(function () { return lunaLaunch('com.webos.app.home', {}).then(function () { return { ok: true, offline: true }; }); });
    }
    if ((path === '/api/launcher/park' || path === '/api/launcher/hidden' || path === '/api/launcher/restart' || path === '/api/launcher/visible' || path === '/api/launcher/prewarm-ready') && method === 'POST') {
      return remoteJson(path, 'POST', lifecyclePayload(), path === '/api/launcher/park' && launcherHost === 'full' ? 8000 : 2500);
    }
    return remoteJson(path, method, body);
  }

  function manualRefreshFromNas() {
    if (!origin) return Promise.reject(new Error('A NAS-kapcsolat nincs beállítva.'));
    var prepare = isDirty() && cachedState ? remoteJson('/api/launcher/config', 'POST', encodeConfigForNas(cachedState.config)).then(function (result) {
      cachedState.config = decodeConfigFromNas(result.config); setDirty(false); persistState();
    }) : Promise.resolve();
    return prepare.then(function () { return remoteJson('/api/launcher/state', 'GET', undefined, 6000); }).then(function (state) {
      state = decodeStateFromNas(state);
      cachedState = state;
      persistState(JSON.stringify(state));
      return deepCopy(state);
    });
  }

  function syncFromNas() {
    nasSyncTimer = null;
    if (!origin || !controller || document.hidden) return;
    if (nasSyncActive) { scheduleNasSync(1500); return; }
    nasSyncActive = true;
    var prepare = isDirty() && cachedState ? remoteJson('/api/launcher/config', 'POST', encodeConfigForNas(cachedState.config)).then(function (result) {
      cachedState.config = decodeConfigFromNas(result.config); setDirty(false); persistState();
    }, function () {}) : Promise.resolve();
    prepare.then(function () { return remoteJson('/api/launcher/state', 'GET', undefined, 5000); }).then(function (state) {
      state = decodeStateFromNas(state);
      var serialized = '';
      try { serialized = JSON.stringify(state); } catch (ignore) {}
      var changed = !!serialized && serialized !== cachedStateSerialized;
      cachedState = state;
      if (changed) {
        persistState(serialized);
        if (controller && controller.useState) controller.useState(deepCopy(state));
      }
    }, function () {}).then(function () { nasSyncActive = false; }, function () { nasSyncActive = false; });
  }

  function scheduleNasSync(delay) {
    if (!origin || !controller) return;
    if (nasSyncTimer) window.clearTimeout(nasSyncTimer);
    nasSyncTimer = window.setTimeout(syncFromNas, Math.max(0, Number(delay || 0)));
  }

  if (!origin && !cachedState) setup('');
  else {
    controller = window.LauncherUI.init(document.getElementById('launcher-root'), {
      apiBase: origin,
      mode: 'tv',
      viewMode: viewMode,
      host: launcherHost,
      initiallyParked: prewarmLaunch,
      request: localRequest,
      onReady: function () {
        if (readySignalLaunch) localRequest('/api/launcher/prewarm-ready', 'POST', {}).catch(function () {});
        if (!prewarmLaunch) armLifecyclePark(1600);
        window.__launcherReadyAt = Date.now();
        recordPaint('__launcherFirstPaintAt');
      },
      onConnection: function () { setup(origin); },
      onRefresh: manualRefreshFromNas,
      onPark: function () { return localRequest('/api/launcher/park', 'POST', {}); },
      onNativePark: function () { return localRequest('/api/launcher/hidden', 'POST', {}); }
    });
    // The local snapshot is the startup source of truth.  A NAS round-trip at
    // 50 ms used to overlap the first paint and could trigger a second full
    // render while the user was already trying to navigate.
    scheduleNasSync(8000);
    window.setInterval(function () { scheduleNasSync(0); }, 300000);
    if (!prewarmLaunch) localRequest('/api/launcher/visible', 'POST', {}).catch(function () {});
  }

  function activateLauncherSurface() {
      try {
        // SAM already activates a retained app before delivering relaunch.
        // Activating it again causes an unnecessary hidden/visible cycle.
        var system = window.PalmSystem || window.webOSSystem;
        if (!document.hidden && system && system.isActivated === true) return;
        if (window.PalmSystem && typeof window.PalmSystem.activate === 'function') window.PalmSystem.activate();
        else if (window.webOSSystem && typeof window.webOSSystem.activate === 'function') window.webOSSystem.activate();
      } catch (ignore) {}
  }

  function reactivateWarmLauncher(event) {
    var nextLaunch = event ? parseLaunchEnvelope(event.detail) : null;
    applyLaunchDisplayPreferences(nextLaunch);
    // The package fixes the window type; stale parameters cannot change it.
    var nextViewMode = viewMode;
    if (nextLaunch && nextLaunch.source === 'preload') {
      prewarmLaunch = true;
      return;
    }
    prewarmLaunch = false;
    var requestId = nextLaunch && String(nextLaunch.homeRequestId || '');
    if (requestId && requestId === lastHomeRequestId) return;
    var newHomeRequest = !!requestId && requestId !== initialHomeRequestId;
    if (requestId) lastHomeRequestId = requestId;
    if (nextLaunch && nextLaunch.source === 'home-short-toggle' && newHomeRequest && nextViewMode === 'overlay') {
      // Paired webOS events share a request ID and are rejected above. A new
      // physical press must remain usable even immediately after closing.
      if (controller && controller.isQuickOpen && controller.isQuickOpen()) {
        if (controller.closeQuick) controller.closeQuick();
        return;
      }
    }
    // With handlesRelaunch, foreground the retained surface before resuming
    // clocks/previews. Visibility notifications already mean it is active.
    cancelBackgroundPark();
    if (controller && controller.prepareResume) controller.prepareResume();
    var resumeSource = nextLaunch && String(nextLaunch.source || '');
    if (controller && controller.beginResumeLoading && /^quick-start(?:-|$)/.test(resumeSource)) {
      controller.beginResumeLoading(1600);
    }
    if (event) activateLauncherSurface();
    if (controller && controller.resume) controller.resume();
    window.__launcherResumeAt = Date.now();
    recordPaint('__launcherResumePaintAt');
    lifecycleParkArmed = true;
    if (nextLaunch && nextLaunch.source !== 'preload') localRequest('/api/launcher/visible', 'POST', {}).catch(function () {});
    // Returning from another app must stay instant; sync once the launcher is
    // already responsive and visible.
    scheduleNasSync(2000);
  }
  document.addEventListener('webOSRelaunch', reactivateWarmLauncher, true);
  document.addEventListener('webOSLaunch', reactivateWarmLauncher, true);
  function armLifecyclePark(delay) {
    if (lifecycleArmTimer) window.clearTimeout(lifecycleArmTimer);
    lifecycleArmTimer = window.setTimeout(function () {
      lifecycleArmTimer = null;
      if (!prewarmLaunch && controller) lifecycleParkArmed = true;
    }, Math.max(0, Number(delay || 0)));
  }
  function cancelBackgroundPark() {
    backgroundParkGeneration += 1;
    if (backgroundParkTimer !== null) window.clearTimeout(backgroundParkTimer);
    backgroundParkTimer = null;
  }
  function parkBackgroundedLauncher() {
    if (controller && controller.suspend) controller.suspend();
    if (launcherHost === 'full') return;
    if (!lifecycleParkArmed) return;
    if (!controller || typeof controller.park !== 'function') return;
    if (controller.isParked && controller.isParked()) return;
    cancelBackgroundPark();
    var parkGeneration = backgroundParkGeneration;
    // webOS emits a short hidden transition during popup reactivation. It
    // has already released native input while hidden; wait for a stable
    // background state before parking, and cancel when the surface returns.
    backgroundParkTimer = window.setTimeout(function () {
      if (parkGeneration !== backgroundParkGeneration) return;
      backgroundParkTimer = null;
      if (!document.hidden || !lifecycleParkArmed || !controller) return;
      if (controller.isParked && controller.isParked()) return;
      lifecycleParkArmed = false;
      controller.park(true);
    }, 150);
  }
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { parkBackgroundedLauncher(); return; }
    cancelBackgroundPark();
    lifecycleParkArmed = true;
    if (launcherHost === 'full' || !controller || !controller.isParked || !controller.isParked()) reactivateWarmLauncher(null);
  }, true);
  if (typeof window.addEventListener === 'function') window.addEventListener('pagehide', parkBackgroundedLauncher, true);
}());
