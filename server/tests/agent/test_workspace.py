import pytest

from threshold.agent.workspace import (
    OP_NAMES,
    BriefSet,
    FindingAdd,
    PrefSet,
    Question,
    QuestionAnswer,
    QuestionAsk,
    Rejected,
    Run,
    RunFinish,
    RunStart,
    Scope,
    Session,
    ShortlistAdd,
    ShortlistRemove,
    ToolDisable,
    ToolEnable,
    Workspace,
    apply,
    clean,
)

from .conftest import plans

SRC = {"layer": "matterport", "method": "geometry", "confidence": "high"}


def doc_with_scope():
    return apply(Workspace(id="w"), BriefSet(scope=Scope(sids=["t1"])))


def test_seventeen_ops():
    assert len(OP_NAMES) == 17 and len(set(OP_NAMES)) == 17


def test_reducer_is_pure_and_upserts_in_place():
    d0 = Workspace(id="w")
    d1 = apply(d0, ToolEnable(tool="door_widths", reason="a"))
    d2 = apply(d1, ToolEnable(tool="room_census", reason="b"))
    d3 = apply(d2, ToolEnable(tool="door_widths", reason="c"))
    assert d0.tools == [] and [t.id for t in d3.tools] == ["door_widths", "room_census"]
    assert d3.tools[0].reason == "c"
    d4 = apply(d3, ToolDisable(tool="door_widths"))
    assert not d4.tools[0].enabled and d3.tools[0].enabled


def test_answer_fills_facts_and_pref_marks_runs_stale():
    d = apply(Workspace(id="w"), QuestionAsk(question=Question(id="q", key="access.door_width_m", text="?",
                                                               tools=["door_widths"], input={"type": "number"})))
    d = apply(d, QuestionAnswer(id="q", value=0.9))
    assert d.brief.facts["access.door_width_m"] == 0.9 and d.questions[0].answered
    d = apply(d, RunStart(record=Run(id="r", tool="door_widths", inputs_from={"min_width_m": "access.door_width_m"})))
    d = apply(d, RunFinish(id="r", status="done"))
    d = apply(d, PrefSet(key="access.door_width_m", value=0.95))
    assert d.runs[0].stale and d.prefs["access.door_width_m"].value == 0.95
    assert "access.door_width_m" not in apply(d, PrefSet(key="access.door_width_m", value=None)).prefs


def test_shortlist_add_remove():
    d = apply(doc_with_scope(), ShortlistAdd(sid="t1"))
    assert [s.sid for s in d.shortlist] == ["t1"]
    assert apply(d, ShortlistRemove(sid="t1")).shortlist == []


def test_clean_drops_unknown_blocks_and_missing_runs_and_measurements():
    d = doc_with_scope()
    raw = {"op": "panel.upsert", "panel": {"id": "p", "title": "T", "blocks": [
        {"type": "Note", "text": "Look at the bathroom door first."},
        {"type": "Sparkles"},
        {"type": "VerdictHeader", "run": "nope"},
        {"type": "Note", "text": "The door is 0.81 m wide."}]}}
    op, notes = clean(d, raw, plans, {"door_widths"})
    assert [b.type for b in op.panel.blocks] == ["Note"] and len(notes) == 3
    with pytest.raises(Rejected):
        clean(d, {"op": "panel.upsert", "panel": {"id": "p", "title": "T", "blocks": [{"type": "Sparkles"}]}},
              plans, set())


def test_clean_strips_bad_anchors_and_rejects_unknown_tools():
    d = doc_with_scope()
    f = {"id": "f", "title": "Doorway", "status": "fail", "detail": "", "source": SRC, "tool": "door_widths"}
    good, _ = clean(d, {"op": "finding.add", "finding": {**f, "anchor": {"sid": "t1", "opening": "o1"}}}, plans, set())
    assert good.finding.anchor is not None
    for bad in ({"sid": "t1", "opening": "ghost"}, {"sid": "zzz", "room": "r1"},
                {"sid": "t1", "pano": "p9", "yaw_deg": 0, "pitch_deg": 0}):
        op, notes = clean(d, {"op": "finding.add", "finding": {**f, "anchor": bad}}, plans, set())
        assert op.finding.anchor is None and notes
    with pytest.raises(Rejected):
        clean(d, {"op": "camera.focus", "anchor": {"sid": "t1", "room": "ghost"}}, plans, set())
    with pytest.raises(Rejected):
        clean(d, {"op": "tool.enable", "tool": "invented"}, plans, {"door_widths"})
    with pytest.raises(Rejected):
        clean(d, {"op": "shortlist.add", "sid": "zzz"}, plans, set())


def test_clean_makes_ids_unique():
    d = doc_with_scope()
    d = apply(d, FindingAdd(finding={"id": "f", "title": "A", "status": "warn", "detail": "", "anchor": None,
                                     "source": SRC, "tool": "room_census"}))
    op, _ = clean(d, {"op": "finding.add", "finding": {"id": "f", "title": "B", "status": "warn", "detail": "",
                                                       "anchor": None, "source": SRC, "tool": "door_widths"}},
                  plans, set())
    assert op.finding.id == "f~2"
    op, _ = clean(d, {"op": "plan.set", "steps": [{"id": "s", "text": "a"}, {"id": "s", "text": "b"}]}, plans, set())
    assert [s.id for s in op.steps] == ["s", "s~2"]


def test_log_undo_and_persistence(tmp_path):
    s = Session.create(root=tmp_path)
    s.submit(ToolEnable(tool="door_widths"), by="user")
    s.submit(ToolEnable(tool="room_census"), by="user")
    s.undo()
    assert [t.id for t in s.doc.tools] == ["door_widths"]
    assert len(s.log) == 3  # append-only: the undo is an entry
    again = Session.load(s.base.id, root=tmp_path)
    assert again.doc == s.doc
    with pytest.raises(LookupError):
        again.undo(2)


def test_agent_ops_are_cleaned_user_ops_are_not(session):
    session.submit(BriefSet(by="user", scope=Scope(sids=["t1"])))
    with pytest.raises(Rejected):
        session.submit({"op": "tool.enable", "tool": "invented"})
    session.submit({"op": "panel.upsert", "panel": {"id": "p", "title": "T", "blocks": [
        {"type": "Note", "text": "ok"}, {"type": "Bogus"}]}})
    assert len(session.doc.panels[0].blocks) == 1
    with pytest.raises(Rejected):
        session.submit({"op": "panel.upsert", "panel": {"id": "p", "title": "T", "blocks": [{"type": "Bogus"}]}},
                       by="user")


def test_exported_schema_is_current():
    from threshold.agent.export import OUT, schema_text
    assert (OUT / "workspace.schema.json").read_text() == schema_text(), "run: uv run python -m threshold.agent.export"
