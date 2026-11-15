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


def garage_plan(sid="g", label="Garage", door_w=4.88, door_h=2.13, objects=(), size=6.2, depth=None):
    walls, openings = [], []

    def wall(wid, a, b, rooms):
        walls.append({"id": wid, "floor": "f1", "a": list(a), "b": list(b), "type": "wall", "thickness": 0.1,
                      "length": math.dist(a, b), "rooms": list(rooms), "openings": []})

    y0, y1 = -2.2, -2.2 + (depth or size)
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


def test_a_low_gym_ceiling_fails_the_verdict():
    p = garage_plan()
    p["rooms"][0]["height"] = 2.2
    r = run(p, count=0, uses=["squat_rack"])
    assert check(r, "gym.ceiling").status == "fail" and r.verdict.status == "fail"


def test_a_motorhome_fails_even_an_unmeasured_door():
    r = run(garage_plan(door_h=2.03), vehicle="class_a_rv", count=1)
    assert check(r, "door_height").status == "fail" and "8 ft" in r.verdict.text


def test_a_chosen_room_is_named_and_a_wrong_id_is_an_error():
    import pytest

    from threshold.tools import ToolError
    r = run(garage_plan(), room="G", vehicle="toyota_camry", count=1)
    assert "unlabelled" not in r.verdict.text
    with pytest.raises(ToolError):
        run(garage_plan(), room="nope")


def test_parked_vehicles_name_a_model_that_ships():
    from pathlib import Path

    from threshold.tools.furniture_fit import MODELS
    from threshold.tools.garage_fit.vehicles import THING_MODEL, VEHICLES, model_of
    trucks = run(garage_plan(), vehicle="ford_f150", count=2)
    assert [o.model for o in trucks.overlays if o.kind == "box" and o.label.startswith("Ford")] == ["vehicle/pickup"] * 2
    by = {o.label: o for o in run(garage_plan(), count=0, uses=["motorcycle", "workbench"]).overlays if o.kind == "box"}
    assert by["Motorcycle"].model == "vehicle/motorcycle"
    assert by["Motorcycle"].size[0] > by["Motorcycle"].size[1]  # a model's length runs along the box's first side
    assert by["Workbench"].model is None  # its box is bench plus standing room, not a bench
    assert model_of("golf_cart") is None and model_of("sprinter_high") == "vehicle/van"
    shipped = Path(__file__).parents[4] / "web/public/models"
    named = {model_of(v) for v in VEHICLES} | set(THING_MODEL.values()) | set(MODELS.values())
    assert not [m for m in named - {None} if not (shipped / f"{m}.glb").is_file()]


def _back_wall_fittings(size=6.2):
    """Shelving and fittings 0.3 m deep along the whole back wall, as a phone scan would measure them."""
    y_face = -2.2 + size - 0.05
    return [{"id": "x0", "floor": "f1", "room": "G", "label": "storage", "category": "storage",
             "center": [size / 2, y_face - 0.15, 0.9], "size": [size - 0.2, 0.3, 1.8], "yaw_deg": 0}]


def test_depth_is_its_own_check_and_back_wall_fittings_count():
    plain = run(garage_plan("f150"), vehicle="ford_f150", count=1)        # 6.1 m (20 ft) inside
    c = check(plain, "depth")
    assert c.status == "warn" and abs(c.measured - 6.1) < 0.01               # 5.89 m truck: no room to walk round
    assert any(x.id == "cannot.garage_depth" for x in plain.checks)          # a wall-graph scan cannot see fittings
    full = run(garage_plan("f150b", objects=_back_wall_fittings()), vehicle="ford_f150", count=1)
    c = check(full, "depth")
    assert c.status == "fail" and abs(c.measured - 5.8) < 0.01 and "clear of 1 object" in c.rule
    assert full.verdict.status == "fail" and not any(x.id == "cannot.garage_depth" for x in full.checks)


def test_a_boat_garage_by_storage_length_and_door_opening():
    # built around the boat: 24 x 25 ft inside, 9.5 ft ceiling, an 18 x 8 ft door
    p = garage_plan("boat", door_w=18 * 0.3048, door_h=8 * 0.3048, size=24 * 0.3048 + 0.1, depth=25 * 0.3048 + 0.1)
    next(r for r in p["rooms"] if r["id"] == "G")["height"] = 9.5 * 0.3048
    overall = run(p, vehicle="boat_20ft", count=1)
    assert check(overall, "depth").status == "warn"                            # 7.0 m overall
    assert check(overall, "door_height").status == "warn"                      # 2.40 m boat under a 2.44 m opening
    assert check(overall, "ceiling").status == "pass"                          # the ceiling is not the limit
    assert "tight: little room to walk round" in overall.verdict.text
    stored = run(p, vehicle="boat_20ft", count=1, storage_length_m=6.4)
    assert check(stored, "depth").status == "pass"
    assert any(a.id == "garage.storage_length_m" and a.value == 6.4 for a in stored.assumptions)


def test_an_8_ft_trailer_does_not_clear_an_8_ft_door():
    r = run(garage_plan("trailer", door_w=2.44), vehicle="utility_trailer", width_m=2.44, count=1)
    c = check(r, "door_width")
    assert c.status == "fail" and "fenders and side lights" in c.rule
