'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const source = fs.readFileSync(path.join(__dirname, '../apps/launcher/launcher-ui.js'), 'utf8');
const handlers = {}, timers = new Map(); let parks=0, clicks=0, edits=0, next=1;
const context = {
  mode:'tv', viewMode:'full', parked:false, editMode:null, okHoldTimer:null, okHeld:false,
  handleSettingsKey(){return false;}, parkLauncher(){parks++;},
  enterEditMode(){edits++;},
  root:{querySelector(){return null;},querySelectorAll(){return [];}},
  document:{hidden:false,
    getElementById(id){ return id==='launcher-boot' ? {hidden:!context.loadingVisible} : null; },
    activeElement:{tagName:'BUTTON',classList:{contains(){return true;}},click(){clicks++;}},
    addEventListener(name,fn){handlers[name]=fn;}},
  global:{setTimeout(fn){let id=next++;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);}}
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('    function installTvNavigation('),source.indexOf('    function iconForApp(')), context);
context.installTvNavigation();
function key(kind, code, repeat=false){handlers[kind]({keyCode:code,repeat,preventDefault(){},stopPropagation(){}});}
for (const state of ['hidden','parked']) {
  context.document.hidden=state==='hidden'; context.parked=state==='parked';
  key('keydown',461); key('keydown',27); key('keydown',13); key('keyup',13);
}
assert.equal(parks,0,'A hidden or preloaded launcher cannot resume the previous app');
assert.equal(clicks,0,'Background OK must not launch the focused tile');
context.document.hidden=false; context.parked=false;
context.loadingVisible=true;
key('keydown',37); key('keydown',13); key('keyup',13); key('keydown',461); key('keyup',461);
assert.equal(clicks,0,'Loading overlay must block OK app launches');
assert.equal(parks,0,'Loading overlay must block Back navigation');
context.loadingVisible=false;
key('keydown',461,true); assert.equal(parks,0,'Repeated Back from an earlier surface is ignored');
key('keydown',461); assert.equal(parks,0,'Fresh Back stays visible until release');
key('keyup',461); assert.equal(parks,1,'Short foreground Back commits on key-up');
key('keydown',461); key('keydown',461,true); key('keydown',461,true); key('keyup',461);
assert.equal(parks,1,'Long Back is consumed without exposing the native Home surface');
key('keydown',13); context.document.hidden=true; handlers.visibilitychange();
context.document.hidden=false; handlers.visibilitychange(); key('keyup',13);
assert.equal(clicks,0,'An OK press spanning hidden/resume must not activate a tile');
key('keydown',13); handlers.webOSRelaunch(); key('keyup',13);
assert.equal(clicks,0,'An old OK press cannot cross relaunch');
key('keydown',13); key('keyup',13); assert.equal(clicks,1,'Normal foreground OK works');
key('keydown',13); context.document.hidden=true;
for(const fn of timers.values()) fn();
assert.equal(edits,0,'A delayed hold callback cannot edit a background tile');
console.log('launcher input lifecycle: PASS');
