"""Coordinate convention (docs/dev/spec-manifest-v0.md, section 2).

World: Blender world coordinates, +Z up, right-handed. Angles in degrees.
theta (azimuth): 0 when the camera is on the -Y side, increasing counter-clockwise
seen from +Z. phi (elevation): 0 horizontal, positive upward.
"""
from __future__ import annotations

import math

Vec3 = tuple[float, float, float]


def norm_theta(theta: float) -> float:
    """Normalize to [0, 360)."""
    t = math.fmod(theta, 360.0)
    if t < 0:
        t += 360.0
    # fmod of tiny negatives can round up to exactly 360.0
    return 0.0 if t >= 360.0 else t


def direction(theta: float, phi: float) -> Vec3:
    """Unit vector from the pivot to the camera."""
    t, p = math.radians(theta), math.radians(phi)
    return (math.cos(p) * math.sin(t), -math.cos(p) * math.cos(t), math.sin(p))


def camera_position(theta: float, phi: float, distance: float, pivot: Vec3 = (0.0, 0.0, 0.0)) -> Vec3:
    d = direction(theta, phi)
    return (pivot[0] + distance * d[0], pivot[1] + distance * d[1], pivot[2] + distance * d[2])


def look_direction(theta: float, phi: float) -> Vec3:
    """Camera forward vector (towards the pivot). Roll is 0: up is +Z."""
    d = direction(theta, phi)
    return (-d[0], -d[1], -d[2])


def angular_diff(a: float, b: float) -> float:
    """Smallest absolute difference between two theta values, in [0, 180]."""
    d = abs(norm_theta(a) - norm_theta(b))
    return min(d, 360.0 - d)
