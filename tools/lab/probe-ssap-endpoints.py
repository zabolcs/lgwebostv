"""Read-only endpoint compatibility probe; never prints registration/key data."""
import sys,json,time
sys.path.insert(0,'/opt/lgtv-control')
from lg_ssap import SsapClient,POWER_URI,FOREGROUND_URI
c=SsapClient('192.168.0.240','/var/lib/lgtv-control/lg-ssap.json',timeout=4)
try:
    c.connect()
    for uri in (POWER_URI,FOREGROUND_URI,'ssap://system/getSystemInfo','ssap://com.webos.surfacemanager/getForegroundWindowInfo'):
        identifier,deadline=c._command('request',uri,{},4)
        r=c._await(identifier,deadline)
        print(json.dumps({'uri':uri,'type':r.get('type'),'error':str(r.get('error',''))[:180],'payload':{k:v for k,v in r.get('payload',{}).items() if k in ('returnValue','errorCode','errorText','state','appId','windowId','windows','foreground')}}),flush=True)
finally:c.close()
