"""A small hand-made apartment for the what-if tests; no sponsor data, no network.

    y=4.2 +-------------+---------------+
          |             |      K        |   K kitchen, 2.4 x 1.7 m
          |      L      LK  (opening)   |
    y=2.5 |   living    +--tk---+--ck---+   CK: closet door 0.60
          |             LT  T   tc  C   |   T bathroom 1.4 m wide: turning circle 1.3 m (fails)
          |             |  bath |closet |   LT: bathroom door 0.75 (fails 32 in), 0.6 m from the corner
    y=0   +------E------+-------+-------+   E: entrance 1.0 on the south wall
         x=0           x=5    x=6.4    x=7.4
"""
import math

import pytest

from threshold.tools import ToolContext


def make_flat(sid: str = "flat") -> dict:
    walls, openings = {}, []

    def wall(wid, a, b, rooms):
        walls[wid] = {"id": wid, "floor": "f1", "a": list(a), "b": list(b), "type": "wall", "thickness": 0.1,
                      "length": math.dist(a, b), "rooms": list(rooms), "openings": []}

    def door(oid, wid, width, kind="doorway", sill=0.0, t=0.5):
        w = walls[wid]
        c = [w["a"][0] + (w["b"][0] - w["a"][0]) * t, w["a"][1] + (w["b"][1] - w["a"][1]) * t]
        openings.append({"id": oid, "wall": wid, "floor": "f1", "type": kind, "width": width, "height": 2.03,
                         "sill": sill, "center": c, "rooms": list(w["rooms"])})
        w["openings"].append(oid)

    wall("l1", (0, 0), (5, 0), "L"); wall("lt", (5, 0), (5, 2.5), "LT"); wall("lk", (5, 2.5), (5, 4.2), "LK")
    wall("l4", (5, 4.2), (0, 4.2), "L"); wall("l5", (0, 4.2), (0, 0), "L")
    wall("t1", (5, 0), (6.4, 0), "T"); wall("tc", (6.4, 0), (6.4, 2.5), "TC"); wall("tk", (5, 2.5), (6.4, 2.5), "TK")
    wall("c1", (6.4, 0), (7.4, 0), "C"); wall("c2", (7.4, 0), (7.4, 2.5), "C"); wall("ck", (6.4, 2.5), (7.4, 2.5), "CK")
    wall("k1", (7.4, 2.5), (7.4, 4.2), "K"); wall("k2", (7.4, 4.2), (5, 4.2), "K")
    door("E", "l1", 1.0); door("LT", "lt", 0.75, t=0.24); door("LK", "lk", 1.2, "opening"); door("CK", "ck", 0.6)

    def room(rid, label, poly, wall_ids):
        return {"id": rid, "floor": "f1", "label": label, "label_confidence": 1, "label_source": "matterport",
                "polygon": [list(p) for p in poly], "extra_polygons": [], "hole_polygons": [], "area": None,
                "height": 2.5, "width": None, "depth": None, "walls": wall_ids, "holes": []}

    rooms = [room("L", "Living Room", [(0, 0), (5, 0), (5, 2.5), (5, 4.2), (0, 4.2)], ["l1", "lt", "lk", "l4", "l5"]),
             room("T", "Bathroom", [(5, 0), (6.4, 0), (6.4, 2.5), (5, 2.5)], ["t1", "tc", "tk", "lt"]),
             room("C", "Closet", [(6.4, 0), (7.4, 0), (7.4, 2.5), (6.4, 2.5)], ["c1", "c2", "ck", "tc"]),
             room("K", "Kitchen", [(5, 2.5), (6.4, 2.5), (7.4, 2.5), (7.4, 4.2), (5, 4.2)], ["tk", "ck", "k1", "k2", "lk"])]
    return {"schema": "scanplan/1", "sid": sid, "name": "Flat", "floors": [{"id": "f1", "label": "1", "sequence": 0,
                                                                        "elevation": 0.0}],
            "geo": None, "walls": list(walls.values()), "openings": openings, "rooms": rooms, "panos": [],
            "floorplans": [], "stairs": [], "has": {"openings": True, "room_labels": True},
            "quality": {"walls": True, "polygons": True, "openings": True, "labels": True, "georef": False,
                        "counts": {}, "notes": []}}


@pytest.fixture
def flat() -> dict:
    return make_flat()


@pytest.fixture
def ctx(flat, tmp_path, monkeypatch):
    """Serves the flat and any what-if scan saved from it; what-if records go to a temporary folder."""
    from threshold.whatif import store
    monkeypatch.setattr(store, "ROOT", tmp_path / "whatif")

    def plans(sid):
        if sid == "flat":
            return make_flat()
        raise LookupError(sid)
    return ToolContext(plans=plans)
