set -eu
python3 - <<'PY'
import json
with open('/etc/lgtv-control/config.json', encoding='utf-8') as handle: cfg=json.load(handle)
for key in ('input_hook_watchdog_enabled','remote_broker_enabled','remote_broker_mode'):
    print(f'{key}={cfg.get(key)}')
PY
systemctl is-active lgtv-control.service || true
journalctl -u lgtv-control.service -n 80 --no-pager
