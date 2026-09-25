from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'checkpoint-original' / 'LGTV-checkpoint-2026-09-19' / 'tools'))
import remote

pve = remote.connect()
try:
    tv = remote.connect_tv(pve)
    try:
        script = Path(__file__).with_suffix('.sh').read_text(encoding='utf-8')
        inp, out, err = tv.exec_command(script, timeout=85)
        inp.channel.shutdown_write()
        for line in out:
            print(line.rstrip(), flush=True)
        print(err.read().decode(), file=sys.stderr, flush=True)
        sys.exit(out.channel.recv_exit_status())
    finally:
        tv.close()
finally:
    pve.close()
