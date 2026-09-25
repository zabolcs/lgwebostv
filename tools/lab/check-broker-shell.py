from pathlib import Path
import base64
import shlex
import subprocess
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "lgtv-remote-broker" / "remote-control"))
sys.path.insert(0, str(root / "checkpoint-original" / "LGTV-checkpoint-2026-09-19" / "tools"))
import server
import remote

commands = []
manager = server.RemoteBrokerManager({
    "tv_host": "192.168.0.240", "tv_user": "root", "ssh_key": "/key",
    "known_hosts": "/known", "remote_broker_mode": "grab",
}, runner=lambda command, **kwargs: commands.append(command[-1]) or subprocess.CompletedProcess(command, 0, "", ""))
manager._stop_locked()

scripts = {
    "init": server.RemoteBrokerManager.INIT_SCRIPT,
    "supervisor": server.RemoteBrokerManager.SUPERVISOR_SCRIPT,
    "stop-command": commands[-1],
}
client = remote.connect()
try:
    for name, script in scripts.items():
        payload = base64.b64encode(script.encode()).decode()
        command = "printf '%s' " + shlex.quote(payload) + " | base64 -d | /bin/sh -n"
        status, output, errors = remote.run(client, "pve", command)
        if status != 0:
            raise SystemExit(name + ": " + errors.decode(errors="replace"))
        print(name + ": shell syntax valid")
finally:
    client.close()
