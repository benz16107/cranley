"""facility_audit's stock and kitchen lines on the hand-made home, relabelled as a small restaurant."""
from threshold.tools import ToolContext, run_tool
from threshold.tools import facility_audit as fa

from ..conftest import make_home


def restaurant(sid="rest"):
    p = make_home(sid)
    ops = {o["id"]: o for o in p["openings"]}
    ops["HL"]["width"], ops["LK"]["sill"] = 1.0, 0.0      # no data error, no step: a clean cart route
    next(r for r in p["rooms"] if r["id"] == "K")["label"] = "Pantry"   # counted as storage
    return p


def run(p, **kw):
    return run_tool("facility_audit", {"scan": p["sid"], "read_panoramas": False, "cleaning": False, **kw},
                    ToolContext(plans=lambda s: p))


def test_cart_route_to_storage_gives_its_bends():
    r = run(restaurant())
    c = {c.id: c for c in r.checks}["cart.K"]
    assert c.rule == "Cart route, entrance to storage: 3 doors and 2 bends, turning 94 degrees in all, the sharpest 51"
    m = {m.id: m for m in r.metrics}
    assert m["cart_sharpest_bend"].value == 51                   # the route cuts the hall's right angle in two
    assert m["storage_area"].value == round(12 * 10.7639)       # the 4 x 3 m pantry
    for k in ("power", "filtration", "cold_storage", "noise", "hot_water"):
        assert {c.id: c.status for c in r.checks}[f"cannot.{k}"] == "unknown"


def test_a_tall_rack_does_not_turn_into_a_narrow_door():
    p = restaurant("narrow")
    next(o for o in p["openings"] if o["id"] == "LK")["width"] = 0.5   # 0.45 m clear, the rack is 0.51 m wide
    assert {c.id: c.status for c in run(p).checks}["cart.K"] == "fail"


def test_hot_water_run_from_the_heater_to_the_farthest_sink(monkeypatch):
    seen = lambda lab, pt: {"label": lab, "point": pt, "finding": {"source": {"confidence": "medium"}}}
    monkeypatch.setattr(fa, "seen_objects", lambda plan, read: [seen("water heater", [0.5, 0.5, 0.0]),
                                                                seen("sink", [11.5, 8.5, 0.9]),
                                                                seen("sink", [5.0, 4.0, 0.9])])
    r = run(restaurant("hot"))
    c = {c.id: c for c in r.checks}["hot_water"]
    assert abs(c.measured - 13.6) < 0.05 and c.status == "pass" and c.threshold == 15.24
    monkeypatch.setattr(fa, "seen_objects", lambda plan, read: [seen("water heater", [0.5, 0.5, 0.0]),
                                                                seen("sink", [20.0, 9.0, 0.9])])
    r = run(restaurant("far"))
    assert {c.id: c.status for c in r.checks}["hot_water"] == "fail"
    assert any(f.id.endswith(":hot_water") for f in r.findings)


def test_backroom_share_and_pallet_spots():
    # store associates: one backroom for all freight, and overstock pallets lined down the sales floor
    from threshold.tools.facility_audit import pallet_positions
    from shapely.geometry import box
    assert pallet_positions(box(0, 0, 10.16, 4.27), 1.83) == 20          # two rows of ten, one shared aisle
    assert pallet_positions(box(0, 0, 10.16, 1.0), 1.83) == 0            # narrower than a pallet
    p = restaurant("store")
    for r in p["rooms"]:
        r["label"] = {"L": "retail floor", "K": "storage"}.get(r["id"], r["label"])
    m = {x.id: x.value for x in run(p).metrics}
    assert m["backroom_share"] == 50                                       # 4 x 3 m pantry, 4 x 6 m living room
    assert m["pallet_positions"] == 2                                      # one row of two and its aisle
    assert any(c.id == "cannot.overstock" for c in run(p).checks)


def test_pallet_rows_each_have_an_aisle():
    from shapely.geometry import box
    from threshold.tools.facility_audit import pallet_positions
    assert pallet_positions(box(0, 0, 3.0, 2.9), 1.83) == 0              # a row fits either way, its aisle does not
    assert pallet_positions(box(0, 0, 10.16, 3.1), 1.83) == 15           # rows turned the other way: 5 rows of 3
    assert pallet_positions(box(0, 0, 10.16, 6.8), 1.83) == 40           # pair, aisle, pair: 4 rows of 10
