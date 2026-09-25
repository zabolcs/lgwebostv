'use strict';

var assert = require('assert');
var fs = require('fs');
var path = require('path');
var vm = require('vm');

var source = fs.readFileSync(path.join(__dirname, '..', 'apps', 'launcher', 'app.js'), 'utf8');
function checkHost(host) {
var now = 1000;
var listeners = {};
var calls = { closeQuick: 0, resume: 0, setViewMode: 0, park: 0 };
var initOptions = null;
var lifecycleOrder = [];
var parked = false;
var timers = [];
var controller = {
  prepareResume: function () { lifecycleOrder.push('cancel-old-hide'); },
  isQuickOpen: function () { return host === 'quick' && !parked; },
  closeQuick: function () { calls.closeQuick += 1; parked = true; },
  park: function () { calls.park += 1; parked = true; },
  isParked: function () { return parked; },
  resume: function () { calls.resume += 1; parked = false; lifecycleOrder.push('resume'); },
  setViewMode: function () { calls.setViewMode += 1; }
};
var state = JSON.stringify({ config: { rows: [] }, apps: [], presets: [] });
var storage = { 'hu.szabi.launcher.offline-state.v1': state };
var rootNode = {};
var context = {
  document: {
    hidden: false,
    documentElement: { classList: { add: function () {} } },
    body: { classList: { add: function () {} } },
    getElementById: function () { return rootNode; },
    addEventListener: function (name, handler) { (listeners[name] || (listeners[name] = [])).push(handler); }
  },
  localStorage: {
    getItem: function (key) { return Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : null; },
    setItem: function (key, value) { storage[key] = String(value); },
    removeItem: function (key) { delete storage[key]; }
  },
  LauncherUI: { init: function (_root, options) { initOptions = options; return controller; } },
  webOSSystem: { launchParams: JSON.stringify({ mode: 'overlay', source: 'home-short-toggle', homeRequestId:'cold-1' }) },
  PalmSystem: { activate: function () { lifecycleOrder.push('activate'); } },
  __LAUNCHER_HOST__: {host:host, appId: host === 'quick' ? 'hu.szabi.launcher.quick' : 'hu.szabi.launcher'},
  Date: { now: function () { return now; } },
  setTimeout: function (callback, delay) { timers.push({callback:callback,delay:delay}); return timers.length; },
  clearTimeout: function (id) { if(timers[id-1]) timers[id-1].cancelled = true; },
  setInterval: function () { return 1; },
  fetch: function () { throw new Error('startup must not fetch synchronously'); },
  JSON: JSON,
  Object: Object,
  Array: Array,
  Number: Number,
  String: String,
  RegExp: RegExp,
  Error: Error,
  console: console
};
context.window = context;
context.globalThis = context;
vm.runInContext(source, vm.createContext(context), { filename: 'launcher/app.js' });
assert.strictEqual(initOptions.initiallyParked, false, 'a real Home launch is visible');
assert.strictEqual(typeof initOptions.onPark, 'function', 'the warm process has a park callback');

function homeEvent(source, id) {
  var launch = { mode: 'overlay', source: source };
  if (id !== null) launch.homeRequestId = id || source;
  return { detail: { launchParams: JSON.stringify(launch) } };
}
function emit(name, event) {
  event.type = name;
  (listeners[name] || []).forEach(function (handler) { handler(event); });
}

context.document.hidden = true;
emit('visibilitychange', {});
assert.strictEqual(calls.park, 0, 'a cold popup hidden event must not close the launcher before its first stable frame');
context.document.hidden = false;
emit('visibilitychange', {});
assert.deepStrictEqual(lifecycleOrder, ['cancel-old-hide','resume'], 'visibility changes must cancel stale hide deadlines without reactivating');
lifecycleOrder.length = 0;

now = 1200;
emit('webOSLaunch', homeEvent('home-short-toggle', 'cold-1'));
assert.deepStrictEqual(lifecycleOrder, ['cancel-old-hide','activate', 'resume'], 'cancel stale hide deadlines before foregrounding, then restart UI work');
assert.strictEqual(calls.closeQuick, 0, 'an explicit open event must never close the quick launcher');

now = 2200;
emit('webOSRelaunch', homeEvent('home-short-toggle'));
assert.strictEqual(calls.closeQuick, host === 'quick' ? 1 : 0, 'the first later short Home must close the open quick launcher');

now = 2250;
var resumesBeforeDuplicate = calls.resume;
emit('webOSLaunch', homeEvent('home-short-toggle'));
assert.strictEqual(calls.closeQuick, host === 'quick' ? 1 : 0, 'the duplicate webOS event must not toggle twice');
assert.strictEqual(calls.resume, resumesBeforeDuplicate, 'a duplicate launch event must not reopen the popup just hidden by Home');

now = 2260;
emit('webOSRelaunch', homeEvent('home-short-toggle', 'fast-reopen-2'));
assert.strictEqual(calls.resume, resumesBeforeDuplicate + 1, 'a distinct Home press reopens immediately, even inside 600 ms');
assert.strictEqual(parked, false);
var resumesAfterFastOpen = calls.resume;
now = 2270;
emit('webOSLaunch', homeEvent('home-short-toggle', 'fast-reopen-2'));
assert.strictEqual(calls.resume, resumesAfterFastOpen, 'paired event for fast reopen is ignored');
assert.strictEqual(calls.closeQuick, host === 'quick' ? 1 : 0, 'duplicate reopen cannot close the quick menu');

now = 2280;
emit('webOSRelaunch', homeEvent('home-short-toggle', 'fast-close-3'));
assert.strictEqual(calls.closeQuick, host === 'quick' ? 2 : 0, 'another distinct fast Home press can close again');
var resumesAfterFastClose = calls.resume;
now = 2290;
emit('webOSRelaunch', homeEvent('home-short-toggle', 'fast-reopen-4'));
assert.strictEqual(calls.resume, resumesAfterFastClose + 1, 'distinct rapid reopen still works after a rapid close');

// Without an ID there is no evidence of a distinct toggle press; retain the
// old open/resume semantics, including a second event without an ID.
var closesBeforeLegacy = calls.closeQuick;
var resumesBeforeLegacy = calls.resume;
emit('webOSRelaunch', homeEvent('home-short-toggle', null));
emit('webOSLaunch', homeEvent('home-short-toggle', null));
assert.strictEqual(calls.closeQuick, closesBeforeLegacy, 'missing-ID events must not start toggling');
assert.strictEqual(calls.resume, resumesBeforeLegacy + 2, 'missing-ID events preserve legacy resume behavior');

context.document.hidden = true;
emit('visibilitychange', {});
assert.strictEqual(calls.park, 0, 'a transient native hidden event must not immediately re-hide the resumed popup');
context.document.hidden = false;
emit('visibilitychange', {});
timers.filter(function(timer){return timer.delay === 150;}).forEach(function(timer){timer.callback();});
assert.strictEqual(calls.park, 0, 'even an already queued transient callback cannot park a visible popup');
context.document.hidden = true;
emit('visibilitychange', {});
timers.filter(function(timer){return timer.delay === 150 && !timer.cancelled;}).forEach(function(timer){timer.callback();});
assert.strictEqual(calls.park, host === 'quick' ? 1 : 0, 'stable native backgrounding must still park the popup');
emit('visibilitychange', {});
assert.strictEqual(calls.park, host === 'quick' ? 1 : 0, 'duplicate hidden events must keep parking idempotent');
assert(source.indexOf('/api/launcher/prewarm-ready') >= 0, 'hidden preload must signal after its first local render');

assert.strictEqual(initOptions.host, host);
assert.strictEqual(initOptions.viewMode, host === 'quick' ? 'overlay' : 'full');
assert.strictEqual(calls.setViewMode, 0, 'A host never changes its manifest window type at relaunch');
context.document.hidden = false;
context.PalmSystem.isActivated = true;
lifecycleOrder.length = 0;
emit('webOSRelaunch', homeEvent('default-home-guard', null));
assert(!lifecycleOrder.includes('activate'), 'SAM-activated card and popup must not be activated twice');
emit('visibilitychange', {});
assert(calls.resume > 0);
}
checkHost('quick');
checkHost('full');
console.log('launcher Home lifecycle tests: PASS');
