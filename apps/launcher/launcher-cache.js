(function (global) {
  'use strict';

  var DB_NAME = 'hu.szabi.launcher.cache.v3';
  var DB_VERSION = 1;
  var STORE = 'images';
  var MAX_BLOB_BYTES = 8 * 1024 * 1024;
  var dbPromise = null;
  var objectUrls = {};
  var retiredUrls = [];
  var activeFetches = {};
  var MAX_URLS = 64;

  function now() { return Date.now(); }
  function sourceText(value) { return String(value || '').slice(0, 4096); }
  function isImageType(value) {
    return /^image\/(?:avif|bmp|gif|jpe?g|png|svg\+xml|webp)(?:\s*;|$)/i.test(String(value || ''));
  }
  function isUsableBlob(blob, contentType) {
    return !!blob && typeof blob.size === 'number' && blob.size > 0 && blob.size <= MAX_BLOB_BYTES &&
      isImageType(blob.type || contentType);
  }

  function openDb() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise(function (resolve, reject) {
      if (!global.indexedDB) { reject(new Error('IndexedDB nem érhető el.')); return; }
      var request = global.indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = function () {
        var db = request.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'key' });
      };
      request.onsuccess = function () {
        var db = request.result;
        db.onversionchange = function () { try { db.close(); } catch (ignore) {} dbPromise = null; };
        resolve(db);
      };
      request.onerror = function () { dbPromise = null; reject(request.error || new Error('A képcache nem nyitható meg.')); };
      request.onblocked = function () { dbPromise = null; reject(new Error('A képcache frissítése blokkolva van.')); };
    });
    return dbPromise;
  }

  // Resolve only after the transaction has committed. A request's onsuccess is
  // not a durability boundary for read/write IndexedDB transactions.
  function withStore(mode, operation) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx;
        try { tx = db.transaction(STORE, mode); } catch (error) { reject(error); return; }
        var value;
        var operationFinished = false;
        var failed = false;
        function succeed(result) { value = result; operationFinished = true; }
        function fail(error) {
          if (failed) return;
          failed = true;
          try { tx.abort(); } catch (ignore) {}
          reject(error || tx.error || new Error('Képcache hiba.'));
        }
        tx.oncomplete = function () {
          if (failed) return;
          if (!operationFinished) { reject(new Error('A képcache művelet nem fejeződött be.')); return; }
          resolve(value);
        };
        tx.onabort = function () { if (!failed) { failed = true; reject(tx.error || new Error('A képcache művelet megszakadt.')); } };
        tx.onerror = function () { /* onabort is the authoritative failure. */ };
        try { operation(tx.objectStore(STORE), succeed, fail); } catch (error) { fail(error); }
      });
    });
  }

  function revokeObjectUrl(key) {
    var current = objectUrls[key];
    if (!current) return;
    try { global.URL.revokeObjectURL(current.url); } catch (ignore) {}
    delete objectUrls[key];
  }

  function remove(key) {
    key = String(key || '');
    if (!key) return Promise.resolve(false);
    revokeObjectUrl(key);
    return withStore('readwrite', function (store, succeed, fail) {
      var request = store.delete(key);
      request.onsuccess = function () { succeed(true); };
      request.onerror = function () { fail(request.error); };
    }).catch(function () { return false; });
  }

  function entryMatches(entry, meta) {
    if (!entry || !isUsableBlob(entry.blob, entry.contentType)) return false;
    meta = meta || {};
    var expectedSource = sourceText(meta.source);
    if (expectedSource && sourceText(entry.source) !== expectedSource) return false;
    if (meta.allowStale) return true;
    var ttlMs = Number(meta.ttlMs || 0);
    if (ttlMs > 0 && now() - Number(entry.savedAt || 0) > ttlMs) return false;
    if (Number(entry.expiresAt || 0) > 0 && now() > Number(entry.expiresAt)) return false;
    return true;
  }

  function getEntry(key, meta) {
    key = String(key || '');
    if (!key) return Promise.resolve(null);
    return withStore('readonly', function (store, succeed, fail) {
      var request = store.get(key);
      request.onsuccess = function () { succeed(request.result || null); };
      request.onerror = function () { fail(request.error); };
    }).then(function (entry) {
      if (entryMatches(entry, meta)) return entry;
      if (entry) remove(key);
      return null;
    }).catch(function () { return null; });
  }

  function put(key, blob, meta) {
    key = String(key || '');
    meta = meta || {};
    var contentType = String(blob && blob.type || meta.contentType || '').toLowerCase();
    if (!key || !isUsableBlob(blob, contentType)) return Promise.resolve(false);
    var ttlMs = Math.max(0, Number(meta.ttlMs || 0));
    var savedAt = now();
    var entry = {
      key: key,
      blob: blob,
      savedAt: savedAt,
      expiresAt: ttlMs ? savedAt + ttlMs : 0,
      contentType: contentType,
      source: sourceText(meta.source)
    };
    return withStore('readwrite', function (store, succeed, fail) {
      var request = store.put(entry);
      request.onsuccess = function () { succeed(true); };
      request.onerror = function () { fail(request.error); };
    }).catch(function () { return false; });
  }

  function objectUrlFor(key, entry) {
    if (!entry || !entry.blob) return '';
    var current = objectUrls[key];
    if (current && current.savedAt === entry.savedAt && current.source === sourceText(entry.source)) return current.url;
    var previous = current && current.url || '';
    try {
      var url = global.URL.createObjectURL(entry.blob);
      objectUrls[key] = { url: url, savedAt: entry.savedAt, expiresAt: entry.expiresAt, source: sourceText(entry.source) };
      var keys = Object.keys(objectUrls);
      if (previous && previous !== url) {
        retiredUrls.push(previous);
        global.setTimeout(function () {
          var position = retiredUrls.indexOf(previous);
          if (position < 0) return;
          retiredUrls.splice(position, 1);
          try { global.URL.revokeObjectURL(previous); } catch (ignore) {}
        }, 30000);
      }
      while (keys.length + retiredUrls.length > MAX_URLS && retiredUrls.length) {
        try { global.URL.revokeObjectURL(retiredUrls.shift()); } catch (ignore) {}
      }
      if (keys.length > MAX_URLS) {
        keys.sort(function (a, b) { return objectUrls[a].savedAt - objectUrls[b].savedAt; });
        keys.slice(0, keys.length - MAX_URLS).forEach(revokeObjectUrl);
      }
      return url;
    } catch (ignore2) { return previous; }
  }

  function getUrl(key, meta) {
    key = String(key || '');
    if (!key) return Promise.resolve('');
    var current = objectUrls[key];
    meta = meta || {};
    if (current && (!meta.source || current.source === sourceText(meta.source))) {
      var ageValid = !meta.ttlMs || now() - current.savedAt <= Number(meta.ttlMs);
      var expiryValid = !current.expiresAt || now() <= current.expiresAt;
      if (meta.allowStale || (ageValid && expiryValid)) return Promise.resolve(current.url);
    }
    return getEntry(key, meta).then(function (entry) { return entry ? objectUrlFor(key, entry) : ''; });
  }

  function fetchBlob(url, timeoutMs) {
    if (!url) return Promise.reject(new Error('Hiányzó kép URL.'));
    var controller = typeof global.AbortController === 'function' ? new global.AbortController() : null;
    var settled = false;
    var timer = null;
    return new Promise(function (resolve, reject) {
      function finish(error, blob) {
        if (settled) return;
        settled = true;
        if (timer) global.clearTimeout(timer);
        if (error) reject(error); else resolve(blob);
      }
      timer = global.setTimeout(function () {
        if (controller) try { controller.abort(); } catch (ignore) {}
        finish(new Error('A kép letöltése időtúllépés miatt megszakadt.'));
      }, Math.max(1000, Number(timeoutMs || 5000)));
      var options = { method: 'GET', cache: 'no-store' };
      if (controller) options.signal = controller.signal;
      global.fetch(url, options).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var contentType = String(response.headers && response.headers.get && response.headers.get('Content-Type') || '').toLowerCase();
        if (!isImageType(contentType)) throw new Error('A válasz nem kép (' + (contentType || 'ismeretlen típus') + ').');
        // Keep the timer alive until response.blob() has consumed the body.
        return response.blob().then(function (blob) {
          if (!isUsableBlob(blob, contentType)) throw new Error('Érvénytelen vagy túl nagy kép.');
          return blob;
        });
      }).then(function (blob) { finish(null, blob); }, function (error) { finish(error); });
    });
  }

  function fetchAndStore(key, url, timeoutMs, meta) {
    key = String(key || '');
    url = sourceText(url);
    if (!key || !url) return Promise.reject(new Error('Hiányzó képcache-kulcs vagy URL.'));
    meta = meta || {};
    var canonicalSource = sourceText(meta.source || url);
    var fetchKey = key + '\n' + url + '\n' + canonicalSource;
    if (activeFetches[fetchKey]) return activeFetches[fetchKey];
    var request = fetchBlob(url, timeoutMs).then(validateDecode).then(function (blob) {
      return put(key, blob, { source: canonicalSource, ttlMs: meta.ttlMs, contentType: blob.type }).then(function (saved) {
        if (!saved) throw new Error('A kép nem menthető a gyorsítótárba.');
        return getEntry(key, { source: canonicalSource, ttlMs: meta.ttlMs });
      }).then(function (entry) { return objectUrlFor(key, entry); });
    });
    activeFetches[fetchKey] = request.then(function (value) { delete activeFetches[fetchKey]; return value; }, function (error) { delete activeFetches[fetchKey]; throw error; });
    return activeFetches[fetchKey];
  }

  function validateDecode(blob) {
    return new Promise(function (resolve, reject) {
      var url = global.URL.createObjectURL(blob);
      var image = new global.Image();
      var done = false;
      var timer = global.setTimeout(function () { finish(false); }, 5000);
      function finish(ok) {
        if (done) return;
        done = true;
        global.clearTimeout(timer);
        image.onload = image.onerror = null;
        global.URL.revokeObjectURL(url);
        if (ok) resolve(blob); else reject(new Error('A kép nem dekódolható.'));
      }
      image.onload = function () { finish(image.naturalWidth > 0); };
      image.onerror = function () { finish(false); };
      image.src = url;
    });
  }

  function invalidate(key, source) {
    key = String(key || '');
    if (!key) return Promise.resolve(false);
    if (!source) return remove(key);
    return getEntry(key).then(function (entry) {
      return entry && sourceText(entry.source) === sourceText(source) ? remove(key) : false;
    });
  }

  // Restore locally before any network work. A refresh is decoded offscreen;
  // failed requests never replace a usable old frame with a broken image.
  function bindPreview(image, key, source, preferredSource, onVisible) {
    var displayed = '';
    var refreshing = null;
    var fresh = false;
    image.onload = function () {
      displayed = image.src;
      image.hidden = false;
      if (onVisible) onVisible();
    };
    image.onerror = function () {
      if (displayed && image.src !== displayed) image.src = displayed;
      else if (!displayed) image.hidden = true;
    };
    var restored = getUrl(key, { source: source, allowStale: true }).then(function (url) {
      if (url && !fresh) image.src = url;
      return url;
    });
    function download(url) {
      return fetchAndStore(key, url, 4500, { source: source });
    }
    image.__launcherRefresh = function () {
      if (refreshing) return refreshing;
      refreshing = restored.then(function () {
        return download(preferredSource || source).catch(function (error) {
          if (!preferredSource || preferredSource === source) throw error;
          return download(source);
        });
      }).then(function (url) {
        fresh = true;
        if (url) image.src = url;
        trim(64);
      }, function () {
        // CORS/storage can be unavailable in a browser admin. Load into a
        // separate image first, keeping any old picture throughout the retry.
        return new Promise(function (resolve) {
          var probe = new global.Image();
          var timer = global.setTimeout(finish, 4500);
          function finish() { global.clearTimeout(timer); probe.onload = probe.onerror = null; resolve(); }
          probe.onload = function () { fresh = true; image.src = probe.src; finish(); };
          probe.onerror = finish;
          probe.src = source + (source.indexOf('?') < 0 ? '?' : '&') + '_launcher=' + now();
        });
      }).then(function () { refreshing = null; });
      return refreshing;
    };
    return restored;
  }

  function trim(maxEntries) {
    maxEntries = Math.max(1, Math.min(64, Number(maxEntries || 64)));
    return withStore('readonly', function (store, succeed, fail) {
      var result = [];
      var request = store.openCursor();
      request.onsuccess = function () {
        var cursor = request.result;
        if (!cursor) { succeed(result); return; }
        result.push({ key: cursor.value.key, size: Number(cursor.value.blob && cursor.value.blob.size || 0), savedAt: Number(cursor.value.savedAt || 0), expiresAt: Number(cursor.value.expiresAt || 0) });
        cursor.continue();
      };
      request.onerror = function () { fail(request.error); };
    }).then(function (items) {
      var timestamp = now();
      var expired = items.filter(function (item) { return item.expiresAt > 0 && item.expiresAt < timestamp; });
      var retained = items.filter(function (item) { return !(item.expiresAt > 0 && item.expiresAt < timestamp); });
      retained.sort(function (a, b) { return a.savedAt - b.savedAt; });
      var overflow = Math.max(0, retained.length - maxEntries);
      var total = retained.reduce(function (sum, item) { return sum + item.size; }, 0);
      for (var i = 0; i < overflow; i += 1) total -= retained[i].size;
      while (total > 32 * 1024 * 1024 && overflow < retained.length) {
        total -= retained[overflow].size; overflow += 1;
      }
      return Promise.all(expired.concat(retained.slice(0, overflow)).map(function (item) { return remove(item.key); }));
    }).catch(function () {});
  }

  global.LauncherImageCache = {
    getUrl: getUrl,
    fetchAndStore: fetchAndStore,
    bindPreview: bindPreview,
    invalidate: invalidate,
    remove: remove,
    trim: trim,
    _isImageType: isImageType
  };
}(window));
