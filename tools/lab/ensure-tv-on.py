"""Wake the lab TV through the existing NAS power API and wait for SSH."""
import json
import socket
import time
import urllib.request

API = "http://192.168.0.223:8765/api/tv/power"
TV_HOST = "192.168.0.240"

def request(body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))

try:
    current = request()
except Exception:
    current = {}
state = ((current.get("power") or {}).get("state") or current.get("state") or "")
print("TV_POWER_BEFORE=" + str(state), flush=True)

if state != "on":
    result = request({"state": "on"})
    print("TV_WAKE_RESPONSE=" + json.dumps(result, separators=(",", ":")), flush=True)

deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((TV_HOST, 22), timeout=1):
            print("TV_SSH_READY=PASS", flush=True)
            raise SystemExit(0)
    except OSError:
        time.sleep(1)

raise SystemExit("TV did not expose SSH within wake window")
