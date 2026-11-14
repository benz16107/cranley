import threshold.tools.life_safety_census as census
from threshold.tools import ToolContext, run_tool

from ..fire_plans import plans, unit


def det(room, conf, pano):
    return {"label": "smoke alarm", "room": room, "in_room": room, "point": None,
            "pano_anchor": {"sid": "unit", "pano": pano, "yaw_deg": 0, "pitch_deg": 80},
            "finding": {"id": f"smoke_alarm_{room}", "title": "smoke alarm", "status": "unknown", "detail": "on ceiling",
                        "anchor": {"sid": "unit", "pano": pano, "yaw_deg": 0, "pitch_deg": 80},
                        "source": {"layer": "model", "method": "vision", "confidence": conf, "note": "x"},
                        "media": [{"kind": "pano", "ref": f"unit/{pano}/0", "box": [0.4, 0.4, 0.5, 0.5]}]}}


def test_seen_not_seen_and_unclear(monkeypatch):
    # B1: a clear alarm. B2: only a low-confidence one. Hallway (serves both bedrooms): nothing, ceiling readable.
    found = [det("B1", "high", "p_B1"), det("B2", "low", "p_B2")]
    monkeypatch.setattr(census, "objects", lambda plan, budget: found)
    monkeypatch.setattr(census, "ceiling_quality", lambda sid, pano: (True, "readable"))
    r = run_tool("life_safety_census", {"scan": "unit"}, ToolContext(plans=plans(unit())))
    by = {f.id.split(":")[-1]: f for f in r.findings}
    assert by["B1"].status == "pass" and by["B1"].media[0].box == (0.4, 0.4, 0.5, 0.5)
    assert by["B2"].status == "unknown" and "possible alarm" in by["B2"].detail
    assert by["H"].status == "warn" and "not a finding of absence" in by["H"].detail
    m = {x.id: x.value for x in r.metrics}
    assert (m["seen"], m["not_seen"], m["could_not_see"]) == (1, 0, 1)
    assert "Tex. Prop. Code §92.255(a)" in r.assumptions[0].label
    assert "not violations" in r.verdict.text


def test_dark_ceiling_and_unread_scan_are_could_not_see(monkeypatch):
    monkeypatch.setattr(census, "ceiling_quality", lambda sid, pano: (False, "ceiling photo too dark to read"))
    monkeypatch.setattr(census, "objects", lambda plan, budget: [])
    r = run_tool("life_safety_census", {"scan": "unit"}, ToolContext(plans=plans(unit())))
    assert {f.status for f in r.findings} == {"unknown"}
    monkeypatch.setattr(census, "objects", lambda plan, budget: None)
    r = run_tool("life_safety_census", {"scan": "unit"}, ToolContext(plans=plans(unit())))
    assert all("not read" in f.detail for f in r.findings)


def test_state_from_address():
    assert census.state_of({"address": "<address>, Los Angeles, CA"}) == "CA"
    assert census.state_of({"address": "<address>, Houston, TX"}) == "TX"
    assert census.state_of({"address": "1 Main St, Trenton, NJ"}) is None
