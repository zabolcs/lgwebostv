"""Bounded warm-OS cold/retained comparisons, using native compositor surfaces."""
import json
from pathlib import Path
import shlex
import sys
import time
import urllib.request
import subprocess
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
sys.path.insert(0,str(ROOT/'lgtv-remote-broker/remote-control'))
import remote
import server
FULL='hu.szabi.launcher';PROBE=FULL+'.startupprobe'
mode=sys.argv[1]
assert mode in ('cold','retained','preload')
apps=sys.argv[2:] or [FULL,PROBE,FULL,PROBE]
assert all(app in (FULL,PROBE) for app in apps)
pve=remote.connect();tv=remote.connect_tv(pve)
def call(uri,payload,timeout=5000):
    rc,out,err=remote.run(tv,'pve','luna-send -t 1 -f -w '+str(timeout)+' luna://'+uri+' '+shlex.quote(json.dumps(payload)),timeout=timeout/1000+2)
    value=server.parse_luna_response((out+err).decode(errors='replace'))
    if rc or value.get('returnValue') is False:raise RuntimeError(value)
    return value
def timing(app):
    try:
        result=subprocess.run(['node',str(ROOT/'measure-launcher-cdp.mjs'),app],capture_output=True,text=True,timeout=5)
        return json.loads(result.stdout) if result.returncode==0 else {'diagnosticError':'CDPUnavailable'}
    except Exception as e:return {'diagnosticError':type(e).__name__}
def running(app):
    value=call('com.webos.service.webappmanager/listRunningApps',{'includeSysApps':False})
    return '"'+app+'"' in json.dumps(value)
def page_identity(app):
    try:
        with urllib.request.urlopen('http://192.168.0.240:9998/json',timeout=1) as r:pages=json.load(r)
        return {'pageId':next(p['id'] for p in pages if '/'+app+'/' in p.get('url',''))}
    except Exception as error:return {'diagnosticError':type(error).__name__}
def launch(app,params=None,**extra):
    return call('com.webos.applicationManager/launch',{'id':app,'noSplash':True,'params':params or {'source':'startup-ab','controlOrigin':'http://192.168.0.223:8765'},**extra})
def wait_surface(app,deadline):
    while time.monotonic()<deadline:
        windows=call('com.webos.surfacemanager/getForegroundWindowInfo',{},1000)
        if any(w.get('appId')==app for w in windows.get('windows',[])):return time.monotonic()
        time.sleep(.1)
    raise RuntimeError('Target surface did not appear')
try:
    for app in apps:
        if mode=='retained':
            launch(app);wait_surface(app,time.monotonic()+20);time.sleep(2)
        launch('youtube.leanback.v4');wait_surface('youtube.leanback.v4',time.monotonic()+20);time.sleep(2)
        if mode in ('cold','preload'):
            if running(app):call('com.webos.service.applicationmanager/closeByAppId',{'id':app})
            time.sleep(.5)
            assert not running(app),'Target unexpectedly preloaded'
        if mode=='preload':
            launch(app,{'source':'preload','controlOrigin':'http://192.168.0.223:8765'},preload='full',keepAlive=True)
            time.sleep(4)
            windows=call('com.webos.surfacemanager/getForegroundWindowInfo',{},1000)
            assert not any(w.get('appId')==app for w in windows.get('windows',[])), 'Preload became visible'
        before=page_identity(app) if mode!='cold' else None
        if mode!='cold':assert running(app),'Not retained; invalid warm comparison'
        began=time.monotonic();ack=launch(app);ack_time=time.monotonic()-began
        shown=wait_surface(app,began+20)-began
        time.sleep(.6)
        print(json.dumps({'mode':mode,'app':app,'ackSeconds':round(ack_time,3),'surfaceSeconds':round(shown,3),'before':before,'after':timing(app)}),flush=True)
finally:
    try:launch(FULL)
    finally:tv.close();pve.close()
