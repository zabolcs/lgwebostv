import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "checkpoint-original" / "LGTV-checkpoint-2026-09-19" / "tools"))
import remote

pve = remote.connect()
try:
    tv = remote.connect_tv(pve)
    try:
        status, output, errors = remote.run(
            tv,
            "pve",
            "/usr/bin/luna-send-pub -t 1 -w 3000 -f "
            "luna://com.webos.applicationManager/launch "
            "'{\"id\":\"hu.szabi.cameraviewer\"}'",
        )
        print("launch", status, output.decode(errors="replace"), errors.decode(errors="replace"))
        for attempt in range(12):
            try:
                with urllib.request.urlopen("http://192.168.0.240:9998/json", timeout=1) as response:
                    pages = json.load(response)
                matches = [
                    {key: page.get(key) for key in ("id", "title", "url", "description", "webSocketDebuggerUrl")}
                    for page in pages
                    if "cameraviewer" in json.dumps(page).lower() or "kamer" in json.dumps(page).lower()
                ]
                print(attempt, json.dumps(matches, ensure_ascii=False))
            except Exception as error:
                print(attempt, type(error).__name__, str(error))
            time.sleep(0.25)
    finally:
        tv.close()
finally:
    pve.close()
