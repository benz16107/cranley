import pytest

from threshold.geometry import reach, route


def test_route_crosses_both_doors_and_finds_narrowest(plan):
    r = route(plan, "A", "C")
    assert r["available"]
    assert [d["opening"] for d in r["doors"]] == ["AB", "BC"]
    assert r["length_m"] == pytest.approx(7.0, abs=0.05)       # centre of A (2,2) to centre of C (9,2)
    assert r["narrowest"]["opening"] == "BC"
    assert r["narrowest"]["width"] == pytest.approx(0.65)      # 0.7 opening less the hung-door allowance
    assert r["narrowest"]["result"] == "likely fail"


def test_corridor_width_is_measured_between_wall_faces(plan):
    corridor = [c for c in route(plan, "A", "C")["chokes"] if c["kind"] == "corridor"]
    assert len(corridor) == 1
    assert corridor[0]["width"] == pytest.approx(0.9)          # 1.0 m between centre lines less two half walls
    assert corridor[0]["status"] == "pass"


def test_route_overlay_matches_contract_4(plan):
    o = route(plan, "entrance", "B")["overlay"]
    assert o["kind"] == "route" and o["floor"] == "f1"
    assert all(len(p) == 3 for p in o["points"]) and o["points"][0][:2] == [0.0, 2.0]
    assert {"point", "width", "status"} <= set(o["chokes"][0])


def test_route_from_a_point(plan):
    r = route(plan, [1.0, 1.0], [9.5, 3.5])
    assert r["available"] and len(r["doors"]) == 2


def test_route_failures_are_reasons_not_exceptions(plan, no_walls):
    assert not route(plan, [50.0, 50.0], "C")["available"]
    assert not route(plan, "nope", "C")["available"]
    assert not route(plan, "A", "D")["available"]               # D is connected to nothing
    assert not route(no_walls, "A", "C")["available"]


def test_reach_judges_each_room_by_its_narrowest_door(plan):
    rooms = {r["room"]: r for r in reach(plan, 0.8128)["rooms"]}
    assert rooms["A"]["result"] == "likely pass"                # entrance 0.95 clear
    assert rooms["B"]["result"] == "likely pass"                # 0.85 clear
    assert rooms["C"]["result"] == "likely fail" and rooms["C"]["bottleneck_width"] == pytest.approx(0.65)
    assert rooms["D"]["connected"] is False
    assert {r["room"]: r["result"] for r in reach(plan, 0.6)["rooms"]}["C"] == "likely pass"


def test_reach_within_tolerance_says_measure_on_site(plan):
    assert {r["room"]: r["result"] for r in reach(plan, 0.84)["rooms"]}["B"] == "measure on site"


def test_implausible_door_is_a_data_error_not_a_fail(plan):
    door = next(o for o in plan["openings"] if o["id"] == "AB")
    door["width"] = 0.03
    rt = route(plan, "entrance", "C")
    ab = next(d for d in rt["doors"] if d["opening"] == "AB")
    assert ab["implausible"] and ab["result"] == "measure on site"
    assert rt["narrowest"]["opening"] != "AB"
    rc = {r["room"]: r for r in reach(plan, 0.6)["rooms"]}
    assert rc["B"]["result"] == "measure on site" and rc["B"]["data_error"] == "AB"


def test_reach_max_step_blocks_a_high_sill(plan):
    # BC has a 0.2 m sill; the floor level is the median sill (0), so a 2 cm robot step stops there
    assert {r["room"]: r["connected"] for r in reach(plan, 0.5, max_step=0.02)["rooms"]}["C"] is False
    assert {r["room"]: r["connected"] for r in reach(plan, 0.5, max_step=0.25)["rooms"]}["C"] is True


def test_route_on_recovered_walls_where_outlines_stop_at_the_inner_face(plan):
    # DXF-recovered walls: the doorway sits on the wall's centre line, each room outline on the wall's inner face
    import copy

    from shapely.geometry import Polygon
    p = copy.deepcopy(plan)
    p["sid"] = "inset"
    for r in p["rooms"]:
        if r["polygon"]:
            r["polygon"] = [list(c) for c in Polygon(r["polygon"]).buffer(-0.09, join_style="mitre").exterior.coords[:-1]]
    r = route(p, "A", "C")
    assert r["available"] and [d["opening"] for d in r["doors"]] == ["AB", "BC"]
