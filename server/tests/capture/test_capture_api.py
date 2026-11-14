"""The phone loop through the routes: pair, list tasks, send a capture, see the finding change in the workspace."""
import json

import pytest
from fastapi.testclient import TestClient

from tests.tools.conftest import plans
from threshold.agent import investigator, workspace
from threshold.api import agent as api
from threshold.api.app import app
from threshold.capture import apply, pair, store

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """A desktop workspace on the hand-made home with door_widths already run. (client, workspace id)"""
    monkeypatch.setattr(workspace, "STORE", tmp_path)
    monkeypatch.setattr(store, "ROOT", tmp_path / "captures")
    c = TestClient(app)
    wid = c.post("/api/workspace").json()["doc"]["id"]
    investigator.attach(api.session(wid), plans)
    c.post(f"/api/workspace/{wid}/ops", json={"op": "brief.set", "scope": {"sids": ["home"]}})
    assert c.post(f"/api/tools/door_widths/run?workspace={wid}", json={"scan": "home", "min_width_m": 0.815}).json()["verdict"] == "fail"
    return c, wid


def send(c, token, meta, body=None):
    return c.post(f"/api/phone/{token}/capture", params={"meta": json.dumps(meta)}, content=body or b"")


def test_pair_measure_and_the_finding_changes(desk):
    c, wid = desk
    p = c.post(f"/api/workspace/{wid}/pair", json={}).json()
    assert p["path"] == f"/m?t={p['token']}" and wid not in p["token"] and p["secure"] is False
    q = c.post(f"/api/workspace/{wid}/pair", json={"origin": "https://desk.example:8470/"}).json()
    assert q["url"].startswith("https://desk.example:8470/m?t=") and q["secure"] and q["qr"].startswith("<svg")
    assert c.post(f"/api/workspace/{wid}/pair", json={"origin": "javascript:alert(1)"}).json()["url"].startswith("/m?t=")
    view = c.get(f"/api/phone/{p['token']}").json()
    assert wid not in json.dumps(view)                                # the phone never sees the workspace id
    assert view["buildings"][0]["sid"] == "home" and {r["label"] for r in view["buildings"][0]["rooms"]} >= {"Bedroom", "Bathroom"}
    task = next(t for t in view["tasks"] if t["id"] == "width:home:RB")
    assert task["status"] == "open" and task["scan_value"] == pytest.approx(0.65)
    before = next(f for f in c.get(f"/api/workspace/{wid}").json()["doc"]["findings"] if f["id"] == "door_widths:home:RB")
    assert before["status"] == "fail" and before["source"]["layer"] == "matterport"
    seq = c.get(f"/api/workspace/{wid}").json()["seq"]

    r = send(c, p["token"], {"kind": "photo", "task": "width:home:RB", "scan": "home", "values": {"value_m": 0.84}}, JPEG).json()
    assert r["outcome"]["verdict"] == "contradicted" and r["outcome"]["status"] == "pass" and r["updated_findings"] == 1
    assert next(t for t in r["view"]["tasks"] if t["id"] == "width:home:RB")["status"] == "done"
    doc = c.get(f"/api/workspace/{wid}?log=true").json()
    after = next(f for f in doc["doc"]["findings"] if f["id"] == "door_widths:home:RB")
    assert after["status"] == "pass" and after["source"] == {"layer": "phone", "method": "manual", "confidence": "high",
                                                             "note": "Checked on site with the phone; the scan's own figure is in the detail"}
    assert after["media"] == [{"kind": "phone", "ref": r["capture"]["id"], "box": None}]
    assert after["detail"].startswith("0.70 m wide, narrower than your 0.815 m. On site: 0.84 m") and "The scan had 0.65 m" in after["detail"]
    ops = [e["op"]["op"] for e in doc["log"][seq:] if e["op"]]        # what a desktop following the workspace receives
    assert ops[0] == "finding.add" and "run.finish" in ops and "panel.upsert" in ops
    fc = next(r for r in doc["doc"]["runs"] if r["tool"] == "field_check")
    assert fc["result"]["verdict"]["text"].startswith("1 of 2 on-site checks done: 1 contradicts the scan")
    assert any(pn["tool"] == "field_check" for pn in doc["doc"]["panels"]) and any(t["id"] == "field_check" for t in doc["doc"]["tools"])
    assert c.get(f"/api/workspace/{wid}/captures").json()[0]["id"] == r["capture"]["id"]
    assert c.get(f"/api/capture/{r['capture']['id']}/file").content == JPEG

    again = send(c, p["token"], {"kind": "reading", "task": "width:home:RB", "values": {"value_m": 0.66}}).json()
    assert again["outcome"]["verdict"] == "confirmed" and again["outcome"]["status"] == "fail"
    after = next(f for f in c.get(f"/api/workspace/{wid}").json()["doc"]["findings"] if f["id"] == "door_widths:home:RB")
    assert after["status"] == "fail" and after["feedback"]["verdict"] == "confirmed" and after["detail"].count("On site:") == 1


def test_a_phone_tool_runs_into_the_workspace_and_a_plain_photo_is_evidence(desk):
    c, wid = desk
    t = c.post(f"/api/workspace/{wid}/pair", json={}).json()["token"]
    r = send(c, t, {"kind": "reading", "tool": "slope_check", "scan": "home", "opening": "E",
                    "values": {"mode": "ramp", "reading_deg": 3.0, "flipped_deg": -2.6}}).json()
    assert r["status"] == "pass" and r["capture"]["result"]["run"] == r["run"]
    for room, level in (("R", 31.0), ("L", 48.0)):
        r = send(c, t, {"kind": "reading", "tool": "noise_level", "scan": "home", "room": room,
                        "values": {"room": room, "leq_dba": level, "seconds": 15}}).json()
    doc = c.get(f"/api/workspace/{wid}").json()["doc"]
    noise = [x for x in doc["runs"] if x["tool"] == "noise_level"][-1]
    assert len(noise["inputs"]["readings"]) == 2                      # the second room's run carries the first room too
    assert next(o for o in doc["overlays"] if o["tool"] == "noise_level")["overlay"]["values"] == {"R": 31.0, "L": 48.0}
    r = send(c, t, {"kind": "photo", "scan": "home", "room": "K", "note": "Water stain by the window"}, JPEG).json()
    f = next(x for x in c.get(f"/api/workspace/{wid}").json()["doc"]["findings"] if x["id"] == f"phone:{r['capture']['id']}")
    assert f["anchor"] == {"sid": "home", "room": "K"} and f["detail"] == "Water stain by the window" and f["media"][0]["kind"] == "phone"


def test_what_a_token_cannot_do(desk):
    c, wid = desk
    t = c.post(f"/api/workspace/{wid}/pair", json={}).json()["token"]
    assert c.get("/api/phone/not-a-token").status_code == 401
    assert c.get(f"/api/phone/{pair.issue(wid, hours=-1)['token']}").status_code == 401            # expired
    assert c.get(f"/api/workspace/{t}").status_code == 404                                         # a token is not a workspace id
    assert c.post(f"/api/phone/{t}/run/facts_query", json={}).status_code == 403                   # only the phone's tools
    assert send(c, t, {"kind": "photo"}, b"MZ\x90\x00" + b"0" * 60).status_code == 415             # not a photo
    assert send(c, t, {"kind": "photo", "bogus": 1}, JPEG).status_code == 422
    assert c.post(f"/api/phone/{t}/capture", params={"meta": json.dumps({"kind": "photo"})}, content=b"0" * 10,
                  headers={"content-length": str(10**9)}).status_code in (400, 413)
    assert c.get("/api/capture/cap_0000000000000000/file").status_code == 404
    assert c.post("/api/workspace/ws_missing/pair", json={}).status_code == 404


def test_a_phone_alone_starts_its_own_workspace_and_picks_a_building(desk, monkeypatch):
    c, _ = desk
    t = c.post("/api/phone/start", json={}).json()["token"]
    investigator.attach(api.session(pair.check(t)), plans)
    assert c.get(f"/api/phone/{t}").json()["buildings"] == []
    view = c.post(f"/api/phone/{t}/place", json={"sid": "home"}).json()
    assert view["buildings"][0]["sid"] == "home" and view["tasks"] == []
    assert c.post(f"/api/phone/{t}/place", json={"sid": "nope"}).status_code == 404
    seen = {}
    monkeypatch.setattr("threshold.api.capture.turn", lambda s, text, sids, *a: seen.update(text=text, sids=sids, budget=a[-1]))
    assert c.post(f"/api/phone/{t}/brief", json={"text": "I use a wheelchair", "sid": "home"}).json() == {"status": "running"}
    for _ in range(50):
        if seen:
            break
        import time
        time.sleep(0.02)
    assert seen["text"] == "I use a wheelchair" and seen["sids"] == ["home"] and seen["budget"].tool_runs == 10


def test_an_alarm_task_takes_the_persons_word_or_a_confident_photo(desk, monkeypatch):
    c, wid = desk
    s = api.session(wid)
    from threshold.agent.workspace import Run
    from threshold.tools import Finding, RoomAnchor, ScanScope, Source, ToolResult, Verdict
    src = Source(layer="model", method="vision", confidence="low")
    f = Finding(id="life_safety_census:home:R", title="Bedroom, smoke alarm not seen", status="warn", detail="No alarm found.",
                anchor=RoomAnchor(sid="home", room="R"), source=src)
    from threshold.agent.workspace import FindingAdd, RunFinish, RunStart, WsFinding
    s.submit(RunStart(record=Run(id="run_ls", tool="life_safety_census", sid="home")), by="system")
    s.submit(RunFinish(id="run_ls", status="done", result=ToolResult(tool="life_safety_census", scope=ScanScope(sid="home"),
             verdict=Verdict(status="warn", text="x"), findings=[f])), by="system")
    s.submit(FindingAdd(finding=WsFinding(**f.model_dump(), run="run_ls", tool="life_safety_census")), by="system")
    t = c.post(f"/api/workspace/{wid}/pair", json={}).json()["token"]
    monkeypatch.setattr(apply, "alarm_in_photo", lambda cid: {"ceiling_visible": True, "smoke_alarm_visible": True, "what": "a white disc", "confidence": "medium"})
    r = send(c, t, {"kind": "photo", "task": "alarm:home:R", "scan": "home"}, JPEG).json()
    assert "does not settle it" in r["problem"] and "outcome" not in r           # a medium-confidence sighting is not enough
    monkeypatch.setattr(apply, "alarm_in_photo", lambda cid: {"ceiling_visible": True, "smoke_alarm_visible": True, "what": "an alarm", "confidence": "high"})
    r = send(c, t, {"kind": "photo", "task": "alarm:home:R", "scan": "home"}, JPEG).json()
    assert r["outcome"]["status"] == "pass" and r["outcome"]["method"] == "vision"
    r = send(c, t, {"kind": "reading", "task": "alarm:home:R", "values": {"answer": "absent"}}).json()
    assert r["outcome"] == {"verdict": "confirmed", "status": "fail", "value": None, "err": None,
                            "text": "No smoke alarm in this room, checked on site.", "method": "manual", "confidence": "high"}
    after = next(x for x in c.get(f"/api/workspace/{wid}").json()["doc"]["findings"] if x["id"] == f.id)
    assert after["status"] == "fail" and after["source"]["layer"] == "phone"
