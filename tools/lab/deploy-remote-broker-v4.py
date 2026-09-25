from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "checkpoint-original" / "LGTV-checkpoint-2026-09-19" / "tools"))
import remote

BINARY = ROOT / "lgtv-remote-broker" / "remote-broker" / "remote-broker.v4"
INSTALLER = ROOT / "lgtv-remote-broker" / "remote-broker" / "install-on-tv.sh"
EXPECTED = "49dea6fef84b4b7b18fa16d53ac7ef3faf16b11f7a2396e3a280d0e966a5d7f5"

pve = remote.connect()
try:
    tv = remote.connect_tv(pve)
    try:
        with tv.open_sftp() as sftp:
            sftp.put(str(BINARY), "/tmp/codex-remote-broker-v4")
            sftp.chmod("/tmp/codex-remote-broker-v4", 0o700)
            sftp.put(str(INSTALLER), "/tmp/codex-install-remote-broker-v4.sh")
            sftp.chmod("/tmp/codex-install-remote-broker-v4.sh", 0o700)
        command = (
            "set -eu; "
            "test ! -e /var/lib/webosbrew/remote-broker/enabled; "
            "! pidof remote-broker >/dev/null 2>&1; "
            "test \"$(sha256sum /tmp/codex-remote-broker-v4 | awk '{print $1}')\" = " + EXPECTED + "; "
            "/bin/sh /tmp/codex-install-remote-broker-v4.sh /tmp/codex-remote-broker-v4 " + EXPECTED + "; "
            "test \"$(/var/lib/webosbrew/remote-broker/remote-broker --version)\" = 4-evdev-relay; "
            "test ! -e /var/lib/webosbrew/remote-broker/enabled; "
            "! pidof remote-broker >/dev/null 2>&1; "
            "echo BROKER_V4_INSTALLED_DISABLED"
        )
        status, output, errors = remote.run(tv, "pve", command, timeout=30)
        sys.stdout.buffer.write(output)
        sys.stderr.buffer.write(errors)
        raise SystemExit(status)
    finally:
        tv.close()
finally:
    pve.close()
