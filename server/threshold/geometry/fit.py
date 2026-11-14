"""Will it fit: turning circles, carrying a box along a route, free wall runs for furniture."""
from __future__ import annotations

import math
import statistics
from itertools import permutations

import numpy as np
import shapely
from shapely.geometry import Point

from ._plan import (
    VERDICT_STATUS,
    default_ceiling,
    geo_source,
    judge,
    openings_by_id,
    polygons,
    room_label,
    rooms_by_id,
    unavailable,
    walls_by_id,
)
from .routes import ADA_DOOR_CLEAR_M, route

WHEELCHAIR_TURN_M = 1.525   # 60 in circle, ADA 2010 section 304.3.1
DEFAULT_DOOR_HEIGHT_M = 2.03
TURN_MIN_DEG = 30           # bends gentler than this are not checked as corners
COLLINEAR_DEG = 3


def _half_thickness(plan: dict, room: dict) -> float:
    walls = walls_by_id(plan)
    ts = [walls[w]["thickness"] for w in room.get("walls") or [] if w in walls and walls[w].get("thickness")]
    return (statistics.median(ts) if ts else 0.12) / 2


def turning_space(plan: dict, room_id: str, diameter: float = WHEELCHAIR_TURN_M) -> dict:
    """Largest circle that fits in the empty room, wall face to wall face, judged against `diameter`."""
    room = rooms_by_id(plan).get(room_id)
    if room is None:
        return unavailable(f"No room {room_id} in this scan.")
    poly = polygons(plan)[room_id]
    if poly is None:
        return unavailable("This room has no floor outline in the scan.", room=room_id)
    line = shapely.maximum_inscribed_circle(poly)
    centre = line.coords[0]
    d = 2 * (line.length - _half_thickness(plan, room))
    res = judge(d, diameter)
    return {"available": True, "room": room_id, "label": room_label(room), "diameter": d, "required": diameter,
            "center": [centre[0], centre[1]], "result": res, "status": VERDICT_STATUS[res],
            "source": geo_source("Empty room: fixtures and furniture usually shrink the circle; ADA lets doors "
                                 "swing into it and allows a T-shaped space instead.", "medium")}


def turning_spaces(plan: dict, diameter: float = WHEELCHAIR_TURN_M) -> dict:
    """turning_space for every room with an outline, plus a lens of diameters."""
    out = [t for t in (turning_space(plan, r["id"], diameter) for r in plan.get("rooms") or []) if t["available"]]
    if not out:
        return unavailable("No room in this scan has a floor outline.")
    return {"available": True, "rooms": out,
            "lens": {"kind": "lens", "values": {t["room"]: round(t["diameter"], 3) for t in out}, "ramp": "sequential",
                     "legend": {"title": "Largest turning circle", "unit": "m", "min": 0,
                                "max": max(t["diameter"] for t in out)}}}


def corner_max_length(a: float, b: float, w: float, angle_deg: float = 90.0) -> float:
    """Longest box of width `w` that turns from a corridor `a` wide into one `b` wide, the route bending by
    `angle_deg` (90 is a right-angle corner): min over theta in (0, phi) of
    a/sin(theta) + b/sin(phi - theta) - w (cot(theta) + cot(phi - theta)). At 90 degrees this is the ladder result
    a/sin + b/cos - w/(sin cos)."""
    if w >= min(a, b):
        return 0.0
    phi = math.radians(min(max(angle_deg, 1.0), 179.0))
    th = np.linspace(1e-3, phi - 1e-3, 4000)
    s1, s2 = np.sin(th), np.sin(phi - th)
    return float(np.min(a / s1 + b / s2 - w * (np.cos(th) / s1 + np.cos(phi - th) / s2)))


def _door_fit(box, clear: float, height: float, flat: bool = False):
    """Best slack carrying the box end-first through a door: one dimension across, one up, one along.
    `flat` keeps box[2] vertical."""
    best = None
    for i, j, _k in permutations(range(3)):
        across, up = box[i], box[j]
        if flat and j != 2:
            continue
        slack = min(clear - across, height - up)
        if best is None or slack > best[0]:
            best = (slack, across, up)
    return best


def _corner_fit(box, a: float, b: float, headroom: float, flat: bool = False, angle_deg: float = 90.0):
    """Best slack (max length minus box length) over which dimension is carried vertical."""
    best = None
    for i, up in enumerate(box):
        if up > headroom or (flat and i != 2):
            continue
        rest = sorted(box[:i] + box[i + 1:])
        w, length = rest
        slack = corner_max_length(a, b, w, angle_deg) - length
        if best is None or slack > best[0]:
            best = (slack, w, length, up)
    return best


def carry(plan: dict, start, end, box: tuple[float, float, float], floor: str | None = None,
          flat: bool = False) -> dict:
    """Can a box (w, d, h in metres) be carried along the route from `start` to `end`?

    Doors: the box goes through end-first, so two of its dimensions must fit the clear width and the opening
    height. Corners: every bend of more than 30 degrees is checked as a corner of that angle between the leg
    widths (a door gap counts as a corridor as wide as the door), with the box upright or on its side as the
    ceiling allows (`flat=True` keeps the third dimension vertical, as for a stretcher). Corners are an
    estimate (`medium`): real moves also tilt and pivot."""
    box = tuple(float(x) for x in box)
    r = route(plan, start, end, min_width=min(box), floor=floor)
    if not r["available"]:
        return r
    ceiling = default_ceiling(plan) or 2.4
    doors = []
    for d in r["doors"]:
        cw, h = d["clear_width"], d["height"] or DEFAULT_DOOR_HEIGHT_M
        slack, across, up = _door_fit(box, cw, h, flat)
        res = "measure on site" if d.get("implausible") else judge(slack, 0.0)
        doors.append({"opening": d["opening"], "clear_width": cw, "height": h, "across": across, "up": up,
                      "slack": slack, "implausible": bool(d.get("implausible")), "result": res, "status": VERDICT_STATUS[res], "center": d["center"]})
    door_w = {d["opening"]: d["clear_width"] for d in r["doors"] if not d.get("implausible")}
    door_h = {d["opening"]: d["height"] or DEFAULT_DOOR_HEIGHT_M for d in r["doors"]}
    corners = []
    legs = r["legs"]
    open_w = 6.0
    for k in range(len(legs) - 1):
        l1, l2 = legs[k], legs[k + 1]
        u1 = np.subtract(l1["b"], l1["a"]) / max(l1["length"], 1e-9)
        u2 = np.subtract(l2["b"], l2["a"]) / max(l2["length"], 1e-9)
        angle = math.degrees(math.acos(float(np.clip(np.dot(u1, u2), -1, 1))))
        if angle < TURN_MIN_DEG:
            continue
        a, b = l1["min_width"] or open_w, l2["min_width"] or open_w
        door = l1["door_at_end"] if l1["door_at_end"] in door_w else None  # a data-error width is no corner
        pairs = [(a, door_w[door]), (door_w[door], b)] if door else [(a, b)]
        headroom = min(ceiling, door_h[door]) if door else ceiling
        fits = [(_corner_fit(box, x, y, headroom, flat, angle), x, y) for x, y in pairs]
        worst = min(fits, key=lambda f: f[0][0] if f[0] else -math.inf)
        fit, x, y = worst
        res = judge(fit[0], 0.0) if fit else "likely fail"
        corners.append({"point": l1["b"], "angle_deg": angle, "a": x, "b": y, "door": door,
                        "slack": fit[0] if fit else None, "box_up": fit[3] if fit else None,
                        "result": res, "status": VERDICT_STATUS[res]})
    results = [d["result"] for d in doors] + [c["result"] for c in corners]
    overall = "likely fail" if "likely fail" in results else "measure on site" if "measure on site" in results \
        else "likely pass"
    z = r["points"][0][2] if r["points"] else 0.0
    boxes = [{"kind": "box", "center": [*c["point"], z + box[2] / 2], "size": list(box), "yaw_deg": 0.0,
              "label": f"Corner, {c['angle_deg']:.0f} degrees", "status": c["status"]}
             for c in corners if c["status"] != "pass"]
    return {"available": True, "box": list(box), "result": overall, "status": VERDICT_STATUS[overall],
            "doors": doors, "corners": corners, "route": {k: r[k] for k in ("floor", "length_m", "points")},
            "overlays": [r["overlay"], *boxes],
            "source": geo_source("Doors: wall opening less a 5 cm hung-door allowance. Corners: right-angle "
                                 "corner formula on empty-room widths, no tilting.", "medium")}


def free_wall_runs(plan: dict, room_id: str) -> dict:
    """Straight stretches of wall in a room with no door, window or open edge, longest first (for furniture).
    Lengths are along the wall face: centre-line runs less half a wall at each end."""
    room = rooms_by_id(plan).get(room_id)
    if room is None:
        return unavailable(f"No room {room_id} in this scan.")
    poly = polygons(plan)[room_id]
    if poly is None:
        return unavailable("This room has no floor outline in the scan.", room=room_id)
    walls = [w for w in plan.get("walls") or [] if w["floor"] == room["floor"]]
    lines = shapely.linestrings([[w["a"], w["b"]] for w in walls]) if walls else np.array([])
    opens = openings_by_id(plan)
    half = _half_thickness(plan, room)
    ring = shapely.geometry.polygon.orient(poly, 1.0).exterior.coords[:-1]
    edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]
    # merge consecutive collinear edges into straight runs, starting at a real corner
    def direction(e):
        return math.atan2(e[1][1] - e[0][1], e[1][0] - e[0][0])

    def bend(e1, e2):
        d = abs(direction(e1) - direction(e2)) % (2 * math.pi)
        return math.degrees(min(d, 2 * math.pi - d))

    start = next((i for i in range(len(edges)) if bend(edges[i - 1], edges[i]) > COLLINEAR_DEG), 0)
    edges = edges[start:] + edges[:start]
    runs: list[list] = []
    for e in edges:
        if runs and bend(runs[-1][-1], e) <= COLLINEAR_DEG:
            runs[-1].append(e)
        else:
            runs.append([e])
    out = []
    for run in runs:
        p0, p1 = np.array(run[0][0]), np.array(run[-1][1])
        length = float(np.linalg.norm(p1 - p0))
        if length < 1e-6:
            continue
        u = (p1 - p0) / length
        blocked = []
        for e in run:
            mid = Point((e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2)
            for i in np.nonzero(shapely.distance(lines, mid) <= 0.03)[0] if len(lines) else ():
                w = walls[i]
                if w.get("type") == "invisible":
                    blocked.append((float(np.dot(np.array(e[0]) - p0, u)), float(np.dot(np.array(e[1]) - p0, u))))
                for oid in w.get("openings") or []:
                    o = opens.get(oid)
                    if o is not None:
                        s = float(np.dot(np.array(o["center"]) - p0, u))
                        blocked.append((s - (o["width"] or 0) / 2, s + (o["width"] or 0) / 2))
        t = half
        for lo, hi in sorted(blocked) + [(length - half, length)]:
            if lo - t > 0.05:
                a, b = p0 + u * t, p0 + u * lo
                out.append({"length": float(lo - t), "a": a.tolist(), "b": b.tolist()})
            t = max(t, hi)
    out.sort(key=lambda x: -x["length"])
    return {"available": True, "room": room_id, "label": room_label(room), "runs": out,
            "longest": out[0]["length"] if out else 0.0,
            "source": geo_source("Wall graph; radiators, built-ins and outlets are not in it.", "medium")}


__all__ = [
    "ADA_DOOR_CLEAR_M",
    "WHEELCHAIR_TURN_M",
    "carry",
    "corner_max_length",
    "free_wall_runs",
    "turning_space",
    "turning_spaces",
]
