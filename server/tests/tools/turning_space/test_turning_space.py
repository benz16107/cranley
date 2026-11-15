from threshold.tools import run_tool


def test_circles_against_the_diameter(ctx):
    r = run_tool("turning_space", {"scan": "home", "diameter_m": 2.92}, ctx)
    st = {c.id: c.status for c in r.checks}
    assert st["turn.L"] == "pass"                       # 4 x 6 m: about 3.9 m
    assert st["turn.T"] == "warn"                       # 2.90 against 2.92: within the scan tolerance
    assert st["turn.H"] == "warn"
    lens = next(o for o in r.overlays if o.kind == "lens")
    assert abs(lens.values["T"] - 2.9) < 0.01           # 3 m wide less half a wall each side


def test_no_outlines_is_unknown(ctx):
    assert run_tool("turning_space", {"scan": "bare"}, ctx).verdict.status == "unknown"


def test_a_small_circle_fails(ctx):
    st = {c.id: c.status for c in run_tool("turning_space", {"scan": "home", "diameter_m": 3.0}, ctx).checks}
    assert st["turn.T"] == "fail" and st["turn.L"] == "pass"


def _store(boxes=False):
    """A 6 x 4 m shop with two long shelving units and, maybe, boxes left on the floor by the door."""
    from tests.tools.conftest import make_plan
    p = make_plan("store", [("s", 0, 0, 6, 4, "Retail")], doors=[("s", None, 1.0)])
    p["openings"][0]["center"] = [1.5, 0]
    p["has"]["objects"] = True
    o = lambda i, c, sz, lab: {"id": i, "floor": "f1", "room": "s", "label": lab, "category": "storage",
                               "center": [*c, 0.8], "size": [*sz, 1.6], "yaw_deg": 0}
    p["objects"] = [o("a", (3, 1.4), (5, 0.8), "shelf"), o("b", (3, 2.9), (5, 0.8), "shelf")]
    if boxes:
        p["objects"].append(o("c", (1.5, 0.55), (0.8, 0.6), "boxes"))
    return p


def test_floor_objects_shrink_the_circle_and_the_aisle():
    from threshold.tools import ToolContext, run_tool
    p = _store()
    st = {c.id: c for c in run_tool("turning_space", {"scan": "store"}, ToolContext(plans=lambda s: p)).checks}
    assert st["turn.s"].status == "fail" and abs(st["turn.s"].measured - 0.95) < 0.01   # 3.9 m in the empty room
    assert st["aisle.s"].status == "pass" and abs(st["aisle.s"].measured - 0.95) < 0.01
    p = _store(boxes=True)
    r = run_tool("turning_space", {"scan": "store"}, ToolContext(plans=lambda s: p))
    st = {c.id: c for c in r.checks}
    assert st["aisle.s"].status == "fail" and st["aisle.s"].measured < 0.3 and "boxes" in st["aisle.s"].rule
    assert "aisle narrower than you need" in r.verdict.text and "cannot.obstructions" in st
