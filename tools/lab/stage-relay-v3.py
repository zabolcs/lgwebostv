"""Stage candidate and run hardware-free tests/read-only device preflight only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'checkpoint-original' / 'LGTV-checkpoint-2026-09-19' / 'tools'))
import remote
root = Path(__file__).parent
pve = remote.connect()
try:
    tv = remote.connect_tv(pve)
    try:
        with tv.open_sftp() as sftp:
            for source, target, mode in [
                (root / 'lgtv-remote-broker/remote-broker/remote-broker', '/tmp/codex-remote-relay-v3', 0o700),
                (root / 'relay-v3-test.conf', '/tmp/codex-remote-relay-v3.conf', 0o600),
                (root / 'test-relay-arm', '/tmp/codex-test-relay-arm', 0o700),
            ]:
                sftp.put(str(source), target)
                sftp.chmod(target, mode)
        status, output, errors = remote.run(tv, 'pve',
            'set -e; test ! -e /var/lib/webosbrew/remote-broker/enabled; '
            '/tmp/codex-test-relay-arm; '
            '/tmp/codex-remote-relay-v3 --version; '
            '/tmp/codex-remote-relay-v3 --config /tmp/codex-remote-relay-v3.conf --check-config; '
            '/tmp/codex-remote-relay-v3 --config /tmp/codex-remote-relay-v3.conf --check-devices; '
            'sha256sum /tmp/codex-remote-relay-v3')
        sys.stdout.buffer.write(output)
        sys.stderr.buffer.write(errors)
        sys.exit(status)
    finally:
        tv.close()
finally:
    pve.close()
