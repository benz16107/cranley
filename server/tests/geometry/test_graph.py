from threshold.geometry import room_graph


def test_links_entrances_and_components(plan):
    g = room_graph(plan)
    assert g["available"]
    assert sorted(l["id"] for l in g["links"]) == ["AB", "BC"]
    assert [(e["id"], e["room"]) for e in g["entrances"]] == [("E", "A")]
    assert g["components"][0] == ["A", "B", "C"] or sorted(g["components"][0]) == ["A", "B", "C"]
    assert ["D"] in g["components"]
    ab = next(l for l in g["links"] if l["id"] == "AB")
    assert ab["width"] == 0.9 and ab["height"] == 2.03 and ab["center"] == [4.0, 2.0]


def test_room_without_polygon_is_a_node_not_an_error(plan):
    d = next(n for n in room_graph(plan)["nodes"] if n["room"] == "D")
    assert d["has_polygon"] is False and d["area"] == 5.0


def test_no_walls_is_not_available(no_walls):
    g = room_graph(no_walls)
    assert g["available"] is False and "no wall graph" in g["reason"]
    assert len(g["nodes"]) == 4


def test_invisible_wall_is_a_link(plan):
    next(w for w in plan["walls"] if w["id"] == "ab")["type"] = "invisible"
    g = room_graph(plan)
    inv = [l for l in g["links"] if l["kind"] == "invisible"]
    assert len(inv) == 1 and inv[0]["width"] == 1.0 and set(inv[0]["rooms"]) == {"A", "B"}


def test_door_on_a_wall_no_room_claims_is_placed_by_probing(plan):
    next(w for w in plan["walls"] if w["id"] == "bc")["rooms"] = []
    next(o for o in plan["openings"] if o["id"] == "BC")["rooms"] = []
    link = next(l for l in room_graph(plan)["links"] if l["id"] == "BC")
    assert set(link["rooms"]) == {"B", "C"} and link["inferred"]


def test_missing_polygon_is_rebuilt_from_walls(plan):
    plan["rooms"][0]["polygon"] = []
    a = next(n for n in room_graph(plan)["nodes"] if n["room"] == "A")
    assert a["has_polygon"] and a["polygon_source"] == "rebuilt" and abs(a["area"] - 16) < 1e-6
