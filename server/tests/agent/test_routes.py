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
    release.set()
    for _ in range(100):
        run = next(r for r in c.get(f"/api/workspace/{wid}").json()["doc"]["runs"] if r["id"] == out["run"])
        if run["status"] != "running":
            break
        time.sleep(0.05)
    assert run["status"] == "done" and c.get(f"/api/workspace/{wid}").json()["doc"]["panels"]
    quick = c.post(f"/api/tools/room_census/run?workspace={wid}&wait=5", json={"scan": "t1"}).json()
    assert quick["verdict"] and "status" not in quick  # a run that finishes inside the wait answers as it always did

