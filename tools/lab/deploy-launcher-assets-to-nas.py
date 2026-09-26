"""Deploy the shared launcher UI assets to the NAS control container via Proxmox."""
from pathlib import Path
import base64
import hashlib
import os
import shlex
import subprocess
import tempfile

import paramiko
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path(__file__).resolve().parents[2]
CTID = "125"
PVE_HOST = "192.168.0.120"
FILES = {
    ROOT / "apps" / "launcher" / "launcher-ui.js": "/opt/lgtv-control/static/launcher-ui.js",
    ROOT / "apps" / "launcher" / "launcher.css": "/opt/lgtv-control/static/launcher.css",
}

cipher = base64.b64decode((ROOT / "tools" / "lab" / "pve-password.enc").read_text(encoding="ascii").strip())
private_key = serialization.load_pem_private_key(
    (Path.home() / ".cache" / "lgtv-deploy-transport" / "private.pem").read_bytes(),
    password=None,
)
password = private_key.decrypt(
    cipher,
    padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    ),
).decode("utf-8")

with tempfile.TemporaryDirectory() as tmp:
    known = Path(tmp) / "known_hosts"
    scan = subprocess.run(
        ["ssh-keyscan", "-T", "3", PVE_HOST],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        text=True,
    )
    if not scan.stdout.strip():
        raise SystemExit("Could not obtain the Proxmox SSH host key")
    known.write_text(scan.stdout, encoding="utf-8")

    client = paramiko.SSHClient()
    client.load_host_keys(str(known))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        PVE_HOST,
        username="root",
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=6,
        auth_timeout=6,
        banner_timeout=6,
    )
    password = ""
    try:
        def run(command: str) -> str:
            _stdin, stdout, stderr = client.exec_command(command, timeout=60)
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            rc = stdout.channel.recv_exit_status()
            if rc:
                raise RuntimeError(f"command failed rc={rc}: {command}\nstdout={out}\nstderr={err}")
            return out.strip()

        stage = run("mktemp -d /tmp/lgtv-launcher-assets.XXXXXX")
        with client.open_sftp() as sftp:
            for local, destination in FILES.items():
                staged = stage + "/" + local.name
                sftp.put(str(local), staged)
                temporary = "/tmp/" + Path(stage).name + "-" + local.name
                run("pct push " + CTID + " " + shlex.quote(staged) + " " + shlex.quote(temporary))
                result = run(
                    "pct exec " + CTID + " -- sh -c " + shlex.quote(
                        "set -eu; install -o root -g root -m 644 "
                        + shlex.quote(temporary) + " " + shlex.quote(destination)
                        + "; sha256sum " + shlex.quote(destination)
                    )
                )
                actual = result.splitlines()[-1].split()[0]
                expected = hashlib.sha256(local.read_bytes()).hexdigest()
                if actual != expected:
                    raise RuntimeError(f"hash mismatch for {local.name}: {actual} != {expected}")
                print(f"HASH_OK {local.name} {actual}", flush=True)

        run("pct exec " + CTID + " -- systemctl restart lgtv-control.service")
        for _ in range(15):
            try:
                state = run("pct exec " + CTID + " -- systemctl is-active lgtv-control.service")
                if state.strip() == "active":
                    break
            except RuntimeError:
                pass
            import time
            time.sleep(1)
        else:
            raise RuntimeError("lgtv-control.service did not become active")

        for local in FILES:
            expected = hashlib.sha256(local.read_bytes()).hexdigest()
            code = (
                "import hashlib,urllib.request; "
                "data=urllib.request.urlopen('http://127.0.0.1:8765/assets/" + local.name + "',timeout=5).read(); "
                "print(hashlib.sha256(data).hexdigest())"
            )
            served = run("pct exec " + CTID + " -- python3 -c " + shlex.quote(code)).strip()
            if served != expected:
                raise RuntimeError(f"served hash mismatch for {local.name}: {served} != {expected}")
            print(f"SERVED_ASSET_OK {local.name} {served}", flush=True)

        print("NAS_LAUNCHER_ASSETS=PASS", flush=True)
    finally:
        client.close()
