"""Make a synthetic capture work dir (no Blender): a disc whose hue is theta and brightness is phi.

Lets the packer and the viewer be exercised end to end before any real render exists.
  PYTHONPATH=. python tools/make_synthetic_capture.py --workdir /tmp/syn --cell 60 --step 15 --size 320x180
"""
from __future__ import annotations

import argparse
import colorsys
import json
from pathlib import Path

import numpy as np

from knokin_core import jobstate as js
from knokin_core.jobs import enumerate_jobs
from knokin_core.manifest import build_grid_manifest
from knokin_core.presets import UniformGrid


def render(theta: float, phi: float, w: int, h: int) -> np.ndarray:
    """Premultiplied scene-linear RGBA: hue disc + a bar whose x position follows theta."""
    img = np.zeros((h, w, 4), np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    r = min(w, h) * 0.35
    cx, cy = w / 2 + 0.25 * w * np.sin(np.radians(theta)), h / 2 - 0.25 * h * np.sin(np.radians(phi))
    disc = (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
    rgb = colorsys.hsv_to_rgb((theta % 360) / 360, 0.8, 0.5 + 0.5 * np.cos(np.radians(phi)))
    img[disc] = [*(c ** 2.2 for c in rgb), 1.0]
    bar = (np.abs(xx - (theta % 360) / 360 * w) < 2) & (yy > h - 8)
    img[bar] = [1, 1, 1, 1]
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--cell", type=int, default=60)
    ap.add_argument("--step", type=int, default=15)
    ap.add_argument("--size", default="320x180")
    a = ap.parse_args()
    import OpenEXR

    w, h = map(int, a.size.split("x"))
    m = build_grid_manifest(
        UniformGrid(cellDeg=a.cell, stepDeg=a.step, phiRange=(-60, 60)),
        camera={"projection": "perspective", "focalMm": 85, "sensorWidthMm": 36, "distance": 3.0, "pivot": [0, 0, 0.9]},
        image={"width": w, "height": h, "alpha": "premultiplied", "colorSpace": "sRGB"},
        title="synthetic", created="2026-10-10", generator="make_synthetic_capture",
    )
    js.init_workdir(a.workdir, m.dumps())

    def write(job, part: Path) -> None:
        px = render(job.theta, job.phi, w, h).astype(np.float16)
        OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}, {"RGBA": px}).write(str(part))

    n = js.run_capture(a.workdir, enumerate_jobs(m.graph), write)
    (a.workdir / "render_meta.json").write_text(json.dumps({"synthetic": True}))
    print(f"rendered {n} frames into {a.workdir}")


if __name__ == "__main__":
    main()
