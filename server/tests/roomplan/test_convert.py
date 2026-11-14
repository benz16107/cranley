"""RoomPlan export to ScanPlan, on the hand-made demo home (threshold/roomplan/demo.py), in the exact format Apple's
decoder accepts. No sponsor data, no network."""
import copy
import json
import math
import pathlib

import pytest
from fastapi.testclient import TestClient

from threshold.geometry import georef
from threshold.roomplan import ExportError, convert
from threshold.roomplan.demo import home
from threshold.tools.registry import ToolContext, run_tool

SID = "u_0123456789ab"
IOS_DEMO = pathlib.Path(__file__).resolve().parents[3] / "ios/Threshold/Threshold/Resources/DemoHome.json"


@pytest.fixture(scope="module")
def plan():
    return convert(home(), SID, "Demo home", kind="house")


def by_label(plan):
    out = {}
    for r in plan["rooms"]:
        out.setdefault(r["label"], []).append(r)
    return out


def test_rooms_from_walls(plan):
    rooms = by_label(plan)
    assert sorted(rooms) == ["Bathroom", "Bedroom", "Hallway", "Kitchen", "Living Room"]
    assert len(rooms["Bedroom"]) == 2
    expect = {"Living Room": 30.0, "Kitchen": 10.5, "Bathroom": 4.5, "Hallway": 3.0}
    for label, area in expect.items():
        assert rooms[label][0]["area"] == pytest.approx(area, rel=0.06), label  # corners jitter by 3 cm
    assert all(r["height"] == pytest.approx(2.44) for r in plan["rooms"])
    assert all(len(r["polygon"]) >= 4 and r["label_source"] == "roomplan" for r in plan["rooms"])
    q = plan["quality"]
    assert q["walls"] and q["polygons"] and q["openings"] and q["labels"] and q["walls_source"] == "roomplan"


def test_openings_measured_and_placed(plan):
    rooms = {r["id"]: r["label"] for r in plan["rooms"]}
    doors = sorted((o["width"], sorted(rooms[r] for r in o["rooms"])) for o in plan["openings"] if o["type"] == "doorway")
    assert doors == [(0.71, ["Bathroom", "Hallway"]), (0.76, ["Bedroom", "Hallway"]), (0.81, ["Bedroom", "Living Room"]),
                     (0.86, ["Hallway", "Living Room"]), (0.91, ["Living Room"])]
    front = next(o for o in plan["openings"] if o["width"] == 0.91)
    assert front["exterior"] is True and front["sill"] == pytest.approx(0.0, abs=1e-6)  # floor shifted to z = 0
    windows = [o for o in plan["openings"] if o["type"] == "window"]
    assert len(windows) == 5 and all(o["exterior"] for o in windows)
    assert sorted(o["sill"] for o in windows)[:2] == pytest.approx([0.9, 0.9])
    walls = {w["id"]: w for w in plan["walls"]}
    for o in plan["openings"]:  # each opening sits on its wall's centre line
        w = walls[o["wall"]]
        assert o["id"] in w["openings"]
        (ax, ay), (bx, by), (cx, cy) = w["a"], w["b"], o["center"]
        assert abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / w["length"] < 1e-6


def test_objects_in_their_rooms(plan):
    rooms = {r["id"]: r["label"] for r in plan["rooms"]}
    where = {(o["category"], rooms.get(o["room"])) for o in plan["objects"]}
    assert {("toilet", "Bathroom"), ("bathtub", "Bathroom"), ("stove", "Kitchen"), ("sofa", "Living Room"),
            ("bed", "Bedroom")} <= where
    tub = next(o for o in plan["objects"] if o["category"] == "bathtub")
    assert tub["size"] == [1.5, 0.75, 0.55] and tub["center"][2] == pytest.approx(0.275)


def test_the_phone_frame_does_not_matter():
    a, b = convert(home(turn_deg=0, shift=(0, 0)), SID), convert(home(turn_deg=63, shift=(5, -2)), SID)
    area = lambda p: sorted(round(r["area"], 2) for r in p["rooms"])  # noqa: E731
    assert area(a) == area(b)


def test_labels_from_objects_when_no_sections():
    ex = home()
    ex["sections"] = []
    labels = sorted(r["label"] or "-" for r in convert(ex, SID)["rooms"])
    assert labels == ["Bathroom", "Bedroom", "Bedroom", "Hallway", "Kitchen", "Living Room"]


def test_captured_structure_two_storeys():
    up = home()
    for k in ("walls", "doors", "windows", "openings", "objects"):
        for s in up[k]:
            s["story"] = 1
            s["transform"][13] += 2.9
    for s in up["sections"]:
        s["story"] = 1
    ground = home()
    structure = {"version": 1, "rooms": [ground, up],
                 **{k: ground[k] + up[k] for k in ("walls", "doors", "windows", "openings", "objects")}}
    p = convert(structure, SID)
    assert [f["elevation"] for f in p["floors"]] == [0.0, 2.9]
    assert len(p["rooms"]) == 12 and {r["floor"] for r in p["rooms"]} == {"f0", "f1"}
    upper_door = next(o for o in p["openings"] if o["floor"] == "f1" and o["type"] == "doorway")
    assert upper_door["sill"] == pytest.approx(2.9)


def test_phone_compass_georef():
    # camera faced east (heading 90) along RoomPlan's -Z, standing at X=1, Z=0
    p = convert(home(), SID, geo={"lat": 40.35, "lon": -74.65, "heading_deg": 90, "camera_forward": [0, -1],
                                  "camera_position": [1, 0]})
    assert p["geo"]["yaw_deg"] == pytest.approx(-90)
    e0, n0 = georef.to_enu(p, 1, 0)       # where the phone stood is the GPS point
    assert (e0, n0) == pytest.approx((0, 0), abs=1e-9)
    e1, n1 = georef.to_enu(p, 1, 1)       # one metre along the camera's forward (+y in the scan) is east
    assert (e1, n1) == pytest.approx((1, 0), abs=1e-9)
    assert p["quality"]["georef"] is False


def test_bad_exports():
    with pytest.raises(ExportError):
        convert({"version": 2, "walls": []}, SID)
    with pytest.raises(ExportError):
        convert([], SID)
    bad = home()
    bad["walls"][0]["transform"] = [1, 2]
    with pytest.raises(ExportError):
        convert(bad, SID)


def test_ios_demo_is_the_same_export():
    if not IOS_DEMO.exists():
        pytest.skip("no iOS checkout")
    assert json.loads(IOS_DEMO.read_text()) == json.loads(json.dumps(home()))


# every geometry tool on a home scanned with a phone
TOOLS = {
    "door_widths": ({"min_width_m": 0.813}, "fail"),     # 0.71, 0.76 and 0.81 m doors
    "step_free_route": ({"read_panoramas": False}, "fail"),
    "turning_space": ({}, "fail"),                        # the hallway
    "furniture_fit": ({"object": "sofa"}, None),
    "stretcher_route": ({}, None),
    "robot_fit": ({}, "pass"),
    "egress_routes": ({}, None),
    "takeoff_bid": ({"trade": "cleaning"}, "pass"),
    "flood_rehearsal": ({"depth_m": 0.6, "floor_height_m": 0.35, "use_drone": False}, "fail"),
    "bathroom_clearance": ({"read_panoramas": False}, "fail"),
    "aging_in_place": ({"read_panoramas": False}, None),
    "room_census": ({}, "pass"),
}


@pytest.mark.parametrize("tool", TOOLS)
def test_tool_runs_on_a_phone_scan(plan, tool):
    inputs, expect = TOOLS[tool]
    ctx = ToolContext(plans=lambda sid: copy.deepcopy(plan) if sid == SID else (_ for _ in ()).throw(LookupError(sid)))
    r = run_tool(tool, {"scan": SID, **inputs}, ctx)
    assert r.verdict.status in ("pass", "warn", "fail"), r.verdict.text
    if expect:
        assert r.verdict.status == expect, r.verdict.text


def test_flood_water_by_room(plan):
    ctx = ToolContext(plans=lambda sid: copy.deepcopy(plan))
    r = run_tool("flood_rehearsal", {"scan": SID, "depth_m": 0.6, "floor_height_m": 0.35, "use_drone": False}, ctx)
    assert any(o.kind == "water" for o in r.overlays)
    assert "0.25 m" in r.verdict.text  # 0.60 m outside, floor 0.35 m up


def test_upload_route_then_plan_and_tool(tmp_path, monkeypatch):
    from threshold.api.app import app
    from threshold.sources import user_scans
    monkeypatch.setattr(user_scans, "ROOT", tmp_path / "user_scans")
    user_scans.plan_json.cache_clear()
    c = TestClient(app)
    r = c.post("/api/scans/user", json={"export": home(), "name": "My flat", "kind": "house", "workspace": "w1"})
    assert r.status_code == 200, r.text
    sid = r.json()["sid"]
    assert user_scans.owns(sid) and r.json()["counts"]["rooms"] == 6
    assert (tmp_path / "user_scans" / sid / "roomplan.json").exists()
    p = c.get(f"/api/scan/{sid}/plan").json()
    assert p["sid"] == sid and p["name"] == "My flat" and len(p["objects"]) == 13
    assert c.get("/api/scans/user", params={"workspace": "w1"}).json()[0]["sid"] == sid
    run = c.post("/api/tools/door_widths/run", json={"scan": sid, "min_width_m": 0.813}).json()
    assert run["verdict"]["status"] == "fail"
    assert c.post("/api/scans/user", json={"export": {"walls": []}}).status_code == 422
    assert c.get("/api/scan/u_ffffffffffff/plan").status_code == 404
    assert not math.isnan(p["rooms"][0]["area"])


@pytest.mark.parametrize("bad", [
    lambda e: e.update(walls=["x"]),
    lambda e: e["walls"][0].update(dimensions=[1]),
    lambda e: e["walls"][0].update(dimensions=["a", 1, 0]),
    lambda e: e["walls"][0].update(story="a"),
    lambda e: e.update(rooms=5),
    lambda e: e["walls"][0].update(dimensions=[float("inf"), 2, 0]),
])
def test_a_malformed_export_is_an_export_error_not_a_crash(bad):
    e = copy.deepcopy(home())
    bad(e)
    with pytest.raises(ExportError):
        convert(e, SID)


def test_too_many_walls_is_refused_before_converting():
    e = copy.deepcopy(home())
    e["walls"] = e["walls"] * 400
    with pytest.raises(ExportError, match="more than"):
        convert(e, SID)


def test_upload_refuses_a_body_over_the_limit_and_a_malformed_export(tmp_path, monkeypatch):
    from threshold.api import user_scans as route
    from threshold.api.app import app
    from threshold.sources import user_scans
    monkeypatch.setattr(user_scans, "ROOT", tmp_path / "user_scans")
    monkeypatch.setattr(route, "MAX_BYTES", 1000)
    c = TestClient(app)
    assert c.post("/api/scans/user", content=b"{" + b" " * 2000 + b"}").status_code == 413
    monkeypatch.setattr(route, "MAX_BYTES", 25_000_000)
    e = copy.deepcopy(home())
    e["walls"][0]["dimensions"] = [1]
    assert c.post("/api/scans/user", json={"export": e}).status_code == 422
    assert not (tmp_path / "user_scans").exists() or not any((tmp_path / "user_scans").iterdir())
