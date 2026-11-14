"""Vexcel's surface model (roofs, trees, ground) around a point as a height grid in east/north metres.

One `dsm/extract` request per patch, resampled by Vexcel to the size asked for and cached by the Vexcel client.
The raster comes back north-up in Web Mercator, which over a few hundred metres is a plain rectangle in east/north.
"""
from __future__ import annotations

import base64

import numpy as np

from ..aerial import site, vexcel
from . import geotiff
from .frame import lonlat_to_enu

GROUND_PERCENTILE = 5   # the ground is the low end of the surface near the building; roofs and trees are the rest
GROUND_RADIUS_M = 35


def grid(lat: float, lon: float, size_m: float = 320, n: int = 256) -> dict:
    """heights (n x n float32, row 0 north, NaN where Vexcel has none), bounds_enu (west, south, east, north) and
    ground_m, the surface model's own height of the ground at the point (its datum, used only as a difference)."""
    data, _ = vexcel.call("GET", "dsm/extract", params={
        "wkt": site.square(lat, lon, size_m), "srid": 4326, "destination-dimensions": f"{n},{n}"})
    r = geotiff.read(data)
    h, w = r.heights.shape
    west, north = lonlat_to_enu(lat, lon, *site._unmerc(r.x0, r.y0))
    east, south = lonlat_to_enu(lat, lon, *site._unmerc(r.x0 + w * r.dx, r.y0 - h * r.dy))
    ys, xs = np.mgrid[0:h, 0:w]
    e = west + (xs + 0.5) / w * (east - west)
    nn = north - (ys + 0.5) / h * (north - south)
    near = (np.hypot(e, nn) < GROUND_RADIUS_M) & np.isfinite(r.heights)
    ground = float(np.percentile(r.heights[near], GROUND_PERCENTILE)) if near.any() else float(np.nanmin(r.heights))
    return {"heights": r.heights, "bounds_enu": (west, south, east, north), "ground_m": ground}


def sample(g: dict, e: np.ndarray, n: np.ndarray) -> np.ndarray:
    """Surface height at east/north points, nearest cell; NaN outside the grid."""
    west, south, east, north = g["bounds_enu"]
    h, w = g["heights"].shape
    c = np.floor((np.asarray(e) - west) / (east - west) * w).astype(int)
    r = np.floor((north - np.asarray(n)) / (north - south) * h).astype(int)
    ok = (c >= 0) & (c < w) & (r >= 0) & (r < h)
    out = np.full(np.shape(e), np.nan, np.float32)
    out[ok] = g["heights"][r[ok], c[ok]]
    return out


def ortho_bounds_enu(lat: float, lon: float, size_m: float, px: int) -> tuple[float, float, float, float]:
    """Where the orthophoto `/api/aerial/ortho` serves for the same arguments sits, in east/north metres."""
    w, s, e, n = site.ortho(lat, lon, size_m, px).bounds
    return (*lonlat_to_enu(lat, lon, w, s), *lonlat_to_enu(lat, lon, e, n))


def encode(g: dict) -> dict:
    """The grid for the browser: centimetres above ground_m as little-endian int16, base64. -32768 is missing."""
    cm = np.where(np.isfinite(g["heights"]), np.clip(np.round((g["heights"] - g["ground_m"]) * 100), -32767, 32767), -32768)
    h, w = g["heights"].shape
    return {"width": w, "height": h, "bounds_enu": [round(v, 3) for v in g["bounds_enu"]],
            "heights_cm_b64": base64.b64encode(cm.astype("<i2").tobytes()).decode(),
            "cell_m": round((g["bounds_enu"][2] - g["bounds_enu"][0]) / w, 3)}

