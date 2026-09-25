set -eu
python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8765/api/remote-mapper/state', timeout=15) as response:
    data=json.load(response)
for code, binding in sorted(data.get('bindings',{}).items(), key=lambda item:int(item[0])):
    safe={'code':int(code),'action':binding.get('action')}
    for field in ('id','keycode','managedBy','bindingType','presetId','cameraId','appId'):
        if field in binding: safe[field]=binding[field]
    if binding.get('bindingType')=='webhook': safe['webhook']='configured'
    print(json.dumps(safe, ensure_ascii=False, separators=(',',':')))
PY
