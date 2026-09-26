const pages = await (await fetch('http://192.168.0.240:9998/json')).json();
const candidates = pages.filter(p => String(p.url || '').includes('/hu.szabi.launcher/'));
if (!candidates.length) throw new Error('No full launcher CDP page');

async function evaluate(page, expression) {
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  return await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { try { ws.close(); } catch {} reject(new Error('CDP timeout')); }, 8000);
    ws.onopen = () => ws.send(JSON.stringify({
      id: 1,
      method: 'Runtime.evaluate',
      params: { expression, returnByValue: true, awaitPromise: true }
    }));
    ws.onmessage = event => {
      const msg = JSON.parse(event.data);
      if (msg.id !== 1) return;
      clearTimeout(timer);
      try {
        if (msg.result && msg.result.exceptionDetails) throw new Error(JSON.stringify(msg.result.exceptionDetails));
        resolve(msg.result.result.value);
      } catch (error) { reject(error); }
      try { ws.close(); } catch {}
    };
    ws.onerror = () => { clearTimeout(timer); reject(new Error('CDP websocket error')); };
  });
}

let page = null;
for (const candidate of candidates) {
  try {
    const visible = await evaluate(candidate, 'JSON.stringify({hidden:document.hidden,activated:!!(window.PalmSystem&&window.PalmSystem.isActivated)})');
    const state = JSON.parse(visible);
    if (!state.hidden && state.activated) { page = candidate; break; }
  } catch {}
}
if (!page) throw new Error('NO_ACTIVE_FULL_LAUNCHER');

const selectedState = await evaluate(page, 'JSON.stringify({hidden:document.hidden,activated:!!(window.PalmSystem&&window.PalmSystem.isActivated),body:document.body.className})');
console.log('ACTIVE_LAUNCHER=' + selectedState);

const result = await evaluate(page, `
(async function () {
  var sleep = function (ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); };
  var root = document.getElementById('launcher-root') || document.body;
  var cover = document.getElementById('launcher-boot');
  if (!cover) throw new Error('launcher boot cover missing');

  // Input lock: make loading logically active without painting it.
  var previousHidden = cover.hidden;
  var previousDisplay = cover.style.getPropertyValue('display');
  var previousPriority = cover.style.getPropertyPriority('display');
  cover.hidden = false;
  cover.style.setProperty('display', 'none', 'important');

  var testButton = document.createElement('button');
  testButton.className = 'launcher-tile';
  testButton.type = 'button';
  testButton.style.position = 'fixed';
  testButton.style.left = '-10000px';
  testButton.style.top = '-10000px';
  var clicks = 0;
  testButton.addEventListener('click', function () { clicks += 1; });
  root.appendChild(testButton);
  testButton.focus();

  function key(type, code) {
    var event = new KeyboardEvent(type, { bubbles: true, cancelable: true });
    try { Object.defineProperty(event, 'keyCode', { value: code }); } catch {}
    try { Object.defineProperty(event, 'which', { value: code }); } catch {}
    document.dispatchEvent(event);
    return event.defaultPrevented;
  }
  var downPrevented = key('keydown', 13);
  var upPrevented = key('keyup', 13);
  await sleep(80);
  var inputBlocked = clicks === 0 && downPrevented && upPrevented;

  cover.hidden = previousHidden;
  if (previousDisplay) cover.style.setProperty('display', previousDisplay, previousPriority || '');
  else cover.style.removeProperty('display');

  // Camera focus promotion: snapshot -> MJPEG after 1 s -> snapshot on blur.
  var tile = document.querySelector('.launcher-camera-preview');
  var cameraResult = { available: !!tile };
  if (tile) {
    var image = tile.querySelector('img[data-preview-url]');
    cameraResult.imageAvailable = !!image;
    if (image) {
      var snapshotUrl = image.getAttribute('data-preview-url') || '';
      var before = image.src || '';
      tile.focus();
      await sleep(1250);
      var live = image.src || '';
      testButton.focus();
      await sleep(180);
      var afterBlur = image.src || '';
      cameraResult.snapshotUrl = snapshotUrl;
      cameraResult.before = before;
      cameraResult.live = live;
      cameraResult.afterBlur = afterBlur;
      cameraResult.promoted = live.indexOf('/api/stream.mjpeg') >= 0;
      cameraResult.restored = afterBlur.indexOf('/api/stream.mjpeg') < 0;
    }
  }

  testButton.remove();
  return JSON.stringify({
    input: { blocked: inputBlocked, clicks: clicks, keydownPrevented: downPrevented, keyupPrevented: upPrevented },
    camera: cameraResult
  });
})()
`);

console.log(result);
const parsed = JSON.parse(result);
if (!parsed.input.blocked) throw new Error('LOADING_INPUT_LOCK=FAIL');
if (!parsed.camera.available || !parsed.camera.imageAvailable) throw new Error('CAMERA_PREVIEW_TILE=FAIL');
if (!parsed.camera.promoted || !parsed.camera.restored) throw new Error('CAMERA_FOCUS_MJPEG=FAIL');
console.log('LOADING_INPUT_LOCK=PASS');
console.log('CAMERA_FOCUS_MJPEG=PASS');
