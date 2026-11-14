"""The georef convention and the footprint refit, on a hand-made L-shaped house; and on real houses when the
data folder has them."""
import json
import math

import pytest
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon

from threshold.config import DATA
from threshold.geometry import georef
from threshold.sources import footprint

from tests.real import real

L_SHAPE = [[0, 0], [12, 0], [12, 5], [5, 5], [5, 9], [0, 9]]


def house(yaw: float = 30.0, t=(2.0, -1.0)) -> dict:
    return {"sid": "test", "geo": {"lat": 29.76, "lon": -95.37, "yaw_deg": yaw, "translation": {"x": t[0], "y": t[1]}},
            "walls": [], "rooms": [{"id": "r1", "floor": "f1", "polygon": L_SHAPE, "walls": [], "holes": []}]}


def footprint_for(plan: dict, turn: float = 0.0, shift=(0.0, 0.0), eaves: float = 0.4) -> Polygon:
    """Where the house really is: the convention's placement, turned and shifted, grown by the eaves."""
    o = footprint.outline_enu(plan, Polygon(L_SHAPE))
    return translate(rotate(o, turn, origin=o.centroid), *shift).buffer(eaves, join_style="mitre")


def test_convention_is_rotate_then_add_translation():
    assert (georef.YAW_SIGN, georef.TRANSLATION) == (1, "enu")
    e, n = georef.to_enu(house(90.0, (3.0, 4.0)), 1.0, 0.0)
    assert (e, n) == pytest.approx((3.0, 5.0))  # scan +x points north, then the translation is added


def test_fit_recovers_turn_and_shift():
    plan = house()
    f = footprint.fit(plan, footprint_for(plan, turn=4.0, shift=(1.5, -2.0)))
    assert f["rotation_deg"] == pytest.approx(4.0, abs=1.0)
    assert f["shift_m"] == pytest.approx(math.hypot(1.5, 2.0), abs=0.3)
    assert f["residual_m"] == pytest.approx(0.4, abs=0.15)  # the eaves
    assert f["iou"] > 0.8 and footprint.verdict(f)


def test_wrong_building_fails_verdict():
    plan = house()
    tower = Polygon([(-40, -40), (40, -40), (40, 40), (-40, 40)])
    assert not footprint.verdict(footprint.fit(plan, tower))


def test_footprint_enu_reads_lonlat_wkt():
    plan = house()
    lat, lon = georef.to_latlon(plan, 0.0, 0.0)
    fp = footprint.footprint_enu(plan, f"POLYGON(({lon} {lat},{lon + 1e-4} {lat},{lon + 1e-4} {lat + 1e-4},{lon} {lat}))")
    e0, n0 = georef.to_enu(plan, 0.0, 0.0)
    assert fp.exterior.coords[0] == pytest.approx((e0, n0), abs=1e-3)


REAL = real("compass_houses", [])


@pytest.mark.parametrize("sid", REAL)
def test_real_house_fits_its_footprint(sid):
    f = DATA / "cache" / "georef_fit" / f"{sid}.json"
    if not f.exists():
        pytest.skip("run scripts/check_compass.py or load the plan once to cache the fit")
    fit = json.loads(f.read_text())["fit"]
    if fit is None or "footprint_enu" not in json.loads(f.read_text()):
        pytest.skip("cached fit from an older version")
    assert footprint.verdict(fit) and abs(fit["rotation_deg"]) < 8


def test_verified_fit_moves_georef_and_marks_quality():
    from threshold.scanplan import apply_georef_fit
    plan = house()
    plan["quality"] = {"georef": False, "counts": {}, "notes": []}
    fit = footprint.fit(plan, footprint_for(plan, turn=4.0, shift=(1.5, -2.0)))
    before = georef.to_enu(plan, 3.0, 2.0)
    apply_georef_fit(plan, fit, footprint.verdict(fit))
    assert plan["quality"]["georef"] and plan["geo"]["fit"]["verified"] and plan["geo"]["fit"]["method"] == "footprint_iou"
    after = georef.to_enu(plan, 3.0, 2.0)
    assert georef.to_enu(plan, 3.0, 2.0, raw=True) == pytest.approx(before)
    assert math.dist(before, after) > 1.0
    assert georef.from_enu(plan, *after) == pytest.approx((3.0, 2.0), abs=1e-6)
    assert georef.azimuth_of(plan, 0.0, 1.0) == pytest.approx((georef.azimuth_of(plan, 0.0, 1.0, raw=True) - fit["rotation_deg"]) % 360)


def test_failed_fit_leaves_georef_false():
    from threshold.scanplan import apply_georef_fit
    plan = house()
    plan["quality"] = {"georef": False, "counts": {}, "notes": []}
    apply_georef_fit(plan, None, False)
    assert not plan["quality"]["georef"] and plan["geo"]["fit"] is None and "not verified" in plan["quality"]["notes"][0]
