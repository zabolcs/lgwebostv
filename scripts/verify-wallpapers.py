#!/usr/bin/env python3
import concurrent.futures
import importlib.util
import pathlib
import urllib.request

server_path = pathlib.Path(__file__).resolve().parents[1] / "remote-control" / "server.py"
spec = importlib.util.spec_from_file_location("lgtv_server", server_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def verify(url):
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, url
    except Exception as error:
        return getattr(error, "code", type(error).__name__), url


with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
    results = list(executor.map(verify, module.DEFAULT_WALLPAPER_URLS))
for status, url in results:
    print(status, url.split("?", 1)[0])
if any(status != 200 for status, _ in results):
    raise SystemExit(1)
