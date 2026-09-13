#!/usr/bin/env python3
"""Verify generated headers round-trip byte-identical to shaders/*.glsl.

Usage: python3 tools/verify_shader_parity.py
"""
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
SHADERS = ENGINE / "shaders"
GEN = ENGINE / "src" / "shaders_gen"

HDR_RE = re.compile(r'R"(?P<d>[A-Za-z_]+)\((?P<body>.*)\)(?P=d)";', re.DOTALL)


def main() -> int:
    bad = []
    count = 0
    for glsl in sorted(SHADERS.glob("*.*")):
        stem = glsl.stem  # e.g. water_web
        kind = "vs.h" if glsl.suffix == ".vs" else "fs.h"
        hdr = GEN / f"{stem}_{kind}"
        if not hdr.is_file():
            bad.append(f"{hdr.name} (missing)")
            continue
        src = glsl.read_text(encoding="utf-8")
        m = HDR_RE.search(hdr.read_text(encoding="utf-8"))
        if not m or m.group("body") != src:
            bad.append(hdr.name)
        count += 1
    if bad:
        print(f"PARITY MISMATCH: {bad}")
        return 1
    print(f"PARITY OK: {count} headers identical to shaders/*.glsl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
