"""A small hand-made ScanPlan: living room A (4 x 4) with the entrance, a 1 m hallway B, bathroom C (2 x 4),
and room D with no walls. Wall centre lines; walls 0.1 m thick.

    y=4  +-----------+               +------+
         |           |               |      |
         E  A        +---AB--B--BC---+  C   |      AB: door 0.9 wide, sill 0     E: entrance 1.0 wide
         |           |               |      |      BC: door 0.7 wide, sill 0.2   W: window on A's south wall
    y=0  +-----W-----+               +------+
        x=0         x=4             x=8   x=10
"""
import json
import math

import pytest

from threshold.config import DATA

FIXTURES = DATA / "fixtures" / "scanplan"


def _plan() -> dict:
    walls, openings = {}, []

    def wall(wid, a, b, rooms, kind="wall"):
        walls[wid] = {"id": wid, "floor": "f1", "a": list(a), "b": list(b), "type": kind, "thickness": 0.1,
                      "length": math.dist(a, b), "rooms": list(rooms), "openings": []}

    def opening(oid, wid, kind, width, t=0.5, height=2.03, sill=0.0):
        w = walls[wid]
        c = [w["a"][0] + (w["b"][0] - w["a"][0]) * t, w["a"][1] + (w["b"][1] - w["a"][1]) * t]
        openings.append({"id": oid, "wall": wid, "floor": "f1", "type": kind, "width": width, "height": height,
                         "sill": sill, "center": c, "rooms": w["rooms"]})
        w["openings"].append(oid)

    wall("a1", (0, 0), (4, 0), "A"); wall("a2", (4, 0), (4, 1.5), "A"); wall("ab", (4, 1.5), (4, 2.5), "AB")
    wall("a3", (4, 2.5), (4, 4), "A"); wall("a4", (4, 4), (0, 4), "A"); wall("a5", (0, 4), (0, 0), "A")
    wall("b1", (4, 1.5), (8, 1.5), "B"); wall("bc", (8, 1.5), (8, 2.5), "BC"); wall("b2", (8, 2.5), (4, 2.5), "B")
    wall("c1", (8, 0), (10, 0), "C"); wall("c2", (10, 0), (10, 4), "C"); wall("c3", (10, 4), (8, 4), "C")
    wall("c4", (8, 4), (8, 2.5), "C"); wall("c5", (8, 1.5), (8, 0), "C")
    opening("E", "a5", "doorway", 1.0)
    opening("W", "a1", "window", 1.2, height=1.2, sill=0.9)
    opening("AB", "ab", "doorway", 0.9)
    opening("BC", "bc", "doorway", 0.7, sill=0.2)

    def room(rid, label, poly, wall_ids, height=2.5):
        return {"id": rid, "floor": "f1", "label": label, "label_confidence": 1, "label_source": "matterport",
                "polygon": [list(p) for p in poly], "area": None, "height": height, "width": None, "depth": None,
                "walls": wall_ids, "holes": []}

    rooms = [room("A", "Living Room", [(0, 0), (4, 0), (4, 1.5), (4, 2.5), (4, 4), (0, 4)],
                  ["a1", "a2", "ab", "a3", "a4", "a5"]),
             room("B", "Hallway", [(4, 1.5), (8, 1.5), (8, 2.5), (4, 2.5)], ["b1", "bc", "b2", "ab"]),
             room("C", "Bathroom", [(8, 0), (10, 0), (10, 4), (8, 4), (8, 2.5), (8, 1.5)],
                  ["c1", "c2", "c3", "c4", "bc", "c5"]),
             room("D", None, [], [], height=None)]
    rooms[3]["area"] = 5.0
    return {"schema": "scanplan/1", "sid": "test", "name": "test", "floors": [{"id": "f1", "label": "1", "sequence": 0}],
            "geo": {"lat": 29.76, "lon": -95.37, "altitude": 0, "yaw_deg": 90.0, "translation": {"x": 0, "y": 0, "z": 0},
                    "source": "test"},
            "walls": list(walls.values()), "openings": openings, "rooms": rooms, "panos": [], "floorplans": [],
            "has": {"openings": True}}


@pytest.fixture
def plan() -> dict:
    return _plan()


@pytest.fixture
def no_walls() -> dict:
    p = _plan()
    p["walls"], p["openings"] = [], []
    for r in p["rooms"]:
        r["polygon"], r["walls"], r["area"] = [], [], 10.0
    return p


def fixture_plans() -> list[dict]:
    return [json.loads(f.read_text()) for f in sorted(FIXTURES.glob("*.json"))] if FIXTURES.exists() else []
