"""AVIF settings sweep on captured masters: size, encode time, and quality (overall + alpha-edge band).

  python tools/bench_pack.py --workdir w_real --out /tmp/k/packbench [--images 12] [--total 5928] [--nodes 108]

Quality is measured against the 8-bit sRGB image the packer would feed the encoder (not against the EXR), i.e. it
isolates the codec loss. Composites over white and black expose halos/dark fringes at the alpha edge.
"""
import argparse
import io
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knokin_core import jobstate  # noqa: E402
from knokin_packer.avif import AvifSettings, downscale, save_avif  # noqa: E402
from knokin_packer.color import encode_rgba8  # noqa: E402
from knokin_packer.exrio import read_exr_rgba  # noqa: E402


def composite(rgba8, bg, premultiplied):
    a = rgba8[..., 3:4].astype(np.float32) / 255
    c = rgba8[..., :3].astype(np.float32)
    return (c if premultiplied else c * a) + bg * (1 - a)


def edge_band(alpha, r=2):
    m = Image.fromarray(((alpha > 0) & (alpha < 255)).astype(np.uint8) * 255)
    return np.asarray(m.filter(ImageFilter.MaxFilter(2 * r + 1))) > 0


def psnr(a, b, mask=None):
    d = (a - b) ** 2
    if mask is not None:
        if not mask.any():
            return float("nan")
        d = d[mask]
    return float(10 * np.log10(255.0**2 / max(np.mean(d), 1e-9)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--images", type=int, default=12)
    ap.add_argument("--total", type=int, default=5928, help="images in the full production set")
    ap.add_argument("--nodes", type=int, default=108)
    ap.add_argument("--alpha", default="premultiplied", choices=["premultiplied", "straight"])
    ap.add_argument("--qualities", default="40,50,60,70,80")
    ap.add_argument("--speeds", default="4,6,8")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    prem = a.alpha == "premultiplied"

    rows = [json.loads(l) for l in (a.workdir / "capture.jsonl").read_text().splitlines()[1:] if l.strip()]
    rows = [r for r in rows if "path" in r]
    pick = [rows[(k * len(rows)) // a.images] for k in range(a.images)]
    src = [encode_rgba8(read_exr_rgba(a.workdir / r["path"]), a.alpha) for r in pick]
    h, w = src[0].shape[:2]
    bands = [edge_band(s[..., 3]) for s in src]
    print(f"{len(src)} images {w}x{h}, edge-band pixels/image: {np.mean([b.sum() for b in bands]):.0f}")

    cfgs = [(q, 6, ss) for ss in ("4:2:0", "4:4:4") for q in map(int, a.qualities.split(","))]
    cfgs += [(60, sp, "4:2:0") for sp in map(int, a.speeds.split(",")) if sp != 6]
    out = []
    for q, sp, ss in cfgs:
        s = AvifSettings(q, sp, ss)
        sizes, secs, p_all, p_w, p_b, p_edge = [], [], [], [], [], []
        for img, band in zip(src, bands):
            buf = a.out / "tmp.avif"
            t = time.perf_counter()
            save_avif(img, buf, s, prem)
            secs.append(time.perf_counter() - t)
            sizes.append(buf.stat().st_size)
            dec = np.asarray(Image.open(buf).convert("RGBA"), dtype=np.uint8)
            if prem and dec.shape == img.shape:
                pass  # Pillow returns the decoded RGBA as stored; compare in the same alpha convention
            for bg, lst in ((255.0, p_w), (0.0, p_b)):
                ca, cb = composite(img, bg, prem), composite(dec, bg, prem)
                lst.append(psnr(ca, cb))
            ca, cb = composite(img, 255.0, prem), composite(dec, 255.0, prem)
            p_edge.append(psnr(ca, cb, band[..., None].repeat(3, -1)))
            p_all.append(psnr(img.astype(np.float32), dec.astype(np.float32)))
        mb = statistics.mean(sizes)
        out.append({
            "quality": q, "speed": sp, "subsampling": ss, "meanKB": mb / 1e3, "encodeSec": statistics.mean(secs),
            "totalGB": mb * a.total / 1e9, "psnrRGBA": statistics.mean(p_all), "psnrOverWhite": statistics.mean(p_w),
            "psnrOverBlack": statistics.mean(p_b), "psnrEdgeWhite": statistics.mean(p_edge),
        })
        o = out[-1]
        print(f"q{q:3d} s{sp:2d} {ss}: {o['meanKB']:7.1f}kB  {o['encodeSec']:.2f}s  all {o['psnrRGBA']:.1f}  edge(white) {o['psnrEdgeWhite']:.1f}  -> {o['totalGB']:.2f}GB", flush=True)
    # low-res node images
    lows = [downscale(s, 480, prem) for s in src]
    low_kb = []
    for l in lows:
        save_avif(l, a.out / "tmp.avif", AvifSettings(), prem)
        low_kb.append((a.out / "tmp.avif").stat().st_size / 1e3)
    res = {"images": len(src), "size": [w, h], "alpha": a.alpha, "total": a.total, "lowKB": statistics.mean(low_kb), "lowTotalMB": statistics.mean(low_kb) * a.nodes / 1e3, "configs": out}
    (a.out / "results.json").write_text(json.dumps(res, indent=1))
    L = ["| quality | speed | chroma | KB/image | encode s | full set GB | PSNR RGBA | PSNR edge band (over white) |", "|---|---|---|---|---|---|---|---|"]
    for o in out:
        L.append(f"| {o['quality']} | {o['speed']} | {o['subsampling']} | {o['meanKB']:.1f} | {o['encodeSec']:.2f} | {o['totalGB']:.2f} | {o['psnrRGBA']:.1f} | {o['psnrEdgeWhite']:.1f} |")
    (a.out / "results.md").write_text("\n".join(L) + f"\n\nlow-res node image (480w, q60): {res['lowKB']:.1f} KB each, {res['lowTotalMB']:.2f} MB for {a.nodes} nodes\n")


main()
