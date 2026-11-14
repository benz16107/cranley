"""ScanPlan on the awkward shapes real scans have: spurs, shared edges, holes, empty boundaries, no walls, several floors."""
from threshold.scanplan import normalize


def floor(fid, points, edges, seq=0, openings=None):
    """points: {vertex id: (x, y)}; edges: {edge id: (vertex a, vertex b)}."""
    return {"id": fid, "label": f"Floor {seq + 1}", "sequence": seq,
            "vertices": [{"id": v, "position": {"x": x, "y": y}} for v, (x, y) in points.items()],
            "edges": [{"id": e, "type": "wall", "thickness": 0.1, "vertices": [{"id": a}, {"id": b}],
                       "openings": (openings or {}).get(e, [])} for e, (a, b) in edges.items()]}


def room(rid, fid, edge_ids, label="Bedroom", area=None, holes=()):
    return {"id": rid, "floor": {"id": fid}, "classifications": [{"label": label, "confidence": 0.9}],
            "dimensions": {"areaFloor": area} if area else {}, "boundary": {"edges": [{"id": e} for e in edge_ids]},
            "holes": [{"edges": [{"id": e} for e in h]} for h in holes]}


SQUARE = {"a": (0, 0), "b": (4, 0), "c": (4, 3), "d": (0, 3)}
SQUARE_EDGES = {"ab": ("a", "b"), "bc": ("b", "c"), "cd": ("c", "d"), "da": ("d", "a")}


def model(floors, rooms, panos=()):
    return {"id": "t", "floors": floors, "rooms": rooms, "panoLocations": list(panos)}


def pano(pid, x, y, z, fid, rid=None):
    return {"id": pid, "position": {"x": x, "y": y, "z": z}, "anchor": {"floor": {"id": fid}, "room": {"id": rid} if rid else None}}


def test_spur_edge_does_not_break_the_outline():
    # a wall stub from the middle of the bottom wall into the room, listed in the room's boundary: degree 1 and 3 vertices
    f = floor("f", SQUARE | {"m": (2, 0), "s": (2, 1)}, SQUARE_EDGES | {"am": ("a", "m"), "mb": ("m", "b"), "ms": ("m", "s")})
    edges = ["am", "mb", "bc", "cd", "da", "ms"]
    plan = normalize(model([f], [room("r", "f", edges, area=12)]))
    r = plan["rooms"][0]
    assert len(r["polygon"]) == 5 and abs(r["area"] - 12) < 1e-9          # the stub is gone; the outline is the four sides
    assert plan["quality"]["polygons"] and plan["quality"]["counts"]["rooms_with_polygon"] == 1


def test_polygon_is_counter_clockwise_whatever_the_edge_order():
    f = floor("f", SQUARE, SQUARE_EDGES)
    r = normalize(model([f], [room("r", "f", ["da", "cd", "bc", "ab"])]))["rooms"][0]
    shoelace = sum(r["polygon"][i][0] * r["polygon"][(i + 1) % 4][1] - r["polygon"][(i + 1) % 4][0] * r["polygon"][i][1] for i in range(4))
    assert shoelace > 0 and r["area_source"] == "polygon" and r["area"] == 12


def test_two_rooms_sharing_an_edge_each_get_their_own_outline():
    pts = SQUARE | {"e": (8, 0), "g": (8, 3)}
    edges = SQUARE_EDGES | {"be": ("b", "e"), "eg": ("e", "g"), "gc": ("g", "c")}
    f = floor("f", pts, edges)
    plan = normalize(model([f], [room("left", "f", list(SQUARE_EDGES)), room("right", "f", ["bc", "be", "eg", "gc"], "Kitchen")]))
    left, right = plan["rooms"]
    assert left["area"] == 12 and right["area"] == 12
    assert [w["rooms"] for w in plan["walls"] if w["id"] == "bc"] == [["left", "right"]]


def test_a_hole_inside_the_outline_is_reported_and_subtracted():
    pts = SQUARE | {"p": (1, 1), "q": (2, 1), "r": (2, 2), "s": (1, 2)}
    edges = SQUARE_EDGES | {"pq": ("p", "q"), "qr": ("q", "r"), "rs": ("r", "s"), "sp": ("s", "p")}
    f = floor("f", pts, edges)
    r = normalize(model([f], [room("r", "f", list(SQUARE_EDGES), holes=[["pq", "qr", "rs", "sp"]])]))["rooms"][0]
    assert len(r["hole_polygons"]) == 1 and abs(r["area"] - 11) < 1e-9
    assert r["holes"] == [["pq", "qr", "rs", "sp"]]                      # the contract's field is untouched


def test_room_with_two_separate_outlines_keeps_the_second():
    pts = SQUARE | {"p": (10, 0), "q": (12, 0), "r": (12, 2), "s": (10, 2)}
    edges = SQUARE_EDGES | {"pq": ("p", "q"), "qr": ("q", "r"), "rs": ("r", "s"), "sp": ("s", "p")}
    r = normalize(model([floor("f", pts, edges)], [room("r", "f", list(edges))]))["rooms"][0]
    assert len(r["polygon"]) == 4 and r["area"] and len(r["extra_polygons"]) == 1


def test_room_with_no_boundary_has_no_outline_and_is_not_counted_against_polygons():
    f = floor("f", SQUARE, SQUARE_EDGES)
    yard = room("yard", "f", [], label="Other", area=400)
    plan = normalize(model([f], [room("r", "f", list(SQUARE_EDGES)), yard], [pano("p1", 20, 20, 1.4, "f", "yard"), pano("p2", 30, 20, 1.4, "f", "yard")]))
    y = plan["rooms"][1]
    assert y["polygon"] == [] and y["label"] is None and y["center"] == [25.0, 20.0] and y["center_source"] == "panos"
    assert y["area"] == 400 and y["area_source"] == "matterport"
    q = plan["quality"]
    assert q["polygons"] and q["counts"]["rooms_unbounded"] == 1 and any("no boundary" in n for n in q["notes"])


def test_scan_with_rooms_but_no_walls():
    f = {"id": "f", "label": "Floor 1", "sequence": 0, "vertices": [], "edges": []}
    plan = normalize(model([f], [room("a", "f", [], "Bedroom", 12), room("b", "f", [], "Kitchen", 9)], [pano("p", 1, 1, 1.4, "f", "a")]))
    q = plan["quality"]
    assert not q["walls"] and not q["polygons"] and not q["openings"] and q["labels"] and not q["georef"]
    assert plan["walls"] == [] and plan["rooms"][0]["center"] == [1.0, 1.0] and plan["rooms"][1]["center"] is None
    assert any("no wall graph" in n for n in q["notes"])


def test_floor_elevation_comes_from_panorama_heights_and_floors_are_ordered():
    upper = floor("up", SQUARE, SQUARE_EDGES, seq=1)
    lower = floor("lo", SQUARE, {"ab2": ("a", "b")}, seq=0)
    plan = normalize(model([upper, lower], [], [pano("p1", 0, 0, 1.4, "lo"), pano("p2", 1, 1, 1.4, "lo"), pano("p3", 0, 0, 4.9, "up")]))
    assert [f["id"] for f in plan["floors"]] == ["lo", "up"]
    assert [f["elevation"] for f in plan["floors"]] == [0.0, 3.5] and plan["floors"][1]["elevation_source"] == "panos"


def test_void_rooms_do_not_count_as_labels_and_other_is_unlabelled():
    f = floor("f", SQUARE, SQUARE_EDGES)
    plan = normalize(model([f], [room("v", "f", list(SQUARE_EDGES), "Void"), room("o", "f", list(SQUARE_EDGES), "Other")]))
    assert [r["label"] for r in plan["rooms"]] == ["Void", None]
    assert not plan["has"]["room_labels"] and not plan["quality"]["labels"] and plan["quality"]["counts"]["rooms_void"] == 1


def test_edge_with_a_missing_vertex_is_dropped_and_counted():
    f = floor("f", SQUARE, SQUARE_EDGES | {"ghost": ("a", "zz")})
    plan = normalize(model([f], [room("r", "f", list(SQUARE_EDGES))]))
    assert len(plan["walls"]) == 4 and plan["quality"]["counts"]["edges_dropped"] == 1


def test_openings_and_georef_flags():
    f = floor("f", SQUARE, SQUARE_EDGES, openings={"ab": [{"id": "o", "type": "doorway", "width": 0.9, "height": 2.0, "lowerElevation": 0}]})
    m = model([f], [room("r", "f", list(SQUARE_EDGES))])
    m["geocoordinates"] = {"latitude": 29.7, "longitude": -95.3, "rotation": {"x": 0, "y": 0, "z": 0.5, "w": 0.8660254}}
    plan = normalize(m)
    assert plan["openings"][0]["center"] == [2.0, 0.0]                  # a missing relativeCenter means the middle of the wall
    q = plan["quality"]
    assert q["openings"] and not q["georef"] and abs(plan["geo"]["yaw_deg"] - 60) < 1e-6
    assert q["walls"] and q["polygons"] and q["counts"]["walls"] == 4


def test_outline_far_from_matterports_area_is_flagged():
    f = floor("f", SQUARE, SQUARE_EDGES)
    plan = normalize(model([f], [room("r", "f", list(SQUARE_EDGES), area=30)]))
    assert plan["quality"]["counts"]["polygon_area_mismatch"] == 1
    assert "_outline_area" not in plan["rooms"][0]
