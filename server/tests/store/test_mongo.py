"""The MongoDB store: persistence, optimistic concurrency, profile merges, live sync, search, memory, places, shares."""
import threading
import time

import pytest

from threshold.agent.workspace import Session
from threshold.store import Conflict

SRC = {"layer": "matterport", "method": "geometry", "confidence": "high"}


def finding(id, title, detail="", status="fail", tool="bathroom_clearance", sid="t1", feedback=None):
    return {"op": "finding.add", "finding": {"id": id, "title": title, "status": status, "detail": detail,
                                             "anchor": {"sid": sid, "room": "r2"}, "source": SRC, "tool": tool,
                                             **({"feedback": feedback} if feedback else {})}}


def until(fn, timeout=30.0):
    """Atlas Search indexes catch up with writes within a second or two."""
    end = time.time() + timeout
    while time.time() < end:
        out = fn()
        if out:
            return out
        time.sleep(0.5)
    return fn()


def test_round_trip_and_undo(ms):
    s = Session.create(store=ms)
    s.submit({"op": "tool.enable", "tool": "door_widths"}, by="user")
    s.submit({"op": "tool.enable", "tool": "room_census"}, by="user")
    s.undo()
    again = Session.load(s.base.id, store=ms)
    assert again.doc == s.doc and [e.seq for e in again.log] == [1, 2, 3]
    assert ms.workspaces.find_one({"_id": s.base.id})["seq"] == 3
    with pytest.raises(LookupError):
        Session.load("ws_nope", store=ms)


def test_two_writers_on_one_workspace_both_land(ms):
    a = Session.create(store=ms)
    b = Session.load(a.base.id, store=ms)  # a second server process holding its own copy
    a.submit({"op": "tool.enable", "tool": "door_widths"}, by="user")
    b.submit({"op": "tool.disable", "tool": "door_widths"}, by="user")  # b's seq 1 is taken: it pulls a's entry first
    assert [e.op.op for e in b.log] == ["tool.enable", "tool.disable", "pref.set"]
    assert [e["seq"] for e in ms.since(a.base.id, 0)] == [1, 2, 3]
    assert a.sync() == 2 and a.doc == b.doc and not a.doc.tools[0].enabled


def test_concurrent_writers_never_lose_an_op(ms):
    a = Session.create(store=ms)
    sessions = [a] + [Session.load(a.base.id, store=ms) for _ in range(3)]
    errors = []

    def write(s, i):
        try:
            for j in range(6):
                s.submit({"op": "shortlist.add", "sid": f"s{i}_{j}"}, by="user")
        except Exception as e:  # noqa: BLE001 - reported below
            errors.append(e)

    threads = [threading.Thread(target=write, args=(s, i)) for i, s in enumerate(sessions)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    log = ms.since(a.base.id, 0)
    assert [e["seq"] for e in log] == list(range(1, 25))
    assert Session.load(a.base.id, store=ms).doc.shortlist.__len__() == 24


def test_a_stale_batch_is_refused_whole(ms):
    a = Session.create(store=ms)
    a.submit({"op": "tool.enable", "tool": "door_widths"}, by="user")
    stale = Session.load(a.base.id, store=ms)
    a.submit({"op": "tool.enable", "tool": "room_census"}, by="user")
    stale._append(None, undo=1)
    stale._append(None, undo=1)
    with pytest.raises(Conflict):
        ms.save(stale.meta(), stale.log, 1, stale.doc)  # seq 2 is taken, so seq 3 must not land either
    assert [e["seq"] for e in ms.since(a.base.id, 0)] == [1, 2]


def test_two_workspaces_on_one_profile_keep_each_others_preferences(ms):
    a, b = Session.create(store=ms), Session.create(store=ms)
    a.submit({"op": "pref.set", "key": "access.door_width_m", "value": 0.9}, by="user")
    b.submit({"op": "pref.set", "key": "space.min_height_m", "value": 2.2}, by="user")
    a.submit({"op": "tool.disable", "tool": "room_census"}, by="user")
    c = Session.create(store=ms)
    assert c.doc.prefs["access.door_width_m"].value == 0.9 and c.doc.prefs["space.min_height_m"].value == 2.2
    b.submit({"op": "pref.set", "key": "access.door_width_m", "value": 0.8}, by="user")  # later edit wins
    a.submit({"op": "shortlist.add", "sid": "t1"}, by="user")                          # an older copy does not
    assert Session.create(store=ms).doc.prefs["access.door_width_m"].value == 0.8
    b.submit({"op": "pref.set", "key": "space.min_height_m", "value": None}, by="user")  # a deletion sticks
    a.submit({"op": "shortlist.remove", "sid": "t1"}, by="user")
    d = Session.create(store=ms)
    assert "space.min_height_m" not in d.doc.prefs and "tool.off.room_census" in d.doc.prefs


def test_change_stream_delivers_another_writers_ops(ms):
    a = Session.create(store=ms)
    a.submit({"op": "tool.enable", "tool": "door_widths"}, by="user")
    got, ready = [], threading.Event()

    def watch():
        for e in ms.watch(a.base.id, after=0, wait=0.2):
            ready.set()
            if e:
                got.append(e)
            if len(got) == 3:
                return

    t = threading.Thread(target=watch, daemon=True)
    t.start()
    ready.wait(5)
    other = Session.load(a.base.id, store=ms)  # another device's writer
    other.submit({"op": "shortlist.add", "sid": "t1", "note": "wide doors"}, by="user")
    other.submit({"op": "shortlist.remove", "sid": "t1"}, by="user")
    t.join(10)
    assert [e["seq"] for e in got] == [1, 2, 3]  # backfill, then the change stream, no gap and no repeat
    assert got[1]["op"] == {"op": "shortlist.add", "by": "user", "run": None, "sid": "t1", "note": "wide doors"}


def test_search_finds_rejections_by_reason_with_facets(ms):
    assert ms.wait_ready(120)
    s = Session.create(profile="pat", store=ms)
    s.submit({"op": "brief.set", "text": "I use a wheelchair and need an apartment in Houston", "summary": "Wheelchair user",
              "scope": {"sids": ["t1", "t2", "t3"]}}, by="user")
    s.submit(finding("f1", "Bathroom door too narrow for a wheelchair", "The bathroom doorway is narrower than ADA"),
             by="user")
    s.submit(finding("f1", "Bathroom door too narrow for a wheelchair", "The bathroom doorway is narrower than ADA",
                     feedback={"verdict": "rejected", "reason": "the bathroom door is too narrow, skip this unit"}),
             by="user")
    s.submit(finding("f2", "No sprinklers seen in the hallway", tool="fire_preplan", status="warn", sid="t3"), by="user")
    s.submit(finding("f3", "Step at the entrance", tool="step_free_route", sid="t2"), by="user")
    other = Session.create(profile="sam", store=ms)
    other.submit(finding("g1", "Narrow bathroom door", feedback={"verdict": "rejected", "reason": "narrow"}), by="user")

    hits = until(lambda: ms.search("narrow bathroom door", profile="pat", feedback="rejected")["hits"])
    assert [h["finding"] for h in hits] == ["f1"] and hits[0]["address"] == "1 Test St"
    assert hits[0]["highlights"]
    res = until(lambda: (r := ms.search("sprinkler", profile="pat"))["hits"] and r)  # stemmed: sprinkler ~ sprinklers
    assert res["hits"][0]["city"] == "Los Angeles" and res["facets"]["tool"] == {"fire_preplan": 1}
    allp = until(lambda: (r := ms.search(profile="pat", kind="finding"))["total"] == 3 and r)
    assert allp["facets"]["city"] == {"Houston": 2, "Los Angeles": 1}
    assert allp["facets"]["feedback"] == {"rejected": 1}
    s.undo(next(e.seq for e in s.log if e.op and e.op.op == "finding.add" and e.op.finding.feedback))
    # the rejection goes away, and so does the search hit
    assert until(lambda: not ms.search("narrow", profile="pat", feedback="rejected")["hits"])


def test_memory_recalls_similar_needs_by_persona(ms):
    assert ms.wait_ready(120)
    needs = [("wheelchair_renter", "I use a wheelchair and need an apartment with wide doors and a roll-in shower"),
             ("wheelchair_renter", "My father uses a walker; we need a ground floor home without steps"),
             ("office_tenant", "We are a team of twelve looking for an office with two meeting rooms"),
             ("none", "I photograph weddings and want a bright loft with tall windows")]
    for persona, text in needs:
        s = Session.create(store=ms)
        s.submit({"op": "brief.set", "text": text, "summary": text[:40], "persona": persona}, by="user")
        s.submit({"op": "tool.enable", "tool": "door_widths", "reason": "doors"}, by="user")
    q = "I'm in a power chair and need step-free access to a bathroom"
    top = until(lambda: (r := ms.recall(q, k=4)) and len(r) == 4 and r)
    assert top[0]["persona"] == "wheelchair_renter" and top[-1]["persona"] != "wheelchair_renter"
    office = ms.recall(q, persona="office_tenant", k=4)
    assert [m["persona"] for m in office] == ["office_tenant"]


def test_shortlist_near_a_point(ms):
    a = Session.create(profile="pat", store=ms)
    for sid in ("t1", "t2", "t3"):
        a.submit({"op": "shortlist.add", "sid": sid}, by="user")
    work = (-95.3690, 29.7605)  # a few hundred metres from t1
    near = ms.shortlist_near(*work, km=3, profile="pat")
    assert [r["sid"] for r in near] == ["t1", "t2"] and near[0]["distance_m"] < near[1]["distance_m"] < 3000
    assert len(ms.shortlist_near(profile="pat")) == 3
    a.submit({"op": "shortlist.remove", "sid": "t1"}, by="user")
    assert [r["sid"] for r in ms.shortlist_near(*work, km=3, profile="pat")] == ["t2"]


def test_share_links_expire(ms):
    link = ms.share("ws_x", days=1)
    assert ms.shared(link["token"])["workspace"] == "ws_x"
    old = ms.share("ws_x", days=-1)
    assert ms.shared(old["token"]) is None
    assert ms.unshare(link["token"]) and ms.shared(link["token"]) is None


def test_an_op_whose_search_items_fail_still_counts(ms, monkeypatch):
    """Once the log entry is stored the op happened: a failing derive must not tell the caller otherwise."""
    s = Session.create(store=ms)
    monkeypatch.setattr(ms, "derive", lambda d: (_ for _ in ()).throw(RuntimeError("embedding model offline")))
    s.submit({"op": "tool.enable", "tool": "door_widths"}, by="user")
    assert [e.seq for e in s.log] == [1] and [e.seq for e in Session.load(s.base.id, store=ms).log] == [1]
