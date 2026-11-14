"""What stands between a point and the sun: the horizon of a surface model (Vexcel's DSM, which holds roofs, trees
and the ground) seen from that point, as the highest elevation angle in each compass direction.

A horizon is computed once per point; testing a sun position against it is then a lookup, so a whole year of sun
costs nothing more. The DSM holds trees as they stood on the capture day, leaves and all, so deciduous trees
shade in winter here as in summer, and eaves narrower than a grid cell or two do not appear.
"""
from __future__ import annotations

import numpy as np

from ..world import terrain

BIN_DEG = 5.0          # azimuth resolution of a horizon
MAX_DIST_M = 110.0     # beyond this a 10 m tree subtends under 5 degrees


def bins() -> np.ndarray:
    return np.arange(0, 360, BIN_DEG) + BIN_DEG / 2


def grid(lat: float, lon: float, size_m: float = 240, n: int = 384) -> dict:
    """The surface model round a point (Vexcel dsm/extract, one cached request), 0.625 m cells by default."""
    return terrain.grid(lat, lon, size_m, n)


def horizon(g: dict, e: float, n: float, z: float, start_m: float = 2.0, max_m: float = MAX_DIST_M,
            facing: float | None = None, half_width: float = 95.0) -> np.ndarray:
    """Elevation angle in degrees of the highest surface seen from (e, n, z) in each azimuth bin (see `bins`),
    in the grid's east/north frame and height datum. Samples nearer than `start_m` are skipped: they are the
    point's own wall or roof edge, blurred by the grid. With `facing`, only bins within `half_width` of it are
    traced (a window sees nothing behind its wall); the rest are 90. NaN cells (no data) never block."""
    cell = (g["bounds_enu"][2] - g["bounds_enu"][0]) / g["heights"].shape[1]
    d = np.arange(start_m, max_m, cell / 2)
    az = bins()
    out = np.full(az.shape, 90.0)
    use = np.ones(az.shape, bool) if facing is None else np.abs((az - facing + 180) % 360 - 180) <= half_width
    a = np.radians(az[use])[:, None]
    h = terrain.sample(g, e + d[None, :] * np.sin(a), n + d[None, :] * np.cos(a))
    ang = np.degrees(np.arctan2(h - z, d[None, :]))
    ang = np.where(np.isfinite(ang), ang, -90.0)
    out[use] = np.maximum(ang.max(axis=1), 0.0)
    return out


def blocked(hz: np.ndarray, sun_az, sun_el) -> np.ndarray:
    """True where the sun at (az, el) is below the horizon `hz` (from `horizon`)."""
    i = (np.asarray(sun_az) % 360 // BIN_DEG).astype(int) % len(hz)
    return np.asarray(sun_el) <= hz[i]


def local_ground(g: dict, e: float, n: float, radius_m: float = 10.0, pct: float = 5) -> float:
    """The ground near a point: a low percentile of the surface model within `radius_m` (roofs and trees are the
    high end). Falls back to the grid's own ground estimate."""
    west, south, east, north = g["bounds_enu"]
    h, w = g["heights"].shape
    ys, xs = np.mgrid[0:h, 0:w]
    ce = west + (xs + 0.5) / w * (east - west)
    cn = north - (ys + 0.5) / h * (north - south)
    near = (np.hypot(ce - e, cn - n) < radius_m) & np.isfinite(g["heights"])
    return float(np.percentile(g["heights"][near], pct)) if near.sum() > 10 else g["ground_m"]
