"""quake_ready on the feng_shui test house (hand-made, no sponsor data); the vision model is replaced by a stub."""
from threshold.tools import ToolContext, run_tool
from threshold.tools import quake_ready as Q

from ..feng_shui.test_feng_shui import house


def go(plan, **inputs):
    return run_tool("quake_ready", {"scan": plan["sid"], **inputs}, ToolContext(plans=lambda sid: plan))


def test_safe_spot_hugs_the_inside_wall_away_from_the_window():
    res = go(house(), look=False)
    spot = next(f for f in res.findings if f.id == "quake_ready:fs:safe:R")
    x, y, _ = spot.anchor.point
    assert abs(x - 6.5) < 1e-6 and spot.status == "pass"  # half a metre off the wall shared with the hall
    c = next(c for c in res.checks if c.id == "safe:R")
    assert c.measured > 3  # the only window is on the east wall at y=3
    titles = [f.title for f in res.findings]
    assert "Bedroom checklist" in titles and "Find the gas shutoff (on site)" in titles


def test_tall_furniture_near_the_bed(monkeypatch):
    p = house()
    p["panos"] = [{"id": "pR", "label": "R", "position": [7.5, 3, 1.5], "rotation": [0, 0, 0, 1], "floor": "f1",
                   "room": "R", "neighbors": []}]
    media = [{"kind": "pano", "ref": "fs/pR/2", "box": [0.1, 0.1, 0.3, 0.6]}]

    def fake(plan, panos):
        assert panos == ["pR"]
        return [{"label": "bed", "room": "R", "point": [7.5, 4.5, 0.3], "finding": {"anchor": {"sid": "fs", "room": "R"}, "media": media}},
                {"label": "tall bookcase or shelf", "room": "R", "point": [8.7, 4.0, 1.0],
                 "finding": {"anchor": {"sid": "fs", "point": [8.7, 4.0, 1.0]}, "media": media}}]
    monkeypatch.setattr(Q, "_find", fake)
    res = go(p)
    tall = [f for f in res.findings if ":tall:" in f.id]
    assert [f.title for f in tall] == ["Tall bookcase or shelf near the bed"] and tall[0].media[0].ref == "fs/pR/2"
    assert not any(f.title == "Bedroom checklist" for f in res.findings)
