from fastapi.testclient import TestClient

from threshold.agent import workspace
from threshold.api.app import app


def test_tools_workspace_ops_and_undo(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "STORE", tmp_path)
    c = TestClient(app)
    tools = {t["id"]: t for t in c.get("/api/tools").json()}
    assert tools["door_widths"]["status"] == "ready" and tools["not_built_yet"]["status"] == "planned"  # the stub from conftest: every real tool is built
    assert c.post("/api/tools/nope/run", json={}).status_code == 404
    assert c.post("/api/tools/door_widths/run", json={"scan": "x"}).status_code == 400

    wid = c.post("/api/workspace").json()["doc"]["id"]
    r = c.post(f"/api/workspace/{wid}/ops", json=[{"op": "tool.enable", "tool": "door_widths"},
                                                 {"op": "tool.disable", "tool": "door_widths", "by": "agent"}])
    body = r.json()
    assert [e["op"]["op"] for e in body["applied"]] == ["tool.enable", "tool.disable", "pref.set"]
    assert all(e["op"]["by"] in ("user", "system") for e in body["applied"])
    assert body["learned"][0]["undo"] == {"op": "pref.set", "key": "tool.off.door_widths", "value": None, "by": "user"}
    assert c.post(f"/api/workspace/{wid}/ops", json={"op": "nonsense"}).status_code == 422
    after = c.post(f"/api/workspace/{wid}/undo", json={}).json()
    assert after["learned"] == [] and after["doc"]["tools"][0]["enabled"]
    assert c.get(f"/api/workspace/{wid}?log=true").json()["log"][-1]["undo"] == 2
    assert c.get("/api/workspace/ws_missing").status_code == 404


def test_turn_takes_places_and_a_budget_and_streams_done(tmp_path, monkeypatch):
    from threshold.api import agent as api
    monkeypatch.setattr(workspace, "STORE", tmp_path)
    seen = {}

    def fake_turn(s, text, sids, places=None, budget=None):
        seen.update(places=places, budget=budget)
        return {"status": "done", "summary": "ok", "budget": budget.report()}
    monkeypatch.setattr(api, "turn", fake_turn)
    c = TestClient(app)
    body = {"text": "Check this community", "places": [{"property_id": 7}, {"geo": [-95.3, 29.7]}],
            "budget": {"model_calls": 12, "parallel": 2}}
    events = c.post("/api/agent/turn", json=body).text
    assert "event: done" in events and '"model_calls": 12' in events
    assert seen["places"] == [{"property_id": 7}, {"geo": (-95.3, 29.7)}] and seen["budget"].parallel == 2
    assert c.post("/api/agent/turn", json={"places": [{}]}).status_code == 422
    assert c.post("/api/agent/turn", json={"budget": {"parallel": 99}}).status_code == 422


def test_a_slow_tool_run_answers_early_and_finishes_in_the_background(tmp_path, monkeypatch):
    import threading
    import time

    from threshold.agent import investigator
    from threshold.api import agent as api
    monkeypatch.setattr(workspace, "STORE", tmp_path)
    monkeypatch.setattr(api, "_sessions", {})
    release, real = threading.Event(), investigator.run_tool

    def slow(tool_id, inputs, ctx=None):  # the tool reports a step, then takes its time
        ctx.step("Half way")
        release.wait(5)
        return real(tool_id, inputs, ctx)
    monkeypatch.setattr(investigator, "run_tool", slow)
    c = TestClient(app)
    wid = c.post("/api/workspace").json()["doc"]["id"]
    s = api.session(wid)
    investigator.attach(s, lambda sid: {"sid": sid, "rooms": [{"id": "r1", "label": "Bedroom", "area": 12.0, "floor": "f1"}],
                                        "floors": [{"id": "f1"}], "walls": [], "openings": [], "panos": []})
    c.post(f"/api/workspace/{wid}/ops", json={"op": "brief.set", "scope": {"sids": ["t1"]}})
    out = c.post(f"/api/tools/room_census/run?workspace={wid}&wait=0.2", json={"scan": "t1"}).json()
    assert out["status"] == "running" and out["run"]
    run = next(r for r in c.get(f"/api/workspace/{wid}").json()["doc"]["runs"] if r["id"] == out["run"])
    assert run["status"] == "running" and run["steps"] == ["Half way"]  # progress is in the workspace while it runs
    assert c.get(f"/api/workspace/{wid}").json()["busy"] == [out["run"]]
    release.set()
    for _ in range(100):  # "busy" clears only when the panel is written, which is after the run reads "done"
        v = c.get(f"/api/workspace/{wid}").json()
        if not v["busy"]:
            break
        time.sleep(0.05)
    run = next(r for r in v["doc"]["runs"] if r["id"] == out["run"])
    assert run["status"] == "done" and v["doc"]["panels"]
    quick = c.post(f"/api/tools/room_census/run?workspace={wid}&wait=5", json={"scan": "t1"}).json()
    assert quick["verdict"] and "status" not in quick  # a run that finishes inside the wait answers as it always did



def test_a_failed_turn_never_shows_a_database_address(tmp_path, monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError

    from threshold.api import agent as api
    monkeypatch.setattr(workspace, "STORE", tmp_path)

    def boom(*a, **k):
        raise ServerSelectionTimeoutError("cluster0-shard-00-00.abcde.mongodb.net:27017: timed out")
    monkeypatch.setattr(api, "turn", boom)
    events = TestClient(app).post("/api/agent/turn", json={"text": "x"}).text
    assert "event: error" in events and "ServerSelectionTimeoutError" in events and "mongodb.net" not in events


def test_a_rejected_op_in_a_list_says_how_many_were_applied(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "STORE", tmp_path)
    c = TestClient(app)
    wid = c.post("/api/workspace").json()["doc"]["id"]
    r = c.post(f"/api/workspace/{wid}/ops", json=[{"op": "tool.enable", "tool": "door_widths"}, {"op": "nonsense"}])
    assert r.status_code == 422 and "the 1 before it were applied" in r.json()["detail"]


def test_equirect_refuses_a_view_that_walks_out_of_the_cache():
    c = TestClient(app)
    assert c.get("/api/scan/AAAAAAAAAAA/pano/p1/equirect.jpg", params={"view": "../../../../tmp"}).status_code == 404


def test_live_resumes_after_the_last_event_id(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(workspace, "STORE", tmp_path)
    c = TestClient(app)
    wid = c.post("/api/workspace").json()["doc"]["id"]
    c.post(f"/api/workspace/{wid}/ops", json=[{"op": "tool.enable", "tool": "door_widths"}, {"op": "shortlist.add", "sid": "t1"}])
    with c.stream("GET", f"/api/workspace/{wid}/live?after=0", headers={"Last-Event-ID": "1"}) as r:
        lines = []
        for line in r.iter_lines():
            lines.append(line)
            if line.startswith("data:") and '"seq"' in line:
                break
    assert "id: 2" in lines and json.loads(lines[-1][5:])["seq"] == 2   # op 1 is not sent again


def test_a_run_a_restart_cut_off_ends_as_an_error(tmp_path, monkeypatch):
    from threshold.agent.workspace import Run, RunStart
    from threshold.api import agent as api
    monkeypatch.setattr(workspace, "STORE", tmp_path)
    c = TestClient(app)
    wid = c.post("/api/workspace").json()["doc"]["id"]
    s = api.session(wid)
    s.submit(RunStart(record=Run(id="run_old", tool="door_widths", started=1.0), run="run_old"), by="system")
    s.submit(RunStart(record=Run(id="run_new", tool="door_widths", started=__import__("time").time()), run="run_new"), by="system")
    runs = {r["id"]: r for r in c.get(f"/api/workspace/{wid}").json()["doc"]["runs"]}
    assert runs["run_old"]["status"] == "error" and "stopped" in runs["run_old"]["error"]
    assert runs["run_new"]["status"] == "running"


def test_feedback_and_the_person_document(tmp_path, monkeypatch):
    """Not relevant hides the kind, the reply counts what went with it, and the person's page lists what was learned."""
    from threshold.api import agent as api

    from .conftest import plans
    monkeypatch.setattr(workspace, "STORE", tmp_path)
    c = TestClient(app)
    ws = c.post("/api/workspace?profile=maya").json()["doc"]["id"]
    api._sessions[ws].plans = plans
    c.post(f"/api/workspace/{ws}/ops", json={"op": "brief.set", "scope": {"sids": ["t1"]}})
    assert c.post(f"/api/tools/door_widths/run?workspace={ws}", json={"scan": "t1", "min_width_m": 0.9}).status_code == 200
    seen = c.get(f"/api/workspace/{ws}").json()["doc"]["findings"]
    r = c.post(f"/api/workspace/{ws}/feedback", json={"finding": seen[0]["id"], "verdict": "not_relevant"}).json()
    assert r["hidden"] == len(seen) - 1 and r["kind"] == "Doorway"
    assert all(f["feedback"]["verdict"] == "rejected" for f in r["doc"]["findings"])
    assert c.post(f"/api/workspace/{ws}/feedback", json={"finding": "nope", "verdict": "useful"}).status_code == 404
    who = c.get(f"/api/person/maya?workspace={ws}").json()
    assert who["schema"] == "person/1" and [f["label"] for f in who["facts"]] == ["Not relevant to you"]
    assert who["facts"][0]["why"] == "you marked it in this investigation"
    assert c.get(f"/api/workspace/{ws}/because").json()["notes"] == []
    assert c.post(f"/api/workspace/{ws}/undo", json={"seq": r["undo"]}).status_code == 200
    assert c.get("/api/person/maya").json()["facts"] == []
