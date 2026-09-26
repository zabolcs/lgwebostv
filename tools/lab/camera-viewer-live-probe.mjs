const TV = 'http://192.168.0.240:9998/json';
const NAS = 'http://192.168.0.223:8765';

const sleep = ms => new Promise(r => setTimeout(r, ms));

async function pages() {
  try {
    return await (await fetch(TV, {signal: AbortSignal.timeout(1200)})).json();
  } catch { return []; }
}

async function evaluate(page, expression) {
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  return await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { try { ws.close(); } catch {} reject(new Error('CDP timeout')); }, 5000);
    ws.onopen = () => ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression,returnByValue:true,awaitPromise:true}}));
    ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.id !== 1) return;
      clearTimeout(timer);
      if (msg.result && msg.result.exceptionDetails) reject(new Error(JSON.stringify(msg.result.exceptionDetails)));
      else resolve(msg.result.result.value);
      try { ws.close(); } catch {}
    };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('CDP websocket error')); };
  });
}

async function activeCameraPage() {
  for (const page of await pages()) {
    if (!String(page.url || '').includes('/hu.szabi.cameraviewer/')) continue;
    try {
      const raw = await evaluate(page, 'JSON.stringify({hidden:document.hidden,screen:document.querySelector("#grid-screen")&&!document.querySelector("#grid-screen").classList.contains("hidden")})');
      const state = JSON.parse(raw);
      if (!state.hidden && state.screen) return page;
    } catch {}
  }
  return null;
}

let page = await activeCameraPage();
if (!page) {
  const response = await fetch(NAS + '/api/launcher/launch', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({type:'app', targetId:'hu.szabi.cameraviewer', label:'Camera Viewer probe'})
  });
  if (!response.ok) throw new Error('CAMERA_LAUNCH=' + response.status);
  for (let i=0;i<40 && !page;i+=1) {
    await sleep(250);
    page = await activeCameraPage();
  }
}
if (!page) throw new Error('NO_ACTIVE_CAMERA_VIEWER');

for (let i = 0; i < 24; i += 1) {
  const count = Number(await evaluate(page, 'document.querySelectorAll(".camera-tile").length')) || 0;
  if (count >= 2) break;
  await sleep(250);
}

const inventory = JSON.parse(await evaluate(page, `JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.camera-tile'), function(tile) {
  var img=tile.querySelector('img:not(.camera-grid-live)');
  var name=tile.querySelector('.tile-name');
  var state=tile.querySelector('.tile-state');
  return {
    profileId:tile.getAttribute('data-profile-id')||'',
    name:name?name.textContent:'',
    snapshot:img?img.src:'',
    state:state?state.textContent:'',
    x:Number(tile.getAttribute('data-grid-x')||0),
    y:Number(tile.getAttribute('data-grid-y')||0)
  };
}))`));
console.log('CAMERA_GRID=' + JSON.stringify(inventory));
if (inventory.length < 2) throw new Error('NOT_ENOUGH_CAMERA_TILES');
if (inventory.some(x => /élő előnézet/i.test(x.state))) throw new Error('LEGACY_LIVE_LABEL_PRESENT');

const stableIndex = Math.min(2, inventory.length - 1);
const stableBefore = inventory[stableIndex].snapshot;

async function focusAndMeasure(index) {
  const start = Date.now();
  await evaluate(page, `(function(){var t=document.querySelectorAll('.camera-tile')[${index}];if(!t)throw new Error('tile missing');t.focus();return true;})()`);
  let state = null;
  while (Date.now() - start < 1600) {
    const raw = await evaluate(page, `JSON.stringify((function(){
      var tiles=document.querySelectorAll('.camera-tile');
      var t=tiles[${index}];
      var live=t&&t.querySelector('.camera-grid-live');
      var badge=t&&t.querySelector('.camera-grid-live-badge');
      return {
        active:document.activeElement===t,
        totalLive:document.querySelectorAll('.camera-grid-live').length,
        liveUrl:live?(live.getAttribute('data-live-mjpeg')||live.src||''):'',
        badge:badge?badge.textContent:'',
        oldLiveLabel:Array.prototype.some.call(document.querySelectorAll('.tile-state'),function(x){return /élő előnézet/i.test(x.textContent||'');})
      };
    })())`);
    state = JSON.parse(raw);
    if (state.active && state.totalLive === 1 && state.liveUrl) break;
    await sleep(60);
  }
  state.elapsedMs = Date.now() - start;
  return state;
}

// Rapid navigation should not fan out multiple MJPEG connections. Only the
// camera that remains focused after the debounce may become live.
for (let i = 0; i < inventory.length; i += 1) {
  await evaluate(page, `(function(){var t=document.querySelectorAll('.camera-tile')[${i}];if(t)t.focus();return true;})()`);
  await sleep(90);
}
await sleep(1150);
const rapid = JSON.parse(await evaluate(page, `JSON.stringify((function(){
  var tiles=document.querySelectorAll('.camera-tile');
  var last=tiles[tiles.length-1];
  var live=last&&last.querySelector('.camera-grid-live');
  return {
    activeLast:document.activeElement===last,
    totalLive:document.querySelectorAll('.camera-grid-live').length,
    liveUrl:live?(live.getAttribute('data-live-mjpeg')||live.src||''):''
  };
})())`));
console.log('RAPID_NAV=' + JSON.stringify(rapid));
if (!rapid.activeLast || rapid.totalLive !== 1 || !rapid.liveUrl) throw new Error('RAPID_NAV_LIVE_FAIL');

const allFocus = [];
for (let i = 0; i < inventory.length; i += 1) {
  const measured = await focusAndMeasure(i);
  allFocus.push({index:i,name:inventory[i].name,elapsedMs:measured.elapsedMs,totalLive:measured.totalLive,liveUrl:measured.liveUrl});
  if (!measured.active || measured.totalLive !== 1 || !measured.liveUrl || measured.badge !== 'LIVE' || measured.oldLiveLabel) {
    throw new Error('FOCUS_STRESS_FAIL_' + i);
  }
  if (measured.elapsedMs > 1450) throw new Error('FOCUS_STRESS_TOO_SLOW_' + i + '=' + measured.elapsedMs);
}
console.log('FOCUS_ALL=' + JSON.stringify(allFocus));

// Exercise the same keyboard path used by the physical remote.
await evaluate(page, `(function(){var t=document.querySelectorAll('.camera-tile')[0];if(t)t.focus();return true;})()`);
await sleep(380);
const remoteCodes = [39, 40, 37, 38, 39, 40];
const remoteNav = [];

function directionMatches(code, before, after) {
  if (code === 37) return after.x < before.x;
  if (code === 39) return after.x > before.x;
  if (code === 38) return after.y < before.y;
  return after.y > before.y;
}

for (const preferredCode of remoteCodes) {
  const before = JSON.parse(await evaluate(page, `JSON.stringify((function(){
    var tiles=Array.prototype.slice.call(document.querySelectorAll('.camera-tile'));
    var i=tiles.indexOf(document.activeElement);
    var t=i>=0?tiles[i]:null;
    return {index:i,x:t?Number(t.getAttribute('data-grid-x')||0):0,y:t?Number(t.getAttribute('data-grid-y')||0):0};
  })())`));

  const candidates = inventory.filter((item, idx) => idx !== before.index && directionMatches(preferredCode, before, item));
  if (!candidates.length) continue;

  const dispatchStarted = Date.now();
  await evaluate(page, `(function(){
    var e=new KeyboardEvent('keydown',{bubbles:true,cancelable:true});
    try{Object.defineProperty(e,'keyCode',{value:${preferredCode}});}catch(ignore){}
    try{Object.defineProperty(e,'which',{value:${preferredCode}});}catch(ignore){}
    window.dispatchEvent(e);
    return true;
  })()`);

  let moved = null;
  while (Date.now() - dispatchStarted < 350) {
    moved = JSON.parse(await evaluate(page, `JSON.stringify((function(){
      var tiles=Array.prototype.slice.call(document.querySelectorAll('.camera-tile'));
      var i=tiles.indexOf(document.activeElement);
      var t=i>=0?tiles[i]:null;
      return {index:i,x:t?Number(t.getAttribute('data-grid-x')||0):0,y:t?Number(t.getAttribute('data-grid-y')||0):0};
    })())`));
    if (moved.index !== before.index) break;
    await sleep(20);
  }
  const dispatchMs = Date.now() - dispatchStarted;
  if (!moved || moved.index === before.index || !directionMatches(preferredCode, before, moved)) {
    throw new Error('REMOTE_DIRECTION_FAIL_' + preferredCode + '=' + JSON.stringify({before,moved}));
  }

  const liveStarted = Date.now();
  let state = null;
  while (Date.now() - liveStarted < 1500) {
    state = JSON.parse(await evaluate(page, `JSON.stringify((function(){
      var tiles=document.querySelectorAll('.camera-tile');
      var target=tiles[${moved.index}];
      var live=target&&target.querySelector('.camera-grid-live');
      return {
        active:document.activeElement===target,
        totalLive:document.querySelectorAll('.camera-grid-live').length,
        live:!!live
      };
    })())`));
    if (state.totalLive > 1) throw new Error('MULTIPLE_LIVE_STREAMS=' + state.totalLive);
    if (state.active && state.totalLive===1 && state.live) break;
    await sleep(40);
  }

  state.code = preferredCode;
  state.from = before;
  state.to = moved;
  state.dispatchMs = dispatchMs;
  state.liveMs = Date.now() - liveStarted;
  remoteNav.push(state);
  console.log('REMOTE_DIRECTION_' + preferredCode + '=' + JSON.stringify(state));
}
console.log('REMOTE_NAV=' + JSON.stringify(remoteNav));
if (remoteNav.length < 3) throw new Error('REMOTE_NAV_TOO_FEW_MOVES=' + remoteNav.length);
for (const state of remoteNav) {
  if (!state.active || state.totalLive !== 1 || !state.live || state.liveMs > 1450 || state.dispatchMs > 350) {
    throw new Error('REMOTE_NAV_FAIL=' + JSON.stringify(state));
  }
}

const first = await focusAndMeasure(0);
console.log('FOCUS_1=' + JSON.stringify(first));
if (!first.active || first.totalLive !== 1 || !first.liveUrl || first.badge !== 'LIVE' || first.oldLiveLabel) throw new Error('FIRST_FOCUS_LIVE_FAIL');
if (first.elapsedMs > 1450) throw new Error('FIRST_FOCUS_TOO_SLOW=' + first.elapsedMs);

const second = await focusAndMeasure(1);
console.log('FOCUS_2=' + JSON.stringify(second));
if (!second.active || second.totalLive !== 1 || !second.liveUrl || second.badge !== 'LIVE' || second.oldLiveLabel) throw new Error('SECOND_FOCUS_LIVE_FAIL');
if (second.elapsedMs > 1450) throw new Error('SECOND_FOCUS_TOO_SLOW=' + second.elapsedMs);

const kapuIndex = inventory.findIndex(x => /^Kapu$/i.test(x.name));
if (kapuIndex >= 0) {
  const kapu = await focusAndMeasure(kapuIndex);
  console.log('FOCUS_KAPU=' + JSON.stringify(kapu));
  if (!/src=camera_kapu_felso_preview(?:&|$)/.test(kapu.liveUrl)) throw new Error('KAPU_MJPEG_SOURCE=' + kapu.liveUrl);
}

await sleep(3000);
const stableAfter = await evaluate(page, `(function(){var t=document.querySelectorAll('.camera-tile')[${stableIndex}];var i=t&&t.querySelector('img:not(.camera-grid-live)');return i?i.src:'';})()`);
console.log('SNAPSHOT_STABLE=' + JSON.stringify({before:stableBefore,after:stableAfter}));
if (stableBefore && stableAfter && stableBefore !== stableAfter) throw new Error('SNAPSHOT_REFRESHED_TOO_SOON');

await evaluate(page, `(function(){var b=document.getElementById('settings-button');if(b)b.focus();return true;})()`);
await sleep(150);
const cleared = JSON.parse(await evaluate(page, `JSON.stringify({live:document.querySelectorAll('.camera-grid-live').length,badges:document.querySelectorAll('.camera-grid-live-badge').length})`));
console.log('AFTER_BLUR=' + JSON.stringify(cleared));
if (cleared.live !== 0 || cleared.badges !== 0) throw new Error('LIVE_NOT_CLEARED');

console.log('CAMERA_VIEWER_LIVE_PROBE=PASS');
