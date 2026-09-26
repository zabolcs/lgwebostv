from __future__ import annotations
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import time

KEY_SOURCE = Path("/media/lgtv/id_rsa")
CT = "192.168.0.223"
TV = "192.168.0.240"


def run(args: list[str], *, check: bool = True, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          check=check, timeout=timeout)


def ssh(base: list[str], host: str, command: str, *, check: bool = True) -> str:
    return run(["ssh", "-T", *base, f"root@{host}", command], check=check).stdout.strip()


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    key = root / "id_rsa"
    shutil.copy2(KEY_SOURCE, key)
    key.chmod(0o600)

    known_ct = root / "known-ct"
    known_tv = root / "known-tv"
    known_ct.write_text(run(["ssh-keyscan", "-T", "3", CT]).stdout)
    known_tv.write_text(run(["ssh-keyscan", "-T", "3", TV]).stdout)

    def base(known: Path) -> list[str]:
        return ["-i", str(key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
                "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}"]

    ct_base = base(known_ct)
    tv_base = base(known_tv)

    backup = "/var/backups/lgtv-control/config.before-long-back-inputhook.json"
    ssh(ct_base, CT,
        "mkdir -p /var/backups/lgtv-control && "
        f"cp -p /etc/lgtv-control/config.json {backup}")

    raw = ssh(ct_base, CT, "cat /etc/lgtv-control/config.json")
    config = json.loads(raw)
    config["input_hook_watchdog_enabled"] = True
    payload = json.dumps(config, ensure_ascii=False, indent=2) + "\n"

    local_cfg = root / "config.json"
    local_cfg.write_text(payload, encoding="utf-8")
    run(["scp", "-q", *ct_base, str(local_cfg), f"root@{CT}:/tmp/lgtv-control-config.json"])
    ssh(ct_base, CT,
        "cp /tmp/lgtv-control-config.json /etc/lgtv-control/config.json && "
        "systemctl restart lgtv-control.service && "
        "systemctl is-active --quiet lgtv-control.service")

    attached = False
    for _ in range(20):
        probe = ssh(tv_base, TV,
                    "p=$(pidof lginput2 2>/dev/null || true); "
                    "[ -n \"$p\" ] && grep -q libphp /proc/$p/maps 2>/dev/null",
                    check=False)
        rc = run(["ssh", "-T", *tv_base, f"root@{TV}",
                  "p=$(pidof lginput2 2>/dev/null || true); "
                  "[ -n \"$p\" ] && grep -q libphp /proc/$p/maps 2>/dev/null"],
                 check=False).returncode
        if rc == 0:
            attached = True
            break
        time.sleep(1)

    if not attached:
        print(ssh(tv_base, TV,
                  "echo '--- watchdog ---'; "
                  "ls -l /var/lib/webosbrew/inputhook-watchdog 2>/dev/null || true; "
                  "echo '--- repair ---'; "
                  "tail -n 80 /tmp/hu.szabi.inputhook-repair-detail.log 2>/dev/null || true; "
                  "echo '--- watchdog log ---'; "
                  "tail -n 80 /tmp/hu.szabi.inputhook-watchdog.log 2>/dev/null || true",
                  check=False), flush=True)
        ssh(ct_base, CT,
            f"cp -p {backup} /etc/lgtv-control/config.json; "
            "systemctl restart lgtv-control.service", check=False)
        raise SystemExit("Input Hook attach failed; config rolled back")

    result = ssh(tv_base, TV,
                 "p=$(pidof lginput2); "
                 "echo LGINPUT2_PID=$p; "
                 "grep -q libphp /proc/$p/maps; echo HOOK_ATTACHED=yes; "
                 "echo WATCHDOG_ENABLED=$(test -f /var/lib/webosbrew/inputhook-watchdog/enabled && echo yes || echo no); "
                 "echo WATCHDOG_INIT=$(test -f /var/lib/webosbrew/init.d/inputhook-watchdog && echo yes || echo no); "
                 "grep -q launcherHome /home/root/.config/lginputhook/keybinds.json; "
                 "echo LAUNCHER_HOME_BINDING=yes")
    print(result, flush=True)
