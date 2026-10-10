"""Regenerate testdata/manifests/grid30_cross.json (the shared golden manifest)."""
from pathlib import Path

from knokin_core.presets import UniformGrid
from tests.golden import GOLDEN_KW

out = Path(__file__).resolve().parents[2] / "testdata" / "manifests" / "grid30_cross.json"
from knokin_core.manifest import build_grid_manifest

out.write_text(build_grid_manifest(UniformGrid(), **GOLDEN_KW).dumps(), encoding="utf-8")
print("wrote", out)
