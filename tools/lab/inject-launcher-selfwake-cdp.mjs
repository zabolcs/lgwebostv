const appId = process.argv[2] || 'hu.szabi.launcher.overlay';
const mode = process.argv[3] || 'install';

const pages = await (await fetch('http://192.168.0.240:9998/json', {
  signal: AbortSignal.timeout(1800)
})).json();
const page = pages.find((p) => p.url.includes('/' + appId + '/'));
if (!page) throw new Error('No renderer for ' + appId);

const installExpression = String.raw`(() => {
  try {
    if (window.__quickSelfWakeProbe && window.__quickSelfWakeProbe.installed) {
      return JSON.stringify({ok:true,reused:true,state:window.__quickSelfWakeProbe,hidden:document.hidden,activated:!!(window.PalmSystem&&window.PalmSystem.isActivated)});
    }
    if (typeof window.PalmServiceBridge !== 'function') {
      return JSON.stringify({ok:false,error:'PalmServiceBridge unavailable'});
    }
    var state = {
      installed: true,
      installedAt: Date.now(),
      armed: false,
      events: [],
      attempts: 0,
      activateCalls: 0,
      lastEvent: '',
      lastAttemptAt: 0,
      firstVisibleAt: 0,
      errors: []
    };
    window.__quickSelfWakeProbe = state;
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && !state.firstVisibleAt) state.firstVisibleAt = Date.now();
    }, true);
    var bridge = new window.PalmServiceBridge();
    window.__quickSelfWakeBridge = bridge;
    bridge.onservicecallback = function (message) {
      try {
        var p = JSON.parse(message || '{}');
        var label = String(p.processing || p.state || '');
        state.events.push({at:Date.now(),state:p.state||'',processing:p.processing||''});
        if (state.events.length > 16) state.events.shift();
        if (p.state === 'Active Standby' || p.state === 'Suspend' || p.state === 'Screen Off') state.armed = true;
        var wakeEdge = p.processing === 'Prepare Resume' || p.processing === 'LastInput Ready' ||
          p.processing === 'Screen On' || p.state === 'Active';
        if (state.armed && wakeEdge && document.hidden) {
          state.attempts += 1;
          state.lastEvent = label;
          state.lastAttemptAt = Date.now();
          var system = window.PalmSystem || window.webOSSystem;
          if (system && typeof system.activate === 'function') {
            system.activate();
            state.activateCalls += 1;
          } else {
            state.errors.push('activate unavailable at ' + label);
          }
        }
      } catch (e) {
        state.errors.push(String(e && e.message || e));
      }
    };
    bridge.call('luna://com.webos.service.tvpower/power/getPowerState', JSON.stringify({subscribe:true}));
    return JSON.stringify({ok:true,reused:false,state:state,hidden:document.hidden,activated:!!(window.PalmSystem&&window.PalmSystem.isActivated)});
  } catch (e) {
    return JSON.stringify({ok:false,error:String(e && e.message || e)});
  }
})()`;

const statusExpression = String.raw`JSON.stringify({
  ok:true,
  state:window.__quickSelfWakeProbe||null,
  hidden:document.hidden,
  activated:!!(window.PalmSystem&&window.PalmSystem.isActivated),
  ready:window.__launcherReadyAt||0,
  resume:window.__launcherResumeAt||0,
  resumePaint:window.__launcherResumePaintAt||0
})`;

const releaseExpression = String.raw`(() => {
  try {
    var system = window.PalmSystem || window.webOSSystem;
    if (!system || typeof system.keepAlive !== 'function') {
      return JSON.stringify({ok:false,error:'keepAlive unavailable'});
    }
    system.keepAlive(false);
    return JSON.stringify({ok:true,hidden:document.hidden,activated:!!system.isActivated});
  } catch (e) {
    return JSON.stringify({ok:false,error:String(e && e.message || e)});
  }
})()`;

const expression = mode === 'status' ? statusExpression :
  mode === 'release' ? releaseExpression : installExpression;
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  const timer = setTimeout(() => { try { ws.close(); } catch {} reject(new Error('CDP timeout')); }, 3000);
  ws.onopen = () => ws.send(JSON.stringify({
    id: 1,
    method: 'Runtime.evaluate',
    params: { returnByValue: true, expression }
  }));
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.id !== 1) return;
    clearTimeout(timer);
    if (message.error) { reject(new Error(JSON.stringify(message.error))); return; }
    const value = message.result && message.result.result && message.result.result.value;
    console.log(value || JSON.stringify({ok:false,error:'no result'}));
    ws.close();
    resolve();
  };
  ws.onerror = reject;
});
