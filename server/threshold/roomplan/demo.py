"""Hand-made RoomPlan exports of a made-up one-storey home and a made-up small cafe, in exactly the format the iPhone
sends (they decode as Apple's `CapturedRoom` in the simulator). The app's demo mode and the tests use them. Both are
TEST DATA: no real place was scanned.

    uv run python -m threshold.roomplan.demo ../ios/Threshold/Threshold/Resources/DemoHome.json
    uv run python -m threshold.roomplan.demo --cafe ../ios/Threshold/Threshold/Resources/DemoCafe.json

Plan (metres, before the home is turned and moved like a real phone scan):
  Living Room 6 x 5 with the front door (0.91 m) | Kitchen 3.5 x 3 | Hallway 2.5 x 1.2 | Bathroom 2.5 x 1.8,
  door 0.71 m (too narrow for a wheelchair) | Bedroom 4 x 4, door 0.81 m | Bedroom 4 x 4, door 0.76 m.
"""
from __future__ import annotations

import json
import math
import random
import sys
import uuid

H = 2.44           # wall height
DOOR_H = 2.03
FLOOR_Y = -1.32    # RoomPlan's origin is where the phone started, about chest height above the floor

WALLS = [((0, 0), (10, 0)), ((10, 0), (10, 8)), ((10, 8), (0, 8)), ((0, 8), (0, 0)),
         ((0, 5), (6, 5)), ((3.5, 5), (3.5, 8)), ((3.5, 6.2), (6, 6.2)), ((6, 0), (6, 8)), ((6, 4), (10, 4))]
# (kind, wall index, centre along x or y, width, height, sill)
OPENINGS = [("door", 0, 2.5, 0.91, DOOR_H, 0.0), ("opening", 4, 1.75, 1.20, 2.10, 0.0), ("door", 4, 4.75, 0.86, DOOR_H, 0.0),
            ("door", 6, 4.75, 0.71, DOOR_H, 0.0), ("door", 7, 3.4, 0.81, DOOR_H, 0.0), ("door", 7, 5.6, 0.76, DOOR_H, 0.0),
            ("window", 0, 4.5, 1.6, 1.3, 0.9), ("window", 1, 2.0, 1.2, 1.3, 0.9), ("window", 1, 6.0, 1.2, 1.3, 0.9),
            ("window", 3, 6.5, 1.0, 1.0, 1.05), ("window", 2, 4.75, 0.6, 0.6, 1.5)]
# (category, centre x, y, width, depth, height, yaw about up in degrees)
OBJECTS = [("sofa", 1.6, 0.6, 2.1, 0.9, 0.85, 0), ("table", 4.0, 3.0, 1.6, 0.9, 0.75, 0), ("chair", 4.0, 3.75, 0.45, 0.5, 0.9, 0),
           ("television", 1.6, 4.85, 1.2, 0.08, 0.7, 0), ("bed", 8.0, 1.9, 1.5, 2.0, 0.6, 90), ("storage", 9.65, 3.3, 0.6, 0.6, 2.0, 90),
           ("bed", 8.4, 6.1, 1.4, 1.9, 0.6, 90), ("stove", 0.35, 6.6, 0.76, 0.65, 0.9, 90),
           ("refrigerator", 0.4, 7.55, 0.8, 0.75, 1.8, 0), ("sink", 1.5, 7.7, 0.8, 0.55, 0.9, 0),
           ("bathtub", 4.3, 7.6, 1.5, 0.75, 0.55, 0), ("toilet", 5.65, 6.6, 0.38, 0.7, 0.75, 90), ("sink", 5.6, 7.7, 0.6, 0.45, 0.85, 0)]
SECTIONS = [("livingRoom", 3.0, 2.5), ("kitchen", 1.75, 6.5), ("bedroom", 8.0, 2.0), ("bedroom", 8.0, 6.0), ("bathroom", 4.75, 7.1)]


# The cafe: a narrow street-front shop, 7 m of frontage and 12 m deep, like many on a small-town main street.
#   Seating 7 x 7.5 with the street door (0.91 m) and the shop windows | Kitchen 4.2 x 4.5 behind it, through a 1.0 m
#   opening, with the rear exit (0.86 m) | Restroom 2.8 x 2.2, door 0.76 m (narrower than a wheelchair needs) |
#   Storage 2.8 x 2.3 off the kitchen, door 0.81 m.
CAFE_WALLS = [((0, 0), (7, 0)), ((7, 0), (7, 12)), ((7, 12), (0, 12)), ((0, 12), (0, 0)),
              ((0, 7.5), (7, 7.5)), ((4.2, 7.5), (4.2, 12)), ((4.2, 9.7), (7, 9.7))]
CAFE_OPENINGS = [("door", 0, 1.5, 0.91, DOOR_H, 0.0), ("window", 0, 3.6, 2.4, 1.9, 0.45), ("window", 0, 6.0, 1.2, 1.9, 0.45),
                 ("opening", 4, 2.6, 1.00, 2.10, 0.0), ("door", 4, 5.6, 0.76, DOOR_H, 0.0),
                 ("door", 2, 2.0, 0.86, DOOR_H, 0.0), ("door", 5, 10.8, 0.81, DOOR_H, 0.0), ("window", 1, 4.0, 1.0, 1.2, 1.0)]
CAFE_OBJECTS = [("table", 1.2, 4.0, 0.75, 0.75, 0.75, 0), ("chair", 1.2, 3.4, 0.45, 0.45, 0.85, 0),
                ("chair", 1.2, 4.6, 0.45, 0.45, 0.85, 0), ("table", 2.9, 4.0, 0.75, 0.75, 0.75, 0),
                ("chair", 2.9, 3.4, 0.45, 0.45, 0.85, 0), ("chair", 2.9, 4.6, 0.45, 0.45, 0.85, 0),
                ("table", 3.6, 1.2, 2.4, 0.5, 0.95, 0),  # window bar
                ("chair", 3.0, 0.8, 0.4, 0.4, 0.95, 0), ("chair", 4.2, 0.8, 0.4, 0.4, 0.95, 0),
                ("sofa", 0.45, 6.1, 1.8, 0.8, 0.85, 90), ("table", 1.4, 6.1, 1.2, 0.6, 0.45, 90),
                ("storage", 5.4, 6.9, 3.0, 0.7, 1.05, 0),  # the service counter with the pastry case
                ("refrigerator", 6.6, 5.6, 0.7, 0.7, 1.9, 90),
                ("stove", 0.45, 9.0, 0.76, 0.7, 0.9, 90), ("oven", 0.45, 10.1, 0.76, 0.7, 0.9, 90),
                ("sink", 2.2, 7.85, 1.2, 0.6, 0.9, 0), ("dishwasher", 3.2, 7.85, 0.6, 0.6, 0.85, 0),
                ("refrigerator", 3.8, 11.6, 0.75, 0.75, 1.9, 0), ("table", 2.1, 10.0, 1.8, 0.75, 0.9, 0),
                ("toilet", 6.6, 8.6, 0.38, 0.7, 0.75, 90), ("sink", 5.3, 9.45, 0.5, 0.4, 0.85, 0),
                ("storage", 6.65, 10.9, 2.0, 0.6, 2.0, 90), ("storage", 5.6, 11.65, 2.0, 0.6, 2.0, 0)]
CAFE_SECTIONS = [("diningRoom", 3.5, 3.5), ("kitchen", 2.1, 9.8), ("bathroom", 5.6, 8.6)]


def cafe(turn_deg: float = -24.0, shift=(1.1, -2.3), noise_m: float = 0.025, seed: int = 11) -> dict:
    return home(turn_deg, shift, noise_m, seed, layout=(CAFE_WALLS, CAFE_OPENINGS, CAFE_OBJECTS, CAFE_SECTIONS, 12, 7))


def home(turn_deg: float = 17.0, shift=(-3.2, 1.4), noise_m: float = 0.03, seed: int = 7, layout=None) -> dict:
    WALLS, OPENINGS, OBJECTS, SECTIONS, depth, width = layout or (globals()["WALLS"], globals()["OPENINGS"],
                                                                      globals()["OBJECTS"], globals()["SECTIONS"], 8, 10)
    rng = random.Random(seed)
    ids = lambda: str(uuid.UUID(int=rng.getrandbits(128))).upper()  # noqa: E731
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))

    def world(x, y):  # plan point -> RoomPlan X, Z after the turn and shift
        px, py = x * c - y * s + shift[0], x * s + y * c + shift[1]
        return px, -py

    def transform(x, y, y_mid, yaw_deg):
        X, Z = world(x, y)
        a = math.radians(yaw_deg + turn_deg)
        ux, uz = math.cos(a), -math.sin(a)          # local x along the item, in X, Z
        return [ux, 0, uz, 0, 0, 1, 0, 0, -uz, 0, ux, 0, X, FLOOR_Y + y_mid, Z, 1]  # col2 = col0 x col1

    def surface(cat, x, y, yaw, w, h, y_mid, parent=None):
        return {"identifier": ids(), "parentIdentifier": parent, "category": cat, "confidence": {"high": {}},
                "dimensions": [w, h, 0], "transform": transform(x, y, y_mid, yaw), "polygonCorners": [],
                "completedEdges": [], "curve": None, "story": 0}

    walls = []
    for (ax, ay), (bx, by) in WALLS:
        jit = lambda: rng.uniform(-noise_m, noise_m)  # noqa: E731
        ax, ay, bx, by = ax + jit(), ay + jit(), bx + jit(), by + jit()
        walls.append(surface({"wall": {}}, (ax + bx) / 2, (ay + by) / 2, math.degrees(math.atan2(by - ay, bx - ax)),
                             math.dist((ax, ay), (bx, by)), H, H / 2))
    out = {"doors": [], "windows": [], "openings": []}
    for kind, wi, at, w, h, sill in OPENINGS:
        (ax, ay), (bx, by) = WALLS[wi]
        horizontal = ay == by
        x, y = (at, ay) if horizontal else (ax, at)
        cat = {"door": {"door": {"isOpen": True}}, "window": {"window": {}}, "opening": {"opening": {}}}[kind]
        yaw = math.degrees(math.atan2(by - ay, bx - ax))
        out[f"{kind}s"].append(surface(cat, x, y, yaw, w, h, sill + h / 2, walls[wi]["identifier"]))
    objects = [{"identifier": ids(), "parentIdentifier": None, "category": {cat: {}}, "confidence": {"high": {}},
                "dimensions": [w, h, d], "transform": transform(x, y, h / 2, yaw), "attributes": {}, "story": 0}
               for cat, x, y, w, d, h, yaw in OBJECTS]
    sections = [{"label": lab, "center": [world(x, y)[0], FLOOR_Y, world(x, y)[1]], "story": 0} for lab, x, y in SECTIONS]
    floor = surface({"floor": {}}, width / 2, depth / 2, 0, width, depth, 0)
    floor["dimensions"] = [width, depth, 0]
    return {"version": 2, "identifier": ids(), "story": 0, "walls": walls, **out, "objects": objects,
            "floors": [], "sections": sections,
            "referenceOriginTransform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--cafe"]
    text = json.dumps(cafe() if "--cafe" in sys.argv else home(), indent=1)
    (open(args[0], "w").write(text + "\n") if args else print(text))
