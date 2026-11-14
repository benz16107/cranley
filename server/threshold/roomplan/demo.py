"""A hand-made RoomPlan export of a made-up one-storey home, in exactly the format the iPhone sends (it decodes as
Apple's `CapturedRoom` in the simulator). The app's demo mode and the converter tests both use it.

    uv run python -m threshold.roomplan.demo ../ios/Threshold/Threshold/Resources/DemoHome.json

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


def home(turn_deg: float = 17.0, shift=(-3.2, 1.4), noise_m: float = 0.03, seed: int = 7) -> dict:
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
    floor = surface({"floor": {}}, 5, 4, 0, 10, 8, 0)
    floor["dimensions"] = [10, 8, 0]
    return {"version": 2, "identifier": ids(), "story": 0, "walls": walls, **out, "objects": objects,
            "floors": [], "sections": sections,
            "referenceOriginTransform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}


if __name__ == "__main__":
    text = json.dumps(home(), indent=1)
    (open(sys.argv[1], "w").write(text + "\n") if len(sys.argv) > 1 else print(text))
