const appId = process.argv[2] || 'hu.szabi.launcher.overlay';

const pages = await (await fetch('http://192.168.0.240:9998/json', {
  signal: AbortSignal.timeout(1800)
})).json();

const page = pages.find((p) => p.url.includes('/' + appId + '/'));
if (!page) {
  console.log(JSON.stringify({ok:true,renderer:false,hidden:true}));
  process.exit(0);
}

const ws = new WebSocket(page.webSocketDebuggerUrl);
let nextId = 1;
const pending = new Map();

function call(method, params) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error('CDP timeout: ' + method));
    }, 2500);
    pending.set(id, {resolve, reject, timer});
    ws.send(JSON.stringify({id, method, params: params || {}}));
  });
}

await new Promise((resolve, reject) => {
  ws.onopen = resolve;
  ws.onerror = reject;
});

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  const p = pending.get(msg.id);
  if (!p) return;
  clearTimeout(p.timer);
  pending.delete(msg.id);
  if (msg.error) p.reject(new Error(JSON.stringify(msg.error)));
  else p.resolve(msg.result);
};

async function state() {
  const result = await call('Runtime.evaluate', {
    returnByValue: true,
    expression: 'JSON.stringify({hidden:document.hidden,activated:!!(window.PalmSystem&&window.PalmSystem.isActivated)})'
  });
  return JSON.parse(result.result.value);
}

let before = await state();
if (!before.hidden) {
  await call('Runtime.evaluate', {
    returnByValue: true,
    expression: `(() => {
      try {
        var s = window.PalmSystem || window.webOSSystem;
        if (!s || typeof s.hide !== 'function') return JSON.stringify({ok:false,error:'hide unavailable'});
        if (typeof s.keepAlive === 'function') s.keepAlive(true);
        s.hide();
        return JSON.stringify({ok:true});
      } catch (e) {
        return JSON.stringify({ok:false,error:String(e && e.message || e)});
      }
    })()`
  });
}

let after = before;
for (let i = 0; i < 20; i += 1) {
  await new Promise((resolve) => setTimeout(resolve, 50));
  after = await state();
  if (after.hidden) break;
}

console.log(JSON.stringify({ok:after.hidden,renderer:true,before,after}));
ws.close();
if (!after.hidden) process.exit(2);
