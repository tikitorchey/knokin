"""8-bit RGBA -> AVIF via Pillow (native AVIF), plus alpha-correct downscaling."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class AvifSettings:
    quality: int = 60
    speed: int = 6
    subsampling: str = "4:2:0"  # '4:4:4' avoids chroma bleed at alpha edges; costs size (to be measured)
    codec: str = "auto"


def downscale(rgba8: np.ndarray, width: int, premultiplied: bool) -> np.ndarray:
    """Resize in premultiplied space so transparent pixels never bleed colour into edges."""
    h, w = rgba8.shape[:2]
    height = max(1, round(h * width / w))
    if premultiplied:
        im = Image.frombuffer("RGBa", (w, h), np.ascontiguousarray(rgba8).tobytes(), "raw", "RGBa", 0, 1)
    else:
        im = Image.fromarray(rgba8, "RGBA").convert("RGBa")
    im = im.resize((width, height), Image.Resampling.LANCZOS)
    if premultiplied:
        return np.frombuffer(im.tobytes(), dtype=np.uint8).reshape(height, width, 4).copy()
    return np.asarray(im.convert("RGBA"), dtype=np.uint8).copy()


def save_avif(rgba8: np.ndarray, path: Path, s: AvifSettings, premultiplied: bool) -> None:
    im = Image.fromarray(np.ascontiguousarray(rgba8), "RGBA")
    im.save(
        path, format="AVIF", quality=s.quality, speed=s.speed, subsampling=s.subsampling, codec=s.codec,
        alpha_premultiplied=premultiplied,
    )
