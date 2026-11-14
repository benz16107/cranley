"""Small hand-made plans for the office tools; no network, no sponsor data, no model calls."""
import pytest

from threshold.tools.room_labeller import facts, store


def rect(rid, x0, y0, x1, y1, label=None, source=None, floor="f1"):
    poly = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    walls = []
    for i in range(4):
        a, b = poly[i], poly[(i + 1) % 4]
        walls.append({"id": f"{rid}w{i}", "floor": floor, "a": a, "b": b, "type": "wall", "thickness": 0.1,
                      "length": abs(b[0] - a[0]) + abs(b[1] - a[1]), "rooms": [rid], "openings": []})
    room = {"id": rid, "floor": floor, "label": label, "label_confidence": 1 if label else None,
            "label_source": source or ("matterport" if label else None), "polygon": poly,
            "area": (x1 - x0) * (y1 - y0), "height": 2.7, "width": None, "depth": None,
            "walls": [w["id"] for w in walls], "holes": [], "center": [(x0 + x1) / 2, (y0 + y1) / 2]}
    return room, walls


def make_plan(sid, spec, doors=(), windows=(), walls=True):
    """spec: [(id, x0, y0, x1, y1, label)]; doors: [(room a, room b or None, width)]; windows: [(room, width)]."""
    rooms, ws, ops, panos = [], [], [], []
    for rid, x0, y0, x1, y1, label in spec:
        r, w = rect(rid, x0, y0, x1, y1, label)
        rooms.append(r)
        ws += w
        panos.append({"id": f"p_{rid}", "label": rid, "position": [(x0 + x1) / 2, (y0 + y1) / 2, 1.5],
                      "rotation": [0, 0, 0, 1], "floor": "f1", "room": rid, "neighbors": []})
    wall_of = {r["id"]: r["walls"][0] for r in rooms}
    for i, (a, b, width) in enumerate(doors):
        oid = f"d{i}"
        ops.append({"id": oid, "wall": wall_of[a], "floor": "f1", "type": "doorway", "width": width, "height": 2.0,
                    "sill": 0, "center": [0, 0], "rooms": [a] + ([b] if b else [])})
        next(w for w in ws if w["id"] == wall_of[a])["openings"].append(oid)
    for i, (a, width) in enumerate(windows):
        oid = f"win{i}"
        ops.append({"id": oid, "wall": wall_of[a], "floor": "f1", "type": "window", "width": width, "height": 1.2,
                    "sill": 0.9, "center": [0, 0], "rooms": [a]})
        next(w for w in ws if w["id"] == wall_of[a])["openings"].append(oid)
    if not walls:
        ws, ops = [], []
        for r in rooms:
            r.update(polygon=[], walls=[])
    return {"schema": "scanplan/1", "sid": sid, "name": sid, "segment": "commercial",
            "has": {"room_labels": any(r["label"] for r in rooms), "openings": bool(ops)},
            "quality": {"walls": walls, "polygons": walls, "openings": bool(ops), "labels": any(r["label"] for r in rooms),
                        "georef": False, "notes": []},
            "floors": [{"id": "f1", "label": "1", "sequence": 0}], "walls": ws, "openings": ops, "rooms": rooms,
            "panos": panos, "floorplans": []}


OFFICE = [("open", 0, 0, 10, 8, "open office"), ("o1", 10, 0, 13, 3.5, "private office"),
          ("o2", 10, 3.5, 13, 7.5, "private office"), ("o3", 13, 0, 17, 4, "private office"),
          ("conf", 13, 4, 18, 8, "conference room"), ("kit", 0, 8, 3, 11, "kitchen or break room"),
          ("wc", 3, 8, 5, 10, "restroom"), ("hall", 5, 8, 18, 9.5, "corridor"), ("store", 18, 0, 20, 2, "storage")]


@pytest.fixture
def office_plan():
    p = make_plan("toffice", OFFICE, doors=[("o1", "hall", 0.9), ("o2", "hall", 0.9), ("conf", "hall", 0.9),
                                            ("wc", "hall", 0.85), ("kit", "hall", 0.7), ("open", None, 1.8)],
                  windows=[("o1", 1.5), ("o3", 1.5), ("open", 3.0), ("store", 1.0)])
    for r in p["rooms"]:
        r["label_source"] = "vision"
    return p


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Overlay in a temp folder; no CoStar lookups."""
    monkeypatch.setattr(store, "DIR", tmp_path / "labels")
    monkeypatch.setattr(facts, "record", lambda sid: None)
    monkeypatch.setattr(facts, "property_id", lambda sid: None)
    monkeypatch.setattr(facts, "siblings", lambda sid: [])
    monkeypatch.setattr(facts, "scan_kind", lambda sid: "office")
    monkeypatch.setattr(facts, "scan_name", lambda sid: sid)
