from threshold.tools import run_tool


def test_checklist_level_by_level(ctx):
    r = run_tool("aging_in_place", {"scan": "home", "read_panoramas": False}, ctx)
    ids = {c.id: c for c in r.checks}
    assert ids["steadi.trip_steps"].status in ("fail", "warn")
    assert ids["level.f2"].status == "warn"
    assert sum(c.id.startswith("not_scan.") and c.status == "unknown" for c in r.checks) == 7
    assert r.verdict.status in ("fail", "warn")


def test_unlabelled_scan_does_not_fail_entry_floor(ctx):
    from tests.tools.conftest import make_home
    from threshold.tools import ToolContext
    p = make_home("nolabels")
    for x in p["rooms"]:
        x["label"] = None
    p["quality"]["labels"] = False
    r = run_tool("aging_in_place", {"scan": "nolabels", "read_panoramas": False}, ToolContext(plans=lambda s: p))
    assert {c.id: c.status for c in r.checks}["steadi.entry_floor_living"] == "unknown"


def test_an_occupational_therapists_home_assessment():
    # an OT lists what they measure: doorways, pinch points, thresholds, seat heights, bath width, steps, the bed
    from tests.tools.conftest import make_home
    from threshold.tools import ToolContext, run_tool
    p = make_home("ot")
    r = run_tool("aging_in_place", {"scan": "ot", "read_panoramas": False}, ToolContext(plans=lambda s: p))
    st = {c.id: c for c in r.checks}
    assert st["ot.doorways"].status == "fail" and abs(st["ot.doorways"].measured - 0.65) < 1e-6   # the 0.70 bedroom door
    assert st["ot.thresholds"].status == "fail" and abs(st["ot.thresholds"].measured - 0.15) < 1e-6
    assert "ot.pinch" in st
    assert {"cannot.ot.seats", "cannot.ot.under_bed", "cannot.ot.beside_bed"} <= set(st)
    assert "Home assessment:" in r.verdict.text
    # as a phone scan: a 2 x 1.5 m bed 0.4 m off the bedroom's west wall, and a bath in the bathroom
    p = make_home("ot2")
    p["has"]["objects"] = True
    p["objects"] = [{"id": "b", "floor": "f1", "room": "R", "label": "bed", "center": [1.4, 4.5, 0.3],
                     "size": [1.5, 2.0, 0.6], "yaw_deg": 0},
                    {"id": "t", "floor": "f1", "room": "T", "label": "bathtub", "center": [7.2, 4.5, 0.3],
                     "size": [0.75, 1.6, 0.55], "yaw_deg": 0}]
    st = {c.id: c for c in run_tool("aging_in_place", {"scan": "ot2", "read_panoramas": False},
                                    ToolContext(plans=lambda s: p)).checks}
    bed = st["ot.beside_bed.b"]
    assert bed.status == "pass" and abs(bed.measured - 1.8) < 0.05    # east side: 2.15 to 3.95 m
    assert st["ot.bath.t"].measured == 0.75 and st["ot.bath.t"].status == "unknown"
