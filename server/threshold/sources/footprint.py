"""Check a scan's compass rotation and position against the Vexcel building footprint, and refine both.

`fit(plan, fp)` turns and shifts the plan outline (all floors, wall centre lines) to best overlap the footprint
(the roof outline seen from above), starting from the georef convention. The footprint includes eaves, so a
perfect plan still leaves a residual of roughly half a metre; a residual over MAX_RESIDUAL_M or an overlap under
MIN_IOU means the scan is not this building (an apartment unit inside a tower) or the fit failed.
"""
from __future__ import annotations

import json
import math

import numpy as np
from shapely import wkt
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..geometry import georef
from ..geometry._plan import polygons
from .upstream import cache_path, write_atomic

MIN_IOU = 0.6         # below this the outline and the footprint are not the same building
MAX_RESIDUAL_M = 1.5  # median distance from the fitted outline to the footprint edge
MAX_ROTATION_DEG = 20  # a refit turning more than this is a wrong match, not a correction
FIT_VERSION = 1


def plan_outline(plan: dict) -> Polygon | None:
    """Union of every room outline on every floor, small gaps between rooms closed, largest part."""
    polys = [p.buffer(0.15, join_style="mitre") for p in polygons(plan).values() if p is not None]
    if not polys:
        return None
    shape = unary_union(polys).buffer(-0.15, join_style="mitre")
    part = max(getattr(shape, "geoms", [shape]), key=lambda g: g.area)
    return Polygon(part.exterior) if part.area > 1 else None


def footprint_enu(plan: dict, footprint_wkt: str | None = None) -> Polygon | None:
    """The Vexcel primary-structure footprint in east/north metres about the scan's geo anchor."""
    g = plan.get("geo") or {}
    if g.get("lat") is None:
        return None
    if footprint_wkt is None:
        from ..aerial import site
        footprint_wkt = site.site_facts(g["lat"], g["lon"]).get("footprint")
    if not footprint_wkt:
        return None
    shape = wkt.loads(footprint_wkt)
    part = max(getattr(shape, "geoms", [shape]), key=lambda p: p.area)
    m, nr = georef._radii(g["lat"])
    k = nr * math.cos(math.radians(g["lat"]))
    return Polygon([(math.radians(lon - g["lon"]) * k, math.radians(lat - g["lat"]) * m)
                    for lon, lat in part.exterior.coords])


def outline_enu(plan: dict, outline: Polygon, **conv) -> Polygon:
    return Polygon([georef.to_enu(plan, x, y, **conv) for x, y in outline.exterior.coords])


def _iou(a: Polygon, b: Polygon) -> float:
    u = a.union(b).area
    return a.intersection(b).area / u if u else 0.0


def residual_m(a: Polygon, b: Polygon, step: float = 0.25) -> float:
    """Median distance from points every `step` metres along a's edge to b's edge."""
    ring, edge = a.exterior, b.exterior
    n = max(8, int(ring.length / step))
    return float(np.median([edge.distance(ring.interpolate(i / n, normalized=True)) for i in range(n)]))


def overlap(plan: dict, fp: Polygon, **conv) -> dict:
    o = outline_enu(plan, plan_outline(plan), **conv)
    return {"iou": _iou(o, fp), "offset_m": o.centroid.distance(fp.centroid)}


def fit(plan: dict, fp: Polygon, max_rot: float = MAX_ROTATION_DEG, **conv) -> dict:
    """Best rotation (degrees, counter-clockwise, about the outline's centroid) and shift (east, north metres)
    applied after the georef convention. Coarse grid over rotation with centroids aligned, then a local search."""
    base = outline_enu(plan, plan_outline(plan), **conv)
    c = base.centroid

    def place(rot: float, dx: float, dy: float) -> Polygon:
        return translate(rotate(base, rot, origin=c), dx, dy)

    def centred(rot: float) -> tuple[float, float, float]:
        r = rotate(base, rot, origin=c)
        return rot, fp.centroid.x - r.centroid.x, fp.centroid.y - r.centroid.y

    best = max((centred(r) for r in np.arange(-max_rot, max_rot + 0.1, 1.0)),
               key=lambda p: _iou(place(*p), fp))
    score, step = _iou(place(*best), fp), [1.0, 0.5, 0.5]
    for _ in range(60):  # pattern search on (rotation, dx, dy)
        moved = False
        for i in range(3):
            for sgn in (1, -1):
                cand = list(best)
                cand[i] += sgn * step[i]
                if abs(cand[0]) > max_rot:
                    continue
                s = _iou(place(*cand), fp)
                if s > score + 1e-5:
                    best, score, moved = tuple(cand), s, True
        if not moved:
            step = [s / 2 for s in step]
            if step[1] < 0.02:
                break
    rot, dx, dy = best
    placed = place(rot, dx, dy)
    return {"rotation_deg": round(float(rot), 2), "shift_m": round(math.hypot(dx, dy), 2),
            "shift_enu": [round(float(dx), 2), round(float(dy), 2)], "pivot_enu": [round(c.x, 2), round(c.y, 2)],
            "iou": round(score, 3), "iou_before": round(_iou(base, fp), 3),
            "residual_m": round(residual_m(placed, fp), 2), "method": "footprint_iou"}


def verdict(f: dict | None) -> bool:
    return bool(f) and f["iou"] >= MIN_IOU and f["residual_m"] <= MAX_RESIDUAL_M \
        and abs(f["rotation_deg"]) < MAX_ROTATION_DEG - 0.5


def scan_fit(plan: dict, fetch: bool = True) -> dict | None:
    """The footprint fit for a scan, cached on disk. None when the scan has no geo or no outline, or when
    fetch is False and nothing is cached. Never raises for an upstream failure (returns None)."""
    f = cache_path("georef_fit", f"{plan['sid']}.json")
    if f.exists():
        hit = json.loads(f.read_text())
        if hit.get("version") == FIT_VERSION:
            return hit["fit"]
    if not fetch or not (plan.get("geo") or {}).get("lat") or plan_outline(plan) is None:
        return None
    try:
        fp = footprint_enu(plan)
    except Exception:  # Vexcel down or no key: the plan still loads, unverified
        return None
    out = fit(plan, fp) if fp is not None else None
    write_atomic(f, json.dumps({"version": FIT_VERSION, "fit": out}).encode())
    return out
