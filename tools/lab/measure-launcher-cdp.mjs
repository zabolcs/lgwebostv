const pages=await (await fetch('http://192.168.0.240:9998/json',{signal:AbortSignal.timeout(1500)})).json();
const page=pages.find(p=>p.url.includes('/'+process.argv[2]+'/'));
if(!page)throw new Error('No renderer');
const ws=new WebSocket(page.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{ws.close();reject(new Error('timeout'));},2000);
  ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{returnByValue:true,expression:'JSON.stringify({navigation:performance.timing.navigationStart,start:window.__launcherStartAt,ready:window.__launcherReadyAt,paint:window.__launcherFirstPaintAt,resume:window.__launcherResumeAt,resumePaint:window.__launcherResumePaintAt,hidden:document.hidden,activated:window.PalmSystem&&window.PalmSystem.isActivated,launchParams:(window.PalmSystem&&window.PalmSystem.launchParams)||(window.webOSSystem&&window.webOSSystem.launchParams)||"",cacheBytes:(localStorage.getItem("hu.szabi.launcher.offline-state.v1")||"").length})'}}));
  ws.onmessage=e=>{const result=JSON.parse(e.data);if(result.id!==1)return;clearTimeout(timer);console.log(JSON.stringify({pageId:page.id,...JSON.parse(result.result.result.value)}));ws.close();resolve();};
  ws.onerror=reject;
});
