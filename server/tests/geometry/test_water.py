import pytest

from threshold.geometry import flood_levels, water


def test_flood_order_follows_sills(plan):
    lv = flood_levels(plan)["levels"]
    assert lv["A"] == pytest.approx(0.0) and lv["B"] == pytest.approx(0.0)
    assert lv["C"] == pytest.approx(0.2)                    # behind the 0.2 m sill of door BC


def test_depths_and_wetted_areas(plan):
    w = water(plan, 0.1)
    rooms = {r["room"]: r for r in w["rooms"]}
    assert rooms["A"]["depth"] == pytest.approx(0.1) and rooms["C"]["depth"] == 0.0
    assert rooms["A"]["wetted_floor_area"] == pytest.approx(16)
    assert rooms["A"]["wetted_wall_area"] == pytest.approx(16 * 0.1 - 1.0 * 0.1 - 0.9 * 0.1)
    assert set(rooms["A"]["openings_overtopped"]) == {"E", "AB"}
    assert w["overlay"] == {"kind": "water", "level_m": 0.1, "datum": "scan_z"}
    assert w["lens"]["values"]["A"] == pytest.approx(0.1)
    assert [o["room"] for o in w["order"]][-1] == "C"


def test_higher_water_reaches_the_bathroom_and_the_window(plan):
    rooms = {r["room"]: r for r in water(plan, 1.0)["rooms"]}
    assert rooms["C"]["depth"] == pytest.approx(1.0)
    assert "W" in rooms["A"]["openings_overtopped"]


def test_entry_limits_where_water_gets_in(plan):
    assert flood_levels(plan, entry="W")["levels"]["A"] == pytest.approx(0.9)   # only through the window sill


def test_no_walls_still_gives_depths(no_walls):
    w = water(no_walls, 0.5)
    assert w["available"] and w["note"]


def test_a_sunken_room_floods_first_and_deeper(plan):
    import copy
    p = copy.deepcopy(plan)
    for o in p["openings"]:
        if o["id"] == "BC":
            o["sill"] = -0.15                                   # the door down into C
    p["panos"] = ([{"id": f"a{i}", "position": [1 + i, 1, 1.4], "floor": "f1", "room": "A", "rotation": None}
                   for i in range(3)] +
                  [{"id": f"c{i}", "position": [9, 1 + i, 1.25], "floor": "f1", "room": "C", "rotation": None}
                   for i in range(2)])
    w = water(p, 0.05)
    rooms = {r["room"]: r for r in w["rooms"]}
    assert rooms["C"]["step_m"] == pytest.approx(-0.15)
    assert rooms["C"]["depth"] == pytest.approx(0.2) and rooms["A"]["depth"] == pytest.approx(0.05)


def test_one_low_panorama_is_not_a_step(plan):
    import copy
    p = copy.deepcopy(plan)
    p["panos"] = [{"id": "a", "position": [1, 1, 1.4], "floor": "f1", "room": "A", "rotation": None},
                  {"id": "c", "position": [9, 1, 1.0], "floor": "f1", "room": "C", "rotation": None}]
    assert {r["room"]: r for r in water(p, 0.3)["rooms"]}["C"]["step_m"] == 0


def test_rooms_sharing_a_wall_without_a_doorway_still_flood(plan):
    import copy
    p = copy.deepcopy(plan)
    p["openings"] = [o for o in p["openings"] if o["id"] != "AB"]
    for w in p["walls"]:
        w["openings"] = [o for o in w["openings"] if o != "AB"]
    w = water(p, 0.3)  # the floor is now the median of two sills, 0.1
    rooms = {r["room"]: r for r in w["rooms"]}
    assert rooms["B"]["depth"] == pytest.approx(rooms["A"]["depth"]) > 0 and rooms["B"]["via"] is None
    assert "share a wall" in w["note"]
