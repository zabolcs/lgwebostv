"""Deploy NAS control files to CT125 through the known-good private Proxmox helper."""
from pathlib import Path
import hashlib
import importlib.util
import os
import shlex
import sys

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

# Relocate the legacy Windows credential source to the private NAS checkpoint.
if hasattr(remote, "OLD") and not Path(remote.OLD).is_file():
    candidates = []
    search_roots = [
        Path("/media/lgtv/checkpoint-20260925-20260925-092443"),
        Path("/media/lgtv/checkpoint-20260919-20260919-211820"),
    ]
    for root in search_roots:
        if not root.exists():
            continue
        for pattern in ("*.md", "*.txt"):
            for path in root.rglob(pattern):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if "- SSH jelszó:" in text:
                    candidates.append(path)
                    break
            if candidates:
                break
        if candidates:
            break
    if not candidates:
        raise SystemExit("Private checkpoint containing the SSH credential marker was not found")
    remote.OLD = candidates[0]
    print(f"Using private credential checkpoint: {remote.OLD}", flush=True)

conn = remote.connect()
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
            "curl -fsS http://127.0.0.1:8765/api/health"))
        print(state, flush=True)

    if "static/index.html" in selected:
        pve(conn, "pct exec "+CTID+" -- sh -c "+shlex.quote(
            "curl -fsS http://127.0.0.1:8765/ | grep -q 'dashboard-control.js'"))
        print("SERVED_INDEX_OK", flush=True)

    if "static/dashboard-control.js" in selected:
        expected = hashlib.sha256((SOURCE/"static/dashboard-control.js").read_bytes()).hexdigest()
        served = pve(conn, "pct exec "+CTID+" -- sh -c "+shlex.quote(
            "curl -fsS http://127.0.0.1:8765/assets/dashboard-control.js | sha256sum | awk '{print $1}'"))
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
