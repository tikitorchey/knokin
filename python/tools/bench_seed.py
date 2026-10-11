"""Temporal noise: does 'fixed' vs 'per-frame' seed change frame-to-frame flicker?

  python tools/bench_seed.py scene.blend [--spp 16] [--width 480]

Renders consecutive poses (theta 0,1,2,... at phi=0, 1 deg apart, as on an edge) with both seed modes and compares
the frame-to-frame RMS difference with that of a high-spp reference. Excess over the reference is noise-induced flicker.
Also reports how much of the noise is *shared* between neighbours (correlation of the residual vs the reference).
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "addon"), str(Path(__file__).resolve().parents[1])]
import bpy  # noqa: E402

from knokin_blender import scene as bs  # noqa: E402
from knokin_core.manifest import build_grid_manifest  # noqa: E402
from knokin_core.presets import UniformGrid  # noqa: E402
from knokin_packer.color import encode_rgba8  # noqa: E402
from knokin_packer.exrio import read_exr_rgba  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("blend")
ap.add_argument("--spp", type=int, default=16)
ap.add_argument("--width", type=int, default=480)
ap.add_argument("--n", type=int, default=6)
ap.add_argument("--ref-spp", type=int, default=512)
ap.add_argument("--denoise", action="store_true")
a = ap.parse_args()
h = round(a.width * 9 / 16)
bpy.ops.wm.open_mainfile(filepath=str(Path(a.blend).resolve()))
m = build_grid_manifest(
    UniformGrid(cellDeg=60, stepDeg=15), camera={"projection": "perspective", "focalMm": 50, "sensorWidthMm": 36, "distance": 5.5, "pivot": [0, 0, 0.9]},
    image={"width": a.width, "height": h, "alpha": "premultiplied", "colorSpace": "sRGB"}, title="c", created="x", generator="x",
)
sc = bpy.context.scene


def render_set(spp, mode, denoise):
    bs.apply_manifest(sc, m, bs.RenderSettings(samples=spp, denoise=denoise, seed_mode=mode))
    out = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(a.n):
            sc.cycles.seed = i if mode == "per-frame" else 0
            bs.place_camera(sc, m, float(i), 0.0)
            p = Path(td) / f"{i}.exr"
            bs.render_to(sc, str(p))
            out.append(encode_rgba8(read_exr_rgba(p), "premultiplied").astype(np.float32))
    return out


def flicker(frames):
    return float(np.mean([np.sqrt(np.mean((frames[i + 1] - frames[i]) ** 2)) for i in range(len(frames) - 1)]), )


ref = render_set(a.ref_spp, "fixed", True)
print(f"scene motion only (ref {a.ref_spp}spp): frame-to-frame RMS = {flicker(ref):.3f}")
for mode in ("fixed", "per-frame"):
    f = render_set(a.spp, mode, a.denoise)
    resid = [x - r for x, r in zip(f, ref)]
    rms = float(np.mean([np.sqrt(np.mean(r**2)) for r in resid]))
    corr = float(np.mean([np.corrcoef(resid[i].ravel(), resid[i + 1].ravel())[0, 1] for i in range(len(f) - 1)]))
    print(f"{mode:9s} spp={a.spp} dn={a.denoise}: frame-to-frame RMS = {flicker(f):.3f}  noise RMS vs ref = {rms:.3f}  "
          f"neighbour residual correlation = {corr:.2f}")
