"""Shared helpers for the access tools (step_free_route, turning_space, bathroom_clearance, stairs_count,
aging_in_place, furniture_fit, stretcher_route, robot_fit, curb_to_door, measure_search).

Nothing here measures on its own: geometry comes from `threshold.geometry`, panoramas from `threshold.vision`.
This module picks the entrance, reads sills against floor levels, asks the panorama about doorways whose
recorded width is a data error, and holds the standards every tool cites.
"""
from __future__ import annotations

import math
import statistics

from ...geometry import room_graph
from ...geometry._plan import IMPLAUSIBLE_DOOR_M, cached, floor_z, implausible
from .. import Source

GEO = Source(layer="matterport", method="geometry", confidence="medium",
             note="Matterport wall graph, empty rooms; door widths are the opening in the wall")
GEO_LOW = Source(layer="matterport", method="geometry", confidence="low",
                 note="Matterport wall graph; part of this answer rests on an assumption named in the result")
VISION = Source(layer="model", method="vision", confidence="low", note="Vision model reading the panoramas")

# Checked against the published texts on 2026-11-13 (ADA: access-board.gov/ada; FHA Design Manual, HUD 1998;
# CDC STEADI "Check for Safety" 2017; IBC 2018 3002.4).
STD = {
    "door": "ADA 2010 404.2.3: 32 in (815 mm) clear minimum; FHA Design Manual Req. 3: nominal 32 in clear",
    "route": "ADA 2010 403.5.1: 36 in (915 mm) walking surface; FHA Design Manual Req. 4: 36 in route",
    "level": "ADA 2010 303.2 to 303.4: 1/4 in may be vertical, to 1/2 in (13 mm) beveled, more must be ramped",
    "turn": "ADA 2010 304.3.1: 60 in (1525 mm) circle; 304.3.2 allows a T in a 60 in square",
    "wc_ada": "ADA 2010 604.3.1: 60 in (1525 mm) from the side wall by 56 in (1420 mm) from the rear wall",
    "wc_fha": "FHA Design Manual Req. 7: one of 48 x 56 in, 48 x 66 in or 60 x 56 in clear at the toilet",
    "wc_center": "ADA 2010 604.2: toilet centreline 16 to 18 in (405 to 455 mm) from the side wall",
    "bar_side": "ADA 2010 604.5.1: side bar 42 in (1065 mm) long, from 12 in off the rear wall to 54 in (1370 mm)",
    "bar_rear": "ADA 2010 604.5.2: rear bar 36 in (915 mm) long",
    "bars_fha": "FHA Design Manual Req. 6: walls reinforced for grab bars at toilet, tub and shower",
    "door_space": "FHA Design Manual Req. 7: 30 x 48 in (760 x 1220 mm) clear floor space outside the door swing",
    "tub": "ADA 2010 607.2: clearance 30 in (760 mm) wide along the full length of the tub",
    "shower": "ADA 2010 608.2.1 transfer shower 36 x 36 in; 608.2.2 roll-in 30 x 60 in; 608.7 threshold 1/2 in",
    "steadi": "CDC STEADI 'Check for Safety' (2017)",
    "stretcher": "IBC 3002.4: ambulance stretcher 24 x 84 in (610 x 2134 mm), flat",
}
IN = 0.0254
STEP_M = 0.013          # ADA 303.3: a level change over 1/2 in must be ramped
SILL_NOISE_M = 0.04     # sill heights scatter about 4 cm on flat floors (geometry wheelchair pack)
STAIR_M = 0.4           # a sill this far off its floor is a stair or a split level, not a threshold
RISER_M = 0.178         # 7 in: a typical residential riser, used only to estimate a step count
LIVING = ("Bedroom", "Bathroom", "Kitchen", "Living Room", "Dining Room", "Family Room")
ENTRY_ROOMS = ("Entrance", "Hallway", "Living Room", "Family Room", "Dining Room", "Kitchen")


def quality(plan: dict) -> dict:
    """plan.quality, or the same booleans worked out here for plans normalized before it existed."""
    q = plan.get("quality")
    if q:
        return q
    walls = [w for w in plan.get("walls") or [] if w.get("type") == "wall"]
    rooms = [r for r in plan.get("rooms") or [] if r.get("label") != "Void"]
    return {"walls": len(walls) >= 3, "openings": bool(plan.get("openings")) and len(walls) >= 3,
            "polygons": any(r.get("polygon") for r in rooms), "labels": sum(bool(r.get("label")) for r in rooms)
            >= 0.5 * max(len(rooms), 1), "georef": bool((plan.get("geo") or {}).get("lat")), "notes": []}


def graph(plan: dict) -> dict:
    return cached(plan, "graph", lambda: room_graph(plan))


def label(room: dict | None) -> str:
    return (room or {}).get("label") or "Unlabelled room"


def rooms(plan: dict) -> dict[str, dict]:
    return {r["id"]: r for r in plan.get("rooms") or []}


def floor_name(plan: dict, floor_id: str) -> str:
    fl = next((f for f in plan.get("floors") or [] if f["id"] == floor_id), None)
    if not fl:
        return "floor ?"
    lab = str(fl.get("label") or (fl.get("sequence") or 0) + 1)
    return lab.lower() if lab.lower().startswith(("floor", "level", "basement")) else f"floor {lab}"


def elevations(plan: dict) -> dict[str, float]:
    """Height of each floor above the lowest, from plan.floors[].elevation, else from the panorama heights."""
    out = {f["id"]: f.get("elevation") for f in plan.get("floors") or []}
    if all(v is not None for v in out.values()):
        return out
    zs: dict[str, list[float]] = {}
    for p in plan.get("panos") or []:
        zs.setdefault(p.get("floor"), []).append(p["position"][2])
    med = {f: statistics.median(v) for f, v in zs.items() if f}
    base = min(med.values(), default=0.0)
    return {f: (v if v is not None else med.get(f, base) - base) for f, v in out.items()}


def entrances(plan: dict) -> list[dict]:
    """Doorways with a room on one side only, main entrance first: on the lowest floor, into an entry-type room,
    then the widest. A one-sided doorway may lead outside or to an unscanned room; the plan cannot tell which."""
    g = graph(plan)
    if not g["available"]:
        return []
    rs, el = rooms(plan), elevations(plan)
    real = [e for e in g["entrances"] if e["kind"] != "invisible" and rs.get(e["room"], {}).get("label") != "Closet"]

    def rank(e):
        lab = rs.get(e["room"], {}).get("label")
        return (el.get(e["floor"]) or 0.0, lab not in ENTRY_ROOMS, ENTRY_ROOMS.index(lab) if lab in ENTRY_ROOMS else 9,
                implausible(e), -(e.get("width") or 0))
    return sorted(real, key=rank)


def pick_entrance(plan: dict, opening: str | None = None) -> dict | None:
    es = entrances(plan)
    if opening:
        return next((e for e in es if e["opening"] == opening), None)
    return es[0] if es else None


def start_point(plan: dict, ent: dict) -> list[float]:
    """A point 0.3 m inside the entrance door, in its room, for geometry.route."""
    from ...geometry._plan import polygons
    poly = polygons(plan).get(ent["room"])
    cx, cy = ent["center"]
    if poly is None:
        return [cx, cy]
    from shapely.geometry import Point
    best = min(((cx + dx * 0.3, cy + dy * 0.3) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))),
               key=lambda p: poly.distance(Point(p)))
    return list(best)


def sill_step(plan: dict, link: dict) -> float | None:
    """Height of a doorway's sill above or below its storey's floor level (sills are absolute scan z)."""
    if link.get("sill") is None:
        return None
    return abs(link["sill"] - cached(plan, "floor_z", lambda: floor_z(plan)).get(link["floor"], 0.0))


def step_kind(step: float | None) -> str:
    """'none', 'step' (a threshold or single step over the scan's noise) or 'stair' (a storey change)."""
    if step is None or step <= STEP_M + SILL_NOISE_M:
        return "none"
    return "stair" if step > STAIR_M else "step"


def links_of(plan: dict) -> dict[str, dict]:
    g = graph(plan)
    return {d["opening"]: d for d in g.get("links", []) + g.get("entrances", []) if d.get("opening")} \
        if g["available"] else {}


def fmt(x: float | None, unit: str = "m", nd: int = 2) -> str:
    return "?" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f} {unit}".strip()


__all__ = ["GEO", "GEO_LOW", "IMPLAUSIBLE_DOOR_M", "IN", "LIVING", "RISER_M", "STD", "STEP_M", "VISION",
           "elevations", "entrances", "floor_name", "fmt", "graph", "implausible", "label", "links_of",
           "pick_entrance", "quality", "rooms", "sill_step", "start_point", "step_kind"]


def room_angle(poly) -> float:
    """Direction of the room's longest edge, radians: clear floor spaces are laid square to the walls."""
    cs = list(poly.exterior.coords)
    a, b = max(zip(cs, cs[1:]), key=lambda e: math.dist(*e))
    return math.atan2(b[1] - a[1], b[0] - a[0])


def rect_fit(poly, w: float, d: float, inside=None, contains=None, step: float = 0.05):
    """Can a w x d rectangle, square to the room's walls (either way round), sit inside `inside` (default `poly`)?
    With `contains` (x, y) it must also cover that point. Returns the rectangle's corners or None.
    shortcut: a grid of placements every `step` m, so a fit tighter than that can be missed."""
    import numpy as np
    import shapely
    from shapely import affinity
    region = inside if inside is not None else poly
    if region is None or region.is_empty:
        return None
    ang = room_angle(poly)
    c = poly.centroid
    rot = affinity.rotate(region, -ang, origin=c, use_radians=True)
    shapely.prepare(rot)
    pt = shapely.Point(*contains) if contains else None
    if pt is not None:
        pt = affinity.rotate(pt, -ang, origin=c, use_radians=True)
    x0, y0, x1, y1 = rot.bounds
    for rw, rd in ((w, d), (d, w)):
        xs = np.arange(x0, x1 - rw + 1e-9, step)
        ys = np.arange(y0, y1 - rd + 1e-9, step)
        if not len(xs) or not len(ys):
            continue
        gx, gy = (a.ravel() for a in np.meshgrid(xs, ys))
        if pt is not None:
            keep = (gx <= pt.x) & (pt.x <= gx + rw) & (gy <= pt.y) & (pt.y <= gy + rd)
            gx, gy = gx[keep], gy[keep]
        if not len(gx):
            continue
        boxes = shapely.box(gx, gy, gx + rw, gy + rd)
        ok = np.nonzero(shapely.contains(rot, boxes))[0]
        if len(ok):
            b = affinity.rotate(boxes[ok[0]], ang, origin=c, use_radians=True)
            return [list(p) for p in b.exterior.coords[:4]]
    return None


def face_polygon(plan: dict, room_id: str):
    """A room's floor at the wall faces (centre-line polygon shrunk by half the wall thickness)."""
    from ...geometry._plan import polygons
    p = polygons(plan).get(room_id)
    if p is None:
        return None
    r = rooms(plan)[room_id]
    ws = {w["id"]: w for w in plan.get("walls") or []}
    ts = [ws[w]["thickness"] for w in r.get("walls") or [] if w in ws and ws[w].get("thickness")]
    half = (statistics.median(ts) if ts else 0.12) / 2
    inner = p.buffer(-half, join_style="mitre")
    return inner if not inner.is_empty else None
