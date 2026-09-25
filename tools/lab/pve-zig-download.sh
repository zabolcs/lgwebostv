set -eu
index=/tmp/codex-zig-index.json
wget -qO "$index" https://ziglang.org/download/index.json
python3 - "$index" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    item = json.load(handle)["0.14.1"]["x86_64-windows"]
print(item["tarball"])
print(item["shasum"])
print(item["size"])
PY
archive=/tmp/codex-zig-0.14.1.zip
wget -qO "$archive" https://ziglang.org/download/0.14.1/zig-x86_64-windows-0.14.1.zip
printf '%s  %s\n' '554f5378228923ffd558eac35e21af020c73789d87afeabf4bfd16f2e6feed2c' "$archive" | sha256sum -c -
