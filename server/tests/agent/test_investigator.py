"""The investigator through real deepagents, with a scripted chat model instead of the network."""
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from threshold.agent.investigator import Investigation, turn
from threshold.agent.workspace import BLOCK, BriefSet, Scope, ToolEnable


class Scripted(GenericFakeChatModel):
    def bind_tools(self, tools, **kw):
        return self


def call(name, args, i):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}", "type": "tool_call"}])


def script():
    return Scripted(messages=iter([
        call("write_todos", {"todos": [{"content": "Check t1", "status": "in_progress"},
                                       {"content": "Point out what matters", "status": "pending"}]}, 1),
        call("task", {"description": "Check doors and rooms on scan t1", "subagent_type": "building"}, 2),
        call("door_widths", {"scan": "t1"}, 3),                      # inside the subagent
        call("room_census", {"scan": "t1"}, 4),
        call("write_file", {"file_path": "/notes/t1.md", "content": "Bedroom doorway matters."}, 5),
        AIMessage(content="door_widths:t1:o1 matters: it is the bedroom door."),
        call("write_todos", {"todos": [{"content": "Check t1", "status": "completed"},
                                       {"content": "Point out what matters", "status": "in_progress"}]}, 6),
        call("focus", {"finding_id": "door_widths:t1:o1", "reason": "Bedroom door"}, 7),
        AIMessage(content="Start with the bedroom doorway."),
    ]))


def ready(session):
    session.submit(BriefSet(by="user", scope=Scope(sids=["t1"]), persona="wheelchair_user", text="wheelchair",
                            summary="Wheelchair user"))
    for t in ("door_widths", "room_census", "not_built_yet"):
        session.submit(ToolEnable(tool=t, status="planned" if t == "not_built_yet" else "ready"))


def test_run_emits_bound_ops_and_compact_summary(session):
    ready(session)
    seen = []
    session.listeners.append(lambda e: seen.append(e.op.op))
    out = Investigation(session).run("door_widths", {"scan": "t1"})
    assert seen[0] == "run.start" and seen.count("run.progress") == 2  # steps stream while the tool runs
    assert [n for n in seen if n != "run.progress"][:3] == ["run.start", "run.finish", "finding.add"]
    assert {"overlay.upsert", "panel.upsert", "camera.focus"} <= set(seen)
    assert out["verdict"] == "fail" and "min_width_m" in out["inputs_from_persona_defaults"]
    assert "checks" not in out and "result" not in out  # the model never sees raw measurements
    panel = session.doc.panels[0]
    assert [b.type for b in panel.blocks][:3] == ["VerdictHeader", "MetricRow", "CheckList"]
    for b in panel.blocks:
        BLOCK.validate_python(b.model_dump())
    assert session.doc.camera.anchor.opening == "o1"


def test_planned_and_out_of_scope_and_missing_inputs(session):
    ready(session)
    inv = Investigation(session)
    assert inv.run("not_built_yet", {})["skipped"]
    assert "not in this workspace" in inv.run("room_census", {"scan": "t2"})["error"]
    session.submit({"op": "brief.set", "persona": "furniture_mover"}, by="user")
    assert "missing" in inv.run("door_widths", {"scan": "t1"})["error"]


def test_deepagents_turn_streams_plan_runs_and_focus(session):
    ready(session)
    ops = []
    session.listeners.append(lambda e: ops.append(e.op))
    out = turn(session, agent_model=script())
    assert out["status"] == "done" and out["summary"] == "Start with the bedroom doorway."
    names = [o.op for o in ops]
    assert names[0] == "run.start" and ops[1].status == "skipped"  # the planned tool
    assert names.count("plan.set") == 2
    runs = [o for o in ops if o.op == "run.start"]
    assert [r.record.tool for r in runs] == ["not_built_yet", "door_widths", "room_census"]
    assert runs[1].record.plan_step == "s1"
    assert ops[[i for i, n in enumerate(names) if n == "camera.focus"][-1]].reason == "Bedroom door"
    assert session.doc.panels[-1].id == "agent:summary"
    assert (session.root / f"{session.base.id}.casefile.json").exists()


def test_turn_stops_at_questions(session):
    class Compose:
        def structured(self, system, user, schema):
            return schema(persona="furniture_mover", summary="Moving a sofa",
                          tools=[{"id": "door_widths", "reason": "Your sofa has to pass every door."}])
    session.submit(BriefSet(by="user", scope=Scope(sids=["t1"])))
    out = turn(session, "Will my sofa fit?", composer=Compose(), agent_model=None)
    assert out["status"] == "questions"
    session.submit({"op": "question.answer", "id": out["questions"][0], "value": 0.9}, by="user")
    assert session.doc.brief.facts["access.door_width_m"] == 0.9


def test_short_keeps_whole_sentences():
    from threshold.agent.investigator import short
    text = "First sentence here. " * 20
    assert len(short(text)) <= 280 and short(text).endswith(".")
    assert short("x" * 300).endswith("…") and len(short("x" * 300)) == 280
    long = "I found two spaces. **Neither** fits well, and here is why in detail. " * 3 + "\n\n1. **The lobby** first."
    assert short(long) == ("I found two spaces. Neither fits well, and here is why in detail. " * 3).strip()


def test_two_buildings_get_a_ranked_table(session):
    ready(session)
    session.submit(BriefSet(by="user", scope=Scope(sids=["t1", "t2"])))
    inv = Investigation(session)
    runs = [inv.run("door_widths", {"scan": s})["run"] for s in ("t1", "t2")]
    inv.compare()
    table = next(p for p in session.doc.panels if p.id == "compare:door_widths").blocks[0]
    assert table.type == "RankedTable" and table.rows == runs
    assert {c.metric for c in table.columns} == {"doorways", "narrowest", "too_narrow"}
