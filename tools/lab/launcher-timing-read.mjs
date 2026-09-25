const pages = await (await fetch('http://192.168.0.240:9998/json')).json();
for (const page of pages.filter(p => p.url.includes('/hu.szabi.launcher/'))) {
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { ws.close(); reject(new Error('timeout')); }, 5000);
    ws.onopen = () => ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{returnByValue:true,expression:process.argv[2] || `JSON.stringify({now:Date.now(),hidden:document.hidden,activated:window.PalmSystem&&window.PalmSystem.isActivated,ready:window.__launcherReadyAt,paint:window.__launcherFirstPaintAt,resume:window.__launcherResumeAt,resumePaint:window.__launcherResumePaintAt,timing:performance.timing.toJSON(),entries:performance.getEntriesByType('resource').map(function(e){return {name:e.name,duration:e.duration,start:e.startTime}}),scripts:Array.from(document.scripts).map(function(s){return s.src}),cacheBytes:(localStorage.getItem('hu.szabi.launcher.offline-state.v1')||'').length})`}}));
    ws.onmessage = event => { const result=JSON.parse(event.data); if(result.id!==1)return; console.log(JSON.stringify(result));clearTimeout(timeout);ws.close();resolve(); };
    ws.onerror = reject;
  });
}
