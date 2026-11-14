"""The yard from the air: area off the building footprint, how much of it is flat, tree shade, a fence, the pool,
the nearest busy road and the next building. Vexcel for the parcel, footprint, heights and photo; OpenStreetMap
(threshold.nearby) for roads and neighbours. Every request is cached by the engines it goes through."""
from __future__ import annotations

import math

import numpy as np
from shapely.geometry import MultiPoint, Point

from ... import nearby
from .._site import fact, footprint, heights, metres, parcel, to_m

MAX_POINTS = 180        # height samples per yard: 3 Vexcel requests per kind
FLAT_PCT = 5.0          # ADA 2010 403.3: steeper than 1:20 a walking surface counts as a ramp
STEEP_PCT = 15.0
CANOPY_M = 2.5          # surface above ground by this much, outside the house: a tree (or a shed; labelled)
STREET = {"residential", "unclassified", "tertiary", "secondary", "primary", "living_street", "trunk"}


def yard_shape(s):
    """(yard polygon in local metres, house polygon in local metres, parcel area m2) or None."""
    fp, pc = footprint(s), parcel(s)
    if fp is None or pc is None:
        return None
    house = metres(fp, s.lat).buffer(0)
    lot = metres(pc, s.lat).buffer(0)
    y = lot.difference(house.buffer(0.5))
    return (y if not y.is_empty else None), house, lot.area


def grid(poly, n_max: int = MAX_POINTS) -> tuple[np.ndarray, float]:
    """Points on a square grid inside `poly` (local metres), at most about n_max, and the spacing."""
    step = max(2.0, math.sqrt(poly.area / n_max))
    x0, y0, x1, y1 = poly.bounds
    xs, ys = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(y0 + step / 2, y1, step))
    pts = np.column_stack([xs.ravel(), ys.ravel()])
    import shapely
    keep = shapely.contains_xy(poly, pts[:, 0], pts[:, 1])
    return pts[keep], step


def slopes(pts: np.ndarray, z: np.ndarray, step: float) -> np.ndarray:
    """Slope in percent at each grid point from its neighbours one step away in x and y (central differences where
    both exist). NaN where a point has no neighbour on an axis."""
    key = {(round(x / step), round(y / step)): i for i, (x, y) in enumerate(pts)}
    out = np.full(len(pts), np.nan)
    for (i, j), k in key.items():
        g = []
        for (a, b) in (((i + 1, j), (i - 1, j)), ((i, j + 1), (i, j - 1))):
            p, m = key.get(a), key.get(b)
            if p is not None and m is not None:
                g.append((z[p] - z[m]) / (2 * step))
            elif p is not None:
                g.append((z[p] - z[k]) / step)
            elif m is not None:
                g.append((z[k] - z[m]) / step)
            else:
                g.append(None)
        if None not in g:
            out[k] = 100 * math.hypot(*g)
    return out


def terrain(s, yard) -> dict | None:
    """Flat, moderate and steep shares of the yard, relief, and tree canopy share, from Vexcel ground (dtm) and
    surface (dsm) heights on a grid."""
    pts, step = grid(yard)
    if len(pts) < 6:
        return None
    back = to_m(s.lat)[1]
    ll = [back(x, y) for x, y in pts]
    dtm = np.array(heights("dtm", ll), float)
    dsm = np.array(heights("dsm", ll), float)
    sl = slopes(pts, dtm, step)
    ok = ~np.isnan(sl)
    n = max(int(ok.sum()), 1)
    canopy = (dsm - dtm) > CANOPY_M
    flat = ok & (sl < FLAT_PCT)
    flat_pts = pts[flat]
    return {"points": len(pts), "step_m": round(step, 2),
            "flat_share": float((ok & (sl < FLAT_PCT)).sum() / n),
            "steep_share": float((ok & (sl >= STEEP_PCT)).sum() / n),
            "median_slope_pct": float(np.nanmedian(sl)) if ok.any() else None,
            "relief_m": float(np.nanmax(dtm) - np.nanmin(dtm)),
            "canopy_share": float(canopy.mean()),
            "flat_area_m2": float(flat.sum() * step * step),
            "flat_center": back(*MultiPoint(flat_pts.tolist()).centroid.coords[0]) if len(flat_pts) else None}


def fence_from_photo(s, use_vision: bool) -> dict | None:
    """Whether a fence or wall line closes the back yard, read by the vision model from a parcel-sized orthophoto."""
    if not use_vision:
        return None
    from ...aerial import site as aerial
    from ...vision.model import CONFIDENCE, ask
    o = aerial.ortho(s.lat, s.lon, 50, 1024)
    q = {"type": "string", "enum": ["yes", "no", "unclear"]}
    schema = {"type": "object", "additionalProperties": False, "required": ["back_yard_fenced", "gaps", "note", "confidence"],
              "properties": {"back_yard_fenced": q, "gaps": q, "note": {"type": "string"}, "confidence": CONFIDENCE}}
    prompt = ("North-up aerial photo, 50 m across, centred on a house. back_yard_fenced: does a fence or wall line run "
              "around the yard behind the house (the side away from the street), as thin lines along the lot edges? gaps: "
              "is there a visible opening in that line (a missing side, an open gate, a driveway)? Answer 'unclear' when "
              "trees or shadows hide the lot edges. A note of a few words says what you see.")
    return ask([o.image], prompt, schema, key=f"pet_fit/fence/{s.lat:.6f},{s.lon:.6f}")


def street_side(s, house) -> tuple | None:
    """The nearest street centre line (local metres) and its name, to tell the back of the lot from the front."""
    from shapely.geometry import LineString
    try:
        a = nearby.area(s.lat, s.lon)
    except RuntimeError:
        return None
    fwd = to_m(s.lat)[0]
    best = None
    for w in a.ways:
        if w["tags"].get("highway") not in STREET or len(w["pts"]) < 2:
            continue
        line = LineString([fwd(*p) for p in w["pts"]])
        d = line.distance(house)
        if best is None or d < best[0]:
            best = (d, line, w["tags"].get("name"))
    return best


def back_yard(yard, house, street) -> object:
    """The part of the yard farther from the street than the house's centre: where a dog actually goes."""
    if street is None:
        return yard
    line = street[1]
    back = yard.difference(line.buffer(line.distance(house.centroid), quad_segs=4))
    return back if back.area > 1 else yard


def rank_doors(doors: list[dict], street, fwd) -> list[dict]:
    """Doors whose outside point is farther from the street come first (a back door), when the plan is placed."""
    if street is None:
        return doors
    for d in doors:
        d["street_m"] = street[1].distance(Point(fwd(*d["ll"]))) if d.get("ll") else None
    return sorted(doors, key=lambda d: -(d.get("street_m") or -1))


def pool_info(s) -> dict:
    enclosed = sum(fact(s, f"pool_{t}_enclosed", 0) or 0 for t in ("in_ground", "above_ground", "hot_tub"))
    return {"pool": fact(s, "pool"), "area": fact(s, "pool_area"), "enclosed": enclosed > 0}
