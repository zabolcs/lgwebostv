const deadline = Date.now() + 100000;
const appNeedle = '/hu.szabi.launcher/';
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function pages() {
  try {
    const response = await fetch('http://192.168.0.240:9998/json', {signal: AbortSignal.timeout(350)});
    return (await response.json()).filter(p => String(p.url || '').includes(appNeedle));
  } catch { return []; }
}

async function inspect(page) {
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  const expression = `JSON.stringify((function(){
    var boot=document.getElementById('launcher-boot');
    var mark=boot&&boot.querySelector('.launcher-boot-mark i');
    return {
      nav:performance.timing.navigationStart,
      hidden:document.hidden,
      activated:window.PalmSystem&&window.PalmSystem.isActivated,
      bootHidden:boot?boot.hidden:null,
      bootDisplay:boot?getComputedStyle(boot).display:null,
      loading:document.body.classList.contains('launcher-loading-active'),
      animation:mark?getComputedStyle(mark).animationName:null
    };
  })())`;
  return await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { try { ws.close(); } catch {} reject(new Error('timeout')); }, 500);
    ws.onopen = () => ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{returnByValue:true,expression}}));
    ws.onmessage = e => {
      const msg = JSON.parse(e.data);
      if (msg.id !== 1) return;
      clearTimeout(timer);
      try { resolve(JSON.parse(msg.result.result.value)); } catch (err) { reject(err); }
      try { ws.close(); } catch {}
    };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('ws')); };
  });
}

let baseline = 0;
for (const page of await pages()) {
  try { baseline = Math.max(baseline, Number((await inspect(page)).nav || 0)); } catch {}
}
console.log('BASE_NAV=' + baseline);

let freshSeenAt = 0;
let last = null;
while (Date.now() < deadline) {
  const list = await pages();
  for (const page of list) {
    try {
      const state = await inspect(page);
      if (baseline && Number(state.nav || 0) === baseline) continue;
      if (!freshSeenAt) {
        freshSeenAt = Date.now();
        console.log('FRESH_RENDERER=' + JSON.stringify(state));
      }
      last = state;
      console.log('LOADER_STATE=' + JSON.stringify(state));
      if (state.bootHidden === true && state.bootDisplay === 'none' && state.loading === false) {
        console.log('LOADER_HIDDEN_AFTER_FRESH_MS=' + (Date.now() - freshSeenAt));
        console.log('LOADER_REBOOT_PROBE=PASS');
        process.exit(0);
      }
    } catch {}
  }
  await sleep(150);
}
console.error('LAST_STATE=' + JSON.stringify(last));
console.error('LOADER_REBOOT_PROBE=FAIL');
process.exit(1);
