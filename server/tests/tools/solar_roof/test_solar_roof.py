"""Solar roof on a hand-made 12 m square gable house, ridge running east-west, 30 degree pitch, in Houston."""
import math

import numpy as np
import pytest
from tests.tools._site.fakes import facts, offline  # noqa: F401

from threshold.aerial import site
from threshold.sun import roof
from threshold.tools import run_tool
from threshold.tools import solar_roof
from threshold.world import terrain

HALF = 6.0


def gable(tree_south: float = 0.0) -> dict:
    n, size = 240, 120.0
    c = (np.arange(n) + 0.5) * size / n - size / 2
    e, nn = np.meshgrid(c, c[::-1])
    h = np.zeros((n, n), np.float32)
    on = (np.abs(e) < HALF) & (np.abs(nn) < HALF)
    h[on] = 3 + (HALF - np.abs(nn[on])) * math.tan(math.radians(30))
    if tree_south:
        h[(nn < -8) & (nn > -14) & (np.abs(e) < 20)] = tree_south
    return {"heights": h, "bounds_enu": (-size / 2, -size / 2, size / 2, size / 2), "ground_m": 0.0}


@pytest.fixture
def house(offline):  # noqa: F811
    offline.setattr(site, "site_facts", lambda lat, lon: facts({"roof_shape": "gable", "solar": False},
                                                               footprint_m=2 * HALF))
    return offline


def test_south_facet_carries_panels_and_north_is_left_bare(house):
    house.setattr(terrain, "grid", lambda *a, **k: gable())
    r = run_tool("solar_roof", {"lat": 29.7, "lon": -95.4})
    by = {f.id.rsplit(":", 1)[1]: f for f in r.findings}
    assert by["S"].status == "pass" and by["N"].status == "unknown"
    m = {x.id: x.value for x in r.metrics}
    assert m["panels"] > 0 and m["system_kw"] == pytest.approx(m["panels"] * 0.4)
    assert m["payback_years"] == pytest.approx(m["system_cost"] / m["annual_savings"], rel=0.02)
    # a south 30 degree plane in Houston gets about the reference plane's sun, so the yield is close to PVWatts'
    assert m["annual_kwh"] / m["system_kw"] == pytest.approx(solar_roof.YIELD["TX"][0], rel=0.06)
    assert any(o.kind == "route" and o.floor == "geo" for o in r.overlays)


def test_trees_to_the_south_take_the_roof(house):
    house.setattr(terrain, "grid", lambda *a, **k: gable(tree_south=25.0))
    m = {x.id: x.value for x in run_tool("solar_roof", {"lat": 29.7, "lon": -95.4}).metrics}
    assert m["panels"] == 0


def test_facets_pitch_and_facing_from_the_surface():
    from shapely.geometry import box
    r = roof.analyse(gable(), box(-HALF, -HALF, HALF, HALF), 29.7, -95.4, 2026)
    by = {f["id"]: f for f in r["facets"]}
    assert by["S"]["pitch_deg"] == pytest.approx(30, abs=2) and by["S"]["azimuth_deg"] == pytest.approx(180, abs=2)
    assert by["N"]["orientation"] < 0.8 < by["S"]["orientation"]


def test_payback_arithmetic():
    solar_roof._check()
