from pathlib import Path
import sys

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / 'checkpoint-original' / 'LGTV-checkpoint-2026-09-19' / 'tools'))
import remote

IPK = ROOT / 'lgtv-remote-broker/build/hu.szabi.cameraviewer_0.3.11_all.ipk'
INSTALLER = ROOT / 'lgtv-remote-broker/scripts/install-local-on-tv.sh'
EXPECTED = '2b7c76f27d2ccb69d0f4f808b2beb1febe1101b76aeb319035b66618ae478591'

pve = remote.connect()
try:
    tv = remote.connect_tv(pve)
    try:
        with tv.open_sftp() as sftp:
            sftp.put(str(IPK), '/tmp/hu.szabi.cameraviewer_0.3.11_all.ipk')
            sftp.chmod('/tmp/hu.szabi.cameraviewer_0.3.11_all.ipk', 0o600)
            sftp.put(str(INSTALLER), '/tmp/codex-install-camera-overlay.sh')
            sftp.chmod('/tmp/codex-install-camera-overlay.sh', 0o700)
        command = (
            "set -e; "
            "test \"$(sha256sum /tmp/hu.szabi.cameraviewer_0.3.11_all.ipk | awk '{print $1}')\" = " + EXPECTED + "; "
            "sh /tmp/codex-install-camera-overlay.sh /tmp/hu.szabi.cameraviewer_0.3.11_all.ipk " + EXPECTED + "; "
            "manifest=/media/developer/apps/usr/palm/applications/hu.szabi.cameraviewer/appinfo.json; "
            "test -f \"$manifest\"; grep -q '\"version\": \"0.3.11\"' \"$manifest\"; "
            "grep -q '\"defaultWindowType\": \"popup\"' \"$manifest\"; "
            "grep -q '\"transparent\": true' \"$manifest\"; "
            "echo CAMERA_OVERLAY_INSTALL_VERIFIED; cat \"$manifest\"; "
            "echo REMOTE_BROKER_STATE; "
            "test -f /var/lib/webosbrew/remote-broker/enabled && echo enabled || echo disabled; pidof remote-broker || true"
        )
        status, output, errors = remote.run(tv, 'pve', command, timeout=45)
        sys.stdout.buffer.write(output)
        sys.stderr.buffer.write(errors)
        sys.exit(status)
    finally:
        tv.close()
finally:
    pve.close()
