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


def test_doorbell_height_and_porch_ceiling():
    # a smart-home owner: mount it too low and it sees shoes and the top of a head; a porch ceiling's IR whites out
    # the night picture
    from threshold.tools.camera_coverage import doorbell_view, porch_glare
    assert doorbell_view(1.22, 90)["face"] == "in view" and doorbell_view(0.9, 90)["face"] == "low"
    assert abs(porch_glare(1.22, 90, 2.4) - 1.18) < 0.01
    p = make_home("bell")
    p["rooms"].append({**p["rooms"][0], "id": "P", "label": "Porch", "polygon": [[0, -2], [4, -2], [4, 0], [0, 0]],
                       "walls": [], "height": 2.2})
    ctx = ToolContext(plans=lambda sid: p)
    r = run_tool("camera_coverage", {"scan": "bell", "doorbell_height_m": 0.9}, ctx)
    st = {c.id: c for c in r.checks}
    assert st["doorbell.E"].status == "fail" and "too low" in st["doorbell.E"].rule
    assert st["porch.E"].status == "warn" and "misses a visitor's face" in r.verdict.text
    r = run_tool("camera_coverage", {"scan": "home", "doorbell_height_m": 1.22}, CTX)
    st = {c.id: c.status for c in r.checks}
    assert st["doorbell.E"] == "pass" and st["cannot.porch.E"] == "unknown"
