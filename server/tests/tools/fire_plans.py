"""Small hand-made ScanPlans for the fire tools; no sponsor data, no network.

A two-bedroom unit, metres, one floor:

    y=6        +--------------+
               |  B1 Bedroom  |   window W1 on the north wall, sill 0.9
    y=2.5 +----+---d1---------+------+
          | L  |   H Hallway  d4  K  |      E: entrance on L's west wall, 0.9 wide
     E  Living d0             |      |      d0 L-H 0.9, d1 H-B1 0.8, d2 H-B2 0.75, d4 H-Bath 0.7
    y=1.5 +----+---d2---------+------+
          |    |  B2 Bedroom  |
    y=-2  +----+--------------+
         x=0  x=5            x=9    x=11
"""
from __future__ import annotations

import math


def rect_plan(rooms, doors, windows=(), sid="unit", floor="f1", geo=None):
    """rooms: (id, label, x0, y0, x1, y1); doors: (id, room_a, room_b or None, [x, y], width);
    windows: (id, room, [x, y], width, sill). Walls are every room edge split where other rooms' corners touch it,
    shared by the rooms on either side, so doors sit on one wall."""
    edges = []
    for rid, _, x0, y0, x1, y1 in rooms:
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        edges += [(rid, corners[i], corners[(i + 1) % 4]) for i in range(4)]
    cuts = {c for _, a, b in edges for c in (a, b)}
    pieces: dict[tuple, set] = {}
    for rid, a, b in edges:
        on = sorted({a, b} | {c for c in cuts if _between(a, b, c)}, key=lambda c: math.dist(a, c))
        for p, q in zip(on, on[1:]):
            pieces.setdefault(tuple(sorted([p, q])), set()).add(rid)
    walls = [{"id": f"w{i}", "floor": floor, "a": list(k[0]), "b": list(k[1]), "type": "wall", "thickness": 0.1,
              "length": math.dist(*k), "rooms": sorted(v), "openings": []} for i, (k, v) in enumerate(pieces.items())]

    def wall_at(pt):
        return next(w for w in walls if _between(tuple(w["a"]), tuple(w["b"]), tuple(pt), strict=False))

    openings = []
    for oid, ra, rb, c, w in doors:
        wl = wall_at(c)
        openings.append({"id": oid, "wall": wl["id"], "floor": floor, "type": "doorway", "width": w, "height": 2.03,
                         "sill": 0.0, "center": list(c), "rooms": [r for r in (ra, rb) if r]})
        wl["openings"].append(oid)
    for oid, r, c, w, sill in windows:
        wl = wall_at(c)
        openings.append({"id": oid, "wall": wl["id"], "floor": floor, "type": "window", "width": w, "height": 1.2,
                         "sill": sill, "center": list(c), "rooms": [r]})
        wl["openings"].append(oid)
    room_rows = []
    for rid, label, x0, y0, x1, y1 in rooms:
        room_rows.append({"id": rid, "floor": floor, "label": label, "label_confidence": 1,
                          "label_source": "matterport", "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                          "area": (x1 - x0) * (y1 - y0), "height": 2.5, "width": x1 - x0, "depth": y1 - y0,
                          "walls": [w["id"] for w in walls if rid in w["rooms"]], "holes": []})
    return {"schema": "scanplan/1", "sid": sid, "name": "Test unit", "address": "1 Test St, Houston, TX",
            "city": "Houston", "segment": "residential", "geo": geo,
            "has": {"room_labels": True, "openings": True}, "ids": {},
            "floors": [{"id": floor, "label": "1", "sequence": 0}], "walls": walls, "openings": openings,
            "rooms": room_rows,
            "panos": [{"id": f"p_{r[0]}", "label": r[0], "floor": floor, "room": r[0], "neighbors": [],
                       "position": [(r[2] + r[4]) / 2, (r[3] + r[5]) / 2, 1.5], "rotation": [0, 0, 0, 1]}
                      for r in rooms],
            "floorplans": []}


def _between(a, b, c, strict=True):
    (ax, ay), (bx, by), (cx, cy) = a, b, c
    if abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) > 1e-9:
        return False
    t = ((cx - ax) * (bx - ax) + (cy - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)
    return 0 < t < 1 if strict else 0 <= t <= 1


def unit(sid="unit", geo=None):
    rooms = [("L", "Living Room", 0, -2, 5, 6), ("H", "Hallway", 5, 1.5, 9, 2.5), ("B1", "Bedroom", 5, 2.5, 9, 6),
             ("B2", "Bedroom", 5, -2, 9, 1.5), ("K", "Bathroom", 9, 1.5, 11, 2.5)]
    doors = [("E", "L", None, [0, 2], 0.9), ("d0", "L", "H", [5, 2], 0.9), ("d1", "H", "B1", [7, 2.5], 0.8),
             ("d2", "H", "B2", [7, 1.5], 0.75), ("d4", "H", "K", [9, 2], 0.7)]
    windows = [("W1", "B1", [7, 6], 1.0, 0.9)]
    return rect_plan(rooms, doors, windows, sid=sid, geo=geo)


def no_walls(sid="flat"):
    p = unit(sid)
    p["walls"], p["openings"] = [], []
    for r in p["rooms"]:
        r["walls"], r["polygon"] = [], []
    p["quality"] = {"walls": False}
    return p


def plans(*ps):
    by = {p["sid"]: p for p in ps}

    def get(sid):
        if sid not in by:
            raise LookupError(sid)
        return by[sid]
    return get
