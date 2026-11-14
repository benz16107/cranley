"""feng_shui on a hand-made L-shaped house; no sponsor data, no network.

    y=9  +-----+--B--+               L living room, H hallway (front door E on the south wall),
         |     | H2  |               T bathroom in the centre square, H2 back hall with back door B,
    y=6  |  L  +--.--+-----+         R bedroom (door from H at y=1, window on the east wall).
         |     |  T  |     |         The north-east square (x 6-9, y 6-9) is empty: a missing corner.
    y=3  |     +--.--+  R  W
         |     .  H  .     |         North is +y (yaw 0), so the front door faces south.
    y=0  +-----+--E--+-----+
        x=0   x=3   x=6   x=9
"""
import math

from threshold.tools import ToolContext, run_tool
from threshold.tools.feng_shui import kua as K


def house(geo=True) -> dict:
    walls, ops = [], []

    def wall(wid, a, b, rooms, doors=()):
        walls.append({"id": wid, "floor": "f1", "a": list(a), "b": list(b), "type": "wall", "thickness": 0.1,
                      "length": math.dist(a, b), "rooms": list(rooms), "openings": []})
        for oid, c, w, kind, rs in doors:
            ops.append({"id": oid, "wall": wid, "floor": "f1", "type": kind, "width": w, "height": 2.03 if kind == "doorway" else 1.2,
                        "sill": 0.0 if kind == "doorway" else 0.9, "center": list(c), "rooms": list(rs)})
            walls[-1]["openings"].append(oid)

    wall("s1", (0, 0), (3, 0), "L"); wall("s2", (3, 0), (6, 0), "H", [("E", (4.5, 0), 1.0, "doorway", ["H"])])
    wall("s3", (6, 0), (9, 0), "R"); wall("e1", (9, 0), (9, 6), "R", [("W", (9, 3), 1.2, "window", ["R"])])
    wall("n1", (9, 6), (6, 6), "R"); wall("e2", (6, 6), (6, 9), ["H2"])
    wall("n2", (6, 9), (3, 9), ["H2"], [("B", (4.5, 9), 0.9, "doorway", ["H2"])]); wall("n3", (3, 9), (0, 9), "L")
    wall("w1", (0, 9), (0, 0), "L")
    wall("x1", (3, 0), (3, 3), ["L", "H"], [("LH", (3, 1.5), 0.9, "doorway", ["L", "H"])])
    wall("x2", (3, 3), (3, 6), ["L", "T"]); wall("x3", (3, 6), (3, 9), ["L", "H2"])
    wall("x4", (6, 0), (6, 3), ["H", "R"], [("RH", (6, 1), 0.8, "doorway", ["R", "H"])]); wall("x5", (6, 3), (6, 6), ["T", "R"])
    wall("y1", (3, 3), (6, 3), ["H", "T"], [("HT", (4.5, 3), 0.8, "doorway", ["H", "T"])])
    wall("y2", (3, 6), (6, 6), ["T", "H2"], [("TH", (4.5, 6), 0.8, "doorway", ["T", "H2"])])

    def room(rid, label, x0, y0, x1, y1):
        return {"id": rid, "floor": "f1", "label": label, "label_confidence": 1, "label_source": "matterport",
                "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "area": (x1 - x0) * (y1 - y0), "height": 2.5,
                "width": None, "depth": None, "walls": [w["id"] for w in walls if rid in w["rooms"]], "holes": []}

    rooms = [room("L", "Living Room", 0, 0, 3, 9), room("H", "Hallway", 3, 0, 6, 3), room("T", "Bathroom", 3, 3, 6, 6),
             room("H2", "Hallway", 3, 6, 6, 9), room("R", "Bedroom", 6, 0, 9, 6)]
    return {"schema": "scanplan/1", "sid": "fs", "name": "L house", "has": {"room_labels": True, "openings": True},
            "floors": [{"id": "f1", "label": "1", "sequence": 0, "elevation": 0.0}],
            "geo": {"lat": 29.7, "lon": -95.4, "altitude": 0, "yaw_deg": 0.0, "translation": {"x": 0, "y": 0}} if geo else None,
            "walls": walls, "openings": ops, "rooms": rooms, "panos": [], "floorplans": [],
            "quality": {"walls": True, "polygons": True, "openings": True, "labels": True, "georef": geo}}


def go(plan, **inputs):
    return run_tool("feng_shui", {"scan": plan["sid"], **inputs}, ToolContext(plans=lambda sid: plan))


def test_kua_formula_and_tables():
    assert [K.kua(1985, "male"), K.kua(1985, "female"), K.kua(2001, "male"), K.kua(2001, "female")] == [6, 9, 8, 7]
    assert K.kua(1990, "male") == 1 and K.kua(1967, "female") == 9
    assert K.kua(1977, "male") == 2 and K.kua(1990, "female") == 8   # Kua 5 years
    for good, bad in K.TABLE.values():
        assert sorted(good + bad) == sorted(K.DIRS)


def test_compass_reading_of_the_l_house():
    res = go(house(), birth_year=1985, gender="female")
    m = {x.id: x.value for x in res.metrics}
    assert m["door_bearing"] == 180 and m["kua"] == 9 and m["turned"] == 0
    titles = {f.id.split(":", 2)[2]: f for f in res.findings}
    assert "missing:f1:NE" in titles and titles["missing:f1:NE"].title == "Missing corner"
    assert titles["bath_centre:T"].anchor.room == "T"
    assert titles["back_door_line"].anchor.opening == "B"
    assert "faces south" in titles["kua"].detail  # Kua 9: south is personal growth (Fu Wei)
    sectors = {c.id: c for c in res.checks if c.id.startswith("sector:")}
    assert "Bathroom" in sectors["sector:f1:C"].rule and sectors["sector:f1:NE"].status == "warn"
    assert "Bedroom" in sectors["sector:f1:E"].rule or "Bedroom" in sectors["sector:f1:SE"].rule
    lens = next(o for o in res.overlays if o.kind == "lens")
    assert lens.values["T"] == 5 and lens.values["L"] in (2, 6, 7)  # the living room spans the west column
    route = next(o for o in res.overlays if o.kind == "route")
    assert route.points[-1][:2] == (4.5, 9)


def test_bed_in_command_position():
    res = go(house(), birth_year=1985, gender="female")
    place = next(f for f in res.findings if f.id == "feng_shui:fs:place:R")
    assert place.status == "pass", place.detail
    bed = next(o for o in res.overlays if o.kind == "box" and o.label.startswith("Suggested bed"))
    (cx, cy, _), (w, d, _) = bed.center, bed.size
    assert 6 < cx < 9 and 0 < cy < 6 and (w, d) == (1.52, 2.03)
    # not in the door's path: the doorway at y 0.6..1.4 looks east across the room
    half = max(w, d) / 2
    assert cy - half > 1.4 or abs(bed.yaw_deg) % 180 == 90 and cy - w / 2 > 1.4
    assert "favourable" in place.detail


def test_western_convention_names_the_door_row():
    res = go(house(), convention="western")
    sec = {c.id: c.rule for c in res.checks if c.id.startswith("sector:")}
    # the square holding the front door is Career, entrance side, middle
    assert "Career" in sec["sector:f1:N"] and "Hallway" in sec["sector:f1:N"]
    assert "Knowledge" in sec["sector:f1:NE"] and "Living Room" in sec["sector:f1:NE"]


def test_no_geocoordinates_falls_back_to_western():
    res = go(house(geo=False), birth_year=1985, gender="female")
    assert "Western" in res.verdict.text
    assert any("no geocoordinates" in a.value for a in res.assumptions if isinstance(a.value, str))
    assert not any(m.id == "door_bearing" for m in res.metrics)


def test_no_walls_is_unknown():
    p = house()
    p["walls"], p["openings"] = [], []
    assert go(p).verdict.status == "unknown"
