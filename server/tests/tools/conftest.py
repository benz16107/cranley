"""A small hand-made two-storey home for the access tools; no sponsor data, no network.

    y=9                    +--------+
                           |   K    |   K kitchen: door LK has a 15 cm sill (a step)
    y=6  +--------+--------+---LK---+
         |   R    |   T    |        |   R bedroom: door RB 0.70 (too narrow)
         |        |        |   L    |   T bathroom: door HT 0.95
    y=3  +---RB---+---HT---+        |   L living room: door HL is recorded 3 cm wide (a data error)
         |       H         HL       |   H hallway: entrance E 1.00 on the south wall
    y=0  +---E----+--------+--------+
        x=0      x=4      x=8     x=12
    Upstairs (2.8 m up): U, a 4 x 4 m bedroom, not linked (the plan has no stairs).
"""
import math

import pytest

from threshold.tools import ToolContext


def make_home(sid: str = "home") -> dict:
    walls, openings = {}, []

    def wall(wid, a, b, rooms, floor="f1"):
        walls[wid] = {"id": wid, "floor": floor, "a": list(a), "b": list(b), "type": "wall", "thickness": 0.1,
                      "length": math.dist(a, b), "rooms": list(rooms), "openings": []}

    def door(oid, wid, width, sill=0.0, t=0.5, kind="doorway"):
        w = walls[wid]
        c = [w["a"][0] + (w["b"][0] - w["a"][0]) * t, w["a"][1] + (w["b"][1] - w["a"][1]) * t]
        openings.append({"id": oid, "wall": wid, "floor": w["floor"], "type": kind, "width": width, "height": 2.03,
                         "sill": sill, "center": c, "rooms": w["rooms"]})
        w["openings"].append(oid)

    wall("h1", (0, 0), (4, 0), "H"); wall("h2", (4, 0), (8, 0), "H"); wall("hl", (8, 0), (8, 3), "HL")
    wall("hr", (0, 3), (4, 3), "HR"); wall("ht", (4, 3), (8, 3), "HT"); wall("h3", (0, 3), (0, 0), "H")
    wall("r1", (0, 6), (0, 3), "R"); wall("r2", (4, 6), (0, 6), "R"); wall("rt", (4, 3), (4, 6), "RT")
    wall("t1", (8, 6), (4, 6), "T"); wall("tl", (8, 3), (8, 6), "TL")
    wall("l1", (8, 0), (12, 0), "L"); wall("l2", (12, 0), (12, 6), "L"); wall("lk", (12, 6), (8, 6), "LK")
    wall("k1", (12, 6), (12, 9), "K"); wall("k2", (12, 9), (8, 9), "K"); wall("k3", (8, 9), (8, 6), "K")
    for wid, a, b in (("u1", (0, 0), (4, 0)), ("u2", (4, 0), (4, 4)), ("u3", (4, 4), (0, 4)), ("u4", (0, 4), (0, 0))):
        wall(wid, a, b, "U", "f2")
    door("E", "h1", 1.0)
    door("RB", "hr", 0.70)
    door("HT", "ht", 0.95)
    door("HL", "hl", 0.03)
    door("LK", "lk", 0.95, sill=0.15)
    door("W1", "l2", 1.2, sill=0.9, kind="window")

    def room(rid, label, poly, ws, floor="f1"):
        return {"id": rid, "floor": floor, "label": label, "label_confidence": 1, "label_source": "matterport",
                "polygon": [list(p) for p in poly], "area": None, "height": 2.5, "width": None, "depth": None,
                "walls": ws, "holes": []}

    rooms = [room("H", "Hallway", [(0, 0), (4, 0), (8, 0), (8, 3), (4, 3), (0, 3)], ["h1", "h2", "hl", "ht", "hr", "h3"]),
             room("R", "Bedroom", [(0, 3), (4, 3), (4, 6), (0, 6)], ["hr", "rt", "r2", "r1"]),
             room("T", "Bathroom", [(4, 3), (8, 3), (8, 6), (4, 6)], ["ht", "tl", "t1", "rt"]),
             room("L", "Living Room", [(8, 0), (12, 0), (12, 6), (8, 6), (8, 3)], ["l1", "l2", "lk", "tl", "hl"]),
             room("K", "Kitchen", [(8, 6), (12, 6), (12, 9), (8, 9)], ["lk", "k1", "k2", "k3"]),
             room("U", "Bedroom", [(0, 0), (4, 0), (4, 4), (0, 4)], ["u1", "u2", "u3", "u4"], "f2")]
    for r in rooms:
        from shapely.geometry import Polygon
        r["area"] = Polygon(r["polygon"]).area
    return {"schema": "scanplan/1", "sid": sid, "name": "Test home", "has": {"room_labels": True, "openings": True},
            "floors": [{"id": "f1", "label": "1", "sequence": 0, "elevation": 0.0},
                       {"id": "f2", "label": "2", "sequence": 1, "elevation": 2.8}],
            "geo": None, "walls": list(walls.values()), "openings": openings, "rooms": rooms, "panos": [],
            "floorplans": [],
            "quality": {"walls": True, "polygons": True, "openings": True, "labels": True, "georef": False}}


def no_walls(sid: str = "bare") -> dict:
    p = make_home(sid)
    p["walls"], p["openings"] = [], []
    for r in p["rooms"]:
        r["polygon"], r["walls"] = [], []
    p["quality"] = {"walls": False, "polygons": False, "openings": False, "labels": True, "georef": False}
    return p


PLANS = {"home": make_home(), "home2": make_home("home2"), "bare": no_walls()}


def plans(sid):
    if sid not in PLANS:
        raise LookupError(sid)
    return PLANS[sid]


@pytest.fixture
def ctx() -> ToolContext:
    return ToolContext(plans=plans)
