"""Deploy NAS control files to CT125 through the known-good private Proxmox helper."""
from pathlib import Path
import base64
import hashlib
import importlib.util
import os
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "remote-control"
CTID = "125"
DEFAULT_HELPER = Path("/media/lgtv/checkpoint-20260925-20260925-092443/source/previous-work-20260905/remote.py")
HELPER = Path(os.environ.get("LGTV_REMOTE_HELPER", str(DEFAULT_HELPER)))

FILES = (
    "server.py","lg_ssap.py","ssap_pairing.py","launcher_early.py",
    "static/index.html","static/ssap-control.js","static/power-control.js",
    "static/launcher-admin.js","static/connections-ui.js","static/dashboard-control.js",
    "lgtv-launcher-early.service",
)
selected = tuple(sys.argv[1:]) or FILES
assert set(selected) <= set(FILES)
if not HELPER.is_file():
    raise SystemExit(f"Private Proxmox helper not found: {HELPER}")

# Preload the runner-compatible SSH stack before the legacy helper prepends its vendored python/ tree.
import paramiko  # noqa: F401
import cryptography  # noqa: F401
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

spec = importlib.util.spec_from_file_location("lgtv_private_remote", HELPER)
remote = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(remote)

def pve(conn, command, timeout=60):
    rc, out, err = remote.run(conn, "pve", command, timeout=timeout)
    if rc != 0:
        raise RuntimeError(
            f"PVE command failed rc={rc}: {command}\n"
            f"stdout={out.decode(errors='replace')}\n"
            f"stderr={err.decode(errors='replace')}"
        )
    return out.decode().strip()

# Decrypt the repository-safe credential blob with the private key that exists
# only on this self-hosted runner, then feed the legacy helper a short-lived
# metadata file so its pinned host-key and connection behavior remain unchanged.
cipher_path = ROOT / "tools" / "lab" / "pve-password.enc"
private_key_path = Path.home() / ".cache" / "lgtv-deploy-transport" / "private.pem"
if not cipher_path.is_file():
    raise SystemExit(f"Encrypted PVE credential not found: {cipher_path}")
if not private_key_path.is_file():
    raise SystemExit(f"Runner deploy private key not found: {private_key_path}")

private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
password = private_key.decrypt(
    base64.b64decode(cipher_path.read_text(encoding="ascii").strip()),
    padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    ),
).decode("utf-8")

fd, metadata_name = tempfile.mkstemp(prefix="lgtv-pve-credential.", suffix=".md")
os.close(fd)
metadata_path = Path(metadata_name)
metadata_path.write_text("- SSH jelszó: `" + password + "`\n", encoding="utf-8")
os.chmod(metadata_path, 0o600)
password = ""
remote.OLD = metadata_path

known_hosts_temp = None
if hasattr(remote, "KNOWN") and not Path(remote.KNOWN).is_file():
    scan = subprocess.run(
        ["ssh-keyscan", "-T", "3", "192.168.0.120"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=True,
    )
    if not scan.stdout.strip():
        raise SystemExit("Could not obtain Proxmox SSH host key from 192.168.0.120")
    fd, known_name = tempfile.mkstemp(prefix="lgtv-pve-known-hosts.")
    os.close(fd)
    known_hosts_temp = Path(known_name)
    known_hosts_temp.write_text(scan.stdout, encoding="utf-8")
    os.chmod(known_hosts_temp, 0o600)
    remote.KNOWN = known_hosts_temp
    print("Using live Proxmox host key for 192.168.0.120", flush=True)

try:
    conn = remote.connect()
finally:
    metadata_path.unlink(missing_ok=True)
    if known_hosts_temp is not None:
        known_hosts_temp.unlink(missing_ok=True)

try:
    stage = pve(conn, "mktemp -d /tmp/lgtv-native-deploy.XXXXXX")
    backup = pve(conn, "pct exec "+CTID+" -- sh -c " + shlex.quote(
        "mkdir -p /var/backups/lgtv-control && mktemp -d /var/backups/lgtv-control/dashboard.XXXXXX"))
    print("Rollback: "+backup, flush=True)

    with conn.open_sftp() as sftp:
        for relative in selected:
            local = SOURCE / relative
            name = relative.replace("/", "_")
            remote_stage = stage + "/" + name
            sftp.put(str(local), remote_stage)
            temporary = "/tmp/" + stage.rsplit("/", 1)[-1] + "-" + name
            pve(conn, "pct push "+CTID+" "+shlex.quote(remote_stage)+" "+shlex.quote(temporary))
            destination = (
                "/etc/systemd/system/"+relative
                if relative.endswith(".service")
                else "/opt/lgtv-control/"+relative
            )
            inner = (
                "set -eu; mkdir -p "+shlex.quote(str(Path(destination).parent))+"; "
                "if [ -f "+shlex.quote(destination)+" ]; then "
                "cp -p "+shlex.quote(destination)+" "+shlex.quote(backup+"/"+name)+"; fi; "
                + (("python3 -m py_compile "+shlex.quote(temporary)+"; ") if relative.endswith(".py") else "")
                + "install -o root -g root -m 644 "+shlex.quote(temporary)+" "+shlex.quote(destination)+"; "
                + "sha256sum "+shlex.quote(destination)
            )
            result = pve(conn, "pct exec "+CTID+" -- sh -c "+shlex.quote(inner))
            digest = result.splitlines()[-1].split()[0]
            expected = hashlib.sha256(local.read_bytes()).hexdigest()
            if digest != expected:
                raise RuntimeError(f"Hash mismatch for {relative}: {digest} != {expected}")
            print(f"HASH_OK {relative} {digest}", flush=True)

    pve(conn, "pct exec "+CTID+" -- systemctl daemon-reload")
    if "server.py" in selected:
        state = pve(conn, "pct exec "+CTID+" -- sh -c "+shlex.quote(
            "set -eu; "
            "systemctl restart lgtv-control.service; "
            "systemctl is-active lgtv-control.service; "
            "python3 -c " + shlex.quote(
                "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=5).read().decode())"
            )))
        print(state, flush=True)

    if "static/index.html" in selected:
        pve(conn, "pct exec "+CTID+" -- python3 -c "+shlex.quote(
            "import urllib.request; data=urllib.request.urlopen('http://127.0.0.1:8765/', timeout=5).read().decode(); "
            "assert 'dashboard-control.js' in data"))
        print("SERVED_INDEX_OK", flush=True)

    if "static/dashboard-control.js" in selected:
        expected = hashlib.sha256((SOURCE/"static/dashboard-control.js").read_bytes()).hexdigest()
        served = pve(conn, "pct exec "+CTID+" -- python3 -c "+shlex.quote(
            "import hashlib,urllib.request; "
            "data=urllib.request.urlopen('http://127.0.0.1:8765/assets/dashboard-control.js', timeout=5).read(); "
            "print(hashlib.sha256(data).hexdigest())"))
        if served.strip() != expected:
            raise RuntimeError(f"Served dashboard hash mismatch: {served.strip()} != {expected}")
        print("SERVED_DASHBOARD_OK "+served.strip(), flush=True)

    if "launcher_early.py" in selected:
        pve(conn, "pct exec "+CTID+" -- sh -c "+shlex.quote(
            "if systemctl is-active --quiet lgtv-launcher-early.service; then "
            "systemctl restart lgtv-launcher-early.service; fi"))

    print("NAS_DEPLOY=PASS", flush=True)
finally:
    conn.close()
