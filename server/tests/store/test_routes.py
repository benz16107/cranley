"""The Atlas routes over HTTP, with the MongoDB store selected by configuration."""
import json

import pytest
from fastapi.testclient import TestClient

from threshold.api import agent as agent_api
from threshold.api.app import app


@pytest.fixture
def client(ms, monkeypatch):
    from threshold import store
    monkeypatch.setenv("THRESHOLD_STORE", "mongo")
    monkeypatch.setattr(store, "connect", lambda *a, **k: ms)
    monkeypatch.setattr(agent_api, "_sessions", {})
    return TestClient(app)


def test_files_store_answers_501(monkeypatch):
    monkeypatch.setenv("THRESHOLD_STORE", "files")  # not delenv: the data folder's .env may say mongo
    assert TestClient(app).get("/api/history/search?profile=x").status_code == 501


def test_share_link_is_read_only_and_revocable(client):
    wid = client.post("/api/workspace?profile=pat").json()["doc"]["id"]
    client.post(f"/api/workspace/{wid}/ops", json={"op": "shortlist.add", "sid": "t1", "note": "near work"})
    link = client.post(f"/api/workspace/{wid}/share", json={"days": 1}).json()
    raw = client.get(f"/api/shared/{link['token']}").text
    view = json.loads(raw)
    assert view["readonly"] and view["seq"] == 1 and view["doc"]["shortlist"][0]["sid"] == "t1"
    assert wid not in raw and view["doc"]["id"] == "shared"  # the viewer never learns the id the owner's routes take
    with client.stream("GET", f"/api/shared/{link['token']}/live") as r:
        lines = []
        for line in r.iter_lines():
            lines.append(line)
            if '"seq"' in line:
                break
    assert wid not in "\n".join(lines) and '"seq": 1' in lines[-1]
    near = client.get(f"/api/shared/{link['token']}/shortlist?near=-95.369,29.7605&km=3").json()
    assert [r["sid"] for r in near] == ["t1"]
    assert client.post(f"/api/shared/{link['token']}/ops", json={}).status_code in (404, 405)  # no writes by link
    assert client.delete(f"/api/workspace/ws_other/share/{link['token']}").status_code == 404
    assert client.delete(f"/api/workspace/{wid}/share/{link['token']}").json() == {"revoked": True}
    assert client.get(f"/api/shared/{link['token']}").status_code == 404


def test_live_route_replays_and_follows(client):
    wid = client.post("/api/workspace").json()["doc"]["id"]
    client.post(f"/api/workspace/{wid}/ops", json=[{"op": "tool.enable", "tool": "door_widths"},
                                                  {"op": "shortlist.add", "sid": "t1"}])
    seqs = []
    with client.stream("GET", f"/api/workspace/{wid}/live?after=1") as r:
        for line in r.iter_lines():
            if line.startswith("data:") and '"seq"' in line:
                seqs.append(json.loads(line[5:])["seq"])
                break
    assert seqs == [2]


def test_search_route_needs_an_owner(client):
    assert client.get("/api/history/search?q=door").status_code == 422
    assert client.get("/api/history/shortlist?near=1,2").status_code == 422
    assert client.get("/api/history/shortlist?profile=p&near=500,2").status_code == 422
