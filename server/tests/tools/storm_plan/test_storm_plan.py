"""storm_plan's pure pieces, and the planner on the hand-made house with a fake inventory."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "flood_rehearsal"))
from flood_house import house

from threshold.tools import storm_plan as sp
from threshold.tools.flood_rehearsal import scenario
from threshold.tools.storm_plan import prep


def test_a_window_bigger_than_a_sheet_takes_several_boards():
    assert prep.boards_for(1.0, 1.0) == [(1.2, 1.2)]
    assert len(prep.boards_for(2.0, 1.0)) == 1        # 2.2 x 1.2 fits a sheet laid sideways
    b = prep.boards_for(2.4, 1.2)                     # 2.6 x 1.4 with overlap: three strips 0.87 x 1.4
    assert len(b) == 3 and all(min(x) <= prep.SHEET_W and max(x) <= prep.SHEET_H for x in b)


def test_packing_counts_sheets():
    assert len(prep.pack([(0.6, 1.2)] * 4)) == 1      # four quarter sheets fit one sheet
    assert len(prep.pack([(1.2, 2.4)] * 3)) == 3
    cut = prep.cut_list([{"id": "a", "width": 0.9, "height": 0.9}, {"id": "b", "width": 0.9, "height": 0.9}])
    assert cut["boards"] == 2 and cut["sheets"] == 1 and cut["windows"][0]["board_w"] == pytest.approx(1.1)
    assert prep.cut_list([{"id": "a", "width": 0.9, "height": 1.2}] * 2)["sheets"] == 2   # 1.1 x 1.4 twice: too tall


def test_door_dam():
    d = prep.door_dam(0.9, 0.2)
    assert d["length_m"] == pytest.approx(1.5) and d["layers"] == 3 and d["bags"] == 4 * 6 and d["holds"]
    assert not prep.door_dam(0.9, 0.8)["holds"]


def test_schedule_drops_what_does_not_fit_and_its_dependants():
    tasks = [{"id": "a", "minutes": 10, "must": True}, {"id": "materials", "minutes": 100},
             {"id": "b", "minutes": 30, "needs": ["materials"]}, {"id": "c", "minutes": 5}]
    kept, dropped = prep.schedule(tasks, 40)
    assert [t["id"] for t in kept] == ["a", "c"]
    assert {t["id"]: t["why"] for t in dropped} == {"materials": "no time left", "b": "its materials trip did not fit"}


def test_generator_zone_and_a_lot_too_small():
    lat0, lon0 = 29.78, -95.245
    _, to_ll = prep._local(lat0, lon0)
    def poly(pts):
        return "POLYGON((" + ",".join(f"{lo} {la}" for lo, la in (to_ll(x, y) for x, y in pts)) + "))"
    house_wkt = poly([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    lot = {"type": "Polygon", "coordinates": [[to_ll(x, y) for x, y in ((-5, -15), (15, -15), (15, 15), (-5, 15), (-5, -15))]]}
    z = prep.generator_zone(house_wkt, lot, lat0, lon0)
    assert not z["empty"] and z["spot_distance_m"] >= prep.GENERATOR_M and z["lot_known"]
    tight = {"type": "Polygon", "coordinates": [[to_ll(x, y) for x, y in ((-3, -3), (13, -3), (13, 13), (-3, 13), (-3, -3))]]}
    assert prep.generator_zone(house_wkt, tight, lat0, lon0)["empty"]


def fake_inv():
    def it(i, name, cost, size, z=0.0):
        return {"id": f"L:{i}", "name": name, "category": "furniture", "count": 1, "fixture": False, "size_class": size,
                "cost_class": cost, "cost": {"$500 to $2,000": (500, 2000), "under $100": (20, 100)}[cost],
                "carry_people": prep_people(size), "confidence": "high", "room": "L", "height_m": z,
                "anchor": {"sid": "house", "point": [2.0, 2.0, z]}, "media": [], "pano": "l1",
                "wet_lo": True, "wet_mid": True, "wet_hi": True}
    return {"items": [it(0, "Television", "$500 to $2,000", "one person carries"), it(1, "Rug", "under $100", "hand-held")],
            "utilities": [{"id": "u0", "label": "electrical panel", "name": "Electrical panel", "room": "G",
                           "height_m": 1.2, "anchor": {"sid": "house", "point": [1, 9.9, 1.2]},
                           "pano_anchor": {"sid": "house", "pano": "g1", "yaw_deg": 0, "pitch_deg": 0}, "media": [],
                           "confidence": "high", "wet_lo": False, "wet_mid": False, "wet_hi": False}]}


def prep_people(size):
    from threshold.tools.valuables_height import CARRY
    return CARRY[size]


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(scenario, "_site", lambda *a: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(sp, "MEMO", tmp_path)
    p = house()
    return p, scenario.run(p, sp.Inputs(scan="house", depth_m=0.5, hours_left=72, adults=2), lambda s: None)


def test_plan_with_time_boards_dams_and_carries(setup):
    p, fl = setup
    r = sp.build("house", p, sp.Inputs(scan="house", depth_m=0.5, hours_left=72, adults=2), fl, fake_inv(), lambda s: None)
    ids = [c.id for c in r.checks if c.status == "pass"]
    assert ids[0] == "find_shutoffs" and ids[1] == "materials" and ids[-1] == "power_off"
    assert any(i.startswith("board:") for i in ids) and any(i.startswith("dam:") for i in ids)
    assert ids.index("carry:L:0") < ids.index("carry:L:1")      # more value per minute first
    assert "Everything fits" in r.verdict.text
    assert any(f.id == "storm_plan:house:dry_area" for f in r.findings)


def test_short_time_drops_the_envelope_and_says_what_changed(setup):
    p, fl = setup
    sp.build("house", p, sp.Inputs(scan="house", depth_m=0.5, hours_left=72, adults=2), fl, fake_inv(), lambda s: None)
    r = sp.build("house", p, sp.Inputs(scan="house", depth_m=0.5, hours_left=4, adults=1), fl, fake_inv(), lambda s: None)
    ids = [c.id for c in r.checks if c.status == "pass"]
    assert not any(i.startswith(("board:", "dam:", "materials")) for i in ids)
    changed = next(f for f in r.findings if f.id == "storm_plan:house:changes").detail
    assert "Hours left: 72.0 h to 4.0 h." in changed and "Dropped: Buy" in changed and "only 4 h left" in changed
    assert any(f.id == "storm_plan:house:no_boards" for f in r.findings)


def test_deep_water_drops_door_dams(setup, monkeypatch):
    p = house()
    fl = scenario.run(p, sp.Inputs(scan="house", depth_m=1.5, hours_left=72, adults=2), lambda s: None)
    r = sp.build("house", p, sp.Inputs(scan="house", depth_m=1.5, hours_left=72, adults=2), fl, fake_inv(),
                 lambda s: None, memo=False)
    assert not any(c.id.startswith("dam:") for c in r.checks)
    assert any(f.title.startswith("No door dam") for f in r.findings)


def test_generator_zone_with_a_multipolygon_lot():
    lat0, lon0 = 29.78, -95.245
    _, to_ll = prep._local(lat0, lon0)
    ring = lambda pts: [list(to_ll(x, y)) for x, y in pts]  # noqa: E731
    house_wkt = "MULTIPOLYGON(((" + ",".join(f"{a} {b}" for a, b in ring([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])) + \
        ")),((" + ",".join(f"{a} {b}" for a, b in ring([(20, 20), (21, 20), (21, 21), (20, 20)])) + ")))"
    lot = {"type": "MultiPolygon", "coordinates": [[ring([(-3, -3), (13, -3), (13, 13), (-3, 13), (-3, -3)])],
                                                   [ring([(30, 30), (31, 30), (31, 31), (30, 30)])]]}
    z = prep.generator_zone(house_wkt, lot, lat0, lon0)
    assert z["available"] and z["farthest_m"] > 0
