from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .avif import AvifSettings
from .pack import PackError, PackSettings, pack


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="knokin_packer", description="Pack EXR masters into AVIF sequences.")
    ap.add_argument("--workdir", required=True, type=Path, help="capture work dir")
    ap.add_argument("--out", required=True, type=Path, help="output dir (deployable)")
    ap.add_argument("--quality", type=int, default=60)
    ap.add_argument("--speed", type=int, default=6)
    ap.add_argument("--subsampling", default="4:2:0", choices=["4:2:0", "4:4:4"])
    ap.add_argument("--low-width", type=int, default=480, help="node low-res width; 0 disables")
    ap.add_argument("--partial", action="store_true", help="pack only captured frames (test shoot)")
    ap.add_argument("--verify-masters", action="store_true", help="re-hash every master")
    a = ap.parse_args(argv)
    s = PackSettings(AvifSettings(a.quality, a.speed, a.subsampling), a.low_width, a.partial)
    try:
        r = pack(a.workdir, a.out, s, verify_masters=a.verify_masters)
    except PackError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(
        f"packed: written={r.written} skipped={r.skipped} outputs={r.total_outputs} "
        f"full={r.bytes_full / 1e6:.1f}MB low={r.bytes_low / 1e6:.1f}MB not-captured={r.missing_masters}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
