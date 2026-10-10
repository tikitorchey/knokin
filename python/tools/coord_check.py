"""Render labelled views through the real Blender camera path and write a contact sheet PNG.

  python tools/coord_check.py scene.blend out.png [--width 480] [--samples 32]

Views: theta 0/90/180/270 at phi=0, plus phi=+45 and -45 at theta=0 and 90.
Expected with tools/make_test_scene.py:  theta=0 sees the yellow nose pointing at the camera and the red arm on the
RIGHT; theta=90 sees the red arm's white tip pointing at the camera and the green arm on the RIGHT; phi=+45 looks
down (blue mast tilts away, floor/shadow below), phi=-45 looks up.
"""
import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "addon"), str(Path(__file__).resolve().parents[1])]
import bpy  # noqa: E402

from knokin_blender import scene as bs  # noqa: E402
from knokin_core.manifest import build_grid_manifest  # noqa: E402
from knokin_core.presets import UniformGrid  # noqa: E402
from knokin_packer.color import encode_rgba8  # noqa: E402
from knokin_packer.exrio import read_exr_rgba  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("blend")
ap.add_argument("out")
ap.add_argument("--width", type=int, default=480)
ap.add_argument("--samples", type=int, default=32)
a = ap.parse_args()
h = round(a.width * 9 / 16)
bpy.ops.wm.open_mainfile(filepath=str(Path(a.blend).resolve()))
m = build_grid_manifest(
    UniformGrid(cellDeg=60, stepDeg=15), camera={"projection": "perspective", "focalMm": 50, "sensorWidthMm": 36, "distance": 5.5, "pivot": [0, 0, 0.9]},
    image={"width": a.width, "height": h, "alpha": "premultiplied", "colorSpace": "sRGB"}, title="c", created="x", generator="x",
)
sc = bpy.context.scene
bs.apply_manifest(sc, m, bs.RenderSettings(samples=a.samples))
views = [(0, 0), (90, 0), (180, 0), (270, 0), (0, 45), (90, 45), (0, -45), (90, -45)]
tiles = []
with tempfile.TemporaryDirectory() as td:
    for th, ph in views:
        bs.place_camera(sc, m, th, ph)
        p = Path(td) / f"{th}_{ph}.exr"
        bs.render_to(sc, str(p))
        rgba = encode_rgba8(read_exr_rgba(p), "straight")
        bg = np.indices((h, a.width)).sum(0) // 16 % 2 * 40 + 100  # checkerboard shows alpha
        a_ = rgba[..., 3:4] / 255.0
        comp = (rgba[..., :3] * a_ + bg[..., None] * (1 - a_)).astype(np.uint8)
        im = Image.fromarray(comp)
        ImageDraw.Draw(im).text((6, 4), f"theta={th} phi={ph}", fill=(255, 255, 255))
        tiles.append(im)
sheet = Image.new("RGB", (a.width * 4, h * 2))
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % 4) * a.width, (i // 4) * h))
sheet.save(a.out)
print("wrote", a.out)
