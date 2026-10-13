"""Propagate the root VERSION file to every place that carries the app version (DD48).

    python scripts/sync_version.py          # rewrite the files
    python scripts/sync_version.py --check  # exit 1 if any file differs (used by tests)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$")

# (file, pattern with one group around the version-bearing line's prefix, suffix)
TARGETS = [
    ("python/pyproject.toml", r'(?m)^(version = ")[^"]+(")'),
    ("python/knokin_core/__init__.py", r'(?m)^(__version__ = ")[^"]+(")'),
    ("viewer/packages/core/package.json", r'(?m)^(  "version": ")[^"]+(")'),
    ("viewer/packages/app/package.json", r'(?m)^(  "version": ")[^"]+(")'),
]


def read_version() -> str:
    v = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.match(v):
        raise SystemExit(f"VERSION {v!r} is not MAJOR.MINOR.PATCH")
    return v


def main(argv: list[str]) -> int:
    check = "--check" in argv
    v = read_version()
    stale = []
    for rel, pat in TARGETS:
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        new, n = re.subn(pat, lambda m: m.group(1) + v + m.group(2), text, count=1)
        if n != 1:
            raise SystemExit(f"{rel}: version line not found")
        if new != text:
            stale.append(rel)
            if not check:
                p.write_text(new, encoding="utf-8")
    if stale:
        print(("out of sync: " if check else "updated: ") + ", ".join(stale))
    return 1 if (check and stale) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
