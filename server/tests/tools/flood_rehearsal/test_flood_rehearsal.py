"""flood_rehearsal on a hand-made house; the aerial, drone and FEMA lookups are switched off."""
import math

import pytest
from flood_house import house, plans_of

from threshold.tools import ToolContext, run_tool
from threshold.tools.flood_rehearsal import floor_height as fh
from threshold.tools.flood_rehearsal import public, scenario


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def no(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(scenario, "_site", no)
    monkeypatch.setattr(public, "fema_zone", no)


def run(plan, **inputs):
    ctx = ToolContext(plans=plans_of(plan))
    return run_tool("flood_rehearsal", {"scan": plan["sid"], "depth_m": 0.5, **inputs}, ctx), ctx


def test_outdoor_panoramas_give_the_floor_height():
    p = house()
    e = fh.scan_outdoor(p, fh.exterior_doors(p)[0])
    assert e["value_m"] == pytest.approx(0.25, abs=0.01) and e["confidence"] == "medium"
    assert fh.exterior_doors(p)[0]["id"] == "F"                 # the living room door before the garage door


def test_door_step_is_a_lower_bound():
    assert fh.door_step(house())["value_m"] == pytest.approx(0.15)


def test_combine_takes_the_most_precise_and_widens_for_disagreement():
    a = fh._est("drone_pixels", 0.20, 0.05, "high", "")
    b = fh._est("scan_outdoor", 0.40, 0.10, "medium", "")
    c = fh._est("vexcel_eave", 1.5, 0.3, "low", "")            # low confidence: reported, does not widen
    out = fh.combine([a, b, c], fh._est("door_step", 0.18, 0.03, "medium", ""))
    assert out["method"] == "drone_pixels" and out["value_m"] == 0.20
    assert out["lo_m"] == pytest.approx(0.18) and out["hi_m"] == pytest.approx(0.40)   # clipped below, widened above
    assert out["widened_by"] == ["scan_outdoor"] and out["clipped_by_bound"]
    assert {(x["a"], x["b"]) for x in out["agreement"]} >= {("drone_pixels", "scan_outdoor")}
    assert fh.combine([a], override=0.33)["method"] == "measured"


def test_drone_rows_turn_into_heights():
    # Camera 1.2 m above a ground plane at z = 0, level, looking north at a wall 15 m away; threshold at 0.3 m.
    lat0, lon0 = 29.78, -95.245
    to_xy, to_ll = fh._local(lat0, lon0)
    lon_c, lat_c = to_ll(0, 0)
    lon_t, lat_t = to_ll(0, 15)
    photo = {"lat": lat_c, "lon": lon_c, "alt_abs": 1.2, "gimbal_pitch_deg": 0.0, "gimbal_yaw_deg": 0.0,
             "focal_px": 3725.0, "cx_px": 2640.0, "cy_px": 1978.0, "lrf_lat": lat_t, "lrf_lon": lon_t, "lrf_alt_abs": 1.2}
    w = 5280
    row = lambda z: 1978.0 - 3725.0 * (z - 1.2) / 15
    h = fh.drone_heights(photo, w, 2640, row(0.3), row(0.0), to_xy)
    assert h["threshold_abs"] == pytest.approx(0.3, abs=1e-6) and h["ground_abs"] == pytest.approx(0.0, abs=1e-6)
    assert h["distance_m"] == pytest.approx(15, rel=1e-3) and h["door_xy"][1] == pytest.approx(15, rel=1e-3)


def test_eave_method_with_a_fake_surface_model():
    p = house()
    lat0, lon0 = 29.78, -95.245
    _, to_ll = fh._local(lat0, lon0)
    corners = [to_ll(x, y) for x, y in ((0, 0), (10, 0), (10, 10), (0, 10), (0, 0))]
    wkt = "POLYGON((" + ",".join(f"{lo} {la}" for lo, la in corners) + "))"
    to_xy, _ = fh._local(lat0, lon0)

    def dsm(pts):  # 3.0 m eave over ground at 10.0 m
        return [13.0 if 0 < to_xy(*q)[0] < 10 and 0 < to_xy(*q)[1] < 10 else 10.0 for q in pts]
    e = fh.vexcel_eave(p, wkt, lat0, lon0, dsm)
    assert e["value_m"] == pytest.approx(3.0 - 2.44 - fh.FRAMING_M, abs=0.01) and e["confidence"] == "low"


def test_flood_rehearsal_on_the_house():
    r, ctx = run(house())
    by = {c.id: c for c in r.checks}
    # floor 0.25 above the ground, water 0.5 above it: 0.25 m on the floor, 0.40 m in the sunken garage
    assert next(m.value for m in r.metrics if m.id == "depth_inside") == pytest.approx(0.25, abs=0.01)
    assert by["G"].measured == pytest.approx(0.40, abs=0.01) and by["R"].status == "fail"
    kinds = [o.kind for o in r.overlays]
    assert kinds[:2] == ["water", "lens"] and "pins" in kinds
    assert r.overlays[0].level_m == pytest.approx(0.25, abs=0.01)
    order = [p.anchor.room for p in next(o for o in r.overlays if o.kind == "pins").pins]
    assert order[0] == "G"                                     # the sunken garage floods first
    assert "flood_rehearsal:house:floor_height" in {f.id for f in r.findings}
    assert any("outdoor panoramas" in s for s in ctx.steps)


def test_the_range_carries_the_floor_error():
    r, _ = run(house())
    m = {x.id: x.value for x in r.metrics}
    assert m["depth_inside_low"] < m["depth_inside"] < m["depth_inside_high"]
    assert m["floor_height_low"] == pytest.approx(0.15)        # clipped by the step at the front door


def test_measured_floor_height_replaces_the_estimate():
    r, _ = run(house(), floor_height_m=0.6)
    m = {x.id: x.value for x in r.metrics}
    assert m["floor_height"] == 0.6 and m["rooms_wet"] == 1     # only the sunken garage (0.15 below) takes water
    assert r.verdict.status == "fail"


def test_water_below_the_floor_warns_only_at_the_high_end():
    r, _ = run(house(), depth_m=0.1)   # 0.15 m below the floor; at the low floor height the garage takes 0.10 m
    assert r.verdict.status == "warn" and "between 0 and 1 of 4 rooms" in r.verdict.text
    assert run(house(), depth_m=0.0)[0].verdict.status == "pass"


def test_no_wall_graph_says_what_it_cannot_do():
    r, _ = run(house(walls=False))
    assert r.verdict.status == "unknown" and "no wall graph" in r.verdict.text
    assert "flood_rehearsal:house:no_walls" in {f.id for f in r.findings}


def test_depth_is_a_slider():
    from threshold.tools import load
    s = load()["flood_rehearsal"].manifest.inputs["properties"]["depth_m"]
    assert s["type"] == "number" and s["x-pref"] == "flood.depth_m" and s["maximum"] == 3


def test_harvey_depth_from_marks(monkeypatch):
    marks = [{"id": i, "lat": 29.78 + i * 1e-4, "lon": -95.245, "distance_m": 300 + i, "water_navd88_m": 10.0 + 0.1 * i,
              "height_above_ground_m": 1.0, "quality": 2, "environment": "Riverine", "waterbody": "Hunting Bayou",
              "description": ""} for i in range(3)]
    monkeypatch.setattr(public, "marks_near", lambda ev, lat, lon, r: marks)
    # Vexcel ground reads 0.5 m above NAVD88 at the marks (ground there 9.0, 9.1, 9.2 m), and 9.3 at the house
    monkeypatch.setattr(scenario, "_heights", lambda kind, pts: [9.8] + [9.5 + 0.1 * i for i in range(3)])
    h = scenario.harvey_depth(29.78, -95.245, lambda s: None)
    assert h["available"] and h["datum_offset_m"] == pytest.approx(0.5)
    assert h["depth_m"] == pytest.approx(10.1 - 9.3, abs=1e-6) and h["lo_m"] <= h["depth_m"] <= h["hi_m"]


def test_harvey_without_marks_falls_back_to_the_typed_depth(monkeypatch):
    monkeypatch.setattr(public, "marks_near", lambda *a: [])
    r, _ = run(house(), scenario="harvey_2017")
    assert "No good-quality USGS Harvey high-water mark" in r.verdict.text
    assert next(m.value for m in r.metrics if m.id == "depth_outside") == 0.5


def test_distance_helper():
    assert public.metres_between(29.78, -95.245, 29.79, -95.245) == pytest.approx(1105.7, abs=1)
    assert math.isclose(public.FT, 0.3048)
