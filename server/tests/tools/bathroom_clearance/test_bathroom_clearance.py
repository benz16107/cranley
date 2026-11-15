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


from threshold.tools import ToolContext
from threshold.tools._access import look
from tests.tools.conftest import make_home


def _bath(p, **kw):
    return run_tool("bathroom_clearance", {"scan": p["sid"], "read_panoramas": False, **kw}, ToolContext(plans=lambda s: p))


def _phone_scan(sid, bin_at=None):
    """The test home as a phone scan: a toilet against the bathroom's north wall, and maybe a bin in front of it."""
    p = make_home(sid)
    p["has"]["objects"] = True
    p["objects"] = [{"id": "x0", "floor": "f1", "room": "T", "category": "toilet", "label": "toilet",
                     "center": [6.0, 5.6, 0.4], "size": [0.45, 0.7, 0.8], "yaw_deg": 0, "source": "roomplan"}]
    if bin_at:
        p["objects"].append({"id": "x1", "floor": "f1", "room": "T", "category": "storage", "label": "bin",
                             "center": [*bin_at, 0.3], "size": [0.4, 0.4, 0.6], "yaw_deg": 0, "source": "roomplan"})
    return p


def test_door_swing_is_not_in_a_wall_graph_scan(ctx):
    r = run_tool("bathroom_clearance", {"scan": "home", "read_panoramas": False}, ctx)
    st = {c.id: c for c in r.checks}
    assert st["T.swing.HT"].status == "unknown" and "not in the scan" in st["T.swing.HT"].rule
    assert {"cannot.bath_objects", "cannot.toilet_height", "cannot.ada"} <= set(st)


def test_door_swing_from_the_scan():
    p = make_home("swing")
    next(o for o in p["openings"] if o["id"] == "HT")["swing"] = "in"
    assert {c.id: c.status for c in _bath(p).checks}["T.swing.HT"] == "warn"   # opens in; 30 x 48 in clear of it
    next(o for o in p["openings"] if o["id"] == "HT")["swing"] = "out"
    assert {c.id: c.status for c in _bath(p).checks}["T.swing.HT"] == "pass"


def test_door_swing_read_from_the_panorama(monkeypatch):
    monkeypatch.setattr(look, "objects", lambda plan, panos: ([], None))
    monkeypatch.setattr(look, "bath_fixtures", lambda plan, room: {"error": "not read"})
    monkeypatch.setattr(look, "door_swing", lambda plan, op, rid: {"swing": "in", "confidence": "medium", "media": []})
    r = _bath(make_home("vis"), read_panoramas=True)
    c = {c.id: c for c in r.checks}["T.swing.HT"]
    assert c.status == "warn" and c.rule.endswith("door opens into the bathroom")


def test_a_bin_in_front_of_the_toilet_blocks_the_front_transfer():
    clear = {c.id: c for c in _bath(_phone_scan("clear")).checks}
    assert clear["T.wc_front"].status == "pass" and clear["T.wc_side"].status == "pass"
    assert "cannot.bath_objects" not in clear                  # a phone scan records objects
    blocked = _bath(_phone_scan("bin", bin_at=(6.0, 4.6)))
    st = {c.id: c for c in blocked.checks}
    assert st["T.wc_front"].status == "fail" and st["T.wc_front"].measured < 0.5
    f = next(f for f in blocked.findings if f.id.endswith(":T:wc_front"))
    assert "In the way: bin" in f.detail
    assert st["T.wc_side"].status == "pass"                    # beside the toilet is still clear
