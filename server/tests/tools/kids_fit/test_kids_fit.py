"""kids_fit on the hand-made two-storey test home: window falls against IRC R312.2.1 and the indoor-only run."""
from tests.tools.conftest import make_home
from threshold.tools import ToolContext, run_tool
from threshold.tools.kids_fit import outward, window_falls


def upstairs_window(plan, oid, sill_above_floor):
    fz = 2.8  # the test home's upper floor; sills are absolute scan z, and a doorway there gives floor_z its level
    if not any(o["id"] == "UD" for o in plan["openings"]):
        plan["openings"].append({"id": "UD", "wall": "u2", "floor": "f2", "type": "doorway", "width": 0.8, "height": 2.0,
                                 "sill": fz, "center": [4, 2], "rooms": ["U"]})
    plan["openings"].append({"id": oid, "wall": "u1", "floor": "f2", "type": "window", "width": 1.0, "height": 1.2,
                             "sill": fz + sill_above_floor, "center": [2, 0], "rooms": ["U"]})


def test_window_falls_follow_the_irc_line_with_the_scan_noise():
    plan = make_home()
    upstairs_window(plan, "low", 0.40)
    upstairs_window(plan, "edge", 0.62)
    upstairs_window(plan, "high", 0.90)
    got = {w["id"]: w["irc"] for w in window_falls(plan)}
    assert got == {"low": "fail", "edge": "measure", "high": "pass"}


def test_outward_points_outside_the_house():
    plan = make_home()
    w1 = next(o for o in plan["openings"] if o["id"] == "W1")    # living room window on the east wall, x = 12
    assert outward(plan, w1)[0] > 12.5
    hl = next(o for o in plan["openings"] if o["id"] == "HT")    # bathroom door between two rooms
    assert outward(plan, hl) is None


def test_indoor_only_run_flags_gates_and_windows(monkeypatch):
    from threshold.sources import index
    monkeypatch.setattr(index, "rows", dict)
    plan = make_home()
    upstairs_window(plan, "low", 0.40)
    r = run_tool("kids_fit", {"scan": "home", "youngest_age": 2, "use_vision": False, "nearby": False},
                 ToolContext(plans=lambda sid: plan))
    st = {c.id: c.status for c in r.checks}
    assert st["stairs"] == "warn" and st["windows"] == "fail" and st["outdoor"] == "unknown"
    assert r.verdict.status == "fail" and "Not checked" in r.verdict.text
