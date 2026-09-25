'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const source = fs.readFileSync(path.join(__dirname, '../apps/launcher/launcher-ui.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, '../apps/launcher/launcher.css'), 'utf8');
const activeClasses = new Set();
const context = {
  document: {body: {classList: {toggle(name, enabled) {
    if (enabled) activeClasses.add(name); else activeClasses.delete(name);
  }}}}
};
const start = source.indexOf('    function applyDisplayPreferences(');
assert.ok(start >= 0);
vm.runInNewContext(source.slice(start, source.indexOf('    function setPresentation(', start)), context);
// Exercise every pair and toggling back from a previous render, including legacy settings.
for (const animationsEnabled of [true, false, undefined]) {
  for (const visualEffectsEnabled of [true, false, undefined]) {
    const settings = Object.freeze({animationsEnabled, visualEffectsEnabled, wallpaperEnabled:true});
    context.applyDisplayPreferences(settings);
    assert.strictEqual(activeClasses.has('launcher-motion-disabled'), animationsEnabled === false);
    assert.strictEqual(activeClasses.has('launcher-effects-disabled'), visualEffectsEnabled === false);
    assert.strictEqual(settings.wallpaperEnabled, true);
  }
}
// Guard the regression that painted the full tile and its caption, covering the wallpaper.
const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)];
let captionProtected = false;
for (const [, selectors, declarations] of rules) {
  if (selectors.includes('.launcher-motion-disabled')) {
    assert.ok(!/(?:background|filter|shadow|opacity)\s*:/i.test(declarations), 'animation switch must only affect motion');
  }
  if (selectors.includes('.launcher-effects-disabled')) {
    assert.ok(!/(?:animation|transition|scroll-behavior)\s*:/i.test(declarations), 'effects switch must not affect motion');
    assert.ok(!/\.launcher-(?:wallpaper|shade|tile-label)(?![\w-])/.test(selectors), 'wallpaper, dimming and caption stay independent');
    assert.ok(!/\.launcher-(?:tile|quick-tile)(?=\s*(?:,|$))/.test(selectors), 'paint media, never the transparent tile wrapper');
  }
  if (selectors.trim() === '.launcher-shell .launcher-tile-label') {
    assert.match(declarations, /background\s*:\s*transparent\s*!important/);
    captionProtected = true;
  }
}
assert.ok(captionProtected, 'full launcher captions always retain transparent backgrounds');
// Home delivers the two global switches even when a popup's offline snapshot is old.
const app = fs.readFileSync(path.join(__dirname, '../apps/launcher/app.js'), 'utf8');
const begin = app.indexOf('  function applyLaunchDisplayPreferences(');
const applied = [];
const launchContext = {
  cachedState: {config: {settings: {animationsEnabled:true, visualEffectsEnabled:false, wallpaperEnabled:true}}},
  controller: {setDisplayPreferences: value => applied.push(value)}
};
vm.runInNewContext(app.slice(begin, app.indexOf('  var launch = params();', begin)), launchContext);
launchContext.applyLaunchDisplayPreferences({displayPreferences:{animationsEnabled:false,visualEffectsEnabled:true,wallpaperEnabled:false}});
assert.deepStrictEqual(launchContext.cachedState.config.settings,{animationsEnabled:false,visualEffectsEnabled:true,wallpaperEnabled:true});
assert.strictEqual(applied[0].animationsEnabled,false);
launchContext.applyLaunchDisplayPreferences({displayPreferences:{animationsEnabled:'false'}});
assert.strictEqual(launchContext.cachedState.config.settings.animationsEnabled,false);
console.log('launcher display preferences tests: PASS');
