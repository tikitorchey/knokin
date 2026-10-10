"""Ground truth for the premultiplyAlpha comparison (see viewer/scripts/premult.mjs).

  python tools/make_premult_truth.py --workdir w_real --out viewer/packages/app/public/premult-truth [--n 4] \
      [--quality 60] [--subsampling 4:2:0] [--alpha premultiplied]

Per sample: <name>.avif (encoded exactly as the packer would), <name>.white.png / <name>.gray.png (the intended picture:
straight colour composited over the background in sRGB space), <name>.edge.png (alpha edge band mask).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knokin_packer.avif import AvifSettings, save_avif  # noqa: E402
from knokin_packer.color import encode_rgba8  # noqa: E402
from knokin_packer.exrio import read_exr_rgba  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--workdir", type=Path, required=True)
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--n", type=int, default=4)
ap.add_argument("--quality", type=int, default=60)
ap.add_argument("--subsampling", default="4:2:0")
ap.add_argument("--alpha", default="premultiplied")
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
rows = [json.loads(l) for l in (a.workdir / "capture.jsonl").read_text().splitlines()[1:] if l.strip()]
rows = [r for r in rows if "path" in r]
for k in range(a.n):
    r = rows[(k * len(rows)) // a.n]
    name = r["id"].replace("/", "_")
    lin = read_exr_rgba(a.workdir / r["path"])
    straight = encode_rgba8(lin, "straight").astype(np.float32)
    al = straight[..., 3:4] / 255
    for bgname, bg in (("white", 255.0), ("gray", 128.0)):
        comp = np.rint(straight[..., :3] * al + bg * (1 - al)).astype(np.uint8)
        Image.fromarray(comp).save(a.out / f"{name}.{bgname}.png")
    edge = ((straight[..., 3] > 0) & (straight[..., 3] < 255)).astype(np.uint8) * 255
    Image.fromarray(edge).filter(ImageFilter.MaxFilter(5)).save(a.out / f"{name}.edge.png")
    save_avif(encode_rgba8(lin, a.alpha), a.out / f"{name}.avif", AvifSettings(a.quality, 6, a.subsampling), a.alpha == "premultiplied")
    print("wrote", name)
