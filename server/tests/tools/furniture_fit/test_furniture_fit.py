from threshold.tools import run_tool


def test_sofa_sticks_at_the_bedroom_door(ctx):
    r = run_tool("furniture_fit", {"scan": "home", "object": "sofa", "room": "R"}, ctx)
    assert r.verdict.status == "fail"
    door = next(c for c in r.checks if c.id == "R.door.RB")
    assert door.status == "fail" and door.measured < 0
    box = next(o for o in r.overlays if o.kind == "box")
    assert box.size == (2.13, 0.97, 0.86) and box.status == "fail"


def test_a_mattress_on_its_edge_passes_the_same_door(ctx):
    r = run_tool("furniture_fit", {"scan": "home", "object": "king mattress", "room": "R"}, ctx)
    assert next(c for c in r.checks if c.id == "R.door.RB").status == "pass"


def test_sizes_are_editable_and_a_small_box_fits(ctx):
    r = run_tool("furniture_fit", {"scan": "home", "object": "washer", "room": "T", "length_m": 0.5,
                                   "depth_m": 0.5, "height_m": 0.5}, ctx)
    assert r.verdict.status == "pass"
    assert {a.id: a.value for a in r.assumptions}["furniture.length_m"] == 0.5
