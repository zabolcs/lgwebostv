"""Run TV shell lifecycle fixtures on Linux, with fake devices and Luna only."""
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'checkpoint-original/LGTV-checkpoint-2026-09-19/tools'))
import remote

files = ['remote-control/server.py', 'remote-control/tests/test_broker_supervisor.py', 'tests/test_home_shell.py']
client = remote.connect()
try:
    code, output, error = remote.run(client, 'pve', 'mktemp -d /tmp/lgtv-wake-tests-20260921.XXXXXX')
    if code: raise RuntimeError(error.decode())
    stage = output.decode().strip()
    with client.open_sftp() as sftp:
        for part in ['remote-control', 'remote-control/tests', 'tests']: sftp.mkdir(stage + '/' + part)
        for relative in files:
            sftp.put(str(ROOT / 'lgtv-remote-broker' / relative), stage + '/' + relative)
    command = 'cd ' + shlex.quote(stage) + ' && python3 remote-control/tests/test_broker_supervisor.py -v && python3 tests/test_home_shell.py -v'
    code, output, error = remote.run(client, 'pve', command, timeout=180)
    sys.stdout.buffer.write(output)
    sys.stderr.buffer.write(error)
    print('fixture_directory=' + stage)
    raise SystemExit(code)
finally:
    client.close()
