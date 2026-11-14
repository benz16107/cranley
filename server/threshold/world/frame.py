"""One rigid transform between the scan frame and east/north metres about the scan's geo anchor.

`geometry.georef.to_enu` applies the convention and then the verified footprint refit, point by point. A 3D scene
needs the same thing as one rotation and one translation, so the two steps are composed here:
    enu = Rz(rot_deg) p + t
"""
from __future__ import annotations

import math

from ..geometry import georef


def scan_to_enu(plan: dict) -> dict | None:
    """{rot_deg, t: [east, north], verified} or None when the scan has no geocoordinates."""
    g = georef._geo(plan)
    if g is None:
        return None
    _, _, yaw, (tx, ty) = g
    rot, t = georef.YAW_SIGN * yaw, (tx, ty)
    f = (plan.get("geo") or {}).get("fit")
    verified = bool(f and f.get("verified"))
    if verified:  # R_f (R_y p + t - pivot) + pivot + shift
        (px, py), (dx, dy) = f["pivot_enu"], f["shift_enu"]
        ex, ey = georef._rot(t[0] - px, t[1] - py, f["rotation_deg"])
        rot, t = rot + f["rotation_deg"], (ex + px + dx, ey + py + dy)
    return {"rot_deg": rot, "t": [t[0], t[1]], "verified": verified}


def enu_to_lonlat(lat0: float, lon0: float, e: float, n: float) -> tuple[float, float]:
    m, nr = georef._radii(lat0)
    return lon0 + math.degrees(e / (nr * math.cos(math.radians(lat0)))), lat0 + math.degrees(n / m)


def lonlat_to_enu(lat0: float, lon0: float, lon: float, lat: float) -> tuple[float, float]:
    m, nr = georef._radii(lat0)
    return math.radians(lon - lon0) * nr * math.cos(math.radians(lat0)), math.radians(lat - lat0) * m
