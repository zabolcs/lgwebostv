(function () {
  'use strict';

  var Core = window.MediaOverlayCore;
  var STORAGE_KEY = 'hu.szabi.mediaoverlay.config.v1';
  var SYNC_URL_KEY = 'hu.szabi.mediaoverlay.sync-url.v1';
  var LAST_SHOW_KEY = 'hu.szabi.mediaoverlay.last-show.v1';
  var APP_ID = 'hu.szabi.mediaoverlay';
  var CAMERA_APP_ID = 'hu.szabi.cameraviewer';
  var FOREGROUND_INFO_URI = 'luna://com.webos.applicationManager/getForegroundAppInfo';
  var LOAD_TIMEOUT_MS = 8000;
  var ERROR_CLOSE_MS = 10000;
  var IMAGE_RETRY_MS = 1500;
  var generation = 0;
  var state = 'BOOT';
  var config = null;
  var currentMedia = null;
  var activeResolved = null;
  var activeExpiry = 0;
  var loadTimer = null;
  var ttlTimer = null;
  var retryTimer = null;
  var closeFallbackTimer = null;
  var suspendedContent = null;
  var cameraLaunchPending = false;
  var cameraBridge = null;
  var cameraTimeout = null;
  var seenRequestIds = [];
  var syncUrl = '';
  var foregroundBridge = null;
  var foregroundTimeout = null;
  var foregroundPresenceTimeout = null;
  var foregroundCheckSerial = 0;

  function element(id) { return document.getElementById(id); }

  function loadConfig() {
    try { return Core.parseStored(localStorage.getItem(STORAGE_KEY)); }
    catch (e) { return Core.defaultConfig(); }
  }

  function storeConfig(next) {
    var normalized = Core.normalizeConfig(next);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    config = normalized;
    pushSync();
    return normalized;
  }

  function canonicalShowRequest(resolved) {
    var preset = resolved.preset;
    var request = {
      v: 1,
      action: 'show',
      kind: preset.kind,
      corner: resolved.layout.corner,
      width: resolved.layout.width,
      height: resolved.layout.height,
      marginX: resolved.layout.marginX,
      marginY: resolved.layout.marginY,
      ttlMs: resolved.ttlMs
    };
    if (preset.kind === 'text') request.text = preset.content;
    else {
      request.url = preset.content;
      request.fit = preset.fit;
    }
    if (preset.clickAction === 'openCamera') {
      request.clickAction = 'openCamera';
      request.cameraId = preset.cameraId;
    }
    if (preset.clickAction === 'dismiss') request.clickAction = 'dismiss';
    if (resolved.fullscreen) request.mode = 'fullscreen';
    return request;
  }

  function storeLastShow(resolved) {
    try {
      localStorage.setItem(LAST_SHOW_KEY, JSON.stringify(canonicalShowRequest(resolved)));
      return true;
    } catch (e) { return false; }
  }

  function loadLastShow() {
    try {
      var raw = localStorage.getItem(LAST_SHOW_KEY);
      if (!raw) return null;
      var params = JSON.parse(raw);
      if (Core.normalizeAction(params) !== 'show' || params.v !== 1) return null;
      return Core.resolveShowRequest(params, config || loadConfig());
    } catch (e) { return null; }
  }

  function isPlainLauncherOpen(params) {
    if (!params || typeof params !== 'object') return false;
    var keys = Object.keys(params);
    if (keys.length === 0) return true;
    return keys.length === 1 && keys[0] === 'storeCaller' && params.storeCaller === 'home';
  }

  function hasActivePiP() {
    return state === 'VISIBLE' || state === 'LOADING' || state === 'CHECKING_FOREGROUND' ||
      (state === 'SUSPENDED' && suspendedContent && suspendedContent.resolved);
  }

  function pushSync() {
    if (!syncUrl || typeof window.fetch !== 'function') return Promise.resolve(false);
    return window.fetch(syncUrl, {
      method: 'POST',
      mode: 'no-cors',
      keepalive: true,
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: JSON.stringify({ module: 'media-overlay', version: 1, config: config || loadConfig() })
    }).then(function () { return true; }, function () { return false; });
  }

  function rememberSyncUrl(value) {
    if (value == null) return;
    syncUrl = Core.normalizeSyncUrl(value);
    localStorage.setItem(SYNC_URL_KEY, syncUrl);
  }

  function cameraPresenceUrl() {
    if (!syncUrl) return '';
    var marker = '/api/tv-sync/';
    var index = syncUrl.indexOf(marker);
    return index > 0 ? syncUrl.slice(0, index) + '/api/tv-presence/camera-viewer' : '';
  }

  function clearTimer(name) {
    if (name === 'load' && loadTimer !== null) { clearTimeout(loadTimer); loadTimer = null; }
    if (name === 'ttl' && ttlTimer !== null) { clearTimeout(ttlTimer); ttlTimer = null; }
    if (name === 'retry' && retryTimer !== null) { clearTimeout(retryTimer); retryTimer = null; }
    if (name === 'close' && closeFallbackTimer !== null) { clearTimeout(closeFallbackTimer); closeFallbackTimer = null; }
  }

  function cancelCameraLaunch() {
    if (cameraTimeout !== null) { clearTimeout(cameraTimeout); cameraTimeout = null; }
    if (cameraBridge !== null) {
      try { if (typeof cameraBridge.cancel === 'function') cameraBridge.cancel(); } catch (e) {}
      cameraBridge = null;
    }
    cameraLaunchPending = false;
  }

  function cancelForegroundCheck() {
    foregroundCheckSerial++;
    if (foregroundTimeout !== null) { clearTimeout(foregroundTimeout); foregroundTimeout = null; }
    if (foregroundPresenceTimeout !== null) { clearTimeout(foregroundPresenceTimeout); foregroundPresenceTimeout = null; }
    if (foregroundBridge !== null) {
      try { if (typeof foregroundBridge.cancel === 'function') foregroundBridge.cancel(); } catch (e) {}
      foregroundBridge = null;
    }
  }

  function removeCurrentMedia() {
    clearTimer('load');
    clearTimer('ttl');
    clearTimer('retry');
    if (currentMedia) {
      currentMedia.onload = null;
      currentMedia.onerror = null;
      currentMedia.oncanplay = null;
      if (currentMedia.tagName === 'VIDEO') {
        try { currentMedia.pause(); } catch (e) {}
        try { currentMedia.removeAttribute('src'); currentMedia.load(); } catch (e2) {}
      } else if (currentMedia.tagName === 'IMG') {
        try { currentMedia.removeAttribute('src'); } catch (e3) {}
      }
    }
    currentMedia = null;
    var host = element('media-host');
    while (host.firstChild) host.removeChild(host.firstChild);
  }

  function beginTransaction() {
    generation++;
    removeCurrentMedia();
    cancelCameraLaunch();
    cancelForegroundCheck();
    clearTimer('close');
    activeResolved = null;
    activeExpiry = 0;
    suspendedContent = null;
    return generation;
  }

  function applyLayout(layout) {
    var overlay = element('overlay');
    overlay.classList.remove('corner-top-left', 'corner-top-right', 'corner-bottom-left', 'corner-bottom-right');
    overlay.classList.add('corner-' + layout.corner);
    document.documentElement.style.setProperty('--overlay-width', String(layout.width) + 'px');
    document.documentElement.style.setProperty('--overlay-height', String(layout.height) + 'px');
    document.documentElement.style.setProperty('--margin-x', String(layout.marginX) + 'px');
    document.documentElement.style.setProperty('--margin-y', String(layout.marginY) + 'px');
  }

  function setStatus(text, error, visible) {
    var node = element('overlay-status');
    node.textContent = text || '';
    node.classList.toggle('error', !!error);
    node.hidden = visible === false;
  }

  function setSettingsStatus(text, error) {
    var node = element('settings-status');
    node.textContent = text || '';
    node.classList.toggle('error', !!error);
  }

  function updateClickableState() {
    var host = element('media-host');
    var clickAction = activeResolved && activeResolved.preset.clickAction || '';
    var clickable = clickAction === 'openCamera' || clickAction === 'dismiss';
    host.classList.toggle('clickable', clickable);
    element('overlay').classList.toggle('dismiss-anywhere', clickAction === 'dismiss');
    element('overlay-controls').hidden = clickAction === 'dismiss';
    host.tabIndex = clickable ? 0 : -1;
    host.setAttribute('aria-label', clickAction === 'dismiss' ? 'Overlay bezárása' : (clickAction === 'openCamera' ? 'Kamera megnyitása' : 'Overlay tartalom'));
  }

  function setFullscreen(enabled) {
    element('overlay').classList.toggle('fullscreen', !!enabled);
    element('fullscreen-button').textContent = enabled ? '⊡' : '⛶';
    element('fullscreen-button').setAttribute('aria-label', enabled ? 'Kis méret' : 'Teljes képernyő');
  }

  function focusContentOrClose() {
    var host = element('media-host');
    if (host.tabIndex >= 0) host.focus();
    else element('close-button').focus();
  }

  function failVisible(message, transactionGeneration) {
    if (transactionGeneration != null && transactionGeneration !== generation) return;
    var finiteLifetime = !!(activeResolved && activeResolved.ttlMs > 0);
    var errorExpiry = activeExpiry;
    removeCurrentMedia();
    activeResolved = null;
    activeExpiry = 0;
    state = 'ERROR';
    element('settings').hidden = true;
    element('overlay').hidden = false;
    setStatus(message || 'Az overlay nem tölthető be.', true, true);
    updateClickableState();
    element('close-button').focus();
    // ttlMs:0 is a strict manual-close contract.  A late media/decoder error
    // must not silently turn it back into a ten-second overlay.
    if (finiteLifetime) {
      var delay = errorExpiry > 0
        ? Math.min(ERROR_CLOSE_MS, Math.max(0, errorExpiry - Date.now()))
        : ERROR_CLOSE_MS;
      ttlTimer = setTimeout(function () {
        if (state === 'ERROR') dismissOverlay();
      }, delay);
    }
  }

  function safePlay(video, transactionGeneration) {
    try {
      var result = video.play();
      if (result && typeof result.catch === 'function') {
        result.catch(function () {
          failVisible('A videó automatikus lejátszását a TV elutasította.', transactionGeneration);
        });
      }
      return true;
    } catch (e) {
      failVisible('A videó nem indítható el.', transactionGeneration);
      return false;
    }
  }

  function finishVisible(transactionGeneration, resumeExpiry) {
    if (transactionGeneration !== generation || !activeResolved || state === 'VISIBLE') return;
    clearTimer('load');
    state = 'VISIBLE';
    setStatus('', false, false);
    if (currentMedia && currentMedia.tagName === 'VIDEO' && !safePlay(currentMedia, transactionGeneration)) return;
    activeExpiry = resumeExpiry || (activeResolved.ttlMs > 0 ? Date.now() + activeResolved.ttlMs : 0);
    if (activeExpiry > 0) {
      var remaining = activeExpiry - Date.now();
      if (remaining <= 0) { dismissOverlay(); return; }
      ttlTimer = setTimeout(function () {
        if (transactionGeneration === generation && state === 'VISIBLE') dismissOverlay();
      }, remaining);
    }
    updateClickableState();
    focusContentOrClose();
  }

  function retryUrl(url) {
    return url + (url.indexOf('?') === -1 ? '?' : '&') + '_overlay_retry=' + Date.now();
  }

  function beginImageLoad(image, preset, transactionGeneration, resumeExpiry, retrying) {
    if (transactionGeneration !== generation || image !== currentMedia) return;
    clearTimer('load');
    clearTimer('retry');
    loadTimer = setTimeout(function () {
      scheduleImageRetry(image, preset, transactionGeneration, resumeExpiry);
    }, LOAD_TIMEOUT_MS);
    image.src = retrying ? retryUrl(preset.content) : preset.content;
  }

  function scheduleImageRetry(image, preset, transactionGeneration, resumeExpiry) {
    if (transactionGeneration !== generation || image !== currentMedia) return;
    clearTimer('load');
    clearTimer('ttl');
    clearTimer('retry');
    var expiry = resumeExpiry || activeExpiry;
    if (expiry > 0 && expiry <= Date.now()) { dismissOverlay(); return; }
    state = 'LOADING';
    setStatus('A képstream megszakadt, újracsatlakozás…', true, true);
    var delay = expiry > 0
      ? Math.min(IMAGE_RETRY_MS, Math.max(0, expiry - Date.now()))
      : IMAGE_RETRY_MS;
    retryTimer = setTimeout(function () {
      if (transactionGeneration !== generation || image !== currentMedia) return;
      if (expiry > 0 && expiry <= Date.now()) { dismissOverlay(); return; }
      beginImageLoad(image, preset, transactionGeneration, expiry, true);
    }, delay);
  }

  function showResolved(resolved, resumeExpiry) {
    var transactionGeneration = beginTransaction();
    config = loadConfig();
    activeResolved = resolved;
    activeExpiry = resumeExpiry || (resolved.ttlMs > 0 ? Date.now() + resolved.ttlMs : 0);
    applyLayout(resolved.layout || config.layout);
    setFullscreen(resolved.fullscreen);
    element('settings').hidden = true;
    element('overlay').hidden = false;
    state = 'LOADING';
    setStatus('Betöltés…', false, true);
    updateClickableState();
    element('close-button').focus();

    var preset = resolved.preset;
    if (preset.kind === 'text') {
      var text = document.createElement('div');
      text.className = 'text-content';
      text.textContent = preset.content;
      currentMedia = text;
      element('media-host').appendChild(text);
      finishVisible(transactionGeneration, resumeExpiry);
      return;
    }

    if (preset.kind === 'image') {
      var image = document.createElement('img');
      image.alt = preset.id;
      image.style.objectFit = preset.fit;
      image.onload = function () { finishVisible(transactionGeneration, activeExpiry); };
      image.onerror = function () { scheduleImageRetry(image, preset, transactionGeneration, activeExpiry); };
      currentMedia = image;
      element('media-host').appendChild(image);
      beginImageLoad(image, preset, transactionGeneration, activeExpiry, false);
      return;
    }

    loadTimer = setTimeout(function () {
      failVisible('A média betöltése túllépte az időkorlátot.', transactionGeneration);
    }, LOAD_TIMEOUT_MS);

    var video = document.createElement('video');
    video.muted = true;
    video.autoplay = true;
    video.setAttribute('playsinline', '');
    video.preload = 'auto';
    video.style.objectFit = preset.fit;
    video.oncanplay = function () { finishVisible(transactionGeneration, resumeExpiry); };
    video.onerror = function () { failVisible('A videó nem tölthető be vagy nem támogatott.', transactionGeneration); };
    currentMedia = video;
    element('media-host').appendChild(video);
    video.src = preset.content;
    try { video.load(); } catch (e) { failVisible('A videó nem indítható el.', transactionGeneration); }
  }

  function cameraViewerIsForegroundViaLuna(callback, checkSerial) {
    if (checkSerial !== foregroundCheckSerial) return;
    if (typeof window.PalmServiceBridge !== 'function') { callback(false); return; }
    var done = false;
    function finish(active) {
      if (done || checkSerial !== foregroundCheckSerial) return;
      done = true;
      if (foregroundTimeout !== null) { clearTimeout(foregroundTimeout); foregroundTimeout = null; }
      foregroundBridge = null;
      callback(active === true);
    }
    try {
      var bridge = new window.PalmServiceBridge();
      foregroundBridge = bridge;
      bridge.onservicecallback = function (raw) {
        var result = null;
        try { result = JSON.parse(raw); } catch (e) {}
        finish(!!(result && result.returnValue === true &&
          String(result.appId || result.id || '') === CAMERA_APP_ID));
      };
      foregroundTimeout = setTimeout(function () {
        try { if (foregroundBridge && typeof foregroundBridge.cancel === 'function') foregroundBridge.cancel(); } catch (e) {}
        finish(false);
      }, 1200);
      bridge.call(FOREGROUND_INFO_URI, JSON.stringify({ subscribe: false }));
    } catch (e2) {
      finish(false);
    }
  }

  function cameraViewerIsForeground(callback) {
    var checkSerial = ++foregroundCheckSerial;
    var presenceUrl = cameraPresenceUrl();
    if (typeof window.fetch !== 'function' || !presenceUrl) {
      cameraViewerIsForegroundViaLuna(callback, checkSerial);
      return;
    }
    var settled = false;
    function fallback() {
      if (settled || checkSerial !== foregroundCheckSerial) return;
      settled = true;
      if (foregroundPresenceTimeout !== null) clearTimeout(foregroundPresenceTimeout);
      foregroundPresenceTimeout = null;
      cameraViewerIsForegroundViaLuna(callback, checkSerial);
    }
    foregroundPresenceTimeout = setTimeout(fallback, 1000);
    try {
      window.fetch(presenceUrl, { method: 'GET', cache: 'no-store' })
        .then(function (response) { return response.json(); })
        .then(function (result) {
          if (settled || checkSerial !== foregroundCheckSerial) return;
          settled = true;
          if (foregroundPresenceTimeout !== null) clearTimeout(foregroundPresenceTimeout);
          foregroundPresenceTimeout = null;
          if (!result || result.ok !== true || typeof result.active !== 'boolean') {
            cameraViewerIsForegroundViaLuna(callback, checkSerial);
            return;
          }
          callback(result.active === true);
        }, fallback);
    } catch (error) { fallback(); }
  }

  function closeSilently() {
    beginTransaction();
    state = 'CLOSING';
    element('settings').hidden = true;
    element('overlay').hidden = true;
    try { window.close(); } catch (e) {}
  }

  function showResolvedUnlessCameraActive(resolved, resumeExpiry, remember) {
    var transactionGeneration = beginTransaction();
    state = 'CHECKING_FOREGROUND';
    element('settings').hidden = true;
    element('overlay').hidden = true;
    cameraViewerIsForeground(function (cameraActive) {
      if (transactionGeneration !== generation || state !== 'CHECKING_FOREGROUND') return;
      if (cameraActive) closeSilently();
      else {
        if (remember) storeLastShow(resolved);
        showResolved(resolved, resumeExpiry || 0);
      }
    });
  }

  function showSettings(message, error) {
    beginTransaction();
    config = loadConfig();
    state = 'SETTINGS';
    element('overlay').hidden = true;
    element('settings').hidden = false;
    renderSettings();
    setSettingsStatus(message || '', error);
    element('corner').focus();
  }

  function dismissOverlay() {
    beginTransaction();
    state = 'CLOSING';
    element('settings').hidden = true;
    element('overlay').hidden = false;
    setStatus('Bezárás…', false, true);
    try { window.close(); } catch (e) {}
    closeFallbackTimer = setTimeout(function () {
      if (state !== 'CLOSING') return;
      state = 'ERROR';
      setStatus('Az app nem záródott be. Nyomd meg a Home gombot, majd zárd be az alkalmazást.', true, true);
      element('close-button').focus();
    }, 900);
  }

  function newRequestId() {
    var result = '';
    try {
      var bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      for (var i = 0; i < bytes.length; i++) result += ('0' + bytes[i].toString(16)).slice(-2);
    } catch (e) {
      while (result.length < 32) result += ('00000000' + Math.floor(Math.random() * 0xffffffff).toString(16)).slice(-8);
      result = result.slice(0, 32);
    }
    return result;
  }

  function launchCamera() {
    if (cameraLaunchPending || state !== 'VISIBLE' || !activeResolved ||
        activeResolved.preset.clickAction !== 'openCamera') return;
    var cameraId = activeResolved.preset.cameraId;
    if (!/^[a-z0-9][a-z0-9._-]{0,31}$/.test(cameraId)) {
      failVisible('A preset kamera-ID-ja érvénytelen.', generation);
      return;
    }
    if (typeof window.PalmServiceBridge !== 'function') {
      setStatus('A Camera Viewer nem indítható: a rendszerhíd nem érhető el.', true, true);
      return;
    }
    cameraLaunchPending = true;
    var transactionGeneration = generation;
    var restoreResolved = activeResolved;
    var restoreExpiry = activeExpiry;
    var releasedVideo = !!(currentMedia && currentMedia.tagName === 'VIDEO');
    if (releasedVideo) {
      removeCurrentMedia();
      setStatus('Camera Viewer megnyitása…', false, true);
    }
    var params = { v: 1, action: 'open', cameraId: cameraId, view: 'full', requestId: newRequestId() };
    var finished = false;
    function finish(result) {
      if (finished) return;
      finished = true;
      if (cameraTimeout !== null) { clearTimeout(cameraTimeout); cameraTimeout = null; }
      cameraBridge = null;
      cameraLaunchPending = false;
      if (transactionGeneration !== generation || state !== 'VISIBLE') return;
      if (!result || result.returnValue !== true) {
        if (releasedVideo && restoreResolved) {
          if (restoreExpiry > 0 && restoreExpiry <= Date.now()) {
            dismissOverlay();
            return;
          }
          showResolved(restoreResolved, restoreExpiry);
          return;
        }
        setStatus('A Camera Viewer indítása sikertelen.', true, true);
        return;
      }
      dismissOverlay();
    }
    try {
      cameraBridge = new PalmServiceBridge();
      cameraBridge.onservicecallback = function (raw) {
        var result = null;
        try { result = JSON.parse(raw); } catch (e) {}
        finish(result);
      };
      cameraTimeout = setTimeout(function () {
        try { if (cameraBridge && typeof cameraBridge.cancel === 'function') cameraBridge.cancel(); } catch (e) {}
        finish(null);
      }, 4000);
      cameraBridge.call('luna://com.webos.applicationManager/launch', JSON.stringify({
        id: CAMERA_APP_ID,
        params: params
      }));
    } catch (e2) {
      finish(null);
    }
  }

  function validateRequestId(params) {
    if (params.requestId == null) return true;
    var value = String(params.requestId);
    if (!/^[0-9a-f]{32}$/.test(value)) throw new Error('A requestId érvénytelen.');
    if (seenRequestIds.indexOf(value) >= 0) return false;
    seenRequestIds.push(value);
    if (seenRequestIds.length > 32) seenRequestIds.shift();
    return true;
  }

  function dispatch(params, isRelaunch) {
    params = params && typeof params === 'object' ? params : {};
    try {
      if (isPlainLauncherOpen(params)) {
        if (isRelaunch && hasActivePiP()) return;
        config = loadConfig();
        var remembered = loadLastShow();
        if (remembered) showResolvedUnlessCameraActive(remembered, 0, false);
        else showSettings('Még nincs visszajátszható korábbi PiP.', false);
        return;
      }
      var action = Core.normalizeAction(params);
      if (action !== 'settings' && params.v !== 1) throw new Error('A launch séma verziója érvénytelen.');
      if (action === 'show' && isRelaunch && hasActivePiP()) return;
      if (!validateRequestId(params)) return;
      if (action === 'dismiss') { dismissOverlay(); return; }
      if (action === 'settings') { showSettings('', false); return; }
      config = loadConfig();
      rememberSyncUrl(params.syncUrl);
      if (action === 'sync') {
        pushSync();
        if (!isRelaunch) setTimeout(dismissOverlay, 700);
        return;
      }
      if (action === 'configure') {
        config.layout = Core.resolveLayoutRequest(params, config.layout);
        storeConfig(config);
        dismissOverlay();
        return;
      }
      if (action === 'preset-save') {
        var launchPreset = Core.resolvePresetRequest(params);
        var replaced = false;
        for (var presetIndex = 0; presetIndex < config.presets.length; presetIndex++) {
          if (config.presets[presetIndex].id === launchPreset.id) {
            config.presets[presetIndex] = launchPreset;
            replaced = true;
            break;
          }
        }
        if (!replaced) {
          if (config.presets.length >= 32) throw new Error('Legfeljebb 32 preset menthető.');
          config.presets.push(launchPreset);
        }
        storeConfig(config);
        dismissOverlay();
        return;
      }
      if (action === 'preset-delete') {
        var deleteId = Core.normalizePresetId(params.presetId);
        var previousLength = config.presets.length;
        config.presets = config.presets.filter(function (item) { return item.id !== deleteId; });
        if (config.presets.length === previousLength) throw new Error('Ismeretlen preset.');
        storeConfig(config);
        dismissOverlay();
        return;
      }
      showResolvedUnlessCameraActive(Core.resolveShowRequest(params, config), 0, true);
    } catch (e) {
      var transactionGeneration = beginTransaction();
      applyLayout((config || loadConfig()).layout);
      element('settings').hidden = true;
      element('overlay').hidden = false;
      failVisible(e && e.message ? e.message : 'Érvénytelen indítási paraméter.', transactionGeneration);
    }
  }

  function parseLaunchEnvelope(raw) {
    try {
      var parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
      for (var depth = 0; parsed && typeof parsed === 'object' && depth < 6; depth++) {
        if (Object.prototype.hasOwnProperty.call(parsed, 'launchParams')) {
          parsed = typeof parsed.launchParams === 'string' ? JSON.parse(parsed.launchParams) : parsed.launchParams;
        } else if (Object.prototype.hasOwnProperty.call(parsed, 'parameters')) {
          parsed = typeof parsed.parameters === 'string' ? JSON.parse(parsed.parameters) : parsed.parameters;
        } else if (parsed.payload && typeof parsed.payload === 'object' &&
                   (parsed.payload.id === APP_ID || parsed.payload.params || parsed.payload.parameters)) {
          parsed = parsed.payload;
        } else if (parsed.params && typeof parsed.params === 'object' &&
                   (parsed.id === APP_ID || parsed.action === 'launch' || parsed.action === 'system.launcher/launch' ||
                    Object.keys(parsed).length === 1)) {
          parsed = parsed.params;
        } else {
          break;
        }
      }
      return parsed && typeof parsed === 'object' ? parsed : {};
    } catch (e) { return {}; }
  }

  function getColdLaunchParams() {
    var raw = window.webOSSystem && window.webOSSystem.launchParams;
    if (!raw) raw = window.PalmSystem && window.PalmSystem.launchParams;
    return parseLaunchEnvelope(raw);
  }

  function getRelaunchParams(event) {
    return parseLaunchEnvelope(event && event.detail);
  }

  function activateAfterRelaunch() {
    try {
      if (window.webOSSystem && typeof window.webOSSystem.activate === 'function') {
        window.webOSSystem.activate();
      } else if (window.PalmSystem && typeof window.PalmSystem.activate === 'function') {
        window.PalmSystem.activate();
      }
    } catch (e) {}
  }

  function handleRelaunch(event) {
    var params = getRelaunchParams(event);
    dispatch(params, true);
    if (state !== 'CLOSING' && params.action !== 'sync') activateAfterRelaunch();
  }

  function suspend() {
    if (state === 'SUSPENDED' || state === 'CLOSING') return;
    if (state === 'VISIBLE' || state === 'LOADING') {
      suspendedContent = { resolved: activeResolved, expiresAt: activeExpiry };
    } else {
      suspendedContent = null;
    }
    generation++;
    removeCurrentMedia();
    cancelCameraLaunch();
    activeResolved = null;
    element('overlay').hidden = true;
    state = 'SUSPENDED';
  }

  function resume() {
    if (state !== 'SUSPENDED') return;
    var saved = suspendedContent;
    suspendedContent = null;
    if (saved && saved.resolved && (!saved.expiresAt || saved.expiresAt > Date.now())) {
      showResolvedUnlessCameraActive(saved.resolved, saved.expiresAt);
    } else {
      showSettings(saved ? 'Az overlay időközben lejárt.' : '', false);
    }
  }

  function layoutFromForm() {
    return Core.normalizeLayout({
      corner: element('corner').value,
      width: element('width').value,
      height: element('height').value,
      marginX: element('margin-x').value,
      marginY: element('margin-y').value,
      ttlMs: String(Number(element('ttl-seconds').value) * 1000)
    });
  }

  function fillPresetEditor(preset) {
    element('preset-id').value = preset ? preset.id : '';
    element('preset-kind').value = preset ? preset.kind : 'text';
    element('preset-fit').value = preset ? preset.fit : 'contain';
    element('preset-content').value = preset ? preset.content : '';
    element('preset-click-action').value = preset ? preset.clickAction : '';
    element('preset-camera-id').value = preset ? preset.cameraId : '';
    updatePresetEditor();
  }

  function selectedPreset() {
    var id = element('preset-list').value;
    for (var i = 0; i < config.presets.length; i++) if (config.presets[i].id === id) return config.presets[i];
    return null;
  }

  function renderPresetList(selectedId) {
    var list = element('preset-list');
    while (list.firstChild) list.removeChild(list.firstChild);
    for (var i = 0; i < config.presets.length; i++) {
      var option = document.createElement('option');
      option.value = config.presets[i].id;
      option.textContent = config.presets[i].id + ' (' + config.presets[i].kind + ')';
      list.appendChild(option);
    }
    if (selectedId) list.value = selectedId;
    fillPresetEditor(selectedPreset());
  }

  function renderSettings() {
    var layout = config.layout;
    element('corner').value = layout.corner;
    element('width').value = String(layout.width);
    element('height').value = String(layout.height);
    element('margin-x').value = String(layout.marginX);
    element('margin-y').value = String(layout.marginY);
    element('ttl-seconds').value = String(layout.ttlMs / 1000);
    renderPresetList(config.presets.length ? config.presets[0].id : '');
  }

  function updatePresetEditor() {
    var kind = element('preset-kind').value;
    element('content-label').firstChild.nodeValue = kind === 'text' ? 'Szöveg ' : 'Média URL ';
    var cameraEnabled = element('preset-click-action').value === 'openCamera';
    element('preset-camera-id').disabled = !cameraEnabled;
  }

  function presetFromForm() {
    return Core.normalizePreset({
      id: element('preset-id').value,
      kind: element('preset-kind').value,
      fit: element('preset-fit').value,
      content: element('preset-content').value,
      clickAction: element('preset-click-action').value,
      cameraId: element('preset-camera-id').value
    });
  }

  function saveLayout() {
    try {
      config.layout = layoutFromForm();
      storeConfig(config);
      setSettingsStatus('Az elrendezés elmentve.', false);
    } catch (e) { setSettingsStatus(e.message, true); }
  }

  function savePreset() {
    try {
      config.layout = layoutFromForm();
      var preset = presetFromForm();
      var replaced = false;
      for (var i = 0; i < config.presets.length; i++) {
        if (config.presets[i].id === preset.id) { config.presets[i] = preset; replaced = true; break; }
      }
      if (!replaced) {
        if (config.presets.length >= 32) throw new Error('Legfeljebb 32 preset menthető.');
        config.presets.push(preset);
      }
      storeConfig(config);
      renderPresetList(preset.id);
      setSettingsStatus('A preset elmentve.', false);
    } catch (e) { setSettingsStatus(e.message, true); }
  }

  function deletePreset() {
    var preset = selectedPreset();
    if (!preset) { setSettingsStatus('Nincs törölhető preset.', true); return; }
    config.presets = config.presets.filter(function (item) { return item.id !== preset.id; });
    try {
      storeConfig(config);
      renderPresetList(config.presets.length ? config.presets[0].id : '');
      setSettingsStatus('A preset törölve.', false);
    } catch (e) { setSettingsStatus(e.message, true); }
  }

  function showSelectedPreset() {
    var preset = selectedPreset();
    if (!preset) { setSettingsStatus('Előbb válassz presetet.', true); return; }
    try {
      var resolved = Core.resolveShowRequest({ presetId: preset.id }, config);
      storeLastShow(resolved);
      showResolved(resolved, 0);
    }
    catch (e) { setSettingsStatus(e.message, true); }
  }

  function focusCycle(direction) {
    var root = state === 'SETTINGS' ? element('settings') : element('overlay');
    var nodes = Array.prototype.slice.call(root.querySelectorAll('button,select,input,textarea,[tabindex="0"]')).filter(function (node) {
      return !node.disabled && !node.hidden;
    });
    if (!nodes.length) return;
    var index = nodes.indexOf(document.activeElement);
    index = index < 0 ? 0 : (index + direction + nodes.length) % nodes.length;
    nodes[index].focus();
  }

  function changeSelect(select, direction) {
    if (!select.options.length) return;
    var next = select.selectedIndex + direction;
    if (next < 0) next = select.options.length - 1;
    if (next >= select.options.length) next = 0;
    select.selectedIndex = next;
    var changeEvent;
    try { changeEvent = new Event('change', { bubbles: true }); }
    catch (e) {
      changeEvent = document.createEvent('Event');
      changeEvent.initEvent('change', true, false);
    }
    select.dispatchEvent(changeEvent);
  }

  function handleKey(event) {
    var code = event.keyCode;
    if (code === 461 || code === 27 || code === 8) {
      event.preventDefault(); event.stopPropagation();
      if (state === 'VISIBLE' && element('overlay').classList.contains('fullscreen')) setFullscreen(false);
      else dismissOverlay();
      return;
    }
    if (code === 37 || code === 38 || code === 39 || code === 40) {
      var intent = Core.keyIntent(event.target && event.target.tagName, code);
      if (intent === 'native') return;
      event.preventDefault(); event.stopPropagation();
      if (intent === 'select') {
        changeSelect(event.target, code === 37 ? -1 : 1);
        return;
      }
      focusCycle(code === 37 || code === 38 ? -1 : 1);
      return;
    }
    if (code === 13 && !event.repeat) {
      if (event.target && event.target.tagName === 'BUTTON') {
        event.preventDefault(); event.stopPropagation(); event.target.click(); return;
      }
      if (state === 'VISIBLE' && activeResolved && (activeResolved.preset.clickAction === 'openCamera' || activeResolved.preset.clickAction === 'dismiss')) {
        event.preventDefault(); event.stopPropagation();
        if (activeResolved.preset.clickAction === 'dismiss') dismissOverlay(); else launchCamera();
      }
    }
  }

  function bindEvents() {
    element('close-button').addEventListener('click', function (event) { event.stopPropagation(); dismissOverlay(); });
    element('fullscreen-button').addEventListener('click', function (event) {
      event.stopPropagation();
      setFullscreen(!element('overlay').classList.contains('fullscreen'));
      element('fullscreen-button').focus();
    });
    element('media-host').addEventListener('click', function (event) {
      event.stopPropagation();
      if (activeResolved && activeResolved.preset.clickAction === 'dismiss') dismissOverlay();
      else launchCamera();
    });
    element('overlay-frame').addEventListener('click', function () {
      if (activeResolved && activeResolved.preset.clickAction === 'dismiss') dismissOverlay();
    });
    element('settings-close-button').addEventListener('click', dismissOverlay);
    element('save-layout-button').addEventListener('click', saveLayout);
    element('save-preset-button').addEventListener('click', savePreset);
    element('delete-preset-button').addEventListener('click', deletePreset);
    element('show-preset-button').addEventListener('click', showSelectedPreset);
    element('new-preset-button').addEventListener('click', function () { fillPresetEditor(null); element('preset-id').focus(); });
    element('preset-list').addEventListener('change', function () { fillPresetEditor(selectedPreset()); });
    element('preset-kind').addEventListener('change', updatePresetEditor);
    element('preset-click-action').addEventListener('change', updatePresetEditor);
    window.addEventListener('keydown', handleKey, true);
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) suspend(); else resume();
    });
    window.addEventListener('pagehide', suspend, true);
    window.addEventListener('pageshow', function () { if (!document.hidden) resume(); });
    document.addEventListener('webOSRelaunch', handleRelaunch, true);
    document.addEventListener('webOSLaunch', handleRelaunch, true);
  }

  function init() {
    if (!Core) throw new Error('A Media Overlay core nem tölthető be.');
    config = loadConfig();
    try { syncUrl = localStorage.getItem(SYNC_URL_KEY) || ''; } catch (e) { syncUrl = ''; }
    bindEvents();
    dispatch(getColdLaunchParams(), false);
  }

  try { init(); }
  catch (error) {
    try {
      element('settings').hidden = false;
      element('overlay').hidden = true;
      setSettingsStatus('Indítási hiba: ' + (error && error.message ? error.message : 'ismeretlen hiba'), true);
    } catch (ignored) {}
  }
}());
