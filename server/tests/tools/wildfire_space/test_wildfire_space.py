"""Defensible space on a hand-made site: a 10 m square house, green 8 m trees in Zone 1 (1.6 to 9 m off
the wall) along its west side and part of its north side, grey pavement everywhere else, flat ground."""
import io

import numpy as np
import pytest
from PIL import Image
from tests.tools._site.fakes import KX, KY, LAT, LON, facts, offline  # noqa: F401

from threshold.aerial import site
from threshold.tools import run_tool
from threshold.tools import wildfire_space as wf
from threshold.tools._site import osm
from threshold.world import terrain

N, SIZE = 200, 100.0
C = (np.arange(N) + 0.5) * SIZE / N - SIZE / 2
E, NN = np.meshgrid(C, C[::-1])
TREES = ((E < -6.6) & (E > -14) & (np.abs(NN) < 14)) | ((NN > 6.6) & (NN < 14) & (np.abs(E) < 5))


def grid(kind="dsm"):
    h = np.zeros((N, N), np.float32)
    if kind == "dsm":
        h[(np.abs(E) < 5) & (np.abs(NN) < 5)] = 6.0
        h[TREES] = 8.0
    return {"heights": h, "bounds_enu": (-SIZE / 2, -SIZE / 2, SIZE / 2, SIZE / 2), "ground_m": 0.0}


class Ortho:
    def __init__(self):
        px = 400
        a = np.full((px, px, 3), 150, np.uint8)
        t = Image.fromarray(TREES.astype(np.uint8) * 255).resize((px, px))
        a[np.asarray(t) > 127] = (60, 120, 50)
        buf = io.BytesIO()
        Image.fromarray(a).save(buf, "PNG")
        self.image = buf.getvalue()
        h = SIZE / 2
        self.bounds = (LON - h / KX, LAT - h / KY, LON + h / KX, LAT + h / KY)


@pytest.fixture
def house(offline):  # noqa: F811
    offline.setattr(site, "site_facts", lambda lat, lon: facts({"roof_material": "tile"}, footprint_m=10, parcel_m=80))
    offline.setattr(terrain, "grid", lambda lat, lon, size, n, kind="dsm": grid(kind))
    offline.setattr(site, "ortho", lambda *a, **k: Ortho())
    offline.setattr(osm, "_query", lambda q: {"elements": [{"lat": LAT + 0.01, "lon": LON, "tags": {"name": "Station 9"}}]})
    return offline


def test_trees_in_zone_one_fail_it_and_are_cleared_first_on_the_west(house):
    r = run_tool("wildfire_space", {"lat": LAT, "lon": LON})
    f = {x.id.rsplit(":", 1)[1]: x for x in r.findings}
    assert f["zone0"].status == "pass"
    assert f["zone1"].status in ("warn", "fail") and "west" in f["zone1"].detail
    assert "Zone 1" in r.verdict.text and "west" in r.verdict.text
    assert "Texas" in r.verdict.text  # a Houston point: the zones are California's
    m = {x.id: x.value for x in r.metrics}
    assert m["station_km"] == pytest.approx(1.1, abs=0.05) and m["slope"] == pytest.approx(0, abs=0.5)
    assert sum(o.kind == "route" and o.floor == "geo" for o in r.overlays) == 3


def test_canopy_needs_height_and_green():
    rgb = np.array([[[60, 120, 50], [60, 120, 50], [150, 150, 150], [20, 26, 20]]], np.float32)
    ndsm = np.array([[8.0, 0.5, 8.0, 8.0]])
    green, canopy = wf.classify(rgb, ndsm)
    assert green.tolist() == [[True, True, False, True]]   # the dark faintly green cell is a shadowed crown
    assert canopy.tolist() == [[True, False, False, True]]  # a grey roof 8 m up is a building, not a tree


def test_zone_limits():
    assert wf.judge("zone0", {"canopy_pct": 0, "veg_pct": 30}) == "fail"
    assert wf.judge("zone1", {"canopy_pct": 35, "veg_pct": 40}) == "warn"
    assert wf.judge("zone2", {"canopy_pct": 10, "veg_pct": 10}) == "pass"


def test_nonwildland_is_outside_the_zones(monkeypatch):
    from threshold.tools.wildfire_space import calfire
    monkeypatch.setattr(calfire, "_query", lambda layer, lat, lon: [{"SRA": "LRA", "FHSZ": 0, "FHSZ_Description": "NonWildland"}])
    assert calfire.zone(34.0, -118.3)["zone"] is None
    monkeypatch.setattr(calfire, "_query", lambda layer, lat, lon: [{"SRA": "LRA", "FHSZ": 3, "FHSZ_Description": "Very High"}])
    assert calfire.zone(34.0, -118.3)["zone"] == "Very High"


def test_branches_over_the_roof_and_the_walk_around_lines(house, monkeypatch):
    # LA residents: insurers ordered branches trimmed off the roof; an inspector's checklist the photos cannot see
    import sys
    r = run_tool("wildfire_space", {"lat": LAT, "lon": LON})
    st = {c.id: c for c in r.checks}
    assert st["over_roof"].status == "pass" and st["over_roof"].measured == 0
    assert {f"cannot.walk.{k}" for k in ("deck", "vents", "gutters", "propane", "firewood", "zone0_rules",
                                        "insurer_score")} <= set(st)
    over = TREES | ((E > 1) & (E < 5) & (np.abs(NN) < 4))              # a crown over the east half of the roof
    monkeypatch.setattr(sys.modules[__name__], "TREES", over)
    r = run_tool("wildfire_space", {"lat": LAT, "lon": LON})
    c = {c.id: c for c in r.checks}["over_roof"]
    assert c.status == "warn" and 15 < c.measured < 30                   # 3.5 x 8 m inside the 9 x 9 m roof
    assert "branches cover about" in r.verdict.text
