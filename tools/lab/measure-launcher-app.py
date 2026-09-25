"""Controlled cold renderer launch on an already booted TV (not an OS reboot)."""
import json
from pathlib import Path
import shlex
import sys
import time

ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
sys.path.insert(0,str(ROOT/'lgtv-remote-broker/remote-control'))
import remote
import server
pve=remote.connect()
tv=remote.connect_tv(pve)
def call(uri,payload):
    rc,out,err=remote.run(tv,'pve','luna-send -t 1 -f -w 2000 luna://'+uri+' '+shlex.quote(json.dumps(payload)),timeout=5)
    if rc: raise RuntimeError(rc)
    result=server.parse_luna_response((out+err).decode())
    if result.get('returnValue') is False: raise RuntimeError(result)
    return result
try:
    print('base='+json.dumps(call('com.webos.applicationManager/launch',{'id':'youtube.leanback.v4'})),flush=True)
    time.sleep(3)
    print('close='+json.dumps(call('com.webos.service.applicationmanager/closeByAppId',{'id':'hu.szabi.launcher'})),flush=True)
    time.sleep(1)
    # Verify it was really reclaimed; the persistent preload worker may run.
    running=call('com.webos.service.webappmanager/listRunningApps',{'includeSysApps':False})
    assert 'hu.szabi.launcher"' not in json.dumps(running),running
    start=time.monotonic()
    print('launch='+json.dumps(call('com.webos.applicationManager/launch',{'id':'hu.szabi.launcher','noSplash':True,'params':{'source':'startup-measure','controlOrigin':'http://192.168.0.223:8765'}})),flush=True)
    print('ackSeconds='+str(round(time.monotonic()-start,3)),flush=True)
    last=None
    first=None
    while time.monotonic()-start<20:
        windows=call('com.webos.surfacemanager/getForegroundWindowInfo',{})
        now=round(time.monotonic()-start,3)
        if windows!=last:
            print(json.dumps({'seconds':now,'windows':windows}),flush=True)
            last=windows
        if 'hu.szabi.launcher"' in json.dumps(windows):
            first=now; break
        time.sleep(.15)
    print('firstNativeSurfaceSeconds='+str(first),flush=True)
finally:
    tv.close();pve.close()
