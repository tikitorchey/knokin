"""EXR reading. OpenEXR (pip) is imported lazily so the rest of the packer works without it."""
from __future__ import annotations

from pathlib import Path

import numpy as np


def read_exr_rgba(path: Path) -> np.ndarray:
    import OpenEXR  # noqa: PLC0415

    ch = OpenEXR.File(str(path)).channels()
    if "RGBA" in ch:
        px = ch["RGBA"].pixels
    elif all(k in ch for k in "RGBA"):
        px = np.stack([ch[k].pixels for k in "RGBA"], axis=-1)
    else:
        raise ValueError(f"{path}: needs R,G,B,A channels, found {sorted(ch.keys())}")
    return np.asarray(px, dtype=np.float32)
