"""What the MongoDB store derives from a workspace document. No database."""
from threshold.agent.workspace import Session
from threshold.store import derive

from .conftest import PLACES
from .test_mongo import finding


def doc(tmp_path):
    s = Session.create(root=tmp_path)
    s.submit({"op": "brief.set", "text": "Need a step-free flat", "summary": "Walker user", "persona": "older_adult",
              "scope": {"sids": ["t1", "zz"]}}, by="user")
    s.submit({"op": "tool.enable", "tool": "door_widths", "reason": "your walker"}, by="user")
    s.submit({"op": "tool.enable", "tool": "room_census", "reason": "rooms"}, by="user")
    s.submit({"op": "tool.disable", "tool": "room_census", "reason": "I know the rooms"}, by="user")
    s.submit(finding("f1", "Narrow door", feedback={"verdict": "rejected", "reason": "my walker fits"}), by="user")
    s.submit(finding("f2", "Old", sid="t2"), by="user")
    s.submit({"op": "finding.add", "finding": {**s.doc.findings[1].model_dump(mode="json"), "superseded_by": "f3"}},
             by="user")
    s.submit({"op": "shortlist.add", "sid": "t1", "note": "close to work"}, by="user")
    s.submit({"op": "shortlist.add", "sid": "zz"}, by="user")
    return s.doc.model_dump(mode="json", by_alias=True)


def test_history_items(tmp_path):
    items = {i["_id"].split(":", 1)[1]: i for i in derive.history(doc(tmp_path), PLACES.get)}
    assert set(items) == {"brief", "f:f1", "t:room_census", "s:t1", "s:zz"}  # the superseded finding is left out
    assert items["brief"]["city"] == ["Houston"] and items["brief"]["persona"] == "older_adult"
    f = items["f:f1"]
    assert (f["feedback"], f["reason"], f["city"], f["tool"]) == ("rejected", "my walker fits", "Houston", "bathroom_clearance")
    assert items["t:room_census"]["reason"] == "I know the rooms"


def test_memory_and_lines(tmp_path):
    m = derive.memory(doc(tmp_path))
    assert m["persona"] == "older_adult" and m["text"].startswith("Need a step-free flat")
    assert [t["id"] for t in m["tools"]] == ["door_widths"] and m["removed"][0]["tool"] == "room_census"
    line = derive.lines([m])[0]
    assert "tools door_widths" in line and "they removed room_census (I know the rooms)" in line
    assert 'they rejected "Narrow door" (my walker fits)' in line
    assert derive.memory({"id": "w", "brief": {}}) is None


def test_shortlist_points(tmp_path):
    rows = {r["sid"]: r for r in derive.shortlist(doc(tmp_path), PLACES.get)}
    assert rows["t1"]["location"] == {"type": "Point", "coordinates": [-95.37, 29.76]}
    assert "location" not in rows["zz"]  # unknown place: kept, without a point


def test_only_this_machine_counts_as_local():
    from threshold.store import is_local
    assert is_local("mongodb://u:p@127.0.0.1:27027/?directConnection=true") and is_local("mongodb://localhost")
    assert not is_local("mongodb+srv://u:p@threshold.abc.mongodb.net/")
    assert not is_local("mongodb://u:p@127.0.0.1:27027,db.example.com:27017/")
