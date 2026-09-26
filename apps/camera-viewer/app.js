(function (root) {
  'use strict';

  var STORAGE_KEY = 'hu.szabi.cameraviewer.profiles.v2';
  var LEGACY_STORAGE_KEY = 'hu.szabi.cameraviewer.profiles.v1';
  var CONFIG_KEY = 'hu.szabi.cameraviewer.config.v3';
  var SYNC_URL_KEY = 'hu.szabi.cameraviewer.sync-url.v1';
  var FULLSCREEN_TRANSPORT_KEY = 'hu.szabi.cameraviewer.fullscreen-transport.v1';
  var FORBIDDEN_HOST = '192.168.0.100';
  var SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$/;
  var CAMERA_ID = /^[a-z0-9][a-z0-9._-]{0,31}$/;
  var REQUEST_ID = /^[0-9a-fA-F]{32}$/;
  var HOSTED_PLAYER_TIMEOUT = 14000;
  var FLOATING_MESSAGE_TIMEOUT = 5000;
  var DEFAULT_PREVIEW_INTERVAL_SECONDS = 60;
  var GRID_SNAPSHOT_STAGGER_MS = 9000;
  var GRID_CACHE_WARM_STAGGER_MS = 150;
  var GRID_LIVE_FOCUS_DELAY_MS = 1000;
  var GRID_LIVE_RETRY_DELAY_MS = 1800;
  var FULLSCREEN_HANDOFF_DELAY_MS = 160;
  var SNAPSHOT_CACHE_MAX_AGE = '24h';
  var SNAPSHOT_REFRESH_CACHE_MAX_AGE = '55s';
  var EMPTY_IMAGE_SRC = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=';
  var MIN_PREVIEW_INTERVAL_SECONDS = 1;
  var MAX_PREVIEW_INTERVAL_SECONDS = 60;
  var LAYOUT_SIZES = [2, 3, 4];
  var SCREEN_SAVER_CLIENT = 'hu.szabi.cameraviewer';
  var SCREEN_SAVER_REGISTER_URI = 'luna://com.webos.service.tvpower/power/registerScreenSaverRequest';
  var SCREEN_SAVER_RESPONSE_URI = 'luna://com.webos.service.tvpower/power/responseScreenSaverRequest';
  var PRESENCE_INTERVAL_MS = 2500;

  var DEFAULT_PROFILES = [];

  // Earlier Camera Viewer builds stored the go2rtc stream alias itself as the
  // cameraId. Treat those entries as the same physical cameras, otherwise the
  // four-profile limit can be exhausted before every canonical default is
  // seeded (most visibly: the Kapu profile disappears).
  var CANONICAL_PROFILE_ALIASES = {
    gyerekszoba: ['gyerekszoba', 'camera_gyerekszoba_preview', 'c210rtsp1', 'c210rtsp1_mjpeg'],
    udvar: ['udvar', 'camera_udvar_felso_h264', 'camera_udvar_felso_preview'],
    kapu: ['kapu', 'camera_kapu_felso_h264', 'camera_kapu_felso_preview']
  };
  var CAMERA_MJPEG_SOURCES = {
    gyerekszoba: 'c210rtsp1_mjpeg',
    kapu: 'camera_kapu_felso_preview',
    kapu2: 'camera_kapu_also_preview',
    udvar: 'camera_udvar_felso_preview',
    udvar2: 'camera_udvar_also_preview'
  };

  function makeProfileId() {
    return 'profile-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
  }

  function normalizePort(value, label) {
    var port = Number(value);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      throw new Error(label + ': 1 és 65535 közötti egész szám legyen.');
    }
    return port;
  }

  function normalizeHost(value) {
    var host = String(value || '').trim();
    var ipv4 = /^(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}$/;
    if (!ipv4.test(host)) {
      throw new Error('A host kanonikus, pontozott RFC1918 IPv4-cím legyen.');
    }
    var raw = host.split('.');
    var octets = raw.map(function (part) { return Number(part); });
    for (var i = 0; i < octets.length; i += 1) {
      if (octets[i] < 0 || octets[i] > 255 || String(octets[i]) !== raw[i]) {
        throw new Error('A host kanonikus IPv4-cím legyen.');
      }
    }
    var isPrivate = octets[0] === 10 ||
      (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
      (octets[0] === 192 && octets[1] === 168);
    if (!isPrivate) {
      throw new Error('Csak RFC1918 privát IPv4-cím engedélyezett.');
    }
    if (octets[3] === 0 || octets[3] === 255) {
      throw new Error('Hálózati vagy broadcast cím nem engedélyezett.');
    }
    if (host === FORBIDDEN_HOST) {
      throw new Error('A 192.168.0.100 cím használata ebben az appban tiltott.');
    }
    return host;
  }

  function normalizeSource(value, label) {
    var source = String(value || '').trim();
    if (!SAFE_ID.test(source)) {
      throw new Error(label + ': 1–48 karakteres betű/szám/._- alias legyen.');
    }
    if (/^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/.test(source) ||
        /(^|[^0-9])192\.168\.0\.100([^0-9]|$)/.test(source)) {
      throw new Error(label + ': IP-cím nem használható streamaliasként.');
    }
    return source;
  }

  function normalizeCameraId(value) {
    var cameraId = String(value || '').trim();
    if (!CAMERA_ID.test(cameraId)) {
      throw new Error('Kamera ID: 1–32 karakteres kisbetű/szám/._- azonosító legyen.');
    }
    return cameraId;
  }

  function validatePlayerPath(value) {
    var playerPath = String(value || '').trim();
    if (!playerPath) return '';
    if (playerPath.length > 192 || !/^\/[A-Za-z0-9._/-]+$/.test(playerPath) || playerPath.indexOf('//') !== -1) {
      throw new Error('A player path egyszerű, / jellel kezdődő helyi útvonal legyen.');
    }
    var segments = playerPath.split('/');
    for (var i = 0; i < segments.length; i += 1) {
      if (segments[i] === '.' || segments[i] === '..') {
        throw new Error('A player path nem tartalmazhat dot-segmentet.');
      }
    }
    return playerPath;
  }

  function validateProfile(input) {
    try {
      var name = String(input && input.name || '').trim();
      if (!name || name.length > 48) {
        throw new Error('A megjelenő név 1–48 karakter legyen.');
      }
      var cameraId = normalizeCameraId(input && input.cameraId);
      var id = String(input && input.id || '').trim();
      if (!SAFE_ID.test(id)) id = makeProfileId();
      var scheme = String(input && input.scheme || 'http').toLowerCase();
      if (scheme !== 'http' && scheme !== 'https') {
        throw new Error('Csak HTTP vagy HTTPS séma engedélyezett.');
      }
      if (input && input.audio !== undefined && typeof input.audio !== 'boolean') {
        throw new Error('A hang beállítása logikai érték legyen.');
      }
      var normalized = {
        id: id,
        cameraId: cameraId,
        name: name,
        scheme: scheme,
        host: normalizeHost(input && input.host),
        port: normalizePort(input && input.port, 'Média port'),
        playerPort: normalizePort(input && input.playerPort, 'Player port'),
        playerPath: validatePlayerPath(input && input.playerPath),
        audio: !!(input && input.audio),
        primarySource: normalizeSource(input && input.primarySource, 'Elsődleges forrás'),
        previewSource: normalizeSource(input && input.previewSource, 'Előnézeti forrás')
      };
      return { ok: true, value: normalized };
    } catch (error) {
      return { ok: false, error: error.message || String(error) };
    }
  }

  function gatewayOrigin(profile, player) {
    var port = player ? profile.playerPort : profile.port;
    return profile.scheme + '://' + profile.host + ':' + port;
  }

  function buildUrl(profile, mode) {
    var source = mode === 'webrtc'
      ? profile.primarySource
      : (mode === 'mjpeg' ? (CAMERA_MJPEG_SOURCES[profile.cameraId] || profile.previewSource) : profile.previewSource);
    var path = mode === 'mjpeg' ? '/api/stream.mjpeg?src=' : '/api/frame.jpeg?src=';
    return gatewayOrigin(profile, false) + path + source;
  }

  function buildPlayerUrl(profile, session) {
    if (!profile.playerPath) return '';
    return gatewayOrigin(profile, true) + profile.playerPath + '#src=' + profile.primarySource + '&session=' + session + '&audio=' + (profile.audio ? '1' : '0');
  }

  function buildSnapshotUrl(profile, maxAge) {
    var url = buildUrl(profile, 'snapshot');
    if (!maxAge) return url;
    return url + '&cache=' + encodeURIComponent(String(maxAge));
  }

  function cacheBusted(url) {
    return url + (url.indexOf('?') === -1 ? '?' : '&') + '_cv=' + Date.now();
  }

  function previewRefreshDelay(intervalSeconds, requestStartedAt, now) {
    var interval = Number(intervalSeconds) * 1000;
    var elapsed = Math.max(0, Number(now) - Number(requestStartedAt));
    return Math.max(50, interval - elapsed);
  }

  function sourceFromLegacyPath(path) {
    var match = /(?:[?&])(?:src|camera|stream)=([A-Za-z0-9][A-Za-z0-9._-]{0,47})(?:&|$)/.exec(String(path || ''));
    return match ? match[1] : null;
  }

  function migrateLegacyProfile(input) {
    try {
      var primary = sourceFromLegacyPath(input && input.path) || String(input && input.cameraId || '');
      var preview = sourceFromLegacyPath(input && input.snapshotPath) || primary;
      return validateProfile({
        id: input && input.id,
        cameraId: input && input.cameraId,
        name: input && input.name,
        scheme: input && input.scheme,
        host: input && input.host,
        port: input && input.port,
        playerPort: input && (input.playerPort || input.port),
        playerPath: input && (input.type === 'snapshot' || input.type === 'mjpeg') ? '' : (input && input.playerPath || ''),
        audio: !!(input && input.audio),
        primarySource: primary,
        previewSource: preview
      });
    } catch (error) {
      return { ok: false, error: error.message || String(error) };
    }
  }

  function canonicalCameraId(profile) {
    if (!profile) return null;
    var values = [profile.cameraId, profile.primarySource, profile.previewSource];
    var cameraIds = Object.keys(CANONICAL_PROFILE_ALIASES);
    for (var i = 0; i < cameraIds.length; i += 1) {
      var cameraId = cameraIds[i];
      var aliases = CANONICAL_PROFILE_ALIASES[cameraId];
      for (var valueIndex = 0; valueIndex < values.length; valueIndex += 1) {
        if (aliases.indexOf(String(values[valueIndex] || '')) !== -1) return cameraId;
      }
    }
    return null;
  }

  function reconcileProfiles(list, legacyFormat) {
    var customProfiles = [];
    var seenCustomIds = Object.create(null);
    if (Array.isArray(list)) {
      for (var i = 0; i < list.length; i += 1) {
        var checked = legacyFormat ? migrateLegacyProfile(list[i]) : validateProfile(list[i]);
        if (!checked.ok) continue;
        if (!seenCustomIds[checked.value.cameraId]) {
          seenCustomIds[checked.value.cameraId] = true;
          customProfiles.push(checked.value);
        }
      }
    }

    return customProfiles;
  }

  function migrateLegacyProfiles(list) {
    return reconcileProfiles(list, true);
  }

  function normalizeSettings(input) {
    input = input || {};
    var layoutSize = Number(input.layoutSize == null ? 2 : input.layoutSize);
    if (LAYOUT_SIZES.indexOf(layoutSize) === -1) throw new Error('A layout 2×2, 3×3 vagy 4×4 lehet.');
    var featuredCameraId = String(input.featuredCameraId || '').trim();
    if (featuredCameraId && !CAMERA_ID.test(featuredCameraId)) throw new Error('A kiemelt kamera ID-ja érvénytelen.');
    if (input.preventScreenSaver !== undefined && typeof input.preventScreenSaver !== 'boolean') {
      throw new Error('A képernyőkímélő-védelem logikai érték legyen.');
    }
    var previewIntervalSeconds = DEFAULT_PREVIEW_INTERVAL_SECONDS;
    return {
      layoutSize: layoutSize,
      featuredCameraId: featuredCameraId,
      preventScreenSaver: input.preventScreenSaver === true,
      previewIntervalSeconds: previewIntervalSeconds
    };
  }

  function normalizeProfileList(list) {
    if (!Array.isArray(list)) throw new Error('A kameralista érvénytelen.');
    var ids = Object.create(null);
    var cameraIds = Object.create(null);
    return list.map(function (item) {
      var checked = validateProfile(item);
      if (!checked.ok) throw new Error(checked.error);
      if (ids[checked.value.id] || cameraIds[checked.value.cameraId]) throw new Error('Ismétlődő kamera-azonosító.');
      ids[checked.value.id] = true;
      cameraIds[checked.value.cameraId] = true;
      return checked.value;
    });
  }

  function normalizeConfig(input) {
    if (!input || input.version !== 3) throw new Error('A Camera Viewer konfiguráció verziója érvénytelen.');
    var profiles = normalizeProfileList(input.profiles);
    var settings = normalizeSettings(input.settings);
    if (settings.featuredCameraId && !profiles.some(function (profile) { return profile.cameraId === settings.featuredCameraId; })) {
      settings.featuredCameraId = '';
    }
    return { version: 3, settings: settings, profiles: profiles };
  }

  function defaultConfig() {
    return normalizeConfig({
      version: 3,
      settings: { layoutSize: 2, featuredCameraId: '', preventScreenSaver: false, previewIntervalSeconds: DEFAULT_PREVIEW_INTERVAL_SECONDS },
      profiles: DEFAULT_PROFILES
    });
  }

  function pageLayout(profiles, settings, requestedPage) {
    profiles = Array.isArray(profiles) ? profiles.slice() : [];
    settings = normalizeSettings(settings);
    var featured = null;
    if (settings.layoutSize >= 3 && settings.featuredCameraId) {
      featured = profiles.find(function (profile) { return profile.cameraId === settings.featuredCameraId; }) || null;
    }
    var regular = featured ? profiles.filter(function (profile) { return profile.id !== featured.id; }) : profiles;
    var regularCapacity = featured ? settings.layoutSize * settings.layoutSize - 4 : settings.layoutSize * settings.layoutSize;
    var pageCount = Math.max(1, Math.ceil(regular.length / regularCapacity));
    var page = Math.max(0, Math.min(pageCount - 1, Number(requestedPage) || 0));
    var items = regular.slice(page * regularCapacity, (page + 1) * regularCapacity).map(function (profile) {
      return { profile: profile, featured: false };
    });
    if (featured) items.unshift({ profile: featured, featured: true });
    return { page: page, pageCount: pageCount, items: items, layoutSize: settings.layoutSize, featured: !!featured };
  }

  function normalizeSyncUrl(value, moduleName) {
    var text = String(value || '').trim();
    var match = /^https?:\/\/(\d{1,3}(?:\.\d{1,3}){3})(?::([0-9]{1,5}))?(\/api\/tv-sync\/(media-overlay|camera-viewer))$/.exec(text);
    if (!match || match[3] !== '/api/tv-sync/' + moduleName) throw new Error('A szinkron URL érvénytelen.');
    normalizeHost(match[1]);
    if (match[2]) normalizePort(match[2], 'Szinkron port');
    return text;
  }

  function parseObject(value) {
    if (!value) return null;
    if (typeof value === 'object') return value;
    if (typeof value === 'string') {
      try { return JSON.parse(value); } catch (error) { return null; }
    }
    return null;
  }

  function unwrapLaunchObject(raw) {
    var parsed = parseObject(raw);
    for (var depth = 0; parsed && depth < 3; depth += 1) {
      if (Object.prototype.hasOwnProperty.call(parsed, 'launchParams')) parsed = parseObject(parsed.launchParams);
      else if (Object.prototype.hasOwnProperty.call(parsed, 'parameters')) parsed = parseObject(parsed.parameters);
      else break;
    }
    return parsed;
  }

  function isPlainLauncherOpen(raw) {
    var parsed = unwrapLaunchObject(raw);
    if (!parsed || typeof parsed !== 'object') return false;
    var keys = Object.keys(parsed);
    if (keys.length === 0) return true;
    return keys.length === 1 && keys[0] === 'storeCaller' && parsed.storeCaller === 'home';
  }

  function reorderProfiles(profiles, cameraIds) {
    if (!Array.isArray(profiles) || !Array.isArray(cameraIds) || profiles.length !== cameraIds.length) {
      throw new Error('A kamerasorrendnek minden kamerát pontosan egyszer kell tartalmaznia.');
    }
    var byCameraId = Object.create(null);
    for (var i = 0; i < profiles.length; i += 1) byCameraId[profiles[i].cameraId] = profiles[i];
    var seen = Object.create(null);
    var ordered = [];
    for (var index = 0; index < cameraIds.length; index += 1) {
      var cameraId = normalizeCameraId(cameraIds[index]);
      if (seen[cameraId] || !byCameraId[cameraId]) {
        throw new Error('A kamerasorrend ismeretlen vagy ismétlődő kamerát tartalmaz.');
      }
      seen[cameraId] = true;
      ordered.push(byCameraId[cameraId]);
    }
    return ordered;
  }

  function extractLaunchCommand(raw) {
    var parsed = unwrapLaunchObject(raw);
    if (!parsed) return { ok: false, error: 'Érvénytelen launch paraméter.' };
    var action = String(parsed.action || '');
    var allowedByAction = {
      open: { v: true, action: true, cameraId: true, profileId: true, view: true, requestId: true },
      sync: { v: true, action: true, syncUrl: true, requestId: true },
      configure: { v: true, action: true, layoutSize: true, featuredCameraId: true, preventScreenSaver: true, previewIntervalSeconds: true, syncUrl: true, requestId: true },
      'camera-save': {
        v: true, action: true, id: true, cameraId: true, name: true, scheme: true, host: true, audio: true,
        port: true, playerPort: true, playerPath: true, primarySource: true, previewSource: true,
        syncUrl: true, requestId: true
      },
      'camera-delete': { v: true, action: true, cameraId: true, syncUrl: true, requestId: true },
      'camera-reorder': { v: true, action: true, cameraIds: true, syncUrl: true, requestId: true }
    };
    var allowed = allowedByAction[action];
    if (parsed.v !== 1 || !allowed) return { ok: false, error: 'A launch kérés művelete érvénytelen.' };
    var keys = Object.keys(parsed);
    for (var i = 0; i < keys.length; i += 1) {
      if (!allowed[keys[i]]) return { ok: false, error: 'A launch paraméter tiltott mezőt tartalmaz.' };
    }
    if (parsed.requestId !== undefined && !REQUEST_ID.test(String(parsed.requestId))) {
      return { ok: false, error: 'A requestId érvénytelen.' };
    }
    var common = {
      action: action,
      requestId: parsed.requestId === undefined ? null : String(parsed.requestId).toLowerCase()
    };
    if (parsed.syncUrl !== undefined) {
      try { common.syncUrl = normalizeSyncUrl(parsed.syncUrl, 'camera-viewer'); }
      catch (syncError) { return { ok: false, error: syncError.message }; }
    }
    if (action === 'sync') return { ok: true, value: common };
    if (action === 'configure') {
      try {
        common.settings = normalizeSettings({
          layoutSize: parsed.layoutSize,
          featuredCameraId: parsed.featuredCameraId,
          preventScreenSaver: parsed.preventScreenSaver,
          previewIntervalSeconds: parsed.previewIntervalSeconds
        });
        return { ok: true, value: common };
      } catch (settingsError) { return { ok: false, error: settingsError.message }; }
    }
    if (action === 'camera-save') {
      var checked = validateProfile(parsed);
      if (!checked.ok) return { ok: false, error: checked.error };
      common.profile = checked.value;
      return { ok: true, value: common };
    }
    if (action === 'camera-delete') {
      try { common.cameraId = normalizeCameraId(parsed.cameraId); }
      catch (cameraError) { return { ok: false, error: cameraError.message }; }
      return { ok: true, value: common };
    }
    if (action === 'camera-reorder') {
      if (!Array.isArray(parsed.cameraIds)) return { ok: false, error: 'A kamerasorrend listája érvénytelen.' };
      common.cameraIds = [];
      var seenCameraIds = Object.create(null);
      try {
        for (var orderIndex = 0; orderIndex < parsed.cameraIds.length; orderIndex += 1) {
          var orderCameraId = normalizeCameraId(parsed.cameraIds[orderIndex]);
          if (seenCameraIds[orderCameraId]) throw new Error('A kamerasorrend ismétlődő kamerát tartalmaz.');
          seenCameraIds[orderCameraId] = true;
          common.cameraIds.push(orderCameraId);
        }
      } catch (orderError) { return { ok: false, error: orderError.message }; }
      return { ok: true, value: common };
    }
    var hasCameraId = Object.prototype.hasOwnProperty.call(parsed, 'cameraId');
    var hasProfileId = Object.prototype.hasOwnProperty.call(parsed, 'profileId');
    if (hasCameraId === hasProfileId) return { ok: false, error: 'Pontosan egy cameraId vagy profileId adható meg.' };
    var targetId = hasCameraId ? parsed.cameraId : parsed.profileId;
    if (parsed.view !== 'full' || !(hasCameraId ? CAMERA_ID : SAFE_ID).test(String(targetId || ''))) {
      return { ok: false, error: 'A launch kérés formátuma érvénytelen.' };
    }
    common.cameraId = hasCameraId ? String(parsed.cameraId) : null;
    common.profileId = hasProfileId ? String(parsed.profileId) : null;
    return { ok: true, value: common };
  }

  function playbackPlan(profile, preferredTransport) {
    var hasVideo = !!(profile && profile.playerPath);
    var preferred = preferredTransport === 'webrtc' && hasVideo ? 'webrtc' : 'mjpeg';
    var plan = [preferred];
    if (hasVideo) plan.push(preferred === 'webrtc' ? 'mjpeg' : 'webrtc');
    plan.push('snapshot');
    return plan;
  }

  function screenSaverResponsePayload(message) {
    if (!message || message.returnValue !== true || message.state !== 'Active') return null;
    var timestamp = String(message.timestamp == null ? '' : message.timestamp);
    if (!/^[0-9]{1,24}$/.test(timestamp)) return null;
    return { clientName: SCREEN_SAVER_CLIENT, ack: false, timestamp: timestamp };
  }

  var api = {
    STORAGE_KEY: STORAGE_KEY,
    LEGACY_STORAGE_KEY: LEGACY_STORAGE_KEY,
    MAX_PROFILES: null,
    CONFIG_KEY: CONFIG_KEY,
    SYNC_URL_KEY: SYNC_URL_KEY,
    FULLSCREEN_TRANSPORT_KEY: FULLSCREEN_TRANSPORT_KEY,
    FORBIDDEN_HOST: FORBIDDEN_HOST,
    DEFAULT_PROFILES: DEFAULT_PROFILES,
    CANONICAL_PROFILE_ALIASES: CANONICAL_PROFILE_ALIASES,
    CAMERA_MJPEG_SOURCES: CAMERA_MJPEG_SOURCES,
    validateProfile: validateProfile,
    validatePlayerPath: validatePlayerPath,
    buildUrl: buildUrl,
    buildSnapshotUrl: buildSnapshotUrl,
    buildPlayerUrl: buildPlayerUrl,
    gatewayOrigin: gatewayOrigin,
    migrateLegacyProfile: migrateLegacyProfile,
    migrateLegacyProfiles: migrateLegacyProfiles,
    reconcileProfiles: reconcileProfiles,
    normalizeSettings: normalizeSettings,
    normalizeProfileList: normalizeProfileList,
    normalizeConfig: normalizeConfig,
    defaultConfig: defaultConfig,
    pageLayout: pageLayout,
    normalizeSyncUrl: normalizeSyncUrl,
    extractLaunchCommand: extractLaunchCommand,
    isPlainLauncherOpen: isPlainLauncherOpen,
    reorderProfiles: reorderProfiles,
    playbackPlan: playbackPlan,
    screenSaverResponsePayload: screenSaverResponsePayload,
    previewRefreshDelay: previewRefreshDelay,
    SCREEN_SAVER_CLIENT: SCREEN_SAVER_CLIENT,
    SCREEN_SAVER_REGISTER_URI: SCREEN_SAVER_REGISTER_URI,
    SCREEN_SAVER_RESPONSE_URI: SCREEN_SAVER_RESPONSE_URI
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CameraViewerCore = api;
  if (!root.document) return;

  var state = {
    profiles: [],
    settings: { layoutSize: 2, featuredCameraId: '', preventScreenSaver: false, previewIntervalSeconds: DEFAULT_PREVIEW_INTERVAL_SECONDS },
    page: 0,
    pageCount: 1,
    syncUrl: '',
    editingId: null,
    selectedId: null,
    view: 'grid',
    suspended: false,
    gridJobs: [],
    gridSnapshotQueue: [],
    gridSnapshotBusy: false,
    activeGridSnapshotJob: null,
    activeGridLiveJob: null,
    activeJob: null,
    generation: 0,
    seenRequestIds: [],
    lastCommandFingerprint: null,
    lastCommandAt: 0,
    pendingLaunchId: null,
    pendingLaunchClosesApp: false,
    viewerClosesApp: false,
    fullscreenTransport: 'mjpeg'
  };
  var ui = {};
  var screenSaverSubscriptionBridge = null;
  var screenSaverResponseBridge = null;
  var screenSaverRegisterTimer = null;
  var floatingMessageTimer = null;
  var viewerStatusTimer = null;
  var presenceTimer = null;

  function byId(id) { return root.document.getElementById(id); }
  function showMessage(text) {
    if (floatingMessageTimer !== null) root.clearTimeout(floatingMessageTimer);
    floatingMessageTimer = null;
    ui.message.textContent = text || '';
    if (text) {
      floatingMessageTimer = root.setTimeout(function () {
        floatingMessageTimer = null;
        ui.message.textContent = '';
      }, FLOATING_MESSAGE_TIMEOUT);
    }
  }

  function stopPresenceHeartbeat() {
    if (presenceTimer !== null) root.clearTimeout(presenceTimer);
    presenceTimer = null;
  }

  function sendPresenceHeartbeat() {
    stopPresenceHeartbeat();
    var marker = '/api/tv-sync/';
    var markerIndex = state.syncUrl.indexOf(marker);
    var presenceUrl = markerIndex > 0 ? state.syncUrl.slice(0, markerIndex) + '/api/tv-presence/camera-viewer' : '';
    if (state.suspended || typeof root.fetch !== 'function' || !presenceUrl) return;
    try {
      root.fetch(presenceUrl, {
        method: 'POST',
        mode: 'no-cors',
        cache: 'no-store',
        keepalive: true,
        headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
        body: JSON.stringify({ active: true })
      }).catch(function () {});
    } catch (error) { /* presence is best effort */ }
    presenceTimer = root.setTimeout(sendPresenceHeartbeat, PRESENCE_INTERVAL_MS);
  }

  function readStoredList(key) {
    var raw = root.localStorage.getItem(key);
    if (!raw) return null;
    try {
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : null;
    } catch (error) {
      return null;
    }
  }

  function loadAppConfig() {
    try {
      var configRaw = root.localStorage.getItem(CONFIG_KEY);
      if (configRaw) return normalizeConfig(JSON.parse(configRaw));
      var currentRaw = root.localStorage.getItem(STORAGE_KEY);
      if (currentRaw !== null) {
        var current = readStoredList(STORAGE_KEY);
        if (!current) {
          showMessage('A mentett kameraadatok sérültek; biztonságos alapértékek töltődtek be.');
          return defaultConfig();
        }
        var reconciled = reconcileProfiles(current);
        var migratedCurrent = normalizeConfig({ version: 3, settings: {}, profiles: reconciled });
        root.localStorage.setItem(CONFIG_KEY, JSON.stringify(migratedCurrent));
        showMessage('A kamerák korlátlan 0.3 formátumra frissítve.');
        return migratedCurrent;
      }
      var migrated = migrateLegacyProfiles(readStoredList(LEGACY_STORAGE_KEY) || []);
      var migratedLegacy = normalizeConfig({ version: 3, settings: {}, profiles: migrated });
      root.localStorage.setItem(CONFIG_KEY, JSON.stringify(migratedLegacy));
      showMessage('A kamerák korlátlan 0.3 formátumra frissítve.');
      return migratedLegacy;
    } catch (error) {
      showMessage('A helyi tárhely nem olvasható; az alap kamerák csak erre a futásra élnek.');
      return defaultConfig();
    }
  }

  function syncPayload() {
    return { module: 'camera-viewer', version: 1, config: {
      version: 3,
      settings: state.settings,
      profiles: state.profiles
    } };
  }

  function pushSync() {
    if (!state.syncUrl || typeof root.fetch !== 'function') return Promise.resolve(false);
    return root.fetch(state.syncUrl, {
      method: 'POST',
      mode: 'no-cors',
      keepalive: true,
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: JSON.stringify(syncPayload())
    }).then(function () { return true; }, function () { return false; });
  }

  function saveProfiles() {
    try {
      var normalized = normalizeConfig({ version: 3, settings: state.settings, profiles: state.profiles });
      state.profiles = normalized.profiles;
      state.settings = normalized.settings;
      root.localStorage.setItem(CONFIG_KEY, JSON.stringify(normalized));
      pushSync();
      return true;
    } catch (error) {
      showMessage('A kamerabeállítás nem menthető a helyi tárhelyre.');
      return false;
    }
  }

  function stopLegacyScreenGuard() {
    if (!ui.screenGuard) return;
    try { ui.screenGuard.pause(); } catch (error) { /* no-op */ }
    ui.screenGuard.removeAttribute('src');
    try { ui.screenGuard.load(); } catch (loadError) { /* no-op */ }
  }

  function startLegacyScreenGuard() {
    // Performance mode: never start a hidden fallback video. A second video
    // decoder can contend with the selected camera stream on older webOS TVs.
    // Screen-saver suppression relies only on the Luna subscription.
    stopLegacyScreenGuard();
  }

  function clearScreenSaverRegisterTimer() {
    if (screenSaverRegisterTimer === null) return;
    root.clearTimeout(screenSaverRegisterTimer);
    screenSaverRegisterTimer = null;
  }

  function cancelBridge(bridge) {
    try { if (bridge && typeof bridge.cancel === 'function') bridge.cancel(); } catch (error) { /* no-op */ }
  }

  function stopScreenGuard() {
    clearScreenSaverRegisterTimer();
    cancelBridge(screenSaverSubscriptionBridge);
    cancelBridge(screenSaverResponseBridge);
    screenSaverSubscriptionBridge = null;
    screenSaverResponseBridge = null;
    stopLegacyScreenGuard();
  }

  function answerScreenSaverRequest(message) {
    var payload = screenSaverResponsePayload(message);
    if (!payload) return;
    cancelBridge(screenSaverResponseBridge);
    screenSaverResponseBridge = null;
    try {
      var bridge = new root.PalmServiceBridge();
      screenSaverResponseBridge = bridge;
      bridge.onservicecallback = function (raw) {
        if (screenSaverResponseBridge !== bridge) return;
        screenSaverResponseBridge = null;
        var result = null;
        try { result = JSON.parse(raw); } catch (error) { /* fail closed to the legacy guard */ }
        if (!result || result.returnValue !== true) startLegacyScreenGuard();
      };
      bridge.call(SCREEN_SAVER_RESPONSE_URI, JSON.stringify(payload));
    } catch (error) {
      screenSaverResponseBridge = null;
      startLegacyScreenGuard();
    }
  }

  function startScreenGuard() {
    if (!state.settings.preventScreenSaver || state.suspended) {
      stopScreenGuard();
      return;
    }
    if (screenSaverSubscriptionBridge) return;
    if (typeof root.PalmServiceBridge !== 'function') {
      startLegacyScreenGuard();
      return;
    }
    try {
      var bridge = new root.PalmServiceBridge();
      screenSaverSubscriptionBridge = bridge;
      bridge.onservicecallback = function (raw) {
        if (screenSaverSubscriptionBridge !== bridge) return;
        var message = null;
        try { message = JSON.parse(raw); } catch (error) { /* handled below */ }
        if (!message || message.returnValue !== true) {
          clearScreenSaverRegisterTimer();
          cancelBridge(bridge);
          screenSaverSubscriptionBridge = null;
          startLegacyScreenGuard();
          return;
        }
        clearScreenSaverRegisterTimer();
        stopLegacyScreenGuard();
        answerScreenSaverRequest(message);
      };
      bridge.call(SCREEN_SAVER_REGISTER_URI, JSON.stringify({
        subscribe: true,
        clientName: SCREEN_SAVER_CLIENT
      }));
      screenSaverRegisterTimer = root.setTimeout(function () {
        screenSaverRegisterTimer = null;
        if (screenSaverSubscriptionBridge === bridge) startLegacyScreenGuard();
      }, 3500);
    } catch (error) {
      screenSaverSubscriptionBridge = null;
      startLegacyScreenGuard();
    }
  }

  function cacheSessionId() {
    var bytes = new Uint8Array(16);
    if (root.crypto && root.crypto.getRandomValues) root.crypto.getRandomValues(bytes);
    else {
      for (var i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    }
    var result = '';
    for (var index = 0; index < bytes.length; index += 1) result += ('0' + bytes[index].toString(16)).slice(-2);
    return result;
  }

  function hardStopImage(image) {
    if (!image) return;
    image.onload = null;
    image.onerror = null;
    try { image.src = EMPTY_IMAGE_SRC; } catch (error) { /* best effort */ }
    try { image.removeAttribute('src'); } catch (removeError) { /* best effort */ }
  }

  function clearGridLivePreview(job) {
    if (!job) return;
    if (job.focusTimer) root.clearTimeout(job.focusTimer);
    job.focusTimer = null;
    var liveImage = job.liveImage;
    var liveBadge = job.liveBadge;
    job.liveImage = null;
    job.liveBadge = null;
    if (job.tile) job.tile.classList.remove('is-live');
    if (state.activeGridLiveJob === job) {
      state.activeGridLiveJob = null;
      root.setTimeout(function () {
        pumpGridSnapshotQueue();
        startScreenGuard();
      }, 80);
    }
    if (liveBadge && liveBadge.parentNode) liveBadge.parentNode.removeChild(liveBadge);
    if (liveImage) {
      liveImage.style.display = 'none';
      hardStopImage(liveImage);
      if (liveImage.parentNode) liveImage.parentNode.removeChild(liveImage);
    }
  }

  function snapshotQueueFlag(kind) {
    return kind === 'cache' ? 'cacheQueued' : 'snapshotQueued';
  }

  function enqueueGridSnapshot(job, kind) {
    if (!job || job.stopped) return;
    var flag = snapshotQueueFlag(kind);
    if (job[flag]) return;
    job[flag] = true;
    state.gridSnapshotQueue.push({ job: job, kind: kind });
  }

  function scheduleGridSnapshot(job, kind, wait) {
    var timerKey = kind === 'cache' ? 'cacheTimer' : 'timer';
    if (job[timerKey]) root.clearTimeout(job[timerKey]);
    job[timerKey] = root.setTimeout(function () {
      job[timerKey] = null;
      if (job.stopped || state.suspended || state.view !== 'grid') return;
      enqueueGridSnapshot(job, kind);
      pumpGridSnapshotQueue();
    }, Math.max(0, Number(wait) || 0));
  }

  function finishGridSnapshot(job, loader, kind, succeeded) {
    if (!job || job.loader !== loader) return;
    job.loader = null;
    job.loadingKind = null;
    if (state.activeGridSnapshotJob === job) state.activeGridSnapshotJob = null;
    state.gridSnapshotBusy = false;

    if (succeeded && !job.stopped && state.view === 'grid' && job.tile &&
        root.document.documentElement.contains(job.tile)) {
      var oldImage = job.image;
      loader.onload = null;
      loader.onerror = null;
      loader.alt = '';
      if (oldImage && oldImage.parentNode) oldImage.parentNode.replaceChild(loader, oldImage);
      job.image = loader;
      job.hasSnapshot = true;
      job.failures = 0;
      job.statusNode.textContent = '';
      job.statusNode.classList.remove('offline');
    } else {
      hardStopImage(loader);
      if (!job.hasSnapshot && !job.stopped) {
        job.failures += 1;
        job.statusNode.textContent = 'nincs előnézet';
        job.statusNode.classList.add('offline');
      }
    }

    if (kind === 'fresh' && !job.stopped && !state.suspended && state.view === 'grid') {
      scheduleGridSnapshot(
        job,
        'fresh',
        previewRefreshDelay(DEFAULT_PREVIEW_INTERVAL_SECONDS, job.requestStartedAt, Date.now())
      );
    }
    root.setTimeout(pumpGridSnapshotQueue, 80);
  }

  function abortActiveGridSnapshot(requeue) {
    var job = state.activeGridSnapshotJob;
    if (!job) return;
    var loader = job.loader;
    var kind = job.loadingKind || 'fresh';
    job.loader = null;
    job.loadingKind = null;
    state.activeGridSnapshotJob = null;
    state.gridSnapshotBusy = false;
    hardStopImage(loader);
    if (requeue && !job.stopped && state.view === 'grid') enqueueGridSnapshot(job, kind);
  }

  function pumpGridSnapshotQueue() {
    if (state.gridSnapshotBusy || state.suspended || state.view !== 'grid' || state.activeGridLiveJob) return;
    while (state.gridSnapshotQueue.length) {
      var entry = state.gridSnapshotQueue.shift();
      var job = entry.job;
      var kind = entry.kind === 'cache' ? 'cache' : 'fresh';
      job[snapshotQueueFlag(kind)] = false;
      if (job.stopped || !job.image || !job.tile || !root.document.documentElement.contains(job.tile)) continue;

      var loader = root.document.createElement('img');
      state.gridSnapshotBusy = true;
      state.activeGridSnapshotJob = job;
      job.loader = loader;
      job.loadingKind = kind;
      job.requestStartedAt = Date.now();

      loader.onload = function (snapshotJob, snapshotLoader, snapshotKind) {
        return function () { finishGridSnapshot(snapshotJob, snapshotLoader, snapshotKind, true); };
      }(job, loader, kind);
      loader.onerror = function (snapshotJob, snapshotLoader, snapshotKind) {
        return function () { finishGridSnapshot(snapshotJob, snapshotLoader, snapshotKind, false); };
      }(job, loader, kind);

      loader.src = cacheBusted(buildSnapshotUrl(
        job.profile,
        kind === 'cache' ? SNAPSHOT_CACHE_MAX_AGE : SNAPSHOT_REFRESH_CACHE_MAX_AGE
      ));
      return;
    }
  }

  function stopGridJobs() {
    abortActiveGridSnapshot(false);
    for (var i = 0; i < state.gridJobs.length; i += 1) {
      var job = state.gridJobs[i];
      job.stopped = true;
      if (job.timer) root.clearTimeout(job.timer);
      if (job.cacheTimer) root.clearTimeout(job.cacheTimer);
      if (job.liveRetryTimer) { root.clearTimeout(job.liveRetryTimer); job.liveRetryTimer = null; }
      clearGridLivePreview(job);
      if (job.tile && job.onFocus && typeof job.tile.removeEventListener === 'function') job.tile.removeEventListener('focus', job.onFocus);
      if (job.tile && job.onBlur && typeof job.tile.removeEventListener === 'function') job.tile.removeEventListener('blur', job.onBlur);
      hardStopImage(job.loader);
      job.loader = null;
      if (job.image) hardStopImage(job.image);
    }
    state.gridJobs = [];
    state.gridSnapshotQueue = [];
    state.gridSnapshotBusy = false;
    state.activeGridSnapshotJob = null;
  }

  function startGridSnapshot(image, profile, cacheDelay, freshDelay, statusNode, tile) {
    var job = {
      image: image,
      profile: profile,
      tile: tile,
      statusNode: statusNode,
      timer: null,
      cacheTimer: null,
      focusTimer: null,
      liveImage: null,
      liveBadge: null,
      liveRetryTimer: null,
      loader: null,
      loadingKind: null,
      onFocus: null,
      onBlur: null,
      stopped: false,
      failures: 0,
      requestStartedAt: 0,
      snapshotQueued: false,
      cacheQueued: false,
      hasSnapshot: false
    };
    state.gridJobs.push(job);

    function scheduleLivePreview(wait) {
      if (job.focusTimer) root.clearTimeout(job.focusTimer);
      job.focusTimer = root.setTimeout(startLivePreview, wait);
    }

    function startLivePreview() {
      job.focusTimer = null;
      if (job.stopped || state.suspended || state.view !== 'grid' || root.document.activeElement !== tile) return;
      if (state.activeGridLiveJob && state.activeGridLiveJob !== job) clearGridLivePreview(state.activeGridLiveJob);
      if (job.liveImage) clearGridLivePreview(job);
      abortActiveGridSnapshot(true);
      stopLegacyScreenGuard();
      state.activeGridLiveJob = job;
      statusNode.textContent = '';
      statusNode.classList.remove('offline');

      var liveImage = root.document.createElement('img');
      var liveBadge = root.document.createElement('span');
      liveImage.alt = '';
      liveImage.className = 'camera-grid-live';
      liveImage.setAttribute('data-live-mjpeg', buildUrl(profile, 'mjpeg'));
      liveBadge.className = 'camera-grid-live-badge';
      liveBadge.textContent = 'LIVE';
      tile.appendChild(liveImage);
      tile.appendChild(liveBadge);
      job.liveImage = liveImage;
      job.liveBadge = liveBadge;
      tile.classList.add('is-live');

      liveImage.onerror = function () {
        if (job.liveImage !== liveImage) return;
        clearGridLivePreview(job);
        if (!job.stopped && !state.suspended && state.view === 'grid' && root.document.activeElement === tile) {
          if (job.liveRetryTimer) root.clearTimeout(job.liveRetryTimer);
          job.liveRetryTimer = root.setTimeout(function () {
            job.liveRetryTimer = null;
            if (root.document.activeElement === tile) scheduleLivePreview(0);
          }, GRID_LIVE_RETRY_DELAY_MS);
        }
      };
      liveImage.src = buildUrl(profile, 'mjpeg');
    }

    job.onFocus = function () {
      if (job.liveRetryTimer) { root.clearTimeout(job.liveRetryTimer); job.liveRetryTimer = null; }
      scheduleLivePreview(GRID_LIVE_FOCUS_DELAY_MS);
    };
    job.onBlur = function () {
      if (job.liveRetryTimer) { root.clearTimeout(job.liveRetryTimer); job.liveRetryTimer = null; }
      clearGridLivePreview(job);
    };
    tile.addEventListener('focus', job.onFocus);
    tile.addEventListener('blur', job.onBlur);

    scheduleGridSnapshot(job, 'cache', cacheDelay);
    scheduleGridSnapshot(job, 'fresh', freshDelay);
  }

  function applyGridGeometry(layoutSize) {
    var width = Number(ui.cameraGrid.clientWidth) || 0;
    var height = Number(ui.cameraGrid.clientHeight) || 0;
    if (!width || !height) return;
    // A 16 px horizontal and 9 px vertical gap also preserves 16:9 when a
    // featured tile spans two columns and two rows.
    var columnGap = 16;
    var rowGap = 9;
    var maxWidth = (width - columnGap * (layoutSize - 1)) / layoutSize;
    var maxHeight = (height - rowGap * (layoutSize - 1)) / layoutSize;
    var cellWidth = Math.min(maxWidth, maxHeight * 16 / 9);
    var cellHeight = cellWidth * 9 / 16;
    ui.cameraGrid.style.gridTemplateColumns = 'repeat(' + layoutSize + ', minmax(0, ' + Math.floor(cellWidth) + 'px))';
    ui.cameraGrid.style.gridTemplateRows = 'repeat(' + layoutSize + ', minmax(0, ' + Math.floor(cellHeight) + 'px))';
    ui.cameraGrid.style.justifyContent = 'center';
    ui.cameraGrid.style.alignContent = 'center';
  }

  function gridTilePosition(index, layoutSize, hasFeatured) {
    if (hasFeatured && index === 0) return { x: 1.5, y: 1.5 };
    var regularIndex = hasFeatured ? index - 1 : index;
    var free = [];
    for (var row = 1; row <= layoutSize; row += 1) {
      for (var column = 1; column <= layoutSize; column += 1) {
        if (hasFeatured && row <= 2 && column <= 2) continue;
        free.push({ x: column, y: row });
      }
    }
    return free[Math.max(0, Math.min(free.length - 1, regularIndex))] || { x: 1, y: 1 };
  }

  function toggleFeaturedCamera(profile) {
    if (!profile) return;
    var removing = state.settings.featuredCameraId === profile.cameraId;
    state.settings.featuredCameraId = removing ? '' : profile.cameraId;
    state.page = 0;
    if (!saveProfiles()) return;
    renderGrid();
    showMessage(removing
      ? 'Kiemelés kikapcsolva.'
      : profile.name + ' kiemelve. A nagy csempe 3×3 vagy 4×4 layoutban látható.');
  }

  function renderGrid() {
    stopGridJobs();
    ui.cameraGrid.textContent = '';
    var layout = pageLayout(state.profiles, state.settings, state.page);
    state.page = layout.page;
    state.pageCount = layout.pageCount;
    ui.cameraGrid.className = 'camera-grid layout-' + layout.layoutSize + (layout.featured ? ' has-featured' : '');
    applyGridGeometry(layout.layoutSize);
    ui.emptyState.classList.toggle('hidden', state.profiles.length !== 0);
    ui.cameraGrid.classList.toggle('hidden', state.profiles.length === 0);
    ui.pageControls.classList.toggle('hidden', state.profiles.length === 0 || layout.pageCount <= 1);
    ui.pageIndicator.textContent = (layout.page + 1) + ' / ' + layout.pageCount;
    ui.pagePrevious.disabled = layout.page <= 0;
    ui.pageNext.disabled = layout.page >= layout.pageCount - 1;
    for (var i = 0; i < layout.items.length; i += 1) {
      (function (entry, index) {
        var profile = entry.profile;
        var cell = root.document.createElement('div');
        var tile = root.document.createElement('button');
        var featureButton = root.document.createElement('button');
        var image = root.document.createElement('img');
        var shade = root.document.createElement('span');
        var caption = root.document.createElement('span');
        var name = root.document.createElement('span');
        var status = root.document.createElement('span');
        tile.type = 'button';
        cell.className = 'camera-cell' + (entry.featured ? ' featured-camera' : '');
        tile.className = 'camera-tile';
        tile.setAttribute('data-profile-id', profile.id);
        var gridPosition = gridTilePosition(index, layout.layoutSize, layout.featured);
        tile.setAttribute('data-grid-x', String(gridPosition.x));
        tile.setAttribute('data-grid-y', String(gridPosition.y));
        tile.setAttribute('aria-label', profile.name + ' megnyitása');
        image.alt = '';
        shade.className = 'tile-shade';
        caption.className = 'tile-caption';
        name.className = 'tile-name';
        name.textContent = profile.name;
        status.className = 'tile-state';
        status.textContent = '';
        caption.appendChild(name);
        caption.appendChild(status);
        tile.appendChild(image);
        tile.appendChild(shade);
        tile.appendChild(caption);
        tile.addEventListener('click', function () { openViewer(profile); });
        featureButton.type = 'button';
        featureButton.className = 'camera-feature' +
          (state.settings.featuredCameraId === profile.cameraId ? ' is-featured' : '');
        featureButton.textContent = '👁';
        featureButton.setAttribute('aria-label', state.settings.featuredCameraId === profile.cameraId
          ? profile.name + ' kiemelésének kikapcsolása'
          : profile.name + ' kiemelése');
        featureButton.addEventListener('click', function (event) {
          event.stopPropagation();
          toggleFeaturedCamera(profile);
        });
        cell.appendChild(tile);
        cell.appendChild(featureButton);
        ui.cameraGrid.appendChild(cell);
        startGridSnapshot(
          image,
          profile,
          index * GRID_CACHE_WARM_STAGGER_MS,
          1000 + index * GRID_SNAPSHOT_STAGGER_MS,
          status,
          tile
        );
      }(layout.items[i], i));
    }
    startScreenGuard();
  }

  function changePage(direction) {
    var next = Math.max(0, Math.min(state.pageCount - 1, state.page + direction));
    if (next === state.page) return;
    state.page = next;
    renderGrid();
    var first = ui.cameraGrid.querySelector('.camera-tile');
    (first || (direction < 0 ? ui.pagePrevious : ui.pageNext)).focus();
  }

  function currentJob(job) {
    return !!job && !job.stopped && state.activeJob === job && state.generation === job.generation && !state.suspended;
  }

  function clearTransport(job) {
    if (!job) return;
    if (job.timer) root.clearTimeout(job.timer);
    if (job.refreshTimer) root.clearTimeout(job.refreshTimer);
    if (job.handoffTimer) root.clearTimeout(job.handoffTimer);
    job.timer = null;
    job.refreshTimer = null;
    job.handoffTimer = null;
    if (job.messageHandler && root.removeEventListener) root.removeEventListener('message', job.messageHandler);
    job.messageHandler = null;
    if (job.node) {
      job.node.onload = null;
      job.node.onerror = null;
      if (job.node.tagName === 'IFRAME') {
        try {
          if (job.node.contentWindow) job.node.contentWindow.postMessage({ channel: 'hu.szabi.cameraviewer.player', type: 'stop', session: job.session }, '*');
        } catch (error) { /* iframe replacement below is the hard stop */ }
        try { job.node.src = 'about:blank'; } catch (blankError) { /* best effort */ }
        job.node.removeAttribute('src');
      } else {
        hardStopImage(job.node);
      }
    }
    job.node = null;
    if (ui.viewerAudio) ui.viewerAudio.classList.add('hidden');
    ui.viewerStage.textContent = '';
  }

  function stopActivePlayer() {
    state.generation += 1;
    var job = state.activeJob;
    state.activeJob = null;
    if (job) {
      job.stopped = true;
      clearTransport(job);
    }
    ui.viewerStage.textContent = '';
  }

  function updateViewerTransportToggle(profile) {
    if (!ui.viewerMode) return;
    var canUseVideo = !!(profile && profile.playerPath);
    ui.viewerMode.classList.toggle('hidden', !canUseVideo);
    if (!canUseVideo) return;
    var usingVideo = state.fullscreenTransport === 'webrtc';
    ui.viewerMode.textContent = usingVideo ? '▦ MJPEG' : '▶ Videó';
    ui.viewerMode.setAttribute('aria-label', usingVideo ? 'Átváltás MJPEG képre' : 'Átváltás videóra');
  }

  function saveFullscreenTransport(value) {
    state.fullscreenTransport = value === 'webrtc' ? 'webrtc' : 'mjpeg';
    try { root.localStorage.setItem(FULLSCREEN_TRANSPORT_KEY, state.fullscreenTransport); } catch (error) {}
  }

  function toggleViewerTransport() {
    var job = state.activeJob;
    if (!currentJob(job) || !job.profile || !job.profile.playerPath) return;
    saveFullscreenTransport(state.fullscreenTransport === 'webrtc' ? 'mjpeg' : 'webrtc');
    updateViewerTransportToggle(job.profile);
    openViewer(job.profile, state.viewerClosesApp);
  }

  function toggleViewerAudio() {
    var job = state.activeJob;
    if (!currentJob(job) || !job.node || job.node.tagName !== 'IFRAME' || !job.profile.audio) return;
    job.audioMuted = !job.audioMuted;
    try {
      job.node.contentWindow.postMessage({
        channel: 'hu.szabi.cameraviewer.player',
        type: 'set-muted',
        session: job.session,
        muted: job.audioMuted
      }, gatewayOrigin(job.profile, true));
    } catch (error) {
      job.audioMuted = !job.audioMuted;
    }
    ui.viewerAudio.textContent = job.audioMuted ? '🔇 Hang bekapcsolása' : '🔊 Hang kikapcsolása';
  }

  function setViewerStatus(job, transport, text, error) {
    if (!currentJob(job)) return;
    if (viewerStatusTimer !== null) root.clearTimeout(viewerStatusTimer);
    viewerStatusTimer = null;
    if (ui.viewerTransport) ui.viewerTransport.textContent = transport || '';
    ui.viewerStatus.textContent = text || '';
    ui.viewerStatus.classList.toggle('is-error', !!error);
    if (text) {
      viewerStatusTimer = root.setTimeout(function () {
        viewerStatusTimer = null;
        ui.viewerStatus.textContent = '';
        ui.viewerStatus.classList.remove('is-error');
      }, FLOATING_MESSAGE_TIMEOUT);
    }
  }

  function advancePlayer(job, reason) {
    if (!currentJob(job)) return;
    clearTransport(job);
    job.transportIndex += 1;
    if (job.transportIndex >= job.plan.length) {
      setViewerStatus(job, 'Nincs jel', reason || 'A kamera egyik biztonságos lejátszási módon sem érhető el.', true);
      return;
    }
    startTransport(job, reason);
  }

  function startHostedPlayer(job) {
    var profile = job.profile;
    var iframe = root.document.createElement('iframe');
    var expectedOrigin = gatewayOrigin(profile, true);
    var session = cacheSessionId();
    job.node = iframe;
    job.session = session;
    iframe.className = 'hosted-player';
    iframe.title = profile.name + ' WebRTC stream';
    iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin');
    iframe.setAttribute('allow', 'autoplay');
    iframe.setAttribute('referrerpolicy', 'no-referrer');
    setViewerStatus(job, 'WebRTC', 'Biztonságos player betöltése…', false);

    job.messageHandler = function (event) {
      if (!currentJob(job) || event.origin !== expectedOrigin || event.source !== iframe.contentWindow) return;
      var data = event.data;
      if (!data || data.channel !== 'hu.szabi.cameraviewer.player' || data.session !== session) return;
      if (data.type === 'ready') {
        setViewerStatus(job, 'WebRTC', 'Kapcsolódás a kamerához…', false);
      } else if (data.type === 'playing') {
        if (job.timer) root.clearTimeout(job.timer);
        job.timer = null;
        job.audioMuted = data.detail !== 'audio';
        if (profile.audio) {
          ui.viewerAudio.classList.remove('hidden');
          ui.viewerAudio.textContent = job.audioMuted ? '🔇 Hang bekapcsolása' : '🔊 Hang kikapcsolása';
        }
        setViewerStatus(job, 'WebRTC', job.audioMuted && profile.audio ? 'A TV némítva indította a streamet; a Hang gombbal bekapcsolható.' : '', false);
      } else if (data.type === 'muted') {
        job.audioMuted = true;
        if (profile.audio) {
          ui.viewerAudio.classList.remove('hidden');
          ui.viewerAudio.textContent = '🔇 Hang bekapcsolása';
        }
      } else if (data.type === 'audio-state') {
        job.audioMuted = data.detail !== 'audio';
        ui.viewerAudio.textContent = job.audioMuted ? '🔇 Hang bekapcsolása' : '🔊 Hang kikapcsolása';
      } else if (data.type === 'error') {
        advancePlayer(job, 'A WebRTC nem indult el (' + String(data.detail || 'ismeretlen') + '), váltás MJPEG-re…');
      }
    };
    root.addEventListener('message', job.messageHandler);
    iframe.onerror = function () {
      advancePlayer(job, 'A hosted player nem tölthető be, váltás MJPEG-re…');
    };
    ui.viewerStage.appendChild(iframe);
    iframe.src = buildPlayerUrl(profile, session);
    job.timer = root.setTimeout(function () {
      advancePlayer(job, 'A WebRTC időtúllépéssel leállt, váltás MJPEG-re…');
    }, HOSTED_PLAYER_TIMEOUT);
  }

  function startMjpeg(job) {
    var image = root.document.createElement('img');
    job.node = image;
    ui.viewerAudio.classList.add('hidden');
    stopLegacyScreenGuard();
    image.alt = job.profile.name;
    image.className = 'viewer-media';
    setViewerStatus(job, 'MJPEG', 'MJPEG indítása…', false);
    image.onload = function () {
      if (!currentJob(job)) return;
      setViewerStatus(job, 'MJPEG', '', false);
    };
    image.onerror = function () {
      advancePlayer(job, 'Az MJPEG nem érhető el, váltás snapshotra…');
    };
    ui.viewerStage.appendChild(image);
    // A multipart MJPEG <img> nem garantál megbízható onload eseményt az első
    // képkockánál. Nem időzítjük ki 9 másodperc után: az korábban egy működő
    // streamet is snapshot fallbackra dobhatott, ami 10 másodperc körüli
    // ugrásoknak látszott a TV-n.
    image.src = cacheBusted(buildUrl(job.profile, 'mjpeg'));
  }

  function startSnapshot(job) {
    var image = root.document.createElement('img');
    var failures = 0;
    job.node = image;
    ui.viewerAudio.classList.add('hidden');
    startScreenGuard();
    image.alt = job.profile.name;
    image.className = 'viewer-media';
    setViewerStatus(job, 'Snapshot', 'Snapshot fallback indítása…', false);
    function schedule(wait) {
      if (currentJob(job)) job.refreshTimer = root.setTimeout(refresh, wait);
    }
    function refresh() {
      if (!currentJob(job)) return;
      image.src = cacheBusted(buildUrl(job.profile, 'snapshot'));
    }
    image.onload = function () {
      failures = 0;
      setViewerStatus(job, 'Snapshot', '', false);
      schedule(3000);
    };
    image.onerror = function () {
      failures += 1;
      setViewerStatus(job, 'Snapshot', 'Nincs friss kép; újrapróbálás…', true);
      schedule(Math.min(15000, failures * 1800));
    };
    ui.viewerStage.appendChild(image);
    refresh();
  }

  function startTransport(job, previousReason) {
    if (!currentJob(job)) return;
    var transport = job.plan[job.transportIndex];
    if (previousReason) setViewerStatus(job, '', previousReason, false);
    if (transport === 'webrtc') startHostedPlayer(job);
    else if (transport === 'mjpeg') startMjpeg(job);
    else startSnapshot(job);
  }

  function openViewer(profile, closeAppOnExit) {
    if (!profile || state.suspended) return;
    if (closeAppOnExit === true) state.viewerClosesApp = true;
    else if (closeAppOnExit === false) state.viewerClosesApp = false;
    var needsDecoderHandoff = !!state.activeGridLiveJob || !!state.activeGridSnapshotJob;
    stopGridJobs();
    stopActivePlayer();
    stopLegacyScreenGuard();
    state.view = 'viewer';
    state.selectedId = profile.id;
    ui.gridScreen.classList.add('hidden');
    ui.viewerScreen.classList.remove('hidden');
    ui.viewerTitle.textContent = profile.name;
    if (viewerStatusTimer !== null) root.clearTimeout(viewerStatusTimer);
    viewerStatusTimer = null;
    ui.viewerStatus.textContent = '';
    if (ui.viewerTransport) ui.viewerTransport.textContent = '';
    var job = {
      profile: profile,
      generation: state.generation,
      stopped: false,
      plan: playbackPlan(profile, state.fullscreenTransport),
      transportIndex: 0,
      timer: null,
      refreshTimer: null,
      handoffTimer: null,
      node: null,
      messageHandler: null,
      session: null
      ,audioMuted: true
    };
    state.activeJob = job;
    updateViewerTransportToggle(profile);
    if (needsDecoderHandoff) {
      job.handoffTimer = root.setTimeout(function () {
        job.handoffTimer = null;
        if (currentJob(job)) startTransport(job);
      }, FULLSCREEN_HANDOFF_DELAY_MS);
    } else {
      startTransport(job);
    }
    ui.viewerScreen.focus();
  }

  function closeViewer(forceGrid) {
    stopActivePlayer();
    if (state.viewerClosesApp && forceGrid !== true) {
      state.viewerClosesApp = false;
      state.view = 'grid';
      state.selectedId = null;
      ui.viewerScreen.classList.add('hidden');
      ui.gridScreen.classList.remove('hidden');
      stopEverything();
      try { root.close(); } catch (error) { /* best effort */ }
      return;
    }
    state.viewerClosesApp = false;
    state.view = 'grid';
    state.selectedId = null;
    ui.viewerScreen.classList.add('hidden');
    ui.gridScreen.classList.remove('hidden');
    if (!state.suspended) {
      renderGrid();
      var selected = ui.cameraGrid.querySelector('.camera-tile');
      (selected || ui.settingsButton).focus();
    }
  }

  function updateProfileSelect(selectedId) {
    ui.profileSelect.textContent = '';
    var blank = root.document.createElement('option');
    blank.value = '';
    blank.textContent = 'Új kamera';
    ui.profileSelect.appendChild(blank);
    for (var i = 0; i < state.profiles.length; i += 1) {
      var option = root.document.createElement('option');
      option.value = state.profiles[i].id;
      option.textContent = state.profiles[i].name;
      ui.profileSelect.appendChild(option);
    }
    ui.profileSelect.value = selectedId || '';
  }

  function updateFeaturedSelect() {
    var selected = state.settings.featuredCameraId;
    ui.featuredCamera.textContent = '';
    var blank = root.document.createElement('option');
    blank.value = '';
    blank.textContent = 'Nincs';
    ui.featuredCamera.appendChild(blank);
    for (var i = 0; i < state.profiles.length; i += 1) {
      var option = root.document.createElement('option');
      option.value = state.profiles[i].cameraId;
      option.textContent = state.profiles[i].name;
      ui.featuredCamera.appendChild(option);
    }
    ui.featuredCamera.value = selected;
  }

  function populateViewSettings() {
    ui.layoutSize.value = String(state.settings.layoutSize);
    ui.preventScreenSaver.checked = state.settings.preventScreenSaver;
    updateFeaturedSelect();
  }

  function saveViewSettings() {
    try {
      state.settings = normalizeSettings({
        layoutSize: ui.layoutSize.value,
        featuredCameraId: ui.featuredCamera.value,
        preventScreenSaver: ui.preventScreenSaver.checked,
        previewIntervalSeconds: DEFAULT_PREVIEW_INTERVAL_SECONDS
      });
      state.page = 0;
      if (!saveProfiles()) return;
      ui.settingsError.textContent = '';
      showMessage('A layout és a működési beállítások elmentve.');
      startScreenGuard();
      closeSettings();
    } catch (error) {
      ui.settingsError.textContent = error.message || String(error);
    }
  }

  function populateForm(profile) {
    state.editingId = profile ? profile.id : null;
    ui.profileName.value = profile ? profile.name : '';
    ui.cameraId.value = profile ? profile.cameraId : '';
    ui.primarySource.value = profile ? profile.primarySource : '';
    ui.previewSource.value = profile ? profile.previewSource : '';
    ui.streamScheme.value = profile ? profile.scheme : 'http';
    ui.streamHost.value = profile ? profile.host : '';
    ui.streamPort.value = profile ? String(profile.port) : '';
    ui.playerPort.value = profile ? String(profile.playerPort) : '';
    ui.playerPath.value = profile ? profile.playerPath : '';
    ui.cameraAudio.checked = profile ? profile.audio : true;
    ui.settingsError.textContent = '';
    updateProfileSelect(state.editingId);
  }

  function openSettings(profileId) {
    if (state.view === 'viewer') return;
    stopGridJobs();
    state.view = 'settings';
    var profile = state.profiles.find(function (item) { return item.id === profileId; }) || null;
    populateViewSettings();
    populateForm(profile);
    ui.settingsPanel.classList.remove('hidden');
    root.setTimeout(function () { ui.profileSelect.focus(); }, 0);
  }

  function closeSettings() {
    ui.settingsPanel.classList.add('hidden');
    state.view = 'grid';
    if (!state.suspended) {
      renderGrid();
      ui.settingsButton.focus();
    }
  }

  function readForm() {
    return {
      id: state.editingId,
      name: ui.profileName.value,
      cameraId: ui.cameraId.value,
      primarySource: ui.primarySource.value,
      previewSource: ui.previewSource.value,
      scheme: ui.streamScheme.value,
      host: ui.streamHost.value,
      port: ui.streamPort.value,
      playerPort: ui.playerPort.value,
      playerPath: ui.playerPath.value
      ,audio: ui.cameraAudio.checked
    };
  }

  function submitSettings(event) {
    event.preventDefault();
    var result = validateProfile(readForm());
    if (!result.ok) {
      ui.settingsError.textContent = result.error;
      return;
    }
    var duplicate = state.profiles.find(function (item) {
      return item.cameraId === result.value.cameraId && item.id !== result.value.id;
    });
    if (duplicate) {
      ui.settingsError.textContent = 'Ez a Kamera ID már egy másik profilhoz tartozik.';
      return;
    }
    var index = state.profiles.findIndex(function (item) { return item.id === result.value.id; });
    if (index === -1) {
      state.profiles.push(result.value);
    } else state.profiles[index] = result.value;
    if (!saveProfiles()) return;
    populateViewSettings();
    showMessage('Kamera mentve: ' + result.value.name);
    closeSettings();
  }

  function deleteCurrentProfile() {
    if (!state.editingId) return;
    state.profiles = state.profiles.filter(function (item) { return item.id !== state.editingId; });
    if (!state.profiles.some(function (item) { return item.cameraId === state.settings.featuredCameraId; })) state.settings.featuredCameraId = '';
    saveProfiles();
    populateViewSettings();
    populateForm(null);
    showMessage('Kamera törölve.');
  }

  function findLaunchProfile(command) {
    if (command.cameraId) return state.profiles.find(function (item) { return item.cameraId === command.cameraId; });
    return state.profiles.find(function (item) { return item.id === command.profileId; });
  }

  function rememberRequestId(requestId) {
    if (!requestId) return true;
    if (state.seenRequestIds.indexOf(requestId) !== -1) return false;
    state.seenRequestIds.push(requestId);
    if (state.seenRequestIds.length > 32) state.seenRequestIds.shift();
    return true;
  }

  function isImmediateDuplicate(command) {
    if (command.requestId) return false;
    var fingerprint = command.cameraId ? 'camera:' + command.cameraId : 'profile:' + command.profileId;
    var now = Date.now();
    var duplicate = state.lastCommandFingerprint === fingerprint && now - state.lastCommandAt < 1200;
    state.lastCommandFingerprint = fingerprint;
    state.lastCommandAt = now;
    return duplicate;
  }

  function activateAfterRelaunch() {
    try {
      if (root.webOSSystem && typeof root.webOSSystem.activate === 'function') root.webOSSystem.activate();
      else if (root.PalmSystem && typeof root.PalmSystem.activate === 'function') root.PalmSystem.activate();
    } catch (error) { /* best effort */ }
  }

  function handleLaunch(raw, isRelaunch) {
    state.pendingLaunchId = null;
    var activate = false;
    try {
      var unwrapped = unwrapLaunchObject(raw);
      if (isPlainLauncherOpen(unwrapped)) {
        showMessage('');
        if (state.view === 'viewer') closeViewer();
        else if (state.view === 'settings') closeSettings();
        if (isRelaunch) activateAfterRelaunch();
        return;
      }
      var command = extractLaunchCommand(raw);
      if (!command.ok) {
        if (unwrapped && Object.keys(unwrapped).length > 0) {
          if (state.view === 'viewer') closeViewer(true);
          showMessage(command.error + ' Nyisd meg a Beállításokat.');
          ui.settingsButton.focus();
        }
        return;
      }
      // A valid open relaunch always foregrounds the app.  This also applies
      // when request de-duplication avoids rebuilding the decoder.
      if (command.value.action === 'open') activate = true;
      if (!rememberRequestId(command.value.requestId)) return;
      if (command.value.syncUrl) {
        state.syncUrl = command.value.syncUrl;
        root.localStorage.setItem(SYNC_URL_KEY, state.syncUrl);
      }
      if (command.value.action !== 'open') {
        if (command.value.action === 'configure') {
          state.settings = command.value.settings;
          saveProfiles();
        } else if (command.value.action === 'camera-save') {
          var duplicate = state.profiles.find(function (item) {
            return item.cameraId === command.value.profile.cameraId && item.id !== command.value.profile.id;
          });
          if (duplicate) throw new Error('Ez a Kamera ID már egy másik profilhoz tartozik.');
          var saveIndex = state.profiles.findIndex(function (item) { return item.id === command.value.profile.id; });
          if (saveIndex < 0) state.profiles.push(command.value.profile);
          else state.profiles[saveIndex] = command.value.profile;
          saveProfiles();
        } else if (command.value.action === 'camera-delete') {
          var previousLength = state.profiles.length;
          state.profiles = state.profiles.filter(function (item) { return item.cameraId !== command.value.cameraId; });
          if (state.profiles.length === previousLength) throw new Error('Ismeretlen kamera.');
          if (state.settings.featuredCameraId === command.value.cameraId) state.settings.featuredCameraId = '';
          saveProfiles();
        } else if (command.value.action === 'camera-reorder') {
          state.profiles = reorderProfiles(state.profiles, command.value.cameraIds);
          saveProfiles();
        } else pushSync();
        if (isRelaunch) {
          if (state.view === 'grid') renderGrid();
          else if (state.view === 'settings') { populateViewSettings(); updateProfileSelect(state.editingId); }
        } else {
          root.setTimeout(function () { try { root.close(); } catch (closeError) {} }, 700);
        }
        return;
      }
      var profile = findLaunchProfile(command.value);
      if (!profile) {
        if (state.view === 'viewer') closeViewer(true);
        else if (state.view === 'settings') closeSettings();
        showMessage('Ismeretlen kamera profil. Nyisd meg a Beállításokat.');
        ui.settingsButton.focus();
        return;
      }
      if (isImmediateDuplicate(command.value)) return;
      if (state.suspended) {
        state.pendingLaunchId = profile.id;
        state.pendingLaunchClosesApp = true;
      } else openViewer(profile, true);
    } catch (error) {
      showMessage(error && error.message ? error.message : 'A TV-ről érkező beállítás nem menthető.');
    } finally {
      if (isRelaunch && activate) activateAfterRelaunch();
    }
  }

  function initialLaunchParams() {
    if (root.webOSSystem && root.webOSSystem.launchParams) return root.webOSSystem.launchParams;
    if (root.PalmSystem && root.PalmSystem.launchParams) return root.PalmSystem.launchParams;
    return null;
  }

  function stopEverything() {
    stopGridJobs();
    stopActivePlayer();
    stopScreenGuard();
    stopPresenceHeartbeat();
  }

  function closeApp() {
    stopEverything();
    root.close();
  }

  function gridColumnCount() {
    return state.settings.layoutSize;
  }

  function directionalTileScore(from, to, keyCode) {
    var dx = to.x - from.x;
    var dy = to.y - from.y;
    var primary;
    var secondary;

    if (keyCode === 37) {
      if (dx >= -2) return null;
      primary = -dx;
      secondary = Math.abs(dy);
    } else if (keyCode === 39) {
      if (dx <= 2) return null;
      primary = dx;
      secondary = Math.abs(dy);
    } else if (keyCode === 38) {
      if (dy >= -2) return null;
      primary = -dy;
      secondary = Math.abs(dx);
    } else {
      if (dy <= 2) return null;
      primary = dy;
      secondary = Math.abs(dx);
    }

    // A másodlagos tengely eltérését erősen büntetjük, így a 2×2-es kiemelt
    // csempéről is a vizuálisan mellette/fölötte lévő kamera kap fókuszt.
    return primary + secondary * 1.6;
  }

  function moveGridFocus(keyCode) {
    var tiles = Array.prototype.slice.call(ui.cameraGrid.querySelectorAll('.camera-tile'));
    if (!tiles.length) return;
    var index = tiles.indexOf(root.document.activeElement);
    if (index < 0) {
      tiles[0].focus();
      return;
    }

    var from = {
      x: Number(tiles[index].getAttribute('data-grid-x')),
      y: Number(tiles[index].getAttribute('data-grid-y'))
    };
    var bestTile = null;
    var bestScore = Infinity;
    for (var candidateIndex = 0; candidateIndex < tiles.length; candidateIndex += 1) {
      if (candidateIndex === index) continue;
      var to = {
        x: Number(tiles[candidateIndex].getAttribute('data-grid-x')),
        y: Number(tiles[candidateIndex].getAttribute('data-grid-y'))
      };
      var score = directionalTileScore(from, to, keyCode);
      if (score !== null && score < bestScore) {
        bestScore = score;
        bestTile = tiles[candidateIndex];
      }
    }

    if (bestTile) {
      bestTile.focus();
      return;
    }
    if (keyCode === 37 && state.page > 0) changePage(-1);
    else if (keyCode === 39 && state.page < state.pageCount - 1) changePage(1);
  }

  function moveSettingsFocus(direction) {
    var selector = 'button:not([disabled]), input:not([disabled]), select:not([disabled])';
    var controls = Array.prototype.slice.call(ui.settingsPanel.querySelectorAll(selector)).filter(function (node) {
      return !node.hidden && !(node.closest && node.closest('.hidden'));
    });
    if (!controls.length) return;
    var index = controls.indexOf(root.document.activeElement);
    if (index < 0) controls[0].focus();
    else controls[(index + direction + controls.length) % controls.length].focus();
  }

  function changeSelectValue(select, direction) {
    var next = Math.max(0, Math.min(select.options.length - 1, select.selectedIndex + direction));
    if (next === select.selectedIndex) return;
    select.selectedIndex = next;
    var changeEvent = root.document.createEvent('HTMLEvents');
    changeEvent.initEvent('change', true, false);
    select.dispatchEvent(changeEvent);
  }

  function onKeyDown(event) {
    var code = event.keyCode || event.which;
    if (code === 461) {
      event.preventDefault();
      event.stopPropagation();
      if (state.view === 'viewer') closeViewer();
      else if (state.view === 'settings') closeSettings();
      else closeApp();
      return;
    }
    if (state.view === 'grid' && [37, 38, 39, 40].indexOf(code) !== -1) {
      event.preventDefault();
      event.stopPropagation();
      moveGridFocus(code);
    }
    if (state.view === 'settings' && (code === 38 || code === 40)) {
      event.preventDefault();
      event.stopPropagation();
      moveSettingsFocus(code === 38 ? -1 : 1);
    } else if (state.view === 'settings' && (code === 37 || code === 39) && root.document.activeElement.tagName === 'SELECT') {
      event.preventDefault();
      event.stopPropagation();
      changeSelectValue(root.document.activeElement, code === 37 ? -1 : 1);
    }
    if (state.view === 'viewer' && [37, 38, 39, 40].indexOf(code) !== -1) {
      event.preventDefault();
      event.stopPropagation();
      if (code === 38 || code === 39) ui.viewerClose.focus();
      else ui.viewerScreen.focus();
    }
    if (state.view === 'viewer' && code === 13 && root.document.activeElement === ui.viewerClose) {
      event.preventDefault();
      event.stopPropagation();
      closeViewer();
    }
  }

  function onVisibilityChange() {
    state.suspended = root.document.hidden;
    if (state.suspended) {
      stopEverything();
      return;
    }
    sendPresenceHeartbeat();
    if (state.pendingLaunchId) {
      var pending = state.profiles.find(function (item) { return item.id === state.pendingLaunchId; });
      state.pendingLaunchId = null;
      if (pending) {
        var closeAppOnExit = state.pendingLaunchClosesApp;
        state.pendingLaunchClosesApp = false;
        openViewer(pending, closeAppOnExit);
        return;
      }
      showMessage('A kért kamera profil már nem létezik.');
    }
    if (state.view === 'viewer') {
      var selected = state.profiles.find(function (item) { return item.id === state.selectedId; });
      if (selected) openViewer(selected);
      else closeViewer();
    } else if (state.view === 'grid') renderGrid();
    else startScreenGuard();
  }

  function onPageHide() {
    state.suspended = true;
    state.pendingLaunchId = null;
    state.pendingLaunchClosesApp = false;
    stopEverything();
  }

  function bindUi() {
    ui.gridScreen = byId('grid-screen');
    ui.viewerScreen = byId('viewer-screen');
    ui.viewerStage = byId('viewer-stage');
    ui.viewerTitle = byId('viewer-title');
    ui.viewerStatus = byId('viewer-status');
    ui.viewerTransport = byId('viewer-transport');
    ui.viewerClose = byId('viewer-close');
    ui.viewerMode = byId('viewer-mode');
    ui.viewerAudio = byId('viewer-audio');
    ui.screenGuard = byId('screen-guard');
    ui.cameraGrid = byId('camera-grid');
    ui.pageControls = byId('page-controls');
    ui.pagePrevious = byId('page-previous');
    ui.pageNext = byId('page-next');
    ui.pageIndicator = byId('page-indicator');
    ui.emptyState = byId('empty-state');
    ui.message = byId('message');
    ui.settingsButton = byId('settings-button');
    ui.settingsPanel = byId('settings-panel');
    ui.profileSelect = byId('profile-select');
    ui.profileName = byId('profile-name');
    ui.cameraId = byId('camera-id');
    ui.primarySource = byId('primary-source');
    ui.previewSource = byId('preview-source');
    ui.streamScheme = byId('stream-scheme');
    ui.streamHost = byId('stream-host');
    ui.streamPort = byId('stream-port');
    ui.playerPort = byId('player-port');
    ui.playerPath = byId('player-path');
    ui.cameraAudio = byId('camera-audio');
    ui.layoutSize = byId('layout-size');
    ui.featuredCamera = byId('featured-camera');
    ui.preventScreenSaver = byId('prevent-screensaver');
    ui.settingsError = byId('settings-error');

    ui.viewerClose.addEventListener('click', closeViewer);
    ui.viewerMode.addEventListener('click', toggleViewerTransport);
    ui.viewerAudio.addEventListener('click', toggleViewerAudio);
    ui.pagePrevious.addEventListener('click', function () { changePage(-1); });
    ui.pageNext.addEventListener('click', function () { changePage(1); });
    ui.settingsButton.addEventListener('click', function () { openSettings(null); });
    byId('empty-settings-button').addEventListener('click', function () { openSettings(null); });
    byId('settings-close').addEventListener('click', closeSettings);
    byId('cancel-settings').addEventListener('click', closeSettings);
    byId('new-profile').addEventListener('click', function () { populateForm(null); });
    byId('delete-profile').addEventListener('click', deleteCurrentProfile);
    byId('save-view-settings').addEventListener('click', saveViewSettings);
    byId('settings-form').addEventListener('submit', submitSettings);
    ui.profileSelect.addEventListener('change', function () {
      var profile = state.profiles.find(function (item) { return item.id === ui.profileSelect.value; });
      populateForm(profile || null);
    });
    root.addEventListener('keydown', onKeyDown);
    root.addEventListener('resize', function () {
      if (state.view === 'grid') applyGridGeometry(state.settings.layoutSize);
    });
    root.document.addEventListener('visibilitychange', onVisibilityChange, true);
    root.document.addEventListener('webOSLaunch', function (event) { handleLaunch(event.detail, false); }, true);
    root.document.addEventListener('webOSRelaunch', function (event) { handleLaunch(event.detail, true); }, true);
    root.addEventListener('pagehide', onPageHide, true);
    root.addEventListener('pageshow', function () {
      if (!root.document.hidden && state.suspended) onVisibilityChange();
    }, true);
    root.addEventListener('beforeunload', stopEverything);
  }

  function bootstrap() {
    bindUi();
    var loaded = loadAppConfig();
    state.profiles = loaded.profiles;
    state.settings = loaded.settings;
    try { state.syncUrl = root.localStorage.getItem(SYNC_URL_KEY) || ''; } catch (error) { state.syncUrl = ''; }
    try {
      state.fullscreenTransport = root.localStorage.getItem(FULLSCREEN_TRANSPORT_KEY) === 'webrtc' ? 'webrtc' : 'mjpeg';
    } catch (error) { state.fullscreenTransport = 'mjpeg'; }
    renderGrid();
    sendPresenceHeartbeat();
    var launch = initialLaunchParams();
    if (launch) handleLaunch(launch, false);
  }

  if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', bootstrap);
  else bootstrap();
}(typeof window !== 'undefined' ? window : globalThis));
