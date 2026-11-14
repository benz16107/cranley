from shapely.geometry import Polygon

from threshold.tools._site import align
from threshold.tools.path_to_water import door_barrier, exterior_doors


def plan():
    """Two rooms side by side (8 x 5 m each); a door between them, a back door on the north wall of room B and a
    front door on the south wall of room A. Geo-referenced with a 30 degree yaw."""
    walls = [
        {"id": "s", "floor": "f", "a": [0, 0], "b": [16, 0], "type": "wall", "thickness": 0.1, "length": 16, "rooms": ["A", "B"], "openings": []},
        {"id": "n", "floor": "f", "a": [16, 5], "b": [0, 5], "type": "wall", "thickness": 0.1, "length": 16, "rooms": ["A", "B"], "openings": []},
        {"id": "w", "floor": "f", "a": [0, 5], "b": [0, 0], "type": "wall", "thickness": 0.1, "length": 5, "rooms": ["A"], "openings": []},
        {"id": "e", "floor": "f", "a": [16, 0], "b": [16, 5], "type": "wall", "thickness": 0.1, "length": 5, "rooms": ["B"], "openings": []},
        {"id": "m", "floor": "f", "a": [8, 0], "b": [8, 5], "type": "wall", "thickness": 0.1, "length": 5, "rooms": ["A", "B"], "openings": []},
    ]
    def door(id, wall, c, rooms):
        return {"id": id, "wall": wall, "floor": "f", "type": "doorway", "width": 0.9, "height": 2.0, "sill": 0, "center": c, "rooms": rooms}
    rooms = [{"id": "A", "floor": "f", "label": "Bedroom", "polygon": [[0, 0], [8, 0], [8, 5], [0, 5]], "area": 40},
             {"id": "B", "floor": "f", "label": "Living Room", "polygon": [[8, 0], [16, 0], [16, 5], [8, 5]], "area": 40}]
    return {"sid": "t", "walls": walls, "rooms": rooms, "floors": [{"id": "f", "sequence": 0}], "panos": [],
            "openings": [door("ab", "m", [8, 2.5], ["A", "B"]), door("back", "n", [12, 5], ["B"]), door("front", "s", [4, 0], ["A"])],
            "geo": {"lat": 29.7, "lon": -95.4, "yaw_deg": 30.0, "translation": {"x": 1.0, "y": 2.0}}}


def test_exterior_doors_point_outward():
    ds = {d["id"]: d for d in exterior_doors(plan())}
    assert set(ds) == {"back", "front"}
    assert ds["back"]["out"][1] > 0.9 and ds["front"]["out"][1] < -0.9


def test_alignment_finds_the_convention_that_fits():
    p = plan()
    truth = align.outline_lonlat(p, 1, "enu")  # pretend Vexcel's footprint is the plan placed this way
    a = align.check(p, Polygon(truth.exterior.coords))
    assert a["available"] and (a["yaw_sign"], a["translation"]) == (1, "enu") and a["confidence"] == "high"
    assert a["iou"] > 0.95


def test_cpsc_door_rules():
    assert door_barrier({"alarm": "yes", "pet_door": "no"}, False)[0] == "pass"
    assert door_barrier({"alarm": "no", "self_closing": "yes", "latch_high": "yes", "pet_door": "no"}, False)[0] == "pass"
    assert door_barrier({"alarm": "no", "self_closing": "no", "latch_high": "no", "pet_door": "no"}, False)[0] == "fail"
    assert door_barrier({"alarm": "yes", "pet_door": "yes"}, False)[0] == "fail"
    assert door_barrier(None, False)[0] == "unknown"
    assert door_barrier(None, True)[0] == "pass"  # a power safety cover protects every door


def test_doors_reach_the_pool_around_the_house_when_none_faces_it():
    from threshold.tools.path_to_water import toward_pool
    side, front = {"id": "s", "direct": False, "yard_m": 7.2}, {"id": "f", "direct": False, "yard_m": 12.0}
    assert [d["id"] for d in toward_pool([front, side])] == ["s", "f"] and side["around"]
    back = {"id": "b", "direct": True, "yard_m": 3.0}
    assert toward_pool([front, back]) == [back] and "around" not in back
    assert toward_pool([{"id": "x", "direct": None}]) == []   # not placed on the map: the caller's fallback decides
