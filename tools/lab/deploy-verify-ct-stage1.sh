set -eu
systemctl is-active lgtv-control.service
python3 - <<'PY'
import json, urllib.request
for path in ('/api/health','/api/remote-mapper/state'):
    with urllib.request.urlopen('http://127.0.0.1:8765'+path, timeout=15) as response:
        data=json.load(response)
    if path.endswith('/state'):
        print(json.dumps({'ok':data.get('ok'),'runtime':data.get('runtime'),'bindingCount':len(data.get('bindings',{})),'appCount':len(data.get('apps',[]))}, ensure_ascii=False, separators=(',',':')))
    else:
        print(json.dumps(data, separators=(',',':')))
PY
journalctl -u lgtv-control.service -n 20 --no-pager
