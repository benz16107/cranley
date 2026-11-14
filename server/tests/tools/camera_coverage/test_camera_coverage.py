"""camera_coverage on the hand-made home: proposal covers the entrance and the window, a badly placed camera does not."""
from tests.tools.conftest import make_home
from threshold.tools import ToolContext, run_tool

CTX = ToolContext(plans=lambda sid: make_home())


def test_proposal_covers_entry_points():
    r = run_tool("camera_coverage", {"scan": "home"}, CTX)
    assert {c.id for c in r.checks} == {"E", "W1"}
    assert all(c.status == "pass" for c in r.checks), [c.model_dump() for c in r.checks]
    assert r.verdict.status == "pass"
    kinds = [o.kind for o in r.overlays]
    assert kinds[:2] == ["lens", "pins"] and "route" in kinds  # entrance to the bedroom


def test_camera_in_the_bedroom_misses_the_front_door():
    r = run_tool("camera_coverage", {"scan": "home", "cameras": [{"x": 0.4, "y": 5.6, "heading_deg": -45}]}, CTX)
    by = {c.id: c.status for c in r.checks}
    assert by["E"] == "fail" and r.verdict.status == "fail"
    rule = next(o for o in r.overlays if o.kind == "rule" and o.style == "fail")
    assert "E" in rule.select.openings
    assert any(f.title.startswith("Not on camera") for f in r.findings)
