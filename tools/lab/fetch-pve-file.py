from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "checkpoint-original" / "LGTV-checkpoint-2026-09-19" / "tools"))
import remote

client = remote.connect()
try:
    with client.open_sftp() as sftp:
        sftp.get("/tmp/codex-zig-0.14.1.zip", str(Path(__file__).parent / "codex-zig-0.14.1.zip"))
finally:
    client.close()
