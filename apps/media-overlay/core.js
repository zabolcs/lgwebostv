(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MediaOverlayCore = api;
}(typeof window !== 'undefined' ? window : this, function () {
  'use strict';

  var BLOCKED_HOST = '192.168.0.100';
  var CORNERS = ['top-left', 'top-right', 'bottom-left', 'bottom-right'];
  var KINDS = ['text', 'image', 'video'];
  var FITS = ['contain', 'cover'];
  var SENSITIVE_QUERY_NAMES = {
    token: true,
    access_token: true,
    password: true,
    auth: true,
    key: true,
    signature: true
  };

  function containsForbiddenAddress(value) {
    var text = String(value == null ? '' : value);
    // A media gateway must receive an opaque alias, never an IP-shaped proxy target.
    // This also rejects leading-zero, mixed-octal-looking dotted forms.
    if (/(^|[^0-9])(?:[0-9]+\.){1,3}[0-9]+([^0-9]|$)/.test(text)) return true;
    if (/0x/i.test(text)) return true;
    // Common single-integer representations of 192.168.0.100.
    return /0x0*c0a80064|0*3232235620|0*30052000144/i.test(text);
  }

  function integer(value, minimum, maximum) {
    var text = String(value == null ? '' : value);
    if (!/^[0-9]+$/.test(text)) return null;
    var number = Number(text);
    if (!Number.isInteger(number) || number < minimum || number > maximum) return null;
    return number;
  }

  function privateIPv4(value) {
    var text = String(value == null ? '' : value).trim();
    if (!/^\d{1,3}(?:\.\d{1,3}){3}$/.test(text)) return null;
    var raw = text.split('.');
    var parts = raw.map(function (part) { return Number(part); });
    for (var i = 0; i < raw.length; i++) {
      if (parts[i] < 0 || parts[i] > 255 || String(parts[i]) !== raw[i]) return null;
    }
    var host = parts.join('.');
    if (host === BLOCKED_HOST || parts[3] === 0 || parts[3] === 255) return null;
    var isPrivate = parts[0] === 10 ||
      (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31) ||
      (parts[0] === 192 && parts[1] === 168);
    return isPrivate ? host : null;
  }

  function sensitiveQueryName(name) {
    name = String(name == null ? '' : name).toLowerCase();
    if (SENSITIVE_QUERY_NAMES[name]) return true;
    var parts = name.split(/[^a-z0-9]+/);
    for (var i = 0; i < parts.length; i++) {
      if (SENSITIVE_QUERY_NAMES[parts[i]]) return true;
    }
    return false;
  }

  function validateQuery(query) {
    if (!query) return;
    var fields = query.split('&');
    for (var i = 0; i < fields.length; i++) {
      if (!fields[i]) continue;
      var equals = fields[i].indexOf('=');
      var name = equals === -1 ? fields[i] : fields[i].slice(0, equals);
      if (!/^[A-Za-z0-9._-]{1,64}$/.test(name)) {
        throw new Error('A média URL query paraméterneve érvénytelen.');
      }
      if (sensitiveQueryName(name)) {
        throw new Error('Titkot hordozó query paraméternév nem engedélyezett.');
      }
    }
  }

  function normalizeMediaUrl(value) {
    var text = String(value == null ? '' : value).trim();
    if (text.indexOf('%') !== -1 || /[\x00-\x20\x7f]/.test(text)) {
      throw new Error('A média URL nem tartalmazhat kódolt részt, szóközt vagy vezérlőkaraktert.');
    }
    var match = /^(https?):\/\/(\d{1,3}(?:\.\d{1,3}){3})(?::([0-9]{1,5}))?(\/[^?#]*)?(?:\?([^#]*))?$/i.exec(text);
    if (!match) throw new Error('A média URL formátuma: http(s)://PRIVÁT_IP[:PORT]/útvonal.');
    var scheme = match[1].toLowerCase();
    var host = privateIPv4(match[2]);
    var port = match[3] == null ? null : integer(match[3], 1, 65535);
    var path = match[4] || '/';
    var query = match[5] == null ? '' : match[5];
    if (!host) throw new Error('A médiahost nem engedélyezett privát IPv4-cím.');
    if (match[3] != null && port === null) throw new Error('A médiaport érvénytelen.');
    if (!path || /[:@%\\\x00-\x20\x7f]/.test(path) || path.indexOf('//') !== -1) {
      throw new Error('A média útvonala érvénytelen.');
    }
    if (containsForbiddenAddress(path) || containsForbiddenAddress(query)) {
      throw new Error('A tiltott 192.168.0.100 cím útvonalban vagy aliasban sem használható.');
    }
    var segments = path.split('/');
    for (var i = 0; i < segments.length; i++) {
      if (segments[i] === '.' || segments[i] === '..') throw new Error('A média útvonala érvénytelen.');
    }
    validateQuery(query);
    return scheme + '://' + host + (port === null ? '' : ':' + port) + path + (query ? '?' + query : '');
  }

  function normalizeLayout(input) {
    input = input || {};
    var corner = String(input.corner || 'top-left');
    var width = integer(input.width == null ? 640 : input.width, 240, 1920);
    var height = integer(input.height == null ? 360 : input.height, 135, 1080);
    var marginX = integer(input.marginX == null ? 32 : input.marginX, 0, 400);
    var marginY = integer(input.marginY == null ? 32 : input.marginY, 0, 300);
    var ttlMs = integer(input.ttlMs == null ? 15000 : input.ttlMs, 0, 3600000);
    if (CORNERS.indexOf(corner) < 0 || width === null || height === null || marginX === null || marginY === null || ttlMs === null) {
      throw new Error('Az overlay elrendezése érvénytelen.');
    }
    return { corner: corner, width: width, height: height, marginX: marginX, marginY: marginY, ttlMs: ttlMs };
  }

  function normalizePresetId(value) {
    var id = String(value || '').trim();
    if (!/^[a-z0-9][a-z0-9._-]{0,31}$/.test(id)) throw new Error('A preset azonosítója érvénytelen.');
    return id;
  }

  function normalizeSyncUrl(value) {
    var text = String(value || '').trim();
    var match = /^http:\/\/(\d{1,3}(?:\.\d{1,3}){3})(?::([0-9]{1,5}))?(\/api\/tv-sync\/media-overlay)$/.exec(text);
    if (!match || !privateIPv4(match[1])) throw new Error('A szinkron URL érvénytelen.');
    if (match[2] != null && integer(match[2], 1, 65535) === null) throw new Error('A szinkron port érvénytelen.');
    return text;
  }

  function resolveLayoutRequest(params, savedLayout) {
    params = params || {};
    savedLayout = normalizeLayout(savedLayout || {});
    var margin = params.margin == null ? null : integer(params.margin, 0, 300);
    if (params.margin != null && margin === null) throw new Error('Az egységes margó érvénytelen.');
    return normalizeLayout({
      corner: params.corner == null ? savedLayout.corner : params.corner,
      width: params.width == null ? savedLayout.width : params.width,
      height: params.height == null ? savedLayout.height : params.height,
      marginX: params.marginX == null ? (margin === null ? savedLayout.marginX : margin) : params.marginX,
      marginY: params.marginY == null ? (margin === null ? savedLayout.marginY : margin) : params.marginY,
      ttlMs: params.ttlMs == null ? savedLayout.ttlMs : params.ttlMs
    });
  }

  function normalizePreset(input) {
    input = input || {};
    var id = normalizePresetId(input.id);
    var kind = String(input.kind || '');
    var fit = String(input.fit || 'contain');
    var clickAction = String(input.clickAction || '');
    var cameraId = String(input.cameraId || '').trim();
    if (KINDS.indexOf(kind) < 0) throw new Error('A preset típusa érvénytelen.');
    if (FITS.indexOf(fit) < 0) throw new Error('Az illesztési mód érvénytelen.');
    if (clickAction !== '' && clickAction !== 'openCamera' && clickAction !== 'dismiss') throw new Error('A kattintási művelet érvénytelen.');
    if (clickAction === 'openCamera' && !/^[a-z0-9][a-z0-9._-]{0,31}$/.test(cameraId)) {
      throw new Error('A kamera-ID érvénytelen.');
    }
    if (clickAction !== 'openCamera') cameraId = '';
    var content = String(input.content == null ? '' : input.content);
    if (!content || content.length > 2048) throw new Error('A preset tartalma 1–2048 karakter legyen.');
    if (kind === 'image' || kind === 'video') content = normalizeMediaUrl(content);
    return { id: id, kind: kind, content: content, fit: fit, clickAction: clickAction, cameraId: cameraId };
  }

  function defaultConfig() {
    return {
      version: 1,
      layout: normalizeLayout({}),
      presets: [normalizePreset({ id: 'welcome', kind: 'text', content: 'Media Overlay', fit: 'contain' })]
    };
  }

  function normalizeConfig(input) {
    if (!input || input.version !== 1) return defaultConfig();
    var layout = normalizeLayout(input.layout);
    if (!Array.isArray(input.presets) || input.presets.length > 32) throw new Error('A presetlista érvénytelen.');
    var seen = {};
    var presets = input.presets.map(function (preset) {
      var normalized = normalizePreset(preset);
      if (seen[normalized.id]) throw new Error('Ismétlődő preset azonosító.');
      seen[normalized.id] = true;
      return normalized;
    });
    return { version: 1, layout: layout, presets: presets };
  }

  function parseStored(raw) {
    if (!raw) return defaultConfig();
    try { return normalizeConfig(JSON.parse(raw)); }
    catch (e) { return defaultConfig(); }
  }

  function resolvePresetRequest(params) {
    params = params || {};
    var id = normalizePresetId(params.presetId);
    var kind = String(params.kind || '');
    var interaction = { clickAction: params.clickAction, cameraId: params.cameraId };
    if (kind === 'text') {
      if (params.url != null || params.src != null || params.fit != null) {
        throw new Error('Szöveges presetnél url, src és fit nem adható meg.');
      }
      return normalizePreset({
        id: id, kind: 'text', content: params.text, fit: 'contain',
        clickAction: interaction.clickAction, cameraId: interaction.cameraId
      });
    }
    if (kind === 'image' || kind === 'video') {
      if (params.text != null) throw new Error('Médiapresetnél text nem adható meg.');
      if (params.url != null && params.src != null) throw new Error('Egyszerre csak url vagy src adható meg.');
      var mediaUrl = params.url != null ? params.url : params.src;
      if (mediaUrl == null) throw new Error('Kép- vagy videopresethez url szükséges.');
      return normalizePreset({
        id: id,
        kind: kind,
        content: mediaUrl,
        fit: params.fit == null ? 'contain' : params.fit,
        clickAction: interaction.clickAction,
        cameraId: interaction.cameraId
      });
    }
    throw new Error('A preset típusa text, image vagy video lehet.');
  }

  function resolveShowRequest(params, config) {
    params = params || {};
    config = normalizeConfig(config);
    var preset = null;
    if (params.presetId != null) {
      if (params.kind != null || params.text != null || params.url != null || params.src != null || params.fit != null ||
          params.clickAction != null || params.cameraId != null) {
        throw new Error('Preset indításnál közvetlen tartalom és kattintási művelet nem adható meg.');
      }
      var presetId = String(params.presetId);
      for (var i = 0; i < config.presets.length; i++) {
        if (config.presets[i].id === presetId) { preset = config.presets[i]; break; }
      }
      if (!preset) throw new Error('Ismeretlen preset.');
    } else {
      var kind = String(params.kind || '');
      if (kind === 'text') {
        if (params.url != null || params.src != null || params.fit != null) {
          throw new Error('Szöveges indításnál url, src és fit nem adható meg.');
        }
        preset = normalizePreset({
          id: 'launch-text', kind: 'text', content: params.text, fit: 'contain',
          clickAction: params.clickAction, cameraId: params.cameraId
        });
      } else if (kind === 'image' || kind === 'video') {
        if (params.text != null) throw new Error('Médiaindításnál text nem adható meg.');
        if (params.url != null && params.src != null) throw new Error('Egyszerre csak url vagy src adható meg.');
        var mediaUrl = params.url != null ? params.url : params.src;
        if (mediaUrl == null) throw new Error('Képhez vagy videóhoz url szükséges.');
        preset = normalizePreset({
          id: 'launch-media',
          kind: kind,
          content: mediaUrl,
          fit: params.fit == null ? 'contain' : params.fit,
          clickAction: params.clickAction,
          cameraId: params.cameraId
        });
      } else {
        throw new Error('A közvetlen indításhoz kind=text, image vagy video szükséges.');
      }
    }
    if (params.mode != null && params.mode !== 'fullscreen') throw new Error('Az overlay mód érvénytelen.');
    var fullscreen = params.mode === 'fullscreen';
    var layout = resolveLayoutRequest(params, config.layout);
    return { preset: preset, layout: layout, ttlMs: layout.ttlMs, fullscreen: fullscreen };
  }

  function normalizeAction(params) {
    params = params && typeof params === 'object' ? params : {};
    var action = params.action == null ? 'settings' : String(params.action);
    if (action === 'close') action = 'dismiss';
    if (action === 'defaults') action = 'configure';
    if (action === 'savePreset') action = 'preset-save';
    if (action === 'deletePreset') action = 'preset-delete';
    if (['show', 'settings', 'dismiss', 'configure', 'preset-save', 'preset-delete', 'sync'].indexOf(action) < 0) {
      throw new Error('Ismeretlen launch action.');
    }
    var allowed = action === 'show'
      ? {
          v: true, action: true, presetId: true, kind: true, text: true, url: true, src: true, fit: true,
          clickAction: true, cameraId: true,
          corner: true, width: true, height: true, margin: true, marginX: true, marginY: true,
          ttlMs: true, mode: true, syncUrl: true, requestId: true
        }
      : (action === 'configure'
          ? {
              v: true, action: true, corner: true, width: true, height: true, margin: true,
              marginX: true, marginY: true, ttlMs: true, syncUrl: true, requestId: true
            }
          : (action === 'preset-save'
              ? {
                  v: true, action: true, presetId: true, kind: true, text: true,
                  url: true, src: true, fit: true, clickAction: true, cameraId: true, syncUrl: true, requestId: true
                }
              : (action === 'preset-delete'
                  ? { v: true, action: true, presetId: true, syncUrl: true, requestId: true }
                  : (action === 'sync'
                      ? { v: true, action: true, syncUrl: true, requestId: true }
                      : { v: true, action: true, syncUrl: true, requestId: true }))));
    var keys = Object.keys(params);
    for (var i = 0; i < keys.length; i++) {
      if (!allowed[keys[i]]) throw new Error('A launch kérés tiltott mezőt tartalmaz.');
    }
    return action;
  }

  function keyIntent(tagName, keyCode) {
    var tag = String(tagName || '').toUpperCase();
    var horizontal = keyCode === 37 || keyCode === 39;
    var vertical = keyCode === 38 || keyCode === 40;
    if (!horizontal && !vertical) return 'other';
    if (tag === 'SELECT') return horizontal ? 'select' : 'focus';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return horizontal ? 'native' : 'focus';
    return 'focus';
  }

  return {
    BLOCKED_HOST: BLOCKED_HOST,
    containsForbiddenAddress: containsForbiddenAddress,
    privateIPv4: privateIPv4,
    normalizeMediaUrl: normalizeMediaUrl,
    normalizeLayout: normalizeLayout,
    resolveLayoutRequest: resolveLayoutRequest,
    normalizePresetId: normalizePresetId,
    normalizeSyncUrl: normalizeSyncUrl,
    normalizePreset: normalizePreset,
    normalizeConfig: normalizeConfig,
    defaultConfig: defaultConfig,
    parseStored: parseStored,
    resolvePresetRequest: resolvePresetRequest,
    resolveShowRequest: resolveShowRequest,
    normalizeAction: normalizeAction,
    keyIntent: keyIntent
  };
}));
