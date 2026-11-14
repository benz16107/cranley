"""field_check: the on-site list and what the visit found, from tasks the capture layer hands it."""
from threshold.tools import ToolContext, run_tool

OPEN = {"id": "width:home:RB", "kind": "width", "title": "Measure the doorway, hallway to bedroom", "tools": ["door_widths"],
        "findings": ["door_widths:home:RB"], "opening": "RB", "room": "H", "scan_value": 0.65, "threshold": 0.815,
        "standard": "ADA 2010 404.2.3", "status": "open"}
DONE = {**OPEN, "status": "done", "capture": "cap_1", "outcome": {
    "verdict": "contradicted", "status": "pass", "value": 0.84, "err": 0.005, "text": "Wide enough, with the measurement's error allowed for.",
    "method": "manual", "confidence": "high", "points": None}}
ALARM = {"id": "alarm:home:R", "kind": "alarm", "title": "Photograph the ceiling in bedroom", "tools": ["life_safety_census"],
         "room": "R", "unit": "", "status": "done", "capture": "cap_2",
         "outcome": {"verdict": "confirmed", "status": "fail", "text": "No smoke alarm in this room, checked on site.",
                     "method": "manual", "confidence": "high"}}


def run(tasks):
    return run_tool("field_check", {"scan": "home", "tasks": tasks}, ToolContext())


def test_by_hand_it_says_how_to_start_and_an_empty_list_passes():
    assert "Continue on phone" in run(None).verdict.text and run(None).verdict.status == "unknown"
    assert run([]).verdict.status == "pass"


def test_open_tasks_are_listed_as_to_do():
    r = run([OPEN])
    assert r.verdict.status == "unknown" and r.verdict.text == "0 of 1 on-site checks done. 1 still to do."
    assert r.checks[0].rule.endswith(": to do on site") and r.checks[0].measured is None and r.checks[0].threshold == 0.815
    assert r.findings == [] and r.overlays[0].pins[0].label == "check on site" and r.overlays[0].pins[0].anchor.opening == "RB"


def test_outcomes_become_findings_with_the_capture_as_evidence():
    r = run([DONE, ALARM, {**OPEN, "id": "width:home:HL", "opening": "HL"}])
    assert r.verdict.text == "2 of 3 on-site checks done: 1 confirms the scan, 1 contradicts the scan. 1 still to do."
    assert r.verdict.status == "fail"                                 # the worst thing found on site
    door = next(f for f in r.findings if f.id == "field_check:home:width:home:RB")
    assert door.title.endswith("contradicts the scan") and door.status == "pass" and door.media[0].ref == "cap_1"
    assert door.source.layer == "phone" and door.source.method == "manual"
    assert door.detail == ("On site: 0.84 m, give or take 0.005 m. Wide enough, with the measurement's error allowed for. "
                           "The scan had 0.65 m. Limit 0.815 m (ADA 2010 404.2.3).")
    alarm = next(f for f in r.findings if "alarm" in f.id)
    assert alarm.detail == "On site: checked by eye. No smoke alarm in this room, checked on site." and alarm.anchor.room == "R"
    assert {m.id: m.value for m in r.metrics} == {"todo": 1, "confirmed": 1, "contradicted": 1, "measured": 0}
    assert [p.status for p in r.overlays[0].pins] == ["pass", "fail", "unknown"]
