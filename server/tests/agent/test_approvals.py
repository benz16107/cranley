"""Approval before slow tools, long-term memory and the live view, through real deepagents with a scripted model."""
from langchain_core.messages import AIMessage

from threshold.agent import investigator as inv_mod
from threshold.agent import live
from threshold.agent.investigator import ALWAYS, RUN, SKIP, turn

from .test_investigator import Scripted, call, ready


def script(final_tool="room_census"):
    return Scripted(messages=iter([
        call("write_todos", {"todos": [{"content": "Check t1", "status": "in_progress"}]}, 1),
        call("task", {"description": "Check rooms on scan t1", "subagent_type": "building"}, 2),
        call("read_file", {"file_path": "/memories/buildings/t1.md"}, 3),       # inside the subagent
        call("door_widths", {"scan": "t1"}, 4),
        call(final_tool, {"scan": "t1"}, 5),                                     # waits for approval
        call("write_file", {"file_path": "/memories/buildings/t1.md", "content": "The bedroom door decides."}, 6),
        AIMessage(content="door_widths:t1:o1 matters."),
        AIMessage(content="Start with the bedroom doorway."),
    ]))


def approval(session):
    return [q for q in session.doc.questions if q.input.get("x-approval")]


def test_slow_tool_waits_for_approval_then_resumes(session, monkeypatch):
    monkeypatch.setitem(inv_mod.APPROVE, "room_census", "it is slow in this test")
    ready(session)
    model = script()
    out = turn(session, agent_model=model)
    assert out["status"] == "approval"
    [q] = approval(session)
    assert q.text.startswith("Room census") and "slow in this test" in q.text
    assert q.input["enum"] == [RUN, SKIP, ALWAYS] and q.input["x-approval"]["tool"] == "room_census"
    assert [r.tool for r in session.doc.runs if r.status == "done"] == ["door_widths"]  # nothing slow ran yet
    snap = live.snapshot(session.base.id)
    assert snap["status"] == "waiting" and snap["lanes"][0]["agent"] == "building"
    assert snap["lanes"][0]["status"] == "waiting" and "door_widths" in snap["lanes"][0]["tools"]
    assert turn(session, agent_model=model)["status"] == "questions"  # unanswered: nothing resumes

    session.submit({"op": "question.answer", "id": q.id, "value": RUN}, by="user")
    out = turn(session, agent_model=model)
    assert out["status"] == "done" and out["summary"] == "Start with the bedroom doorway."
    assert [r.tool for r in session.doc.runs if r.status == "done"] == ["door_widths", "room_census"]
    assert live.snapshot(session.base.id)["lanes"][0]["status"] == "done"

    # the subagent's memory outlives the turn, in the LangGraph store, under the person's profile
    from threshold.agent.durable import saver_and_store
    item = saver_and_store(session.store)[1].get(("threshold", session.base.profile or "default", "memories"),
                                                 "/buildings/t1.md")
    assert item and "bedroom door" in str(item.value)


def test_skipped_tool_never_runs(session, monkeypatch):
    monkeypatch.setitem(inv_mod.APPROVE, "room_census", "it is slow in this test")
    ready(session)
    model = script()
    turn(session, agent_model=model)
    session.submit({"op": "question.answer", "id": approval(session)[0].id, "value": SKIP}, by="user")
    assert turn(session, agent_model=model)["status"] == "done"
    assert "room_census" not in [r.tool for r in session.doc.runs]


def test_always_skips_the_question_next_time(session, monkeypatch):
    monkeypatch.setitem(inv_mod.APPROVE, "room_census", "it is slow in this test")
    ready(session)
    model = script()
    turn(session, agent_model=model)
    session.submit({"op": "question.answer", "id": approval(session)[0].id, "value": ALWAYS}, by="user")
    turn(session, agent_model=model)
    out = turn(session, agent_model=script())  # a second turn calls the same tool: no new question
    assert out["status"] == "done" and len(approval(session)) == 1


def test_always_and_run_in_one_batch_resume_cleanly(session, monkeypatch):
    """Two slow calls in one message pause together; "Always" on one must not shift the decisions on resume."""
    monkeypatch.setitem(inv_mod.APPROVE, "room_census", "slow")
    monkeypatch.setitem(inv_mod.APPROVE, "door_widths", "slow")
    ready(session)
    both = AIMessage(content="", tool_calls=[{"name": "door_widths", "args": {"scan": "t1"}, "id": "c3", "type": "tool_call"},
                                            {"name": "room_census", "args": {"scan": "t1"}, "id": "c4", "type": "tool_call"}])
    model = Scripted(messages=iter([
        call("task", {"description": "Check t1", "subagent_type": "building"}, 2), both,
        AIMessage(content="Done."), AIMessage(content="Start with the bedroom doorway.")]))
    assert turn(session, agent_model=model)["status"] == "approval"
    qs = approval(session)
    assert [q.input["x-approval"]["tool"] for q in qs] == ["door_widths", "room_census"]
    assert qs[0].input["x-approval"]["spent"]["calls"] >= 2  # the cap carries across the pause
    session.submit({"op": "question.answer", "id": qs[0].id, "value": ALWAYS}, by="user")
    session.submit({"op": "question.answer", "id": qs[1].id, "value": SKIP}, by="user")
    assert turn(session, agent_model=model)["status"] == "done"
    assert [r.tool for r in session.doc.runs if r.status == "done"] == ["door_widths"]  # the skipped one never ran
