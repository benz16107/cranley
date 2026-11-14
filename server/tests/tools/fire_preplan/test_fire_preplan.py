import threshold.tools.fire_preplan as fp
from threshold.tools import ToolContext, run_tool

from ..fire_plans import no_walls, plans, unit


def _offline(monkeypatch, tmp_path):
    monkeypatch.setattr(fp, "_record", lambda sids: None)          # no CoStar kit
    monkeypatch.setattr(fp, "SHEETS", tmp_path)
    monkeypatch.setattr(fp, "objects", lambda plan, budget: None)   # no vision model


def test_preplan_from_the_scan_alone(monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path)
    r = run_tool("fire_preplan", {"scan": "unit"}, ToolContext(plans=plans(unit())))   # no geo: no aerial
    items = {f.title: f for f in r.findings}
    assert "§6.2.2 Doorways out" in items and "§6.2.2 Hose stretch inside" in items
    assert items["§5.2.2.1 Construction"].status == "unknown"
    assert items["§5.4.1 Site and access"].status == "unknown"
    assert all(f.source is not None for f in r.findings)
    sheet = r.findings[0]
    assert sheet.title == "Printable pre-plan sheet" and sheet.media[0].ref.startswith("fire_preplan/unit.html")
    html = (tmp_path / "unit.html").read_text()
    assert "<svg" in html and "Doorways out" in html and "is not \"absent\"" in html
    assert {c.id for c in r.checks} >= {"section:5.2", "section:6", "section:7"}


def test_not_seen_is_never_absent(monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path)
    monkeypatch.setattr(fp, "objects", lambda plan, budget: [])     # read, nothing found
    r = run_tool("fire_preplan", {"scan": "unit"}, ToolContext(plans=plans(unit())))
    alarm = next(f for f in r.findings if f.title == "§7.5 Smoke alarm")
    assert alarm.status == "unknown" and "Not seen is not absent" in alarm.detail
    assert not any("absent" in f.detail and "not absent" not in f.detail for f in r.findings)


def test_no_wall_scan_still_gives_a_plan(monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path)
    r = run_tool("fire_preplan", {"scan": "flat"}, ToolContext(plans=plans(no_walls())))
    egress = next(f for f in r.findings if f.title == "§6.2.2 Means of egress")
    assert egress.status == "unknown" and "floor plan images" in egress.detail
    assert any(f.title.startswith("§5.2.2.5 Layout") for f in r.findings)
