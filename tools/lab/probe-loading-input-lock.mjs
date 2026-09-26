const pages = await (await fetch('http://192.168.0.240:9998/json', {signal: AbortSignal.timeout(1500)})).json();
const page = pages.find(p => String(p.url || '').includes('/hu.szabi.launcher/'));
if (!page) throw new Error('launcher renderer not found');

const ws = new WebSocket(page.webSocketDebuggerUrl);
let nextId = 1;
const pending = new Map();

function evaluate(expression) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('evaluate timeout')); }, 1500);
    pending.set(id, {resolve, reject, timer});
    ws.send(JSON.stringify({id, method:'Runtime.evaluate', params:{returnByValue:true, expression}}));
  });
}

await new Promise((resolve, reject) => {
  ws.onopen = resolve;
  ws.onerror = () => reject(new Error('websocket error'));
  ws.onmessage = e => {
    const msg = JSON.parse(e.data);
    const item = pending.get(msg.id);
    if (!item) return;
    clearTimeout(item.timer);
    pending.delete(msg.id);
    item.resolve(msg?.result?.result?.value);
  };
});

const result = JSON.parse(await evaluate(`JSON.stringify((function(){
  var cover=document.getElementById('launcher-boot');
  var tile=document.querySelector('.launcher-tile:not(.launcher-page-spacer)');
  if(!cover||!tile)return {ok:false,reason:'missing cover or tile'};
  var clicks=0;
  var onClick=function(){clicks+=1;};
  tile.addEventListener('click',onClick);
  tile.focus();
  var beforeActive=document.activeElement;
  var beforeParked=document.body.classList.contains('launcher-parked');
  cover.hidden=false;

  function fire(type,code){
    var e=new Event(type,{bubbles:true,cancelable:true});
    Object.defineProperty(e,'keyCode',{value:code});
    Object.defineProperty(e,'which',{value:code});
    document.dispatchEvent(e);
  }

  fire('keydown',13); fire('keyup',13);
  fire('keydown',39); fire('keyup',39);
  fire('keydown',461); fire('keyup',461);

  var sameFocus=document.activeElement===beforeActive;
  var parked=document.body.classList.contains('launcher-parked');
  cover.hidden=true;
  tile.removeEventListener('click',onClick);
  return {
    ok:true,
    clicks:clicks,
    sameFocus:sameFocus,
    beforeParked:beforeParked,
    afterParked:parked,
    coverHidden:cover.hidden
  };
})())`));

console.log('LOADING_INPUT_PROBE=' + JSON.stringify(result));
if (!result.ok) throw new Error(result.reason || 'probe failed');
if (result.clicks !== 0) throw new Error('OK activated a tile under loading cover');
if (!result.sameFocus) throw new Error('navigation moved focus under loading cover');
if (result.beforeParked !== result.afterParked) throw new Error('Back changed launcher parked state under loading cover');
if (result.coverHidden !== true) throw new Error('probe did not restore cover hidden state');
console.log('LOADING_INPUT_LOCK_PROBE=PASS');
ws.close();
