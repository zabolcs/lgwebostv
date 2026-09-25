from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'checkpoint-original' / 'LGTV-checkpoint-2026-09-19' / 'tools'))
import remote
pve = remote.connect()
try:
    tv = remote.connect_tv(pve)
    try:
        with tv.open_sftp() as sftp:
            sftp.put(str(Path(__file__).parent / 'test-relay-arm'), '/tmp/codex-test-relay-arm')
            sftp.chmod('/tmp/codex-test-relay-arm', 0o700)
        _, out, err = tv.exec_command('/tmp/codex-test-relay-arm; command -v flock', timeout=10)
        print(out.read().decode())
        print(err.read().decode())
    finally:
        tv.close()
finally:
    pve.close()
