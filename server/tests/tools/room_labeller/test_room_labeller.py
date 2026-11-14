from threshold.tools import ToolContext, run_tool
from threshold.tools.room_labeller import _similar, label_scan, store
from threshold.vision import reader

from ..conftest import make_plan


def plan_two_offices():
    return make_plan("tlab", [("a", 0, 0, 3, 4, None), ("b", 3, 0, 6, 4, None), ("big", 0, 4, 12, 12, None)],
                     doors=[("a", "big", 0.9), ("b", "big", 0.9)], windows=[("a", 1.2)])


def fake_reader(monkeypatch, answers, calls):
    def label_rooms(plan, rooms=None, *, labels=None, context=None, hints=None, examples=None, views=1, **kw):
        calls.append({"sid": plan["sid"], "rooms": list(rooms or []), "examples": examples or [], "hints": hints})
        return [{"room": r, "label": answers(r, examples), "confidence": "medium", "reason": "seen",
                 "evidence": {"sid": plan["sid"], "pano": f"p_{r}", "face": 1}} for r in rooms]
    monkeypatch.setattr(reader, "label_rooms", label_rooms)
    monkeypatch.setattr(reader, "peek_rooms", lambda *a, **k: [])


def test_labels_go_into_the_overlay_and_onto_the_plan(monkeypatch):
    p = plan_two_offices()
    calls = []
    fake_reader(monkeypatch, lambda r, ex: "open office" if r == "big" else "storage", calls)
    ctx = ToolContext(plans=lambda sid: p)
    res = run_tool("room_labeller", {"scan": "tlab"}, ctx)
    assert res.verdict.text.startswith("3 of 3 rooms labelled")
    assert calls[0]["hints"]["a"].startswith("floor area 12.0 m2")  # measured facts reach the model as evidence
    labelled = store.apply(p)
    assert {r["id"]: (r["label"], r["label_source"]) for r in labelled["rooms"]}["big"] == ("open office", "vision")
    assert all(f.media for f in res.findings)


def test_a_correction_wins_and_rechecks_similar_rooms(monkeypatch):
    p = plan_two_offices()
    calls = []
    # first pass calls both small rooms storage; once shown the corrected room, the model says private office
    fake_reader(monkeypatch, lambda r, ex: "private office" if ex else ("open office" if r == "big" else "storage"), calls)
    ctx = ToolContext(plans=lambda sid: p)
    label_scan(ctx, "tlab")
    out = label_scan(ctx, "tlab", corrections={"a": "private office"})
    doc = store.load("tlab")
    assert doc["rooms"]["a"]["label_source"] == "user"
    assert doc["rooms"]["b"]["label"] == "private office" and doc["rooms"]["b"]["was"] == "storage"
    assert out["changed"] == [{"sid": "tlab", "room": "b", "from": "storage", "to": "private office"}]
    recheck = calls[-1]
    assert recheck["rooms"] == ["b"] and recheck["examples"][0]["label"] == "private office"
    assert "big" not in recheck["rooms"]  # 96 m2 is not similar to a 12 m2 room


def test_vision_never_replaces_a_matterport_label(monkeypatch):
    p = make_plan("tmp", [("k", 0, 0, 3, 3, "Kitchen"), ("x", 3, 0, 6, 3, None)])
    store.save({"sid": "tmp", "rooms": {"k": {"label": "storage", "confidence": "high", "label_source": "vision"},
                                       "x": {"label": "storage", "confidence": "low", "label_source": "vision"}},
                "finishes": {}, "corrections": []})
    labels = {r["id"]: r["label"] for r in store.apply(p)["rooms"]}
    assert labels == {"k": "Kitchen", "x": "storage"}
    store.save({"sid": "tmp", "rooms": {"k": {"label": "Pantry", "confidence": "high", "label_source": "user"}},
                "finishes": {}, "corrections": []})
    assert store.apply(p)["rooms"][0]["label"] == "Pantry"


def test_similar():
    f = lambda area, doors: {"area": area, "doors": doors}
    assert _similar(f(12, 1), f(20, 2))
    assert not _similar(f(12, 1), f(30, 1))
    assert not _similar(f(12, 1), f(12, 4))
    assert _similar(f(12, None), f(14, 3))
