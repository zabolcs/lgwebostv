set -eu
sleep 5
python3 - <<'PY'
import json, urllib.request
base='http://127.0.0.1:8765'
with urllib.request.urlopen(base+'/api/remote-mapper/state', timeout=15) as response:
    before=json.load(response)['runtime']
print('before='+json.dumps(before,separators=(',',':')))
assert before['active'] is True and before['enabled'] is True and before['nativeHookLoaded'] is False
body=json.dumps({'keyCode':398,'action':'cameraOpen','cameraId':'kapu'}).encode()
request=urllib.request.Request(base+'/api/remote-mapper/bind', data=body, method='POST', headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request, timeout=40) as response:
    data=json.load(response)
summary={'changed':data.get('changed'),'runtime':data.get('runtime'),'runtimeSyncError':data.get('runtimeSyncError')}
print('resync='+json.dumps(summary,separators=(',',':')))
assert data.get('changed') is False
assert not data.get('runtimeSyncError')
assert data['runtime']['active'] is True and data['runtime']['mode']=='grab'
PY
sleep 8
python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8765/api/remote-mapper/state', timeout=15) as response:
    runtime=json.load(response)['runtime']
print('after='+json.dumps(runtime,separators=(',',':')))
assert runtime['active'] is True and runtime['enabled'] is True and runtime['nativeHookLoaded'] is False
PY
