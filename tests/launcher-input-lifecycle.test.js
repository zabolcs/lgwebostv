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
  document:{hidden:false, activeElement:{tagName:'BUTTON',classList:{contains(){return true;}},click(){clicks++;}},
    addEventListener(name,fn){handlers[name]=fn;}},
  global:{setTimeout(fn){let id=next++;timers.set(id,fn);return id;},clearTimeout(id){timers.delete(id);}}
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('    function installTvNavigation('),source.indexOf('    function iconForApp(')), context);
context.installTvNavigation();
function key(kind, code, repeat=false){handlers[kind]({keyCode:code,repeat,preventDefault(){}});}
for (const state of ['hidden','parked']) {
  context.document.hidden=state==='hidden'; context.parked=state==='parked';
  key('keydown',461); key('keydown',27); key('keydown',13); key('keyup',13);
}
assert.equal(parks,0,'A hidden or preloaded launcher cannot resume the previous app');
assert.equal(clicks,0,'Background OK must not launch the focused tile');
context.document.hidden=false; context.parked=false;
key('keydown',461,true); assert.equal(parks,0,'Repeated Back from an earlier surface is ignored');
key('keydown',461); assert.equal(parks,1,'Fresh foreground Back keeps working');
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
