const pages=await (await fetch('http://192.168.0.240:9998/json',{signal:AbortSignal.timeout(1500)})).json();
const matches=pages.filter(p=>p.url.includes('/'+process.argv[2]+'/'));
if(!matches.length)throw new Error('No renderer');

const expression='JSON.stringify({navigation:performance.timing.navigationStart,start:window.__launcherStartAt,ready:window.__launcherReadyAt,paint:window.__launcherFirstPaintAt,resume:window.__launcherResumeAt,resumePaint:window.__launcherResumePaintAt,hidden:document.hidden,activated:window.PalmSystem&&window.PalmSystem.isActivated,launchParams:(window.PalmSystem&&window.PalmSystem.launchParams)||(window.webOSSystem&&window.webOSSystem.launchParams)||"",cacheBytes:(localStorage.getItem("hu.szabi.launcher.offline-state.v1")||"").length})';

async function inspect(page){
  const ws=new WebSocket(page.webSocketDebuggerUrl);
  try{
    const value=await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{try{ws.close();}catch{};reject(new Error('timeout'));},1200);
      ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{returnByValue:true,expression}}));
      ws.onmessage=e=>{
        const result=JSON.parse(e.data);
        if(result.id!==1)return;
        clearTimeout(timer);
        try{
          const raw=result?.result?.result?.value;
          if(typeof raw!=='string')throw new Error('missing result');
          resolve(JSON.parse(raw));
        }catch(err){reject(err);}
        finally{try{ws.close();}catch{}}
      };
      ws.onerror=()=>{clearTimeout(timer);reject(new Error('websocket error'));};
    });
    return {pageId:page.id,...value};
  }catch{
    try{ws.close();}catch{}
    return null;
  }
}

const inspected=(await Promise.all(matches.map(inspect))).filter(Boolean);
if(!inspected.length)throw new Error('No responsive renderer');
inspected.sort((a,b)=>(Number(b.navigation)||0)-(Number(a.navigation)||0));
console.log(JSON.stringify(inspected[0]));
