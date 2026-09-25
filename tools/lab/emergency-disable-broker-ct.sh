#!/bin/sh
set -eu
CONFIG=/etc/lgtv-control/config.json
python3 - <<'PY'
import json, os
path='/etc/lgtv-control/config.json'
with open(path, encoding='utf-8') as handle: config=json.load(handle)
config['remote_broker_enabled']=False
config['remote_broker_mode']='passive'
config['input_hook_watchdog_enabled']=False
temporary=path+'.emergency-new'
with open(temporary,'w',encoding='utf-8') as handle:
    json.dump(config,handle,ensure_ascii=False,indent=2,sort_keys=True); handle.write('\n')
os.chmod(temporary,0o640)
os.replace(temporary,path)
PY
chown root:lgtv-control "$CONFIG"
chmod 0640 "$CONFIG"
systemctl restart lgtv-control.service
sleep 5
systemctl is-active --quiet lgtv-control.service
python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen('http://127.0.0.1:8765/api/remote-mapper/state',timeout=15) as response:
    runtime=json.load(response)['runtime']
print(json.dumps(runtime,separators=(',',':')))
assert runtime['enabled'] is False and runtime['active'] is False
PY
