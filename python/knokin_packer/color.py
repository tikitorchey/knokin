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
