from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "checkpoint-original" / "LGTV-checkpoint-2026-09-19" / "tools"))
import remote

TEST_BINARY = ROOT / "lgtv-remote-broker" / "remote-broker" / "test-relay.v4"
EXPECTED = "8bb18e5248dd942fc852338970b56bfbe5fc086019f8cef527fb0b46f33a4357"

pve = remote.connect()
try:
    tv = remote.connect_tv(pve)
    try:
        with tv.open_sftp() as sftp:
            sftp.put(str(TEST_BINARY), "/tmp/codex-test-relay-v4")
            sftp.chmod("/tmp/codex-test-relay-v4", 0o700)
        command = (
            "set -eu; "
            "test \"$(sha256sum /tmp/codex-test-relay-v4 | awk '{print $1}')\" = " + EXPECTED + "; "
            "/tmp/codex-test-relay-v4; rm -f /tmp/codex-test-relay-v4"
        )
        status, output, errors = remote.run(tv, "pve", command, timeout=20)
        sys.stdout.buffer.write(output)
        sys.stderr.buffer.write(errors)
        raise SystemExit(status)
    finally:
        tv.close()
finally:
    pve.close()
