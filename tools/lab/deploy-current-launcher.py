"""Build and deploy the current launcher suite to the TV with rollback."""
from pathlib import Path
import importlib.util
import json
import shlex
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/lab/checkpoint-original/LGTV-checkpoint-2026-09-19/tools"))
import remote

spec = importlib.util.spec_from_file_location("builder", ROOT / "scripts/build-all.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

SLUGS = ("launcher", "launcher-quick", "launcher-overlay")

def checked(tv, command, timeout=60):
    rc, out, err = remote.run(tv, "pve", command, timeout=timeout)
    if rc:
        raise RuntimeError((out + err).decode(errors="replace"))
    return (out + err).decode(errors="replace")

packages = [builder.build(slug, builder.APPS[slug]) for slug in SLUGS]
pve = remote.connect()
tv = remote.connect_tv(pve)
try:
    backup = checked(tv, "mktemp -d /var/lib/webosbrew/launcher-current-backup.XXXXXX").strip()
    print("rollback=" + backup, flush=True)
    checked(tv, "tar -czf " + shlex.quote(backup + "/apps.tgz") + " -C /media/developer/apps/usr/palm/applications hu.szabi.launcher hu.szabi.launcher.quick hu.szabi.launcher.overlay")
    stage = checked(tv, "mktemp -d /tmp/launcher-current.XXXXXX").strip()
    with tv.open_sftp() as sftp:
        sftp.put(str(ROOT / "scripts/install-local-on-tv.sh"), stage + "/install.sh")
        for pkg, _ in packages:
            sftp.put(str(pkg), stage + "/" + pkg.name)
    for pkg, digest in packages:
        print(checked(tv, "sh " + shlex.quote(stage + "/install.sh") + " " + shlex.quote(stage + "/" + pkg.name) + " " + digest), flush=True)
        time.sleep(2)
    for slug in SLUGS:
        app = builder.APPS[slug]["id"]
        manifest = json.loads(checked(tv, "cat /media/developer/apps/usr/palm/applications/" + app + "/appinfo.json"))
        assert manifest["version"] == "0.3.15", (app, manifest["version"])
    runtime = checked(tv, "cat /media/developer/apps/usr/palm/applications/hu.szabi.launcher/launcher-runtime.js")
    assert "directPresetMjpeg" in runtime
    assert "launcher-loading-active" in runtime
    print("DEPLOY_CURRENT_LAUNCHER=PASS", flush=True)
finally:
    tv.close()
    pve.close()
