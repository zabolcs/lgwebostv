from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "checkpoint-original" / "LGTV-checkpoint-2026-09-19" / "tools"))
import remote

source = Path(sys.argv[1]).resolve()
target = sys.argv[2]
client = remote.connect()
try:
    with client.open_sftp() as sftp:
        sftp.put(str(source), target)
        sftp.chmod(target, 0o700)
finally:
    client.close()
