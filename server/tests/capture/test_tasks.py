"""Phone tasks from other tools' results, and what a measurement that comes back means."""
import pytest

from tests.tools.conftest import plans
from threshold.agent.investigator import Investigation, attach
from threshold.agent.workspace import BriefSet, Run, Scope, Session
from threshold.capture.tasks import LEVEL_VERTICAL_M, judge, tasks
from threshold.tools import Assumption, Check, Finding, Metric, RoomAnchor, ScanScope, Source, ToolResult, Verdict

SRC = Source(layer="model", method="vision", confidence="low")


@pytest.fixture
def session(tmp_path):
    s = attach(Session.create(root=tmp_path), plans)
    s.submit(BriefSet(scope=Scope(sids=["home"])), by="user")
    return s


def fake(s, tool, findings=(), metrics=(), checks=(), assumptions=(), inputs=None):
    s.doc.runs.append(Run(id=f"run_{tool}", tool=tool, sid="home", status="done", inputs=inputs or {}, result=ToolResult(
        tool=tool, scope=ScanScope(sid="home"), verdict=Verdict(status="warn", text="x"), findings=list(findings),
        metrics=list(metrics), checks=list(checks), assumptions=list(assumptions))))


def by_id(ts):
    return {t["id"]: t for t in ts}


def test_door_tools_become_width_and_step_tasks(session):
    inv = Investigation(session)
    inv.run("door_widths", {"scan": "home", "min_width_m": 0.815})
    inv.run("step_free_route", {"scan": "home", "min_width_m": 0.815, "read_panoramas": False})
    t = by_id(tasks(session.doc, plans))
    rb = t["width:home:RB"]                                        # the 0.70 m bedroom door, flagged by both tools: one task
    assert rb["tools"] == ["door_widths", "step_free_route"] and len(rb["findings"]) == 2
    assert rb["scan_value"] == pytest.approx(0.65) and rb["threshold"] == 0.815 and "ADA 2010 404.2.3" in rb["standard"]
    assert rb["title"] == "Measure the doorway, hallway to bedroom 1" and rb["opening"] == "RB" and rb["status"] == "open"
    widths = [x["id"] for x in tasks(session.doc, plans) if x["kind"] == "width"]
    assert widths[:2] == ["width:home:HL", "width:home:RB"]         # both on the route; the data error first
    assert t["width:home:HL"]["scan_value"] is None                # a 3 cm "door" is a data error: no scan value to compare
    assert t["step:home:LK"]["threshold"] == LEVEL_VERTICAL_M and "303.2" in t["step:home:LK"]["standard"]
    assert not any(k.startswith("width:home:HT") for k in t)       # the 0.95 m door passed: nothing to do there


def test_alarm_flood_and_daylight_tasks(session):
    fake(session, "life_safety_census", findings=[
        Finding(id="life_safety_census:home:R", title="Bedroom, smoke alarm not seen", status="warn", detail="", anchor=RoomAnchor(sid="home", room="R"), source=SRC),
        Finding(id="life_safety_census:home:U", title="Bedroom, smoke alarm could not see", status="unknown", detail="", anchor=None, source=SRC),
        Finding(id="life_safety_census:home:T", title="Hallway, smoke alarm seen", status="pass", detail="", anchor=None, source=SRC),
        Finding(id="life_safety_census:home:level:f2", title="Level, smoke alarm not seen", status="warn", detail="", anchor=None, source=SRC)])
    fake(session, "flood_rehearsal", findings=[Finding(id="flood_rehearsal:home:floor_height", title="Floor height", status="pass", detail="", anchor=None, source=SRC)],
         metrics=[Metric(id="floor_height", label="Floor", value=0.3, unit="m", source=SRC)])
    fake(session, "daylight", checks=[Check(id=r, rule="Direct sun", measured=h, threshold=None, unit="h", status="pass")
                                      for r, h in (("L", 6.0), ("K", 2.5), ("T", None))],
         assumptions=[Assumption(id="compass_verified", label="x", value=False)])
    t = by_id(tasks(session.doc, plans))
    assert t["alarm:home:R"]["title"] == "Photograph the ceiling in bedroom 1" and t["alarm:home:U"]["title"].endswith("bedroom 2")
    assert "alarm:home:T" not in t and not any("level" in k for k in t)      # seen alarms and whole-level leads are not tasks
    assert t["floor_height:home:door"]["scan_value"] == 0.3
    assert set(k for k in t if k.startswith("heading")) == {"heading:home:L", "heading:home:K"}   # only rooms with sun hours
    assert "not verified" in t["heading:home:L"]["why"]
    assert (t["heading:home:L"]["unit"], t["alarm:home:R"]["unit"], t["floor_height:home:door"]["unit"]) == ("h", "", "m")
    assert [x["kind"] for x in tasks(session.doc, plans)][0] == "floor_height"                    # the weakest number first


def test_a_capture_with_a_result_marks_its_task_done(session):
    Investigation(session).run("door_widths", {"scan": "home", "min_width_m": 0.815})
    caps = [{"id": "cap_1", "task": "width:home:RB", "result": {"verdict": "contradicted", "status": "pass", "value": 0.84}},
            {"id": "cap_2", "task": "width:home:HL", "result": None}]
    ts = tasks(session.doc, plans, caps)
    t = by_id(ts)
    assert t["width:home:RB"]["status"] == "done" and t["width:home:RB"]["capture"] == "cap_1"
    assert t["width:home:HL"]["status"] == "open" and ts[-1]["id"] == "width:home:RB"            # done tasks sink


def test_judge_width_with_its_error():
    t = {"kind": "width", "threshold": 0.815, "scan_value": 0.65}
    assert judge(t, 0.84)["status"] == "pass" and judge(t, 0.84)["verdict"] == "contradicted"     # the scan had 0.65
    assert judge(t, 0.66)["status"] == "fail" and judge(t, 0.66)["verdict"] == "confirmed"
    assert judge(t, 0.817)["status"] == "warn"                                                   # inside the tape's error
    assert judge(t, 0.84, err=0.04)["status"] == "warn"                                          # a photo's wider error
    assert judge({**t, "scan_value": None}, 0.84)["verdict"] == "measured"


def test_judge_step_and_alarm():
    s = {"kind": "step", "threshold": LEVEL_VERTICAL_M, "scan_value": None}
    assert judge(s, 0.0)["status"] == "pass" and judge(s, 0.0)["verdict"] == "contradicted"       # the scan suspected a step
    assert judge(s, 0.010)["status"] == "warn" and judge(s, 0.15)["status"] == "fail" and judge(s, 0.15)["verdict"] == "confirmed"
    a = {"kind": "alarm"}
    assert judge(a, None, answer="present") == {"verdict": "contradicted", "status": "pass", "value": None, "err": None,
                                                "text": "A smoke alarm is there. The scan's photos did not show it."}
    assert judge(a, None, answer="absent")["status"] == "fail" and judge(a, None, answer="unclear")["status"] == "unknown"


def test_a_step_seen_in_a_panorama_says_where_it_is(session):
    fake(session, "step_free_route", findings=[
        Finding(id="step_free_route:home:seen:step_or_threshold_1", title="Panorama shows step or threshold", status="warn",
                detail="Wood-to-carpet transition at bedroom door. Seen by the vision model in the panorama, not measured.", anchor=None, source=SRC),
        Finding(id="step_free_route:home:seen:step_or_threshold_2", title="Panorama shows step or threshold", status="warn", detail="", anchor=None, source=SRC)])
    t = by_id(tasks(session.doc, plans))
    assert t["step:home:step_or_threshold_1"]["title"] == "Measure the step: wood-to-carpet transition at bedroom door"
    assert t["step:home:step_or_threshold_2"]["title"] == "Measure the step seen on your route"   # no description: the old words
