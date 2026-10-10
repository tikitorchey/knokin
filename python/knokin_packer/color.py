"""Pixel math (NumPy only): scene-linear premultiplied float RGBA -> 8-bit sRGB RGBA.

Blender writes transparent-film EXR as scene-linear, alpha-associated (premultiplied) data. The view
transform must be 'Standard' for the sRGB OETF below to match what was previewed in Blender.
"""
from __future__ import annotations

import numpy as np

PREMULTIPLIED, STRAIGHT = "premultiplied", "straight"
_EPS = 1e-6


def srgb_oetf(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def encode_rgba8(rgba: np.ndarray, alpha_mode: str) -> np.ndarray:
    """(h,w,4) linear premultiplied float -> (h,w,4) uint8, sRGB-encoded, in the requested alpha mode.

    Colour is un-premultiplied before the OETF (the curve is non-linear, so it must act on straight
    colour), then re-multiplied by alpha when the output is 'premultiplied'.
    """
    if alpha_mode not in (PREMULTIPLIED, STRAIGHT):
        raise ValueError(f"unknown alpha mode {alpha_mode!r}")
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError(f"expected (h,w,4), got {rgba.shape}")
    f = np.nan_to_num(rgba.astype(np.float32), nan=0.0, posinf=1.0, neginf=0.0)
    a = np.clip(f[..., 3:4], 0.0, 1.0)
    straight = np.where(a > _EPS, f[..., :3] / np.maximum(a, _EPS), 0.0)
    enc = srgb_oetf(straight)
    if alpha_mode == PREMULTIPLIED:
        enc = enc * a
    out = np.concatenate([enc, a], axis=-1)
    return np.rint(out * 255.0).astype(np.uint8)


def bleed_straight(rgba8: np.ndarray, iters: int) -> np.ndarray:
    """Straight-alpha only: fill the colour of fully transparent pixels from their opaque neighbours.

    Invisible pixels keep alpha 0, so the picture is unchanged; but the codec (chroma subsampling, DCT ringing) then
    blends edge colour with a smooth continuation instead of with black, which removes dark/odd fringes at the
    silhouette. `iters` = how many pixels outward to fill (each pass grows the filled area by 1px).
    """
    if iters <= 0:
        return rgba8
    out = rgba8.copy()
    col = out[..., :3].astype(np.float32)
    known = (out[..., 3] > 0).astype(np.float32)
    if known.all() or not known.any():
        return out
    h, w = known.shape

    def box(x: np.ndarray) -> np.ndarray:  # 3x3 sum, zero padded
        p = np.pad(x, [(1, 1), (1, 1)] + [(0, 0)] * (x.ndim - 2))
        return sum(p[dy : dy + h, dx : dx + w] for dy in range(3) for dx in range(3))

    for _ in range(iters):
        wsum = box(known)
        fill = (known == 0) & (wsum > 0)
        if not fill.any():
            break
        avg = box(col * known[..., None]) / np.maximum(wsum, 1)[..., None]
        col[fill] = avg[fill]
        known = np.where(fill, 1.0, known)
    out[..., :3] = np.rint(col).astype(np.uint8)
    return out
