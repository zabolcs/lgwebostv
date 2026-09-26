"""Deploy NAS control files to CT125 through the Proxmox host with rollback."""
from pathlib import Path
import hashlib
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "remote-control"
PVE = "192.168.0.120"
CTID = "125"
KEY = Path("/media/lgtv/id_rsa")

FILES = (
    "server.py","lg_ssap.py","ssap_pairing.py","launcher_early.py",
    "static/index.html","static/ssap-control.js","static/power-control.js",
    "static/launcher-admin.js","static/connections-ui.js","static/dashboard-control.js",
    "lgtv-launcher-early.service",
)
selected = tuple(sys.argv[1:]) or FILES
assert set(selected) <= set(FILES)

def run(args, timeout=60):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=timeout, check=True)
    return result.stdout.strip()

with tempfile.TemporaryDirectory() as tmp:
    known = Path(tmp) / "known_hosts"
    scan = subprocess.run(["ssh-keyscan","-T","3",PVE], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, check=True)
    known.write_text(scan.stdout)
    base = ["-i",str(KEY),"-o","BatchMode=yes","-o","ConnectTimeout=4",
            "-o","StrictHostKeyChecking=yes","-o","UserKnownHostsFile="+str(known)]
    ssh = ["ssh","-T"] + base + ["root@"+PVE]
    scp = ["scp","-q"] + base

    def pve(command, timeout=60):
        return run(ssh + [command], timeout)

    stage = pve("mktemp -d /tmp/lgtv-native-deploy.XXXXXX")
    backup = pve("pct exec "+CTID+" -- sh -c " + shlex.quote(
        "mkdir -p /var/backups/lgtv-control && mktemp -d /var/backups/lgtv-control/native-launcher.XXXXXX"))
    print("Rollback: "+backup, flush=True)

    for relative in selected:
        name = relative.replace("/","_")
        local = SOURCE / relative
        remote_stage = stage + "/" + name
        run(scp + [str(local), "root@"+PVE+":"+remote_stage])
        temporary = "/tmp/" + stage.rsplit("/",1)[-1] + "-" + name
        pve("pct push "+CTID+" "+shlex.quote(remote_stage)+" "+shlex.quote(temporary))
        destination = ("/etc/systemd/system/"+relative if relative.endswith(".service")
                       else "/opt/lgtv-control/"+relative)
        inner = (
            "mkdir -p "+shlex.quote(str(Path(destination).parent))+"; "
            "if [ -f "+shlex.quote(destination)+" ]; then cp -p "+shlex.quote(destination)+" "+shlex.quote(backup+"/"+name)+"; fi; "
            + (("python3 -m py_compile "+shlex.quote(temporary)+"; ") if relative.endswith(".py") else "")
            + "install -o root -g root -m 644 "+shlex.quote(temporary)+" "+shlex.quote(destination)+"; "
            + "sha256sum "+shlex.quote(destination)
        )
        digest = pve("pct exec "+CTID+" -- sh -c "+shlex.quote(inner)).split()[-2]
        assert digest == hashlib.sha256(local.read_bytes()).hexdigest(), relative

    pve("pct exec "+CTID+" -- systemctl daemon-reload")
    if "server.py" in selected:
        state = pve("pct exec "+CTID+" -- sh -c "+shlex.quote(
            "systemctl restart lgtv-control.service && systemctl is-active lgtv-control.service && "
            "curl -fsS http://127.0.0.1:8765/api/health"))
        print(state, flush=True)
    if "launcher_early.py" in selected:
        pve("pct exec "+CTID+" -- sh -c "+shlex.quote(
            "if systemctl is-active --quiet lgtv-launcher-early.service; then systemctl restart lgtv-launcher-early.service; fi"))
    print("NAS_DEPLOY=PASS", flush=True)
