"""Build and safely deploy the current Camera Viewer package to the TV."""
from pathlib import Path
import importlib.util
import json
import shlex
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]

spec = importlib.util.spec_from_file_location("builder", ROOT / "scripts/build-all.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

pkg, digest = builder.build("camera-viewer", builder.APPS["camera-viewer"])
expected = json.loads((ROOT / "apps/camera-viewer/appinfo.json").read_text(encoding="utf-8"))["version"]

def run(args, timeout=60):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout, check=True)
    return result.stdout

with tempfile.TemporaryDirectory() as tmp:
    known = Path(tmp) / "known_hosts"
    key = Path("/media/lgtv/id_rsa")
    scan = subprocess.run(["ssh-keyscan","-T","3","192.168.0.240"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True)
    known.write_text(scan.stdout)
    base = ["-i", str(key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=3", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile="+str(known)]
    ssh = ["ssh","-T"] + base + ["root@192.168.0.240"]
    scp = ["scp","-q"] + base

    def checked(command, timeout=60):
        return run(ssh + [command], timeout=timeout)

    running = checked("luna-send -n 1 -f -w 1500 luna://com.webos.service.webappmanager/listRunningApps '{\"includeSysApps\":false}' 2>&1 || true")
    if "hu.szabi.cameraviewer" in running:
        print(checked("luna-send -n 1 -f -w 3000 luna://com.webos.service.applicationmanager/closeByAppId '{\"id\":\"hu.szabi.cameraviewer\"}' 2>&1 || true"), flush=True)
        for _ in range(20):
            time.sleep(0.25)
            running = checked("luna-send -n 1 -f -w 1500 luna://com.webos.service.webappmanager/listRunningApps '{\"includeSysApps\":false}' 2>&1 || true")
            if "hu.szabi.cameraviewer" not in running:
                break
        else:
            raise RuntimeError("Camera Viewer did not stop")

    backup = checked("mktemp -d /var/lib/webosbrew/camera-viewer-current-backup.XXXXXX").strip()
    print("rollback=" + backup, flush=True)
    checked("tar -czf " + shlex.quote(backup + "/app.tgz") + " -C /media/developer/apps/usr/palm/applications hu.szabi.cameraviewer")
    stage = checked("mktemp -d /tmp/camera-viewer-current.XXXXXX").strip()
    run(scp + [str(ROOT / "scripts/install-local-on-tv.sh"), "root@192.168.0.240:" + stage + "/install.sh"])
    run(scp + [str(pkg), "root@192.168.0.240:" + stage + "/" + pkg.name])
    print(checked("sh " + shlex.quote(stage + "/install.sh") + " " + shlex.quote(stage + "/" + pkg.name) + " " + digest), flush=True)

    manifest = json.loads(checked("cat /media/developer/apps/usr/palm/applications/hu.szabi.cameraviewer/appinfo.json"))
    assert manifest["version"] == expected, (manifest["version"], expected)
    runtime = checked("cat /media/developer/apps/usr/palm/applications/hu.szabi.cameraviewer/app.js")
    assert "DEFAULT_PREVIEW_INTERVAL_SECONDS = 60" in runtime
    assert "GRID_LIVE_FOCUS_DELAY_MS = 600" in runtime
    assert "GRID_LIVE_RETRY_DELAY_MS = 1800" in runtime
    assert "index * 1000" in runtime
    print("CAMERA_VIEWER_CURRENT_DEPLOY=PASS version=" + expected, flush=True)
