from threshold.agent import prefs
from threshold.agent.investigator import Investigation, attach
from threshold.agent.workspace import BriefSet, Scope, Session, ToolEnable

from .conftest import plans


def setup(session):
    session.submit(BriefSet(by="user", scope=Scope(sids=["t1"]), persona="wheelchair_user"))
    session.submit(ToolEnable(tool="door_widths"))


def test_removing_a_tool_is_learned_and_undo_forgets_it(session):
    setup(session)
    entries = session.submit({"op": "tool.disable", "tool": "door_widths"}, by="user")
    assert entries[1].cause == entries[0].seq and "tool.off.door_widths" in session.doc.prefs
    assert prefs.learned(session.doc)[0]["text"].startswith("You removed Door widths")
    session.undo()
    assert "tool.off.door_widths" not in session.doc.prefs and session.doc.tools[0].enabled


def test_rejected_finding_is_muted_on_the_next_run(session):
    setup(session)
    inv = Investigation(session)
    inv.run("door_widths", {"scan": "t1"})
    f = session.doc.findings[0]
    session.submit({"op": "finding.add", "finding": {**f.model_dump(), "feedback": {"verdict": "rejected",
                                                                                   "reason": "I never use that door"}}},
                   by="user")
    assert any(k.startswith("mute.") for k in session.doc.prefs)
    out = inv.run("door_widths", {"scan": "t1"})
    assert out["hidden_because_rejected"] == 1
    assert f.id not in [x["id"] for x in out["findings"]]


def test_threshold_edit_is_used_and_marks_the_run_stale(session):
    setup(session)
    inv = Investigation(session)
    first = inv.run("door_widths", {"scan": "t1"})
    assert first["inputs_from_preferences"] == {"min_width_m": "access.door_width_m", "standard": "access.door_standard"}
    session.submit({"op": "pref.set", "key": "access.door_width_m", "value": 0.6}, by="user")
    assert next(r for r in session.doc.runs if r.id == first["run"]).stale
    assert inv.run("door_widths", {"scan": "t1"})["verdict"] == "pass"


def test_label_correction_reaches_tools(session):
    setup(session)
    session.submit({"op": "pref.set", "key": "label.t1.r3", "value": "Kitchen"}, by="user")
    session.submit(ToolEnable(tool="room_census"))
    Investigation(session).run("room_census", {"scan": "t1"})
    metrics = {m.id for m in session.doc.runs[-1].result.metrics}
    assert "area.Kitchen" in metrics and "area.Unlabelled" not in metrics
    assert prefs.learned(session.doc)[-1]["text"] == "You said this room is a Kitchen"


def test_a_new_session_starts_with_what_the_profile_learned(tmp_path):
    a = attach(Session.create(root=tmp_path), plans)
    a.submit({"op": "pref.set", "key": "access.door_width_m", "value": 0.9, "reason": "You set it"}, by="user")
    b = Session.create(root=tmp_path)
    assert b.doc.prefs["access.door_width_m"].value == 0.9 and b.base.id != a.base.id


def test_rerun_retires_findings_it_no_longer_reports(session):
    setup(session)
    inv = Investigation(session)
    inv.run("door_widths", {"scan": "t1"})
    assert len(session.doc.findings) == 2
    session.submit({"op": "pref.set", "key": "access.door_width_m", "value": 0.6}, by="user")
    second = inv.run("door_widths", {"scan": "t1"})["run"]
    assert {f.superseded_by for f in session.doc.findings} == {second}
