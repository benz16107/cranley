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


def _three_bedrooms(sid):
    from .conftest import make_plan
    p = make_plan(sid)
    p["rooms"].append({**p["rooms"][0], "id": "r5", "area": 30.0})  # a second, bigger Bedroom
    return p


def test_label_correction_spreads_to_siblings_and_marks_doubts(tmp_path):
    ps = {"u1": _three_bedrooms("u1"), "u2": _three_bedrooms("u2"), "u3": _three_bedrooms("u3")}
    s = attach(Session.create(root=tmp_path), ps.__getitem__)
    s.siblings = lambda sid: [x for x in ps if x != sid]
    s.submit(BriefSet(by="user", scope=Scope(sids=list(ps)), persona="wheelchair_user"))
    s.submit(ToolEnable(tool="room_census"))
    run = Investigation(s).run("room_census", {"scan": "u2"})["run"]
    entries = s.submit({"op": "pref.set", "key": "label.u1.r1", "value": "Office"}, by="user")
    spread = {e.op.key: e.op for e in entries[1:]}
    assert all(e.cause == entries[0].seq for e in entries[1:])
    assert spread["label.u2.r1"].value == "Office" and spread["label.u3.r1"].value == "Office"  # same label, same size
    assert spread["doubt.u1.r5"].value == {"label": "Bedroom", "because": "label.u1.r1"}      # same scan, other bedroom
    assert "label.u2.r5" not in spread and "you corrected the same room (r1) in scan u1" in spread["label.u2.r1"].reason
    assert next(r for r in s.doc.runs if r.id == run).stale                                   # u2 was re-labelled
    view = prefs.with_labels(s.plans, s.doc)
    r1, r5 = view("u2")["rooms"][0], view("u1")["rooms"][-1]
    assert (r1["label"], r1["label_confidence"]) == ("Office", 0.7) and r5["label_doubt"] == "label.u1.r1"
    assert next(i for i in prefs.learned(s.doc) if i["key"] == "label.u3.r1")["because"] == "label.u1.r1"
    s.submit({"op": "pref.set", "key": "label.u3.r1", "value": None}, by="user")  # undo one spread label alone
    assert "label.u3.r1" not in s.doc.prefs and "label.u2.r1" in s.doc.prefs
    s.submit({"op": "pref.set", "key": "label.u1.r1", "value": None}, by="user")  # forget the correction: all of it goes
    assert not [k for k in s.doc.prefs if k.startswith(("label.", "doubt."))]


def test_undoing_a_correction_undoes_its_spread(tmp_path):
    ps = {"u1": _three_bedrooms("u1"), "u2": _three_bedrooms("u2")}
    s = attach(Session.create(root=tmp_path), ps.__getitem__)
    s.siblings = lambda sid: [x for x in ps if x != sid]
    s.submit(BriefSet(by="user", scope=Scope(sids=list(ps))))
    s.submit({"op": "pref.set", "key": "label.u1.r1", "value": "Office"}, by="user")
    assert "label.u2.r1" in s.doc.prefs
    s.undo()
    assert not [k for k in s.doc.prefs if k.startswith(("label.", "doubt."))]


def test_two_workspaces_on_one_profile_keep_each_others_preferences(tmp_path):
    a, b = Session.create(root=tmp_path), Session.create(root=tmp_path)
    a.submit({"op": "pref.set", "key": "access.door_width_m", "value": 0.9}, by="user")
    b.submit({"op": "pref.set", "key": "space.min_height_m", "value": 2.2}, by="user")
    a.submit({"op": "tool.disable", "tool": "room_census"}, by="user")  # a saves again, without b's key
    c = Session.create(root=tmp_path)
    assert c.doc.prefs["access.door_width_m"].value == 0.9 and c.doc.prefs["space.min_height_m"].value == 2.2
    b.submit({"op": "pref.set", "key": "access.door_width_m", "value": 0.8}, by="user")  # later edit wins
    a.submit({"op": "shortlist.add", "sid": "t1"}, by="user")                          # an older copy does not
    assert Session.create(root=tmp_path).doc.prefs["access.door_width_m"].value == 0.8
    b.submit({"op": "pref.set", "key": "space.min_height_m", "value": None}, by="user")  # a deletion sticks
    a.submit({"op": "shortlist.remove", "sid": "t1"}, by="user")
    d = Session.create(root=tmp_path)
    assert "space.min_height_m" not in d.doc.prefs and "tool.off.room_census" in d.doc.prefs
    a.undo(next(e.seq for e in a.log if e.op and e.op.op == "tool.disable"))  # undoing tool.disable in a removes what it taught from the profile too
    assert "tool.off.room_census" not in Session.create(root=tmp_path).doc.prefs
