"""garage_fit on hand-made plans; no sponsor data, no network.

    y=6  +-----------------+
         |     House H     |
    y=4  +-----------------+    garage G: 6.1 x 6.1 m inside walls on centre lines 0..6.2, 4..-2.2? no:
         |                 |    G spans x 0..6.2, y -2.2..4 (6.2 x 6.2 centre lines, 0.1 m walls: 6.1 m inside),
         |     Garage G    |    a 4.9 m (16 ft) door centred on the south wall, a person door to the house.
    y=-2.2 +---[ door ]----+
"""
import math

from shapely.geometry import Polygon

from threshold.tools import ToolContext, run_tool


def garage_plan(sid="g", label="Garage", door_w=4.88, door_h=2.13, objects=(), size=6.2):
    walls, openings = [], []

    def wall(wid, a, b, rooms):
        walls.append({"id": wid, "floor": "f1", "a": list(a), "b": list(b), "type": "wall", "thickness": 0.1,
                      "length": math.dist(a, b), "rooms": list(rooms), "openings": []})

    y0, y1 = -2.2, -2.2 + size
    wall("gs", (0, y0), (size, y0), ["G"]); wall("ge", (size, y0), (size, y1), ["G"]); wall("gw", (0, y1), (0, y0), ["G"])
    wall("gh", (0, y1), (size, y1), ["G", "H"]); wall("hn", (0, y1 + 3), (size, y1 + 3), ["H"])
    wall("he", (size, y1), (size, y1 + 3), ["H"]); wall("hw", (0, y1 + 3), (0, y1), ["H"])
    if door_w:
        openings.append({"id": "GD", "wall": "gs", "floor": "f1", "type": "doorway", "width": door_w, "height": door_h,
                         "sill": 0.0, "center": [size / 2, y0], "rooms": ["G"]})
    openings.append({"id": "HD", "wall": "gh", "floor": "f1", "type": "doorway", "width": 0.86, "height": 2.03,
                     "sill": 0.0, "center": [1.0, y1], "rooms": ["G", "H"]})

    def room(rid, lab, poly):
        return {"id": rid, "floor": "f1", "label": lab, "label_confidence": 1, "label_source": "matterport",
                "polygon": [list(p) for p in poly], "area": Polygon(poly).area, "height": 2.7, "width": None,
                "depth": None, "walls": [w["id"] for w in walls if rid in w["rooms"]], "holes": []}

    rooms = [room("G", label, [(0, y0), (size, y0), (size, y1), (0, y1)]),
             room("H", "Living Room", [(0, y1), (size, y1), (size, y1 + 3), (0, y1 + 3)])]
    return {"schema": "scanplan/1", "sid": sid, "name": "Test garage", "floors": [{"id": "f1", "label": "1", "sequence": 0,
            "elevation": 0.0}], "geo": None, "walls": walls, "openings": openings, "rooms": rooms, "panos": [],
            "objects": list(objects), "floorplans": [],
            "quality": {"walls": True, "polygons": True, "openings": True, "labels": True, "georef": False}}


def run(plan, **inputs):
    return run_tool("garage_fit", {"scan": plan["sid"], **inputs}, ToolContext(plans=lambda s: plan))


def check(r, cid):
    return next(c for c in r.checks if c.id == cid)


def test_two_camrys_fit_in_a_20_ft_garage_with_doors_open():
    r = run(garage_plan())
    assert {m.id: m.value for m in r.metrics}["garage.width"] == 6.1
    camry = run(garage_plan(), vehicle="toyota_camry", count=2)
    assert camry.verdict.status == "pass", camry.verdict.text
    boxes = [o for o in camry.overlays if o.kind == "box" and o.label.startswith("Toyota")]
    assert len(boxes) == 2 and all(b.status == "pass" for b in boxes)
    # parked inside the garage, nose toward the house (+y), on the floor
    g = Polygon([(0.05, -2.15), (6.15, -2.15), (6.15, 3.95), (0.05, 3.95)])
    for b in boxes:
        assert g.buffer(0.01).contains(Polygon([(b.center[0] - b.size[1] / 2, b.center[1] - b.size[0] / 2),
                                                (b.center[0] + b.size[1] / 2, b.center[1] - b.size[0] / 2),
                                                (b.center[0] + b.size[1] / 2, b.center[1] + b.size[0] / 2),
                                                (b.center[0] - b.size[1] / 2, b.center[1] + b.size[0] / 2)]))
        assert abs(b.yaw_deg - 90) < 1 and abs(b.center[2] - b.size[2] / 2) < 1e-6


def test_two_f150s_are_tight_and_three_do_not_fit():
    r = run(garage_plan(), vehicle="ford_f150", count=2)
    assert r.verdict.status == "warn"
    sides = [c for c in r.checks if c.id.endswith((".left", ".right"))]
    assert sides and all(c.status == "warn" and 0.45 <= c.measured < 0.9 for c in sides)
    three = run(garage_plan(), vehicle="ford_f150", count=3)
    assert three.verdict.status == "fail" and "do not fit" in three.verdict.text
    assert {m.id: m.value for m in three.metrics}["tight_count"] == 2


def test_a_narrow_door_and_a_low_door():
    r = run(garage_plan(door_w=2.44, door_h=2.13), vehicle="ford_f150", count=1)  # an 8 ft single door
    assert check(r, "door_width").status == "warn"  # mirrors out 2.44 + 0.3 > 2.44; folded 2.13 fits
    tall = run(garage_plan(door_h=2.13), vehicle="sprinter_high", count=1)
    assert check(tall, "door_height").status == "fail" and tall.verdict.status == "fail"
    lifted = run(garage_plan(door_h=2.13), vehicle="jeep_wrangler", count=1, lift_in=3, roof_load_m=0.45)
    assert check(lifted, "door_height").measured == 2.13 and check(lifted, "door_height").status == "fail"


def test_unmeasured_door_height_is_never_a_firm_answer():
    r = run(garage_plan(door_h=2.03), vehicle="ford_f150", count=1)  # Matterport's default, not a measurement
    c = check(r, "door_height")
    assert c.status == "warn" and "Not measured" in c.standard
    assert {m.id: m.value for m in r.metrics}["garage.door_height"] is None


def test_wheelchair_van_needs_its_ramp_strip():
    r = run(garage_plan(), vehicle="wheelchair_van", count=1)
    assert r.verdict.status == "pass" and check(r, "car1.right").threshold == 2.44
    two = run(garage_plan(), vehicle="wheelchair_van", count=2)
    assert two.verdict.status == "fail"


def test_phone_scan_objects_take_floor():
    shelf = {"id": "x1", "floor": "f1", "room": "G", "category": "storage", "label": "Storage",
             "center": [3.1, 3.4, 0.9], "size": [6.0, 1.0, 1.8], "yaw_deg": 0, "source": "roomplan"}
    r = run(garage_plan(objects=[shelf]), vehicle="ford_f150", count=1)
    assert r.verdict.status == "fail"  # 6.1 m deep less a 1 m shelf along the back wall
    assert any(f.title.startswith("In the garage") for f in r.findings)


def test_home_gym_and_workbench_without_a_car():
    r = run(garage_plan(), count=0, uses=["squat_rack", "workbench"])
    assert r.verdict.status == "pass"
    assert check(r, "gym.ceiling").status == "pass" and check(r, "room.squat_rack").status == "pass"
    assert not any(c.id == "door_height" for c in r.checks)


def test_no_garage_says_so():
    p = garage_plan(label="Living Room", door_w=None)
    r = run(p)
    assert r.verdict.status == "unknown" and "no garage" in r.verdict.text


def test_unlabelled_room_with_a_car_wide_door_counts():
    r = run(garage_plan(label=None), vehicle="toyota_camry", count=1)
    assert r.verdict.status == "pass" and "unlabelled" in r.verdict.text
