"""What a point sees through the wall graph: a 2D visibility polygon (isovist), cut to a field of view and range."""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import Polygon

from .plan2d import Segs, crossings, ray_hits

RAY_STEP_DEG = 1.0


def isovist(p, segs: Segs, *, heading_deg: float = 0.0, fov_deg: float = 360.0, max_range: float = 10.0,
            solid: np.ndarray | None = None) -> Polygon:
    """Polygon of the floor visible from p: one ray per degree across the field of view, each stopped at the first
    solid wall piece (doorways are gaps). Angles are in the scan frame, counter-clockwise from +x."""
    n = max(8, int(math.ceil(fov_deg / RAY_STEP_DEG)))
    full = fov_deg >= 360
    ang = np.radians(heading_deg + np.linspace(-fov_deg / 2, fov_deg / 2, n, endpoint=not full))
    dirs = np.column_stack([np.cos(ang), np.sin(ang)])
    d = ray_hits(p, dirs, segs, max_range, solid)
    pts = np.asarray(p, float) + dirs * d[:, None]
    ring = [tuple(x) for x in pts] if full else [tuple(p), *map(tuple, pts)]
    poly = Polygon(ring)
    return poly if poly.is_valid else poly.buffer(0)


def sees(p, targets: np.ndarray, segs: Segs, *, heading_deg: float = 0.0, fov_deg: float = 360.0,
         max_range: float = 10.0, solid: np.ndarray | None = None, short_m: float = 0.05) -> np.ndarray:
    """Booleans: is each target point in view (within range and field of view, no solid wall piece between)?
    Each sight line stops `short_m` before its target so a point on a wall (a door) is not hidden by that wall."""
    p = np.asarray(p, float)
    t = np.asarray(targets, float).reshape(-1, 2)
    v = t - p
    dist = np.hypot(v[:, 0], v[:, 1])
    ok = dist <= max_range
    if fov_deg < 360:
        off = (np.degrees(np.arctan2(v[:, 1], v[:, 0])) - heading_deg + 180) % 360 - 180
        ok &= np.abs(off) <= fov_deg / 2
    short = p + v * np.clip((dist - short_m) / np.maximum(dist, 1e-9), 0, 1)[:, None]
    sel = np.ones(len(segs), bool) if solid is None else solid
    sub = Segs(segs.a[sel], segs.b[sel], segs.kind[sel], segs.thickness[sel], [w for w, s in zip(segs.wall, sel) if s])
    return ok & ~crossings(p, short, sub).any(axis=1)
