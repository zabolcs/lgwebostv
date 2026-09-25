'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const source = fs.readFileSync(path.join(__dirname, '../apps/launcher/launcher-popup-lifecycle.js'), 'utf8');
const context = {window: {}};
vm.runInNewContext(source, context);

function fixture(nativeHide) {
  const calls = [];
  const listeners = new Set();
  const timers = new Map();
  const allTimers = [];
  const doc = {
    hidden:false,
    addEventListener(name, callback) {
      assert.strictEqual(name, 'visibilitychange');
      calls.push('listen'); listeners.add(callback);
    },
    removeEventListener(name, callback) {
      assert.strictEqual(name, 'visibilitychange'); listeners.delete(callback);
    }
  };
  function emit(hidden) {
    doc.hidden = hidden;
    [...listeners].forEach(callback => callback());
  }
  const system = {
    keepAlive(value) { assert.strictEqual(this, system); assert.strictEqual(value, true); calls.push('keepAlive'); },
    hide() { assert.strictEqual(this, system); calls.push('hide'); if (nativeHide) nativeHide(doc, emit); }
  };
  const lifecycle = context.window.LauncherPopupLifecycle.create({
    system, document:doc,
    setTimeout(callback, delay) {
      assert.strictEqual(delay, 450);
      const id = allTimers.length;
      allTimers.push(callback); timers.set(id, callback); return id;
    },
    clearTimeout(id) { timers.delete(id); }
  });
  const results = [];
  function callbacks(name = 'one') {
    return {
      beforeHide() { calls.push('beforeHide'); },
      onHidden() { results.push(name + ':hidden'); },
      onFailure(error) { assert.ok(error); results.push(name + ':failed'); }
    };
  }
  function deadline() { [...timers.values()].forEach(callback => callback()); }
  function assertClean() { assert.strictEqual(listeners.size, 0); assert.strictEqual(timers.size, 0); }
  return {lifecycle, doc, emit, system, calls, listeners, timers, allTimers, results, callbacks, deadline, assertClean};
}

// Native hide can synchronously emit visibilitychange or only update hidden.
for (const nativeHide of [(doc, emit) => emit(true), doc => {doc.hidden = true;}]) {
  const f = fixture(nativeHide);
  assert.strictEqual(f.lifecycle.hide(f.callbacks()), true);
  assert.deepStrictEqual(f.calls, ['listen', 'beforeHide', 'keepAlive', 'hide']);
  assert.deepStrictEqual(f.results, ['one:hidden']);
  f.emit(true); f.deadline();
  assert.deepStrictEqual(f.results, ['one:hidden']);
  f.assertClean();
}

// An asynchronous visibility event confirms hiding and cancels the fallback.
{
  const f = fixture();
  assert.strictEqual(f.lifecycle.hide(f.callbacks()), true);
  assert.deepStrictEqual(f.results, []);
  f.emit(false);
  assert.deepStrictEqual(f.results, []);
  f.emit(true);
  f.allTimers[0](); // Deliberately run a callback already queued before cleanup.
  assert.deepStrictEqual(f.results, ['one:hidden']);
  f.assertClean();
}

// Some firmware updates hidden without delivering an event; the deadline checks it.
{
  const f = fixture();
  f.lifecycle.hide(f.callbacks()); f.doc.hidden = true; f.deadline();
  assert.deepStrictEqual(f.results, ['one:hidden']);
  f.assertClean();
}

// A native no-op fails once, allowing the caller to close the popup safely.
{
  const f = fixture();
  f.lifecycle.hide(f.callbacks()); f.deadline(); f.allTimers[0](); f.emit(true);
  assert.deepStrictEqual(f.results, ['one:failed']);
  f.assertClean();
}

for (const missing of ['keepAlive', 'hide']) {
  const f = fixture();
  delete f.system[missing];
  assert.strictEqual(f.lifecycle.hide(f.callbacks()), false);
  assert.deepStrictEqual(f.results, ['one:failed']);
  assert.deepStrictEqual(f.calls, []);
  f.assertClean();
}

for (const throwing of ['keepAlive', 'hide', 'beforeHide']) {
  const f = fixture();
  const callbacks = f.callbacks();
  const target = throwing === 'beforeHide' ? callbacks : f.system;
  target[throwing] = () => {throw new Error('Native/notification failure');};
  assert.strictEqual(f.lifecycle.hide(callbacks), false);
  f.emit(true); f.deadline();
  assert.deepStrictEqual(f.results, ['one:failed']);
  if (throwing !== 'hide') assert.ok(!f.calls.includes('hide'));
  f.assertClean();
}

// Resume must invalidate both a queued visibility handler and a frozen JS deadline.
{
  const f = fixture();
  f.lifecycle.hide(f.callbacks());
  const oldListener = [...f.listeners][0];
  f.lifecycle.cancel();
  f.doc.hidden = true; oldListener();
  f.doc.hidden = false; f.allTimers[0]();
  assert.deepStrictEqual(f.results, []);
  f.assertClean();
}

// Repeated hides replace the pending attempt rather than closing a resumed popup.
{
  const f = fixture();
  f.lifecycle.hide(f.callbacks('old'));
  const oldListener = [...f.listeners][0];
  f.lifecycle.hide(f.callbacks('new'));
  f.allTimers[0]();
  f.doc.hidden = true; oldListener();
  assert.deepStrictEqual(f.results, []);
  f.emit(true); f.allTimers[1]();
  assert.deepStrictEqual(f.results, ['new:hidden']);
  f.assertClean();
}

// Cancelling from beforeHide must stop native hiding of the now active popup.
{
  const f = fixture();
  const callbacks = f.callbacks();
  callbacks.beforeHide = () => f.lifecycle.cancel();
  assert.strictEqual(f.lifecycle.hide(callbacks), false);
  assert.deepStrictEqual(f.calls, ['listen']);
  assert.deepStrictEqual(f.results, []);
  f.assertClean();
}

console.log('launcher native popup lifecycle tests: PASS');
