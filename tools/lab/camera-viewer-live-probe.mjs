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

const inventory = JSON.parse(await evaluate(page, `JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.camera-tile'), function(tile) {
  var img=tile.querySelector('img:not(.camera-grid-live)');
  var name=tile.querySelector('.tile-name');
  var state=tile.querySelector('.tile-state');
  return {
    profileId:tile.getAttribute('data-profile-id')||'',
    name:name?name.textContent:'',
    snapshot:img?img.src:'',
    state:state?state.textContent:''
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

const first = await focusAndMeasure(0);
console.log('FOCUS_1=' + JSON.stringify(first));
if (!first.active || first.totalLive !== 1 || !first.liveUrl || first.badge !== 'LIVE' || first.oldLiveLabel) throw new Error('FIRST_FOCUS_LIVE_FAIL');
if (first.elapsedMs > 1100) throw new Error('FIRST_FOCUS_TOO_SLOW=' + first.elapsedMs);

const second = await focusAndMeasure(1);
console.log('FOCUS_2=' + JSON.stringify(second));
if (!second.active || second.totalLive !== 1 || !second.liveUrl || second.badge !== 'LIVE' || second.oldLiveLabel) throw new Error('SECOND_FOCUS_LIVE_FAIL');
if (second.elapsedMs > 1100) throw new Error('SECOND_FOCUS_TOO_SLOW=' + second.elapsedMs);

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
