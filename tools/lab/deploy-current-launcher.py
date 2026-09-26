"""Build and deploy the current launcher suite to the TV with rollback."""
from pathlib import Path
import importlib.util
import json
import shlex
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("builder", ROOT / "scripts/build-all.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

SLUGS = ("launcher", "launcher-quick", "launcher-overlay")

def run(args, timeout=60):
    completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=True, text=True)
    return completed.stdout

packages = [builder.build(slug, builder.APPS[slug]) for slug in SLUGS]
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
    backup = checked("mktemp -d /var/lib/webosbrew/launcher-current-backup.XXXXXX").strip()
    print("rollback=" + backup, flush=True)
    checked("tar -czf " + shlex.quote(backup + "/apps.tgz") + " -C /media/developer/apps/usr/palm/applications hu.szabi.launcher hu.szabi.launcher.quick hu.szabi.launcher.overlay")
    stage = checked("mktemp -d /tmp/launcher-current.XXXXXX").strip()
    run(scp + [str(ROOT / "scripts/install-local-on-tv.sh"), "root@192.168.0.240:" + stage + "/install.sh"])
    for pkg, _ in packages:
        run(scp + [str(pkg), "root@192.168.0.240:" + stage + "/" + pkg.name])
    for pkg, digest in packages:
        print(checked("sh " + shlex.quote(stage + "/install.sh") + " " + shlex.quote(stage + "/" + pkg.name) + " " + digest), flush=True)
        time.sleep(2)
    for slug in SLUGS:
        app = builder.APPS[slug]["id"]
        manifest = json.loads(checked("cat /media/developer/apps/usr/palm/applications/" + app + "/appinfo.json"))
        assert manifest["version"] == "0.3.15", (app, manifest["version"])
    runtime = checked("cat /media/developer/apps/usr/palm/applications/hu.szabi.launcher/launcher-runtime.js")
    assert "directPresetMjpeg" in runtime
    assert "launcher-loading-active" in runtime
    print("DEPLOY_CURRENT_LAUNCHER=PASS", flush=True)
