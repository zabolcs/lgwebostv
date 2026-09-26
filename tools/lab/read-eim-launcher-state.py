"""Read-only EIM metadata diagnostics for the launcher input."""
from pathlib import Path
import subprocess
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    known = Path(tmp) / "known_hosts"
    key = Path("/media/lgtv/id_rsa")
    scan = subprocess.run(
        ["ssh-keyscan", "-T", "3", "192.168.0.240"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True
    )
    known.write_text(scan.stdout)
    base = ["-i", str(key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=3",
            "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile="+str(known)]
    ssh = ["ssh", "-T"] + base + ["root@192.168.0.240"]
    command = """echo ===GET===;
luna-send -n 1 -f -w 2000 luna://com.webos.service.eim/getTotalDeviceList '{}';
echo ===FROZEN_DB===;
cat /var/lib/webosbrew/launcher-eim/frozen-view/eim_device_db.json 2>/dev/null || true;
echo ===RUNTIME_DB===;
cat /var/lib/eim/eim_device_db.json 2>/dev/null || true;
echo ===LAST===;
cat /var/lib/webosbrew/launcher-eim/frozen-view/lastinput 2>/dev/null || true"""
    out = subprocess.run(ssh + [command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=True)
    print(out.stdout)
    extra = [
        ("APPINFO", "luna-send -n 1 -f -w 2000 luna://com.webos.service.applicationmanager/getAppInfo '{\"id\":\"hu.szabi.launcher\"}' 2>&1 || true"),
        ("BOOT", "grep -n -E 'firstApp|first app|splash|hu.szabi.launcher|foregroundAppId' /var/log/bootd.log 2>/dev/null | tail -180 || true"),
        ("MESSAGES", "grep -n -E 'splash|hu.szabi.launcher' /var/log/messages 2>/dev/null | tail -120 || true"),
    ]
    for label, cmd in extra:
        print("===" + label + "===")
        res = subprocess.run(ssh + [cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        print(res.stdout)
