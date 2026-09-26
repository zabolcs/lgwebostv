from pathlib import Path
import subprocess, tempfile, time

ROOT = Path(__file__).resolve().parents[2]
TV = "192.168.0.240"
KEY = Path("/media/lgtv/id_rsa")
GUARD = ROOT / "tools/generated-tv-scripts/guard.sh"

subprocess.run(["sh","-n",str(GUARD)], check=True)

def run(args, timeout=30):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, check=True)
    return p.stdout.strip()

with tempfile.TemporaryDirectory() as tmp:
    known = Path(tmp) / "known_hosts"
    scan = subprocess.run(["ssh-keyscan","-T","3",TV], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True)
    known.write_text(scan.stdout)
    base = ["-i",str(KEY),"-o","BatchMode=yes","-o","ConnectTimeout=3","-o","StrictHostKeyChecking=yes","-o","UserKnownHostsFile="+str(known)]
    ssh = ["ssh","-T"] + base + ["root@"+TV]
    scp = ["scp","-q"] + base

    before = run(ssh + ["luna-send -t 1 -f -w 1200 luna://com.webos.applicationManager/getForegroundAppInfo '{}' || true"])
    print("FOREGROUND_BEFORE="+before, flush=True)

    backup = run(ssh + ["mktemp -d /var/lib/webosbrew/launcher-guard-backup.XXXXXX"])
    print("ROLLBACK="+backup, flush=True)
    run(ssh + [f"cp -p /var/lib/webosbrew/launcher-home/guard.sh {backup}/guard.sh"])
    run(scp + [str(GUARD), "root@"+TV+":/tmp/hu.szabi.launcher.guard.new"])
    run(ssh + ["touch /tmp/hu.szabi.launcher.install-handoff; cp /tmp/hu.szabi.launcher.guard.new /var/lib/webosbrew/launcher-home/guard.sh; chmod 755 /var/lib/webosbrew/launcher-home/guard.sh"])

    pid = run(ssh + ["cat /tmp/hu.szabi.launcher-home.pid 2>/dev/null || true"])
    if pid.isdigit():
        subprocess.run(ssh + [f"kill -TERM {pid} 2>/dev/null || true"], check=False)
    run(ssh + ["i=0; while [ -e /tmp/hu.szabi.launcher-home.pid ] && [ $i -lt 40 ]; do /bin/usleep 100000; i=$((i+1)); done; nohup /var/lib/webosbrew/launcher-home/guard.sh </dev/null >>/tmp/hu.szabi.launcher-home.log 2>&1 &"])

    ok = False
    for _ in range(50):
        result = run(ssh + ["grep -q 'guard v0.5.4 started' /tmp/hu.szabi.launcher-wake.log 2>/dev/null && ! test -e /tmp/hu.szabi.launcher.install-handoff && echo PASS || true"])
        if result.endswith("PASS"):
            ok = True
            break
        time.sleep(0.1)
    if not ok:
        raise SystemExit("guard handoff did not complete")

    after = run(ssh + ["luna-send -t 1 -f -w 1200 luna://com.webos.applicationManager/getForegroundAppInfo '{}' || true"])
    print("FOREGROUND_AFTER="+after, flush=True)
    print("GUARD_DEPLOY=PASS", flush=True)
