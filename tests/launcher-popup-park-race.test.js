'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const source = fs.readFileSync(path.join(__dirname, '../apps/launcher/launcher-ui.js'), 'utf8');
function functions(first, next) {
  return source.slice(source.indexOf('    function ' + first + '('), source.indexOf('    function ' + next + '('));
}
function method(name, next) {
  const start = source.indexOf('      ' + name + ': function (');
  const end = source.indexOf('      ' + next + ':', start);
  return source.slice(start, end).trim().replace(name + ': ', 'this.' + name + ' = ').replace(/,$/, ';');
}
function fixture(animationsEnabled = true) {
  const timers = []; const cleared = []; const classes = new Set();
  const calls = {hidden:0, cancelled:0, rendered:0};
  const context = {
    popupParkTimer:null, popupParkGeneration:0,
    parkRequested:false, parked:false, quickClosing:false,
    viewMode:'overlay', mode:'tv', imageQueueTimer:null, quickNeedsRender:true,
    options:{host:'quick'}, data:{config:{settings:{animationsEnabled}}},
    stopFullViewWork(){}, stopPreviewWork(){}, pumpImages(){},
    renderQuick(){calls.rendered++;},
    focusQuickState(){calls.focused = (calls.focused || 0) + 1;},
    startQuickClock(){calls.clock = (calls.clock || 0) + 1;},
    currentQuickCategory(){return {id:'favorites'};},
    document:{body:{classList:{
      add(name){classes.add(name);},
      remove(...names){names.forEach(name => classes.delete(name));}
    }}},
    root:{setAttribute(){}, removeAttribute(){}},
    popupLifecycle:{cancel(){calls.cancelled++;}, hide(){calls.hidden++;}},
    global:{
      setTimeout(callback, delay){const id = timers.length; timers.push({callback, delay}); return id;},
      clearTimeout(id){cleared.push(id);}
    }, Promise
  };
  vm.createContext(context);
  vm.runInContext(functions('cancelPendingPopupPark', 'closeApplicationFallback') +
    functions('parkLauncher', 'closeQuick') + method('prepareResume', 'setDisplayPreferences') +
    method('resume', 'setViewMode'), context);
  return {context, timers, cleared, classes, calls};
}

// Normal animation completion still invokes native hide exactly as before.
// An activation during the asynchronous initial state read must survive it.
{
  const f = fixture();
  f.context.data = null;
  f.context.parked = true;
  f.context.parkRequested = true;
  f.classes.add('launcher-parked');
  f.context.resume();
  assert.strictEqual(f.context.parked, false, 'early activation must not be lost');
  assert.strictEqual(f.context.parkRequested, false);
  assert.ok(!f.classes.has('launcher-parked'));
  assert.strictEqual(f.calls.rendered, 0, 'do not render before the state arrives');
}

{
  const f = fixture();
  f.context.parkLauncher(false);
  assert.strictEqual(f.timers[0].delay, 170);
  f.timers[0].callback();
  assert.strictEqual(f.calls.hidden, 1);
  assert.strictEqual(f.context.popupParkTimer, null);
}

// Test both the activation preparation and the direct resume entry point.
for (const entry of ['prepareResume', 'resume']) {
  const f = fixture();
  f.context.parkLauncher(false);
  f.context[entry]();
  assert.ok(f.cleared.includes(0), 'clear timer even when its ID is zero');
  f.timers[0].callback(); // Already queued before freeze; deliberately bypass clearTimeout.
  assert.strictEqual(f.calls.hidden, 0, entry + ' must invalidate the old close');
  assert.ok(!f.classes.has('launcher-parked'), 'stale close cannot conceal the resumed DOM');
}

// An old callback must not cancel or prematurely run a later, legitimate close.
{
  const f = fixture();
  f.context.parkLauncher(false);
  f.context.prepareResume(); f.context.resume();
  f.context.parkLauncher(false);
  const newTimer = f.context.popupParkTimer;
  f.timers[0].callback();
  assert.strictEqual(f.calls.hidden, 0);
  assert.strictEqual(f.context.popupParkTimer, newTimer);
  f.timers[newTimer].callback();
  assert.strictEqual(f.calls.hidden, 1);
}

// Animations-off and explicit immediate parks keep their immediate native path.
for (const [animations, immediate] of [[false, false], [true, true]]) {
  const f = fixture(animations);
  f.context.parkLauncher(immediate);
  assert.strictEqual(f.calls.hidden, 1);
  assert.strictEqual(f.timers.length, 0);
}
// A preloaded or previously shown menu keeps its prepared DOM and decoded icons.
{
  const f = fixture(); f.context.quickNeedsRender = false;
  f.context.resume(); f.context.resume();
  assert.strictEqual(f.calls.rendered, 0);
  assert.strictEqual(f.calls.focused, 2);
  assert.strictEqual(f.calls.clock, 2);
  f.context.quickNeedsRender = true; f.context.resume();
  assert.strictEqual(f.calls.rendered, 1, 'Changed menu data must still render');
}
console.log('launcher popup delayed park race tests: PASS');
