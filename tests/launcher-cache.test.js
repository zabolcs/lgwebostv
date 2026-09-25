'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../apps/launcher/launcher-cache.js'), 'utf8');
const entries = new Map();
let abortWrite = false, fetchCount = 0, sequence = 0, imageValid = true;
const liveUrls = new Set();
const transactions = [];
function transaction(_name, mode) {
  const tx = { abort() { setImmediate(() => tx.onabort && tx.onabort()); } };
  tx.objectStore = () => {
    function request(operation) {
      const req = {};
      setImmediate(() => {
        const value = operation();
        req.result = value;
        if (req.onsuccess) req.onsuccess();
        setImmediate(() => {
          if (mode === 'readwrite' && abortWrite) { if (tx.onabort) tx.onabort(); }
          else if (tx.oncomplete) tx.oncomplete();
        });
      });
      return req;
    }
    return {
      get: key => request(() => entries.get(key)),
      put: value => request(() => { if (!abortWrite) entries.set(value.key, value); return value.key; }),
      delete: key => request(() => entries.delete(key)),
      openCursor() {
        const req = {}, values = [...entries.values()]; let i = 0;
        function step() {
          req.result = i < values.length ? { value: values[i++], continue() { setImmediate(step); } } : null;
          if (req.onsuccess) req.onsuccess();
          if (!req.result) setImmediate(() => tx.oncomplete && tx.oncomplete());
        }
        setImmediate(step);
        return req;
      }
    };
  };
  transactions.push(tx);
  return tx;
}
const env = {
  indexedDB: { open() {
    const req = {};
    setImmediate(() => { req.result = { transaction }; req.onsuccess(); });
    return req;
  } },
  URL: {
    createObjectURL() { const url = 'blob:' + (++sequence); liveUrls.add(url); return url; },
    revokeObjectURL(url) { liveUrls.delete(url); }
  },
  Image: class {
    set src(_value) {
      this._src = _value;
      this.naturalWidth = imageValid ? 24 : 0;
      setImmediate(() => { if (imageValid) { if (this.onload) this.onload(); } else if (this.onerror) this.onerror(); });
    }
    get src() { return this._src; }
  },
  fetch: async () => {
    fetchCount++;
    return { ok: true, headers: { get: () => 'image/png' }, blob: async () => ({ size: 1024, type: 'image/png' }) };
  },
  setTimeout(callback, delay) { const timer = setTimeout(callback, delay); if (delay > 10000) timer.unref(); return timer; },
  clearTimeout, AbortController, Promise, Date, Object, Number, String, Error, Math
};
env.window = env;
vm.runInNewContext(source, env);
const cache = env.LauncherImageCache;
(async () => {
  const first = cache.fetchAndStore('icon', 'http://test/icon', 1000, { ttlMs: 10000 });
  assert.strictEqual(cache.fetchAndStore('icon', 'http://test/icon', 1000), first, 'parallel requests deduplicate');
  assert((await first).startsWith('blob:'));
  assert.strictEqual(fetchCount, 1);
  assert((await cache.getUrl('icon', { source: 'http://test/icon' })).startsWith('blob:'));
  const transactionCount = transactions.length;
  assert((await cache.getUrl('icon', { source: 'http://test/icon' })).startsWith('blob:'));
  assert.strictEqual(transactions.length, transactionCount, 'warm image lookup must not reopen IndexedDB');
  await cache.fetchAndStore('wallpaper', 'http://proxy/wallpaper', 1000, { source: 'https://original/wallpaper' });
  assert((await cache.getUrl('wallpaper', { source: 'https://original/wallpaper' })).startsWith('blob:'), 'proxy bytes use canonical identity');
  entries.set('camera', {key:'camera',blob:{type:'image/jpeg',size:123},source:'http://camera/frame',savedAt:1,expiresAt:2});
  const preview = new env.Image();
  await cache.bindPreview(preview, 'camera', 'http://camera/frame', 'http://proxy/preview');
  assert(preview.src.startsWith('blob:'), 'even old camera frames restore without fetching');
  const beforeRefresh = fetchCount;
  await preview.__launcherRefresh();
  assert.strictEqual(fetchCount, beforeRefresh + 1);
  assert.strictEqual(entries.get('camera').source, 'http://camera/frame');
  assert.strictEqual(await cache.getUrl('icon', { source: 'http://test/changed' }), '', 'changed URL invalidates');
  await new Promise(setImmediate);
  abortWrite = true;
  await assert.rejects(cache.fetchAndStore('aborted', 'http://test/abort', 1000), /menthető/);
  abortWrite = false;
  assert.strictEqual(await cache.getUrl('aborted'), '', 'request success before tx abort must not be reported as a saved image');
  imageValid = false;
  await assert.rejects(cache.fetchAndStore('bad', 'http://test/bad', 1000), /dekódolható/);
  assert(!entries.has('bad'), 'invalid image bytes must not poison the persistent cache');
  imageValid = true;
  entries.set('expired', { key: 'expired', blob: { type: 'image/png', size: 123 }, source: 'x', savedAt: 1, expiresAt: 2 });
  assert.strictEqual(await cache.getUrl('expired'), '');
  for (let i = 0; i < 70; i++) {
    entries.set('bulk-' + i, { key: 'bulk-' + i, blob: { type: 'image/png', size: 1024 * 1024 }, source: 'x', savedAt: i + 1 });
    await cache.getUrl('bulk-' + i);
  }
  assert(liveUrls.size <= 64, 'decoded blob URLs are bounded');
  await cache.trim(64);
  const bytes = [...entries.values()].reduce((sum, value) => sum + value.blob.size, 0);
  assert(entries.size <= 64);
  assert(bytes <= 32 * 1024 * 1024, 'persistent images are size bounded as well as count bounded');
  console.log('launcher image-cache tests: PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
