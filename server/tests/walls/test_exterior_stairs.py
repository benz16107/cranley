"""openings[].exterior and plan.stairs on hand-made scans.

    y=3  d------e------f       r1: a b e d (4 x 3), r2: b c f e (4 x 3)
         |  r1  |  r2  |       door "front" on d-a (outer edge), door "mid" on b-e (between the rooms),
    y=0  a------b------c       window "win" on c-f (outer edge of r2), door "closet" on a stub inside r1
"""
from tests.data_layer.test_scanplan_hardening import floor, model, pano, room
from threshold.scanplan import apply_georef_fit, normalize

PTS = {"a": (0, 0), "b": (4, 0), "c": (8, 0), "d": (0, 3), "e": (4, 3), "f": (8, 3), "s": (2, 1.5), "t": (2, 3)}
EDGES = {"ab": ("a", "b"), "bc": ("b", "c"), "cf": ("c", "f"), "fe": ("f", "e"), "ed": ("e", "d"), "da": ("d", "a"),
         "be": ("b", "e"), "st": ("s", "t")}


def door(oid, kind="doorway"):
    return [{"id": oid, "type": kind, "width": 0.9, "height": 2.0, "lowerElevation": 0, "relativeCenter": 0.5}]


def two_rooms(kind="house"):
    f = floor("f", PTS, EDGES, openings={"da": door("front"), "be": door("mid"), "cf": door("win", "window"),
                                         "st": door("closet")})
    m = model([f], [room("r1", "f", ["ab", "be", "ed", "da", "st"]), room("r2", "f", ["bc", "cf", "fe", "be"])])
    return normalize(m, {"kind": kind})


def by_id(plan):
    return {o["id"]: o for o in plan["openings"]}


def test_house_doors_on_the_outline_lead_outside():
    o = by_id(two_rooms())
    assert o["front"]["exterior"] is True and o["front"]["on_outline"]
    assert o["mid"]["exterior"] is False and o["mid"]["exterior_source"] == "rooms"
    assert o["win"]["exterior"] is True
    assert o["closet"]["exterior"] is False and not o["closet"]["on_outline"]  # inside the outline: unscanned closet


def test_unit_door_on_the_outline_is_unknown_but_window_is_exterior():
    plan = two_rooms("apartment_unit")
    o = by_id(plan)
    assert o["front"]["exterior"] is None and o["win"]["exterior"] is True
    assert plan["quality"]["counts"]["openings_exterior_unknown"] == 1


def test_footprint_settles_outline_doors():
    plan = two_rooms("apartment_unit")
    plan["geo"] = {"lat": 29.76, "lon": -95.37, "yaw_deg": 0.0, "translation": {"x": 0.0, "y": 0.0}}
    fit = {"rotation_deg": 0.0, "shift_m": 0.0, "shift_enu": [0.0, 0.0], "pivot_enu": [0.0, 0.0], "iou": 0.9,
           "residual_m": 0.3, "method": "footprint_iou"}
    # the building runs far west, south and north of the unit: the front door (x=0) is deep inside it, so it
    # opens to a corridor; the window (x=8) is 0.5 m from the east wall of the building
    apply_georef_fit(plan, fit, True, [[-10, -3], [8.5, -3], [8.5, 6], [-10, 6], [-10, -3]])
    o = by_id(plan)
    assert o["front"]["exterior"] is False and o["front"]["exterior_source"] == "footprint"
    assert o["win"]["exterior"] is True and o["win"]["exterior_source"] == "footprint"


def test_stairs_join_floors_but_a_view_across_a_void_does_not():
    f0 = floor("f0", PTS, EDGES, seq=0)
    f1 = floor("f1", {k: v for k, v in PTS.items()}, {f"u{k}": v for k, v in EDGES.items()}, seq=1)
    panos = [pano("p0", 1, 1, 1.5, "f0", "r1"), pano("p1", 4.5, 1, 4.5, "f1"),   # 3 m up, 3.5 m along: a stair
             pano("p2", 7, 2, 1.5, "f0"), pano("p3", 7, 2.2, 4.6, "f1"),          # almost straight above: too steep
             pano("p4", 1, 2, 1.5, "f0"), pano("p5", 9.9 + 1, 2, 4.5, "f1")]     # 9.9 m along for 3 m up: a view
    for a, b in (("p0", "p1"), ("p2", "p3"), ("p4", "p5")):
        next(p for p in panos if p["id"] == a)["anchor"]["neighbors"] = [b]
        next(p for p in panos if p["id"] == b)["anchor"]["neighbors"] = [a]
    plan = normalize(model([f0, f1], [], panos))
    pairs = {tuple(s["panos"]) for s in plan["stairs"]}
    assert ("p0", "p1") in pairs and ("p4", "p5") not in pairs
    s = next(s for s in plan["stairs"] if s["panos"] == ["p0", "p1"])
    assert s["floors"] == ["f0", "f1"] and s["rooms"] == ["r1", None] and s["rise_m"] == 3.0
    assert ("p2", "p3") not in pairs  # 0.2 m along for 3.1 up is steeper than any stair; a ladder or a mislabel
