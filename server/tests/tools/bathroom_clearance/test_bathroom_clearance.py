from threshold.tools import run_tool


def test_bathroom_without_panoramas(ctx):
    r = run_tool("bathroom_clearance", {"scan": "home", "read_panoramas": False}, ctx)
    st = {c.id: c.status for c in r.checks}
    assert st["T.door.HT"] == "pass" and st["T.turn"] == "pass"
    assert st["T.door_space"] == "pass" and st["T.wc_any"] == "pass"   # 4 x 3 m holds 60 x 56 in
    assert any(o.kind == "box" for o in r.overlays)


def test_tiny_bathroom_fails_the_toilet_space(ctx):
    from tests.tools.conftest import make_home
    p = make_home("tiny")
    t = next(x for x in p["rooms"] if x["id"] == "T")
    t["polygon"] = [[4, 3], [5.2, 3], [5.2, 4.2], [4, 4.2]]  # 1.2 x 1.2 m outline, the walls keep their place
    from threshold.tools import ToolContext
    r = run_tool("bathroom_clearance", {"scan": "tiny", "read_panoramas": False}, ToolContext(plans=lambda s: p))
    assert {c.id: c.status for c in r.checks}["T.wc_any"] == "fail"
