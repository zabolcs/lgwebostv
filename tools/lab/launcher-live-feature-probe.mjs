async function launcherPages() {
  const pages = await (await fetch('http://192.168.0.240:9998/json')).json();
  return pages.filter(p => String(p.url || '').includes('/hu.szabi.launcher/'));
}

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

async function activeLauncherPage() {
  for (const candidate of await launcherPages()) {
    try {
      const visible = await evaluate(candidate, 'JSON.stringify({hidden:document.hidden,activated:!!(window.PalmSystem&&window.PalmSystem.isActivated)})');
      const state = JSON.parse(visible);
      if (!state.hidden && state.activated) return candidate;
    } catch {}
  }
  return null;
}

let page = await activeLauncherPage();
if (!page) {
  const response = await fetch('http://192.168.0.223:8765/api/launcher/launch', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({type:'app', targetId:'hu.szabi.launcher', label:'Launcher probe'})
  });
  if (!response.ok) throw new Error('LAUNCHER_FOREGROUND_REQUEST=' + response.status);
  for (let i = 0; i < 24 && !page; i += 1) {
    await new Promise(resolve => setTimeout(resolve, 250));
    page = await activeLauncherPage();
  }
}
if (!page) throw new Error('NO_ACTIVE_FULL_LAUNCHER');

const selectedState = await evaluate(page, 'JSON.stringify({hidden:document.hidden,activated:!!(window.PalmSystem&&window.PalmSystem.isActivated),body:document.body.className})');
console.log('ACTIVE_LAUNCHER=' + selectedState);

const inventory = await evaluate(page, `JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.launcher-camera-preview'), function(tile) {
  var image = tile.querySelector('img[data-preview-url]');
  var snapshot = image ? String(image.getAttribute('data-preview-url') || '') : '';
  var mjpeg = '';
  try {
    var parsed = new URL(snapshot);
    if (parsed.pathname === '/api/frame.jpeg') {
      parsed.pathname = '/api/stream.mjpeg';
      mjpeg = parsed.protocol + '//' + parsed.host + parsed.pathname + parsed.search;
    }
  } catch (ignore) {}
  return {
    itemId: tile.getAttribute('data-item-id') || '',
    targetId: tile.getAttribute('data-target') || '',
    label: (tile.getAttribute('aria-label') || tile.textContent || '').trim(),
    snapshot: snapshot,
    mjpeg: mjpeg,
    current: image ? image.src : ''
  };
}))`);
console.log('CAMERA_INVENTORY=' + inventory);

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
