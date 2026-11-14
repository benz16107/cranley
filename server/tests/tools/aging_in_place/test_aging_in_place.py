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
