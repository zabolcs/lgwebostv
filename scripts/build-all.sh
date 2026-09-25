#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

# Keep one canonical allowlist and one archive implementation. Besides avoiding
# Python/shell package drift, this gives both entry points byte-identical IPKs.
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "missing tool: Python 3" >&2
  exit 2
fi

exec "$PYTHON" "$ROOT/scripts/build-all.py"
