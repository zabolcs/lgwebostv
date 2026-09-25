set -eu
date -Iseconds
printf 'service='; systemctl is-active lgtv-control.service || true
printf 'python='; python3 --version
printf 'disk='; df -Pk /opt | tail -n 1
printf 'config-flags\n'
python3 - <<'PY'
import json
with open('/etc/lgtv-control/config.json', encoding='utf-8') as handle:
    cfg=json.load(handle)
for key in ('tv_host','public_base_url','input_hook_watchdog_enabled','remote_broker_enabled','remote_broker_mode'):
    print(f'{key}={cfg.get(key, "<missing>")}')
PY
printf 'installed-files\n'
ls -ld /opt/lgtv-control /opt/lgtv-control/static 2>/dev/null || true
sha256sum /opt/lgtv-control/server.py 2>/dev/null || true
curl -fsS http://127.0.0.1:8765/api/health
printf '\n'
