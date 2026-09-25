'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const source = fs.readFileSync(path.join(__dirname, '../apps/launcher/launcher-ui.js'), 'utf8');
const start = source.indexOf('    function handleSettingsKey(');
const end = source.indexOf('    function visibleFocusables(', start);
const navOne = {name:'Home',tagName:'BUTTON'}, navTwo = {name:'Display',tagName:'BUTTON'};
const choice = {name:'choice',tagName:'BUTTON'}, input = {name:'field',tagName:'INPUT'};
const close = {name:'close',tagName:'BUTTON'};
let changed = 0, closed = 0;
choice.__launcherChangeChoice = delta => {changed += delta;};
choice.click = () => choice.__launcherChangeChoice(1);
const nav = {controls:[navOne,navTwo],contains:n => n === navOne || n === navTwo,querySelector:() => navOne};
const panel = {controls:[choice,input]};
const overlay = {hidden:false,querySelector:s => s.includes('-nav') ? nav : s.includes('-section') ? panel : close};
const document = {activeElement:navOne};
const context = {document,root:{querySelector:()=>overlay},visibleFocusables:n=>n.controls,
  focusNode:n=>{if(n)document.activeElement=n;},closeOverlays:()=>{closed++;}};
vm.runInContext(source.slice(start,end),vm.createContext(context));
function key(code, repeat=false) {
  const e = {keyCode:code,repeat,preventDefault(){this.prevented=true;},stopPropagation(){}};
  assert.strictEqual(context.handleSettingsKey(e),true); return e;
}
key(39); assert.strictEqual(document.activeElement,choice,'Right enters the active settings group');
key(39); key(37); assert.strictEqual(changed,0,'Left/Right change the choice, not the focus');
key(13); key(13,true); assert.strictEqual(changed,1,'Holding OK cannot repeatedly toggle a setting');
key(40); assert.strictEqual(document.activeElement,input,'Down follows the form in order');
assert.ok(!key(39).prevented,'Text input keeps normal cursor/keyboard handling');
key(461); assert.strictEqual(document.activeElement,navOne,'Back returns to the group list');
assert.strictEqual(closed,0);
key(40); assert.strictEqual(document.activeElement,navTwo,'Group navigation is predictable');
key(461); assert.strictEqual(closed,1,'Back on the group list closes settings');
overlay.hidden=true; assert.strictEqual(context.handleSettingsKey({keyCode:40}),false);
console.log('TV settings remote navigation: PASS');
