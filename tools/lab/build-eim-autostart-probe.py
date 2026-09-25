#!/usr/bin/env python3
"""Build the isolated EIM autostart probe package."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("lgtv_build", ROOT / "scripts" / "build-all.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("scripts/build-all.py cannot be loaded")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)

def main() -> None:
    output, digest = BUILDER.build(
        "eim-autostart-probe",
        BUILDER.DIAGNOSTIC_APPS["eim-autostart-probe"],
    )
    print(f"{digest}  {output}")

if __name__ == "__main__":
    main()
