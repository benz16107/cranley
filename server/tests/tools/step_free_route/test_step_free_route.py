import copy

from threshold.tools import ToolContext, run_tool
from threshold.tools._access import look
from threshold.tools.step_free_route import targets

from ..conftest import OFFICE, make_home, make_plan


def test_office_labels_count_as_bathroom_and_kitchen():
    p = make_plan("toffice", OFFICE)
    assert [r["id"] for r in targets(p, ["Bathroom", "Bedroom", "Kitchen"])] == ["wc", "kit"]


def _run(p, **kw):
    return run_tool("step_free_route", {"scan": p["sid"], "read_panoramas": False, **kw}, ToolContext(plans=lambda s: p))


def test_steps_lead_the_verdict():
    r = _run(make_home())
    assert r.verdict.text.startswith("Steps from the entrance:")
    assert "kitchen, a 15 cm step at a doorway" in r.verdict.text
    assert "bathroom, none found at 2 doorways" in r.verdict.text
    assert "Not step-free: kitchen. Too narrow for you: bedroom." in r.verdict.text
    st = {c.id: c for c in r.checks}
    assert r.checks[0].id.startswith("steps.")
    assert st["steps.K"].status == "fail" and abs(st["steps.K"].measured - 0.15) < 1e-6
    assert st["steps.T"].status == "pass" and st["steps.U"].status == "fail"   # upstairs, no elevator: stairs
    assert "stairs only, no elevator" in st["stepfree.rooms"].rule and "kitchen" in st["stepfree.rooms"].rule
    assert {"cannot.outside", "cannot.obstructions", "cannot.ada", "cannot.elevator"} <= set(st)
    assert all(st[k].status == "unknown" for k in st if k.startswith("cannot."))


def test_an_elevator_makes_upstairs_elevator_only():
    p = make_home("lift")
    p["rooms"].append({**copy.deepcopy(p["rooms"][1]), "id": "EL", "label": "Elevator", "polygon": [], "walls": []})
    r = _run(p)
    st = {c.id: c for c in r.checks}
    assert st["steps.U"].status == "warn" and "elevator only" in st["steps.U"].rule
    assert st["route.U"].status == "warn" and "only step-free way is the elevator" in st["route.U"].rule
    assert "only by the elevator" in st["stepfree.rooms"].rule


def test_a_step_seen_inside_counts_against_the_route(monkeypatch):
    seen = {"label": "step or threshold", "room": "T", "point": [6, 4, 0],
            "finding": {"id": "s1", "detail": "a raised threshold", "anchor": {"sid": "seen", "point": [6, 4, 0]},
                        "media": [], "source": {"layer": "model", "method": "vision", "confidence": "low"}}}
    monkeypatch.setattr(look, "objects", lambda plan, panos: ([seen], None))
    monkeypatch.setattr(look, "central_pano", lambda plan, room: {"id": "p_" + room["id"]})
    p = make_home("seen")
    r = run_tool("step_free_route", {"scan": "seen"}, ToolContext(plans=lambda s: p))
    st = {c.id: c for c in r.checks}
    assert st["steps.T"].status == "warn" and "seen in a panorama" in st["steps.T"].rule
    assert st["route.T"].status == "warn"


def test_each_chair_gets_its_route():
    chairs = [{"name": "Travel chair", "door_width_m": 0.6}, {"name": "Everyday chair", "door_width_m": 0.85}]
    r = _run(make_home("chairs"), chairs=chairs)
    st = {c.id: c for c in r.checks}
    assert st["chair0.R"].status == "fail" and st["chair0.R"].threshold == 0.85   # widest first
    assert st["chair1.R"].status == "pass"                                          # 0.65 m clear, needs 0.60
    assert "Everyday chair reaches bathroom;" in r.verdict.text
    assert "Travel chair reaches bathroom, bedroom" in r.verdict.text
