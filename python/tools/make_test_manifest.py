"""Write a (reduced) grid manifest for test shoots.

  python tools/make_test_manifest.py out.json [--cell 60] [--step 10] [--width 480] [--height 270]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knokin_core.manifest import build_grid_manifest  # noqa: E402
from knokin_core.presets import UniformGrid  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--cell", type=float, default=60)
ap.add_argument("--step", type=float, default=10)
ap.add_argument("--phi", type=float, default=60)
ap.add_argument("--diagonals", choices=["none", "cross"], default="cross")
ap.add_argument("--width", type=int, default=480)
ap.add_argument("--height", type=int, default=270)
ap.add_argument("--low-width", type=int, default=0, help="declare image.low (0 = packer decides)")
a = ap.parse_args()

m = build_grid_manifest(
    UniformGrid(cellDeg=a.cell, phiRange=(-a.phi, a.phi), stepDeg=a.step, diagonals=a.diagonals),
    camera={"projection": "perspective", "focalMm": 50, "sensorWidthMm": 36, "distance": 5.5, "pivot": [0, 0, 0.9]},
    image={"width": a.width, "height": a.height, "alpha": "premultiplied", "colorSpace": "sRGB"},
    title=f"test-c{a.cell:g}-s{a.step:g}", created="2026-10-10", generator="make_test_manifest",
)
Path(a.out).write_text(m.dumps(), encoding="utf-8")
print(a.out, len(m.graph.nodes), "nodes", len(m.graph.edges), "edges")
