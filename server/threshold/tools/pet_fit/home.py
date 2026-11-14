"""Inside the home, from the scan: stairs, open floor, floor finishes, a crate spot, a litter box spot, pet door
candidates and windows a cat could fall from. Pure functions of a ScanPlan except `finishes` (vision, cached).
Nothing here judges a pet; `judge.py` does."""
from __future__ import annotations

import math

import shapely
from shapely.geometry import Point

from ...geometry import route
from ...geometry._plan import floor_z, polygons
from .._access import elevations, face_polygon, quality, rect_fit
from ..stairs_count import levels

# Crate sizes by dog size, inside length x width x height (m), from the usual 24/36/42/48 in wire crates, with
# 0.3 m in front for the door to open. Small animals get a 1.2 x 0.6 m pen (a common rabbit and guinea pig size).
CRATE = {"small": (0.61, 0.46, 0.5), "medium": (0.91, 0.61, 0.68), "large": (1.07, 0.71, 0.79),
         "giant": (1.22, 0.76, 0.84), "pen": (1.2, 0.6, 0.6)}
LITTER = (0.6, 0.5, 0.4)
FRONT_M = 0.3
CRATE_ROOMS = ("Living Room", "Family Room", "Bedroom", "Office", "Dining Room", "Den", "Bonus Room")
LITTER_ROOMS = ("Laundry", "Utility Room", "Bathroom", "Closet", "Hallway", "Office", "Bedroom")
FOOD_ROOMS = ("Kitchen", "Dining Room")
LITTER_FROM_FOOD_M = 3.0
PET_DOOR_ROOMS = ("Kitchen", "Family Room", "Living Room", "Laundry", "Utility Room", "Dining Room", "Hallway", "Garage",
                  "Sunroom", "Mudroom")
UPPER_M = 2.0          # a floor this high above the lowest is an upper floor
OUTDOOR_ROOMS = ("Balcony", "Terrace", "Patio", "Porch", "Deck")


def label(r: dict | None) -> str:
    return (r or {}).get("label") or "room"


def stairs(plan: dict, riser: float = 0.178) -> dict:
    """Steps from the entrance floor to the farthest floor, floors, and whether a bedroom is on the entrance floor."""
    lv = levels(plan, riser)
    L = lv["levels"]
    entry = next((f for f in L if f["entry"]), None)
    return {"floors": len(L), "steps_max": max((f["steps"] or 0 for f in L), default=0),
            "bedroom_on_entry": bool(entry and entry["bedrooms"]),
            "bedrooms_elsewhere": sum(f["bedrooms"] for f in L if not f["entry"]),
            "levels": L}


def open_floor(plan: dict) -> dict | None:
    """The room with the longest clear run: the long side of its minimum rotated rectangle, and its largest
    clear circle (wall face to wall face, empty room)."""
    best = None
    for r in plan.get("rooms") or []:
        if r.get("label") in ("Void", "Closet", "Bathroom", "Garage") + OUTDOOR_ROOMS:
            continue
        p = face_polygon(plan, r["id"])
        if p is None or p.is_empty:
            continue
        mrr = p.minimum_rotated_rectangle
        xs = list(mrr.exterior.coords)
        sides = sorted(math.dist(a, b) for a, b in zip(xs, xs[1:]))
        circle = 2 * shapely.maximum_inscribed_circle(p).length
        cand = {"room": r["id"], "label": label(r), "run_m": sides[-1], "circle_m": circle, "area": p.area,
                "floor": r["floor"]}
        if best is None or cand["run_m"] * min(cand["circle_m"], 4) > best["run_m"] * min(best["circle_m"], 4):
            best = cand
    return best


def _doors_clear(plan: dict, room_id: str, poly):
    """The room minus a 0.9 m disc at each of its doorways: a crate or a litter box must not block a door."""
    cut = [Point(o["center"]).buffer(0.9) for o in plan.get("openings") or []
           if o["type"] != "window" and room_id in (o.get("rooms") or [])]
    region = poly
    for c in cut:
        region = region.difference(c)
    return region


def _spot(plan: dict, rooms: tuple[str, ...], size: tuple[float, float, float], ok=lambda r, box: True) -> dict | None:
    """The first room by preference (then largest) where the box plus a front clearance fits clear of doors."""
    w, d, h = size
    polys = {r["id"]: face_polygon(plan, r["id"]) for r in plan.get("rooms") or [] if r.get("label") in rooms}
    order = sorted((r for r in plan["rooms"] if polys.get(r["id"]) is not None),
                   key=lambda r: (rooms.index(r["label"]), -polys[r["id"]].area))
    fz = floor_z(plan)
    for r in order:
        poly = polys[r["id"]]
        box = rect_fit(poly, w, d + FRONT_M, inside=_doors_clear(plan, r["id"], poly))
        if not box or not ok(r, box):
            continue
        (x0, y0), (x1, y1), (x2, y2) = box[0], box[1], box[2]
        cx, cy = (x0 + x2) / 2, (y0 + y2) / 2
        yaw = math.degrees(math.atan2(y1 - y0, x1 - x0))
        long_first = math.dist(box[0], box[1]) >= math.dist(box[1], box[2])
        return {"room": r["id"], "label": r["label"], "floor": r["floor"], "corners": box,
                "center": (cx, cy, fz.get(r["floor"], 0.0) + h / 2), "size": (w, d + FRONT_M, h) if long_first else
                (d + FRONT_M, w, h), "yaw_deg": yaw}
    return None


def crate_spot(plan: dict, size: str) -> dict | None:
    return _spot(plan, CRATE_ROOMS, CRATE[size])


def litter_spot(plan: dict) -> dict | None:
    """A litter box spot at least LITTER_FROM_FOOD_M (straight line) from the kitchen and dining room on its floor."""
    polys = polygons(plan)
    food = [(r["floor"], polys[r["id"]]) for r in plan["rooms"] if r.get("label") in FOOD_ROOMS and polys.get(r["id"]) is not None]

    def far(r, box):
        c = Point((box[0][0] + box[2][0]) / 2, (box[0][1] + box[2][1]) / 2)
        return all(fl != r["floor"] or p.distance(c) >= LITTER_FROM_FOOD_M for fl, p in food)
    s = _spot(plan, LITTER_ROOMS, LITTER, far) or _spot(plan, LITTER_ROOMS, LITTER)  # else the best spot, flagged by the rule
    if s:
        c = Point(s["center"][:2])
        same = [p.distance(c) for fl, p in food if fl == s["floor"]]
        s["food_m"] = min(same) if same else None
    return s


def pet_doors(plan: dict) -> list[dict]:
    """Exterior doors a pet door could go in, from rooms where one usually goes; lowest floor only."""
    from ..path_to_water import exterior_doors
    rooms = {r["id"]: r for r in plan["rooms"]}
    el = elevations(plan)
    low = min(el.values(), default=0.0)
    out = []
    for d in exterior_doors(plan):
        r = rooms.get(d["room"])
        if (el.get(d["floor"]) or 0.0) - low > 0.5 or label(r) not in PET_DOOR_ROOMS:
            continue
        out.append({**d, "label": label(r)})
    return sorted(out, key=lambda d: PET_DOOR_ROOMS.index(d["label"]))


def door_route(plan: dict, door: dict) -> dict | None:
    """Route from the main living space to just inside the door (a pet's way out)."""
    living = [r for r in plan["rooms"] if r.get("label") in ("Living Room", "Family Room") and r["floor"] == door["floor"]]
    if not living or living[0]["id"] == door["room"]:
        return None
    r = route(plan, living[0]["id"], list(door["inner"]), min_width=0.3)
    return r if r.get("available") else None


def fall_windows(plan: dict) -> dict:
    """Windows on upper floors (height above the lowest floor plus sill) and balcony-like rooms on any floor."""
    el = elevations(plan)
    fz = floor_z(plan)
    low = min(el.values(), default=0.0)
    rooms = {r["id"]: r for r in plan["rooms"]}
    wins = []
    for o in plan.get("openings") or []:
        if o["type"] != "window":
            continue
        rise = (el.get(o["floor"]) or 0.0) - low
        sill = (o.get("sill") or 0.0) - fz.get(o["floor"], 0.0) if o.get("sill") is not None else None
        if rise >= UPPER_M:
            wins.append({"id": o["id"], "floor": o["floor"], "room": label(rooms.get((o.get("rooms") or [None])[0])),
                         "drop_m": rise + max(sill or 0.0, 0.0), "sill_m": sill, "center": o["center"]})
    balconies = [{"id": r["id"], "label": r["label"], "floor": r["floor"], "rise_m": (el.get(r["floor"]) or 0.0) - low}
                 for r in plan["rooms"] if r.get("label") in ("Balcony", "Terrace")]
    return {"windows": sorted(wins, key=lambda w: -w["drop_m"]), "balconies": balconies,
            "upper_floors": sum(1 for v in el.values() if v - low >= UPPER_M)}


HARD = {"hardwood or wood-look", "tile or stone", "polished or sealed concrete", "vinyl or linoleum"}


def finishes(plan: dict) -> dict | None:
    """Area-weighted share of carpet and hard floor over the rooms the vision model read; None without panoramas."""
    from ...vision import reader
    if not plan.get("panos") or not quality(plan).get("polygons"):
        return None
    got = reader.floor_finishes(plan)
    polys = polygons(plan)
    area = {"carpet": 0.0, "hard": 0.0, "other": 0.0}
    rooms = {}
    for rid, f in got.items():
        p = polys.get(rid)
        a = p.area if p is not None else 0.0
        kind = "carpet" if f["finish"] == "carpet" else "hard" if f["finish"] in HARD else "other"
        area[kind] += a
        rooms[rid] = {**f, "kind": kind, "area": a}
    tot = sum(area.values()) or 1.0
    return {"carpet_share": area["carpet"] / tot, "hard_share": area["hard"] / tot, "rooms": rooms,
            "area_m2": tot, "confidence": "medium" if rooms else "low"}
