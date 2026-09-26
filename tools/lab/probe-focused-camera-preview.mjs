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
    const result = msg?.result?.result?.value;
    item.resolve(result);
  };
});

const initialRaw = await evaluate(`JSON.stringify((function(){
  var button=document.querySelector('.launcher-camera-preview');
  if(!button)return {found:false};
  var image=button.querySelector('img[data-preview-url]');
  button.focus();
  return {found:true,active:document.activeElement===button,src:image?image.src:'',snapshot:image?image.getAttribute('data-preview-url'):''};
})())`);
const initial = JSON.parse(initialRaw);
console.log('CAMERA_FOCUS_INITIAL=' + JSON.stringify(initial));
if (!initial.found || !initial.active) throw new Error('camera preview tile not focusable');

await new Promise(r => setTimeout(r, 1250));
const live = JSON.parse(await evaluate(`JSON.stringify((function(){
  var button=document.querySelector('.launcher-camera-preview');
  var image=button&&button.querySelector('img[data-preview-url]');
  return {active:document.activeElement===button,src:image?image.src:''};
})())`));
console.log('CAMERA_FOCUS_AFTER_1250MS=' + JSON.stringify(live));
if (!/\/api\/stream\.mjpeg\?src=/.test(live.src)) throw new Error('focused camera did not switch to MJPEG');

await evaluate(`(function(){var button=document.querySelector('.launcher-camera-preview'); if(button)button.blur(); return true;})()`);
await new Promise(r => setTimeout(r, 120));
const afterBlur = JSON.parse(await evaluate(`JSON.stringify((function(){
  var button=document.querySelector('.launcher-camera-preview');
  var image=button&&button.querySelector('img[data-preview-url]');
  return {active:document.activeElement===button,src:image?image.src:'',snapshot:image?image.getAttribute('data-preview-url'):''};
})())`));
console.log('CAMERA_AFTER_BLUR=' + JSON.stringify(afterBlur));
if (/\/api\/stream\.mjpeg\?src=/.test(afterBlur.src)) throw new Error('MJPEG remained active after blur');
if (!/\/api\/frame\.jpeg\?src=/.test(afterBlur.src)) throw new Error('snapshot was not restored after blur');
console.log('FOCUSED_CAMERA_MJPEG_PROBE=PASS');
ws.close();
