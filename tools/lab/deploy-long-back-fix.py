"""Deploy the protected long-Back broker fix to the TV with rollback."""
from pathlib import Path
import hashlib
import shlex
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
TV = "192.168.0.240"
KEY = Path("/media/lgtv/id_rsa")
BROKER_DIR = ROOT / "remote-broker"
BROKER = BROKER_DIR / "remote-broker"
HOME_KEY = ROOT / "tools/generated-tv-scripts/home-key.sh"
TV_ROOT = "/var/lib/webosbrew/remote-broker"
TV_HOME_KEY = "/var/lib/webosbrew/launcher-home/home-key.sh"

def run(args, timeout=60):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, timeout=timeout, check=True)
    return p.stdout.strip()

compiler = os.environ.get("BROKER_CC", "").strip()
if not compiler:
    raise RuntimeError("BROKER_CC is required for the ARM broker build")
subprocess.run(["make", "-C", str(BROKER_DIR), "clean", "all", "CC=" + compiler], check=True)
digest = hashlib.sha256(BROKER.read_bytes()).hexdigest()

with tempfile.TemporaryDirectory() as temporary:
    tmp = Path(temporary)
    known = tmp / "known_hosts"
    action = tmp / "back-long-action"
    action.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "export LAUNCHER_HOME_FORCE_MODE=full\n"
        "export LAUNCHER_HOME_FORCE_SOURCE=back-long\n"
        "exec /var/lib/webosbrew/launcher-home/home-key.sh\n",
        encoding="utf-8",
    )
    action.chmod(0o700)
    scan = subprocess.run(["ssh-keyscan", "-T", "3", TV], stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, check=True)
    known.write_text(scan.stdout, encoding="utf-8")
    base = ["-i", str(KEY), "-o", "BatchMode=yes", "-o", "ConnectTimeout=3",
            "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(known)]
    ssh = ["ssh", "-T"] + base + ["root@" + TV]
    scp = ["scp", "-q"] + base

    def checked(command, timeout=45):
        return run(ssh + [command], timeout=timeout)

    backup = checked("test -d " + shlex.quote(TV_ROOT) + "; "
                     "mktemp -d /var/lib/webosbrew/long-back-backup.XXXXXX")
    was_enabled = checked("test -f " + shlex.quote(TV_ROOT + "/enabled")
                          + " && echo 1 || echo 0") == "1"
    checked("cp -a " + shlex.quote(TV_ROOT) + " " + shlex.quote(backup + "/remote-broker")
            + "; cp -p " + shlex.quote(TV_HOME_KEY) + " " + shlex.quote(backup + "/home-key.sh"))
    print("ROLLBACK=" + backup, flush=True)
    print("BROKER_WAS_ENABLED=" + ("1" if was_enabled else "0"), flush=True)

    run(scp + [str(BROKER), "root@" + TV + ":/tmp/hu.szabi.remote-broker.new"])
    run(scp + [str(HOME_KEY), "root@" + TV + ":/tmp/hu.szabi.home-key.new"])
    run(scp + [str(action), "root@" + TV + ":/tmp/hu.szabi.back-long-action.new"])

    def stop_broker():
        checked(
            "rm -f " + shlex.quote(TV_ROOT + "/enabled") + "; "
            "for pfile in /tmp/hu.szabi.remote-broker-supervisor.pid /tmp/hu.szabi.remote-broker.pid; do "
            "p=$(cat \"$pfile\" 2>/dev/null || true); "
            "case \"$p\" in ''|*[!0-9]*) continue;; esac; "
            "kill -TERM \"$p\" 2>/dev/null || true; "
            "i=0; while kill -0 \"$p\" 2>/dev/null && [ \"$i\" -lt 40 ]; do "
            "/bin/usleep 100000; i=$((i+1)); done; "
            "kill -9 \"$p\" 2>/dev/null || true; done; "
            "rm -f /tmp/hu.szabi.remote-broker.pid /tmp/hu.szabi.remote-broker-supervisor.pid"
        )

    try:
        stop_broker()
        install = (
            "set -eu; "
            "test \"$(sha256sum /tmp/hu.szabi.remote-broker.new | awk '{print $1}')\" = " + shlex.quote(digest) + "; "
            "install -o root -g root -m 700 /tmp/hu.szabi.remote-broker.new " + shlex.quote(TV_ROOT + "/remote-broker") + "; "
            "install -o root -g root -m 755 /tmp/hu.szabi.home-key.new " + shlex.quote(TV_HOME_KEY) + "; "
            "mkdir -p " + shlex.quote(TV_ROOT + "/actions") + "; "
            "install -o root -g root -m 700 /tmp/hu.szabi.back-long-action.new " + shlex.quote(TV_ROOT + "/actions/412") + "; "
            "grep -v '^412=' " + shlex.quote(TV_ROOT + "/bindings.conf") + " >" + shlex.quote(TV_ROOT + "/bindings.conf.new") + "; "
            "printf '%s\\n' '412=long-action' >>" + shlex.quote(TV_ROOT + "/bindings.conf.new") + "; "
            "chown root:root " + shlex.quote(TV_ROOT + "/bindings.conf.new") + "; "
            "chmod 600 " + shlex.quote(TV_ROOT + "/bindings.conf.new") + "; "
            "mv " + shlex.quote(TV_ROOT + "/bindings.conf.new") + " " + shlex.quote(TV_ROOT + "/bindings.conf") + "; "
            + shlex.quote(TV_ROOT + "/remote-broker") + " --config " + shlex.quote(TV_ROOT + "/bindings.conf") + " --check-config"
        )
        checked(install)
        if was_enabled:
            checked("touch " + shlex.quote(TV_ROOT + "/enabled") + "; sh /var/lib/webosbrew/init.d/remote-broker")
            ok = False
            for _ in range(50):
                state = checked("p=$(cat /tmp/hu.szabi.remote-broker-supervisor.pid 2>/dev/null || true); "
                                "case \"$p\" in ''|*[!0-9]*) exit 0;; esac; "
                                "kill -0 \"$p\" 2>/dev/null && echo PASS || true")
                if state.endswith("PASS"):
                    ok = True
                    break
                time.sleep(0.1)
            if not ok:
                raise RuntimeError("remote broker supervisor did not restart")
        checked("grep -qx '412=long-action' " + shlex.quote(TV_ROOT + "/bindings.conf")
                + "; test -x " + shlex.quote(TV_ROOT + "/actions/412")
                + "; grep -q 'LAUNCHER_HOME_FORCE_MODE=full' " + shlex.quote(TV_ROOT + "/actions/412")
                + "; grep -q 'FORCE_MODE=' " + shlex.quote(TV_HOME_KEY))
    except Exception:
        try:
            stop_broker()
            checked("rm -rf " + shlex.quote(TV_ROOT)
                    + "; cp -a " + shlex.quote(backup + "/remote-broker") + " " + shlex.quote(TV_ROOT)
                    + "; cp -p " + shlex.quote(backup + "/home-key.sh") + " " + shlex.quote(TV_HOME_KEY))
            if was_enabled:
                checked("touch " + shlex.quote(TV_ROOT + "/enabled") + "; sh /var/lib/webosbrew/init.d/remote-broker")
        finally:
            raise

    print("LONG_BACK_TV_DEPLOY=PASS", flush=True)
