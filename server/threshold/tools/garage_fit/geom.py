"""Garage geometry on a ScanPlan: find the garage, set up a frame square to its vehicle door, park vehicles in it,
and find room for a bench, a charger or a rack beside them. Pure functions; every number comes from the plan.

Frame: u runs along the door wall, v points into the garage from it (v = 0 on the wall line), metres.
"""
from __future__ import annotations

import math
import statistics

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import LineString, Point, box

from ...geometry._plan import default_ceiling, polygons, room_floor_z, walls_by_id
from .._access import elevations, face_polygon

VEHICLE_DOOR_M = 1.8       # an opening this wide in a garage is a vehicle door, not a person door
CANDIDATE_DOOR_M = 2.2     # in an unlabelled room, a one-sided opening this wide makes it a possible garage
CANDIDATE_AREA_M2 = 15.0
DEFAULT_DOOR_H = 2.03      # Matterport records this when it did not measure a door (117 of 188 garage doors)
STANDARD_DOOR_H = 2.13     # 7 ft, the usual US garage door
REAR_M, REAR_TIGHT_M = 0.15, 0.05  # bumper to the inside of the door line: the door closes in the opening
FRONT_FITS_M, FRONT_TIGHT_M = 0.60, 0.05  # room ahead of the bumper: walk round / parked to the tennis ball
SQUEEZE_M = 0.45           # beside the body: a person squeezes out of a half-open door
MIRROR_MARGIN_M = 0.15     # each side, driving in with mirrors out
BODY_MARGIN_M = 0.05       # each side, mirrors folded, crawling in
HEIGHT_FITS_M, HEIGHT_TIGHT_M = 0.10, 0.03
DRIFT_M = 0.30             # a car may end up this far sideways of where it crossed the door, steering a little
STEP_M = 0.05
UNLABELLED = (None, "", "Other", "Storage", "Utility Room", "Unknown")


def _opens(plan: dict, rid: str) -> list[dict]:
    return [o for o in plan.get("openings") or [] if rid in (o.get("rooms") or []) and o.get("type") != "window"
            and o.get("width")]


def find_garages(plan: dict) -> list[dict]:
    """Garages, largest first: rooms labelled Garage or Carport, else (only then) unlabelled rooms on the lowest floor
    with a one-sided opening wide enough for a car. Each: {room, how}."""
    rooms = [r for r in plan.get("rooms") or [] if r.get("label") != "Void"]
    out = [{"room": r, "how": "label"} for r in rooms if (r.get("label") or "").lower() in ("garage", "carport")]
    if not out:
        el = elevations(plan)
        low = min(el.values(), default=0.0)
        for r in rooms:
            if r.get("label") in UNLABELLED and (r.get("area") or 0) >= CANDIDATE_AREA_M2 \
                    and (el.get(r["floor"]) or 0.0) <= low + 0.5 \
                    and any(len(o.get("rooms") or []) == 1 and o["width"] >= CANDIDATE_DOOR_M for o in _opens(plan, r["id"])):
                out.append({"room": r, "how": "wide door"})
    return sorted(out, key=lambda g: -(g["room"].get("area") or 0))


def door_height(o: dict) -> tuple[float | None, bool]:
    """(height, measured). Matterport's default 2.03 m and heights under 1.5 m are not measurements."""
    h = o.get("height")
    if h is None or h < 1.5 or abs(h - DEFAULT_DOOR_H) < 0.006:
        return None, False
    return h, True


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _wall_line(plan: dict, o: dict, poly):
    w = walls_by_id(plan).get(o.get("wall"))
    if w:
        return w["a"], w["b"]
    # no wall record: the polygon edge nearest the door
    cs = list(poly.exterior.coords)
    c = Point(o["center"])
    return min(zip(cs, cs[1:]), key=lambda e: LineString(e).distance(c))


class Frame:
    """u along the door wall, v into the garage."""

    def __init__(self, origin, u, v):
        self.o, self.u, self.v = origin, u, v

    def to(self, p):
        dx, dy = p[0] - self.o[0], p[1] - self.o[1]
        return dx * self.u[0] + dy * self.u[1], dx * self.v[0] + dy * self.v[1]

    def back(self, uu, vv):
        return (self.o[0] + uu * self.u[0] + vv * self.v[0], self.o[1] + uu * self.u[1] + vv * self.v[1])

    def geom(self, g):
        return shapely.transform(g, lambda c: np.column_stack([
            (c[:, 0] - self.o[0]) * self.u[0] + (c[:, 1] - self.o[1]) * self.u[1],
            (c[:, 0] - self.o[0]) * self.v[0] + (c[:, 1] - self.o[1]) * self.v[1]]))

    def scan_yaw(self, deg: float) -> float:
        """A direction given in the frame (degrees from +u toward +v), as a yaw in the scan frame."""
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
        return math.degrees(math.atan2(c * self.u[1] + s * self.v[1], c * self.u[0] + s * self.v[0]))

    @property
    def yaw_deg(self) -> float:  # direction a car parked nose-in faces, scan frame
        return math.degrees(math.atan2(self.v[1], self.v[0]))


def _frame_from(a, b, poly) -> Frame:
    u = _unit(a, b)
    v = (-u[1], u[0])
    c = poly.centroid
    if (c.x - a[0]) * v[0] + (c.y - a[1]) * v[1] < 0:
        v = (-v[0], -v[1])
    return Frame(tuple(a), u, v)


def obstacles(plan: dict, rid: str, poly) -> list[dict]:
    """Objects the phone scan found standing in the garage (RoomPlan storage, fridges, washers...), as footprints."""
    out = []
    for x in plan.get("objects") or []:
        c, s = x.get("center"), x.get("size")
        if not c or not s or not (x.get("room") == rid or poly.contains(Point(c[0], c[1]))):
            continue
        fp = affinity.rotate(box(c[0] - s[0] / 2, c[1] - s[1] / 2, c[0] + s[0] / 2, c[1] + s[1] / 2),
                             x.get("yaw_deg") or 0, origin=(c[0], c[1]))
        out.append({"id": x.get("id"), "label": x.get("label") or x.get("category") or "object", "footprint": fp,
                    "size": s, "center": c, "yaw_deg": x.get("yaw_deg") or 0})
    return out


def survey(plan: dict, room: dict) -> dict | None:
    """The garage measured: frames to try, vehicle doors, the clear floor (obstacles taken out), ceiling, floor z,
    inside width and depth. None when the room has no outline."""
    rid = room["id"]
    poly = face_polygon(plan, rid) or polygons(plan).get(rid)
    if poly is None or poly.area < 4:
        return None
    obs = obstacles(plan, rid, poly)
    clear = poly.difference(shapely.union_all([o["footprint"] for o in obs])) if obs else poly
    if clear.geom_type != "Polygon":
        clear = max(getattr(clear, "geoms", [clear]), key=lambda g: g.area)
    wide = sorted([o for o in _opens(plan, rid) if o["width"] >= VEHICLE_DOOR_M], key=lambda o: -o["width"])
    frames, doors = [], []
    if wide:
        a, b = _wall_line(plan, wide[0], poly)
        f = _frame_from(a, b, poly)
        frames.append(f)
        for o in wide:
            uc, vc = f.to(o["center"])
            if abs(vc) > 0.6:  # a second vehicle door on another wall: noted, not parked through
                continue
            h, measured = door_height(o)
            doors.append({"opening": o["id"], "width": o["width"], "lo": uc - o["width"] / 2, "hi": uc + o["width"] / 2,
                          "height": h, "measured": measured, "center": o["center"], "rooms": len(o.get("rooms") or [])})
    else:  # no vehicle door in the scan (closed and scanned as wall, or not captured): try both ways square to the walls
        cs = list(poly.minimum_rotated_rectangle.exterior.coords)
        for i in (0, 1):
            frames.append(_frame_from(cs[i], cs[i + 1], poly))
    hgt = room.get("height")
    ceiling = {"value": hgt, "measured": True} if hgt else {"value": default_ceiling(plan), "measured": False}
    z = room_floor_z(plan).get(rid, 0.0)
    return {"room": room, "poly": poly, "clear": clear, "obstacles": obs, "frames": frames, "doors": doors,
            "ceiling": ceiling, "z": z, "other_doors": [o for o in wide if o["id"] not in {d["opening"] for d in doors}]}


def interval_at(region, f_axis: str, at: float, near: float) -> tuple[float, float] | None:
    """The stretch of `region` (frame coords) on the line u = at (f_axis "v") or v = at ("u") holding `near`."""
    x0, y0, x1, y1 = region.bounds
    line = LineString([(x0 - 1, at), (x1 + 1, at)]) if f_axis == "u" else LineString([(at, y0 - 1), (at, y1 + 1)])
    g = region.intersection(line)
    parts = [p for p in getattr(g, "geoms", [g]) if p.geom_type == "LineString" and not p.is_empty]
    best = None
    for p in parts:
        cs = [c[0] if f_axis == "u" else c[1] for c in p.coords]
        lo, hi = min(cs), max(cs)
        d = 0 if lo <= near <= hi else min(abs(near - lo), abs(near - hi))
        if best is None or d < best[0]:
            best = (d, lo, hi)
    return (best[1], best[2]) if best else None


def size_in(region, doors: list[dict]) -> dict:
    """Inside width across the garage halfway in, and depth from the door line at the door (or the middle)."""
    x0, y0, x1, y1 = region.bounds
    uc = statistics.mean([(d["lo"] + d["hi"]) / 2 for d in doors]) if doors else (x0 + x1) / 2
    w = interval_at(region, "u", (y0 + y1) / 2, uc)
    d = interval_at(region, "v", uc, (y0 + y1) / 2)
    return {"width": round(w[1] - w[0], 3) if w else None, "depth": round(d[1] - d[0], 3) if d else None,
            "door_line": y0}


def gaps_for(n: int, gap: float, ramp: float) -> list[float]:
    """Clearances left of car 0, between cars, right of the last. A ramp van needs its ramp strip on its right."""
    return [gap] + [max(gap, ramp) for _ in range(n)]


def lines_up(centre: float, span: float, doors: list[dict]) -> bool:
    """Could a car parked with this centre have come through one of the doors with `span` to spare?"""
    return any(d["lo"] + span / 2 - DRIFT_M - 1e-6 <= centre <= d["hi"] - span / 2 + DRIFT_M + 1e-6
               and d["hi"] - d["lo"] >= span - 1e-6 for d in doors)


def place(region, n: int, w: float, l: float, gaps: list[float], front: float, doors: list[dict], span: float,
          rear: float = REAR_M):
    """Lower-left (u, v) of each of n cars, w wide and l long, parked nose-in side by side with `gaps`, `front`
    clear ahead and each car's `span` (body or mirrors plus margin) inside a vehicle door. None if no placement.
    shortcut: a grid every 5 cm across and 10 cm in, so a fit tighter than that can be missed."""
    if n <= 0:
        return []
    x0, y0, x1, y1 = region.bounds
    bw, bd = n * w + sum(gaps), l + rear + front
    if bw > x1 - x0 + 1e-9 or bd > y1 - y0 + 1e-9:
        return None
    shapely.prepare(region)
    contains = region.contains
    offs = [sum(gaps[:i + 1]) + i * w for i in range(n)]
    vmax = y0 + (0.6 if doors else y1 - y0 - bd)  # with a door, the car stops just inside it
    for v0 in np.arange(y0 + 0.003, min(vmax, y1 - bd) + 1e-9, 0.1):  # just inside: an edge on the wall reads as out
        for u0 in np.arange(x0 + 0.003, x1 - bw + 1e-9, STEP_M):
            if doors and not all(lines_up(u0 + o + w / 2, span, doors) for o in offs):
                continue
            if contains(box(u0, v0, u0 + bw, v0 + bd)):
                return [(u0 + o, v0 + rear) for o in offs]
    return None


def spread(region, cars: list[tuple], w: float, l: float, doors: list[dict], span: float) -> list[tuple]:
    """Re-space a found placement evenly across the floor it stands on, when every car still lines up with a door."""
    n = len(cars)
    v0 = cars[0][1]
    lo = min(c[0] for c in cars)
    hi = max(c[0] for c in cars) + w
    band = lambda a, b: box(a, v0, b, v0 + l)
    while lo - STEP_M > region.bounds[0] - 1 and region.contains(band(lo - STEP_M, hi)):
        lo -= STEP_M
    while region.contains(band(lo, hi + STEP_M)) and hi + STEP_M < region.bounds[2] + 1:
        hi += STEP_M
    g = (hi - lo - n * w) / (n + 1)
    even = [(lo + g + i * (w + g), v0) for i in range(n)]
    ok = not doors or all(lines_up(u + w / 2, span, doors) for u, _ in even)
    return even if ok else cars


def clearances(region, cars: list[tuple], w: float, l: float) -> list[dict]:
    """Measured room on each side of each car (to the next car or the wall), ahead of it and behind it."""
    out = []
    for i, (u, v) in enumerate(cars):
        side = interval_at(region, "u", v + l / 2, u + w / 2)
        ahead = interval_at(region, "v", u + w / 2, v + l / 2)
        left = (u - cars[i - 1][0] - w) if i > 0 else (u - side[0] if side else None)
        right = (cars[i + 1][0] - u - w) if i + 1 < len(cars) else (side[1] - u - w if side else None)
        out.append({"left": left, "right": right, "front": (ahead[1] - v - l) if ahead else None,
                    "rear": (v - ahead[0]) if ahead else None})
    return out


def overflow(region, n: int, w: float, l: float) -> list[tuple]:
    """Where n cars would stand if pushed in side by side regardless: evenly across the widest stretch, overlapping
    walls when they do not fit, to show by how much."""
    x0, y0, x1, y1 = region.bounds
    span = interval_at(region, "u", y0 + REAR_M + l / 2, (x0 + x1) / 2) or (x0, x1)
    g = (span[1] - span[0] - n * w) / (n + 1)
    return [(span[0] + g + i * (w + g), y0 + REAR_M) for i in range(n)]


def free_spot(region, taken, size: tuple[float, float]):
    """A size[0] x size[1] rectangle square to the walls in the floor left over; its corners, or None."""
    from .._access import rect_fit
    free = region.difference(taken) if taken is not None and not taken.is_empty else region
    if free.is_empty:
        return None
    parts = sorted(getattr(free, "geoms", [free]), key=lambda g: -g.area)
    for p in parts[:4]:
        r = rect_fit(region, size[0], size[1], inside=p.buffer(-1e-6) if p.area > 0 else p, step=0.1)
        if r:
            return r
    return None






def door_limit(doors: list[dict]) -> tuple[float, bool]:
    """Lowest vehicle-door height and whether it was measured; the usual 7 ft door when none was."""
    hs = [d["height"] for d in doors if d["measured"]]
    return (min(hs), True) if hs else (STANDARD_DOOR_H, False)






def corners_center(corners) -> tuple[tuple[float, float], float, tuple[float, float]]:
    """Centre, yaw (degrees, along the first edge) and (length, depth) of a rectangle from its four corners."""
    (ax, ay), (bx, by), (cx, cy) = corners[0], corners[1], corners[2]
    return (((ax + cx) / 2, (ay + cy) / 2), math.degrees(math.atan2(by - ay, bx - ax)),
            (math.dist((ax, ay), (bx, by)), math.dist((bx, by), (cx, cy))))
