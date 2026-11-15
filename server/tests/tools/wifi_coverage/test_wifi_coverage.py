"""wifi_coverage on the hand-made two-storey home: wall and floor losses, best spot, result shape."""
import numpy as np

from tests.tools.conftest import make_home
from threshold.tools import ToolContext, run_tool
from threshold.tools.wifi_coverage.model import BANDS, House, fspl_1m


def test_one_wall_costs_its_loss_and_a_floor_costs_more():
    h = House(make_home())
    src = (2.0, 1.5, "f1")
    th = np.radians(70)  # 3 m away both: out through the entrance gap, and through the solid part of hr
    open_pt, behind = np.array([[2.0, -1.5]]), np.array([[2.0 + 3 * np.cos(th), 1.5 + 3 * np.sin(th)]])
    a = h.signal(src, open_pt, "f1", "5", 23.0)[0]
    b = h.signal(src, behind, "f1", "5", 23.0)[0]
    assert abs((a - b) - BANDS["5"]["light"]) < 1e-6
    dz = 0.5
    expect = 23.0 - (fspl_1m(5500.0) + 20 * np.log10(np.hypot(3.0, dz)))
    assert abs(a - expect) < 1e-6
    up = h.signal(src, np.array([[2.0, 1.5]]), "f2", "5", 23.0)[0]  # straight up, through the floor
    assert a - up > 10  # the floor costs more than the shorter distance gains


def test_best_spot_and_result():
    r = run_tool("wifi_coverage", {"scan": "home"}, ToolContext(plans=lambda sid: make_home()))
    assert r.verdict.status in ("pass", "warn", "fail")
    lens = next(o for o in r.overlays if o.kind == "lens")
    assert set(lens.values) >= {"H", "R", "L", "U"} and lens.legend.unit == "dBm"
    pins = next(o for o in r.overlays if o.kind == "pins")
    assert pins.pins[0].id == "router"
    assert r.findings[0].id == "wifi_coverage:home:router"
    assert not any(ch.isdigit() for f in r.findings for ch in f.title.replace("Bedroom 2", ""))  # no numbers in titles


def test_router_in_a_room_and_no_walls():
    r = run_tool("wifi_coverage", {"scan": "home", "router_room": "K"}, ToolContext(plans=lambda sid: make_home()))
    by = {c.id: c.measured for c in r.checks}
    assert by["K"] > by["R"]  # the bedroom is three walls away from the kitchen
    from tests.tools.conftest import no_walls
    r = run_tool("wifi_coverage", {"scan": "bare"}, ToolContext(plans=lambda sid: no_walls()))
    assert r.verdict.status == "unknown"


def test_metal_ducts_and_coated_glass_cost_more_than_a_stud_wall():
    # installers and owners: "air ducts", and a glass-walled room that killed a Zigbee link
    from threshold.tools.wifi_coverage.model import MATERIALS
    src, behind = (2.0, 1.5, "f1"), np.array([[2.0 + 3 * np.cos(np.radians(70)), 1.5 + 3 * np.sin(np.radians(70))]])
    plain = House(make_home()).signal(src, behind, "f1", "5", 23.0)[0]
    glass = House(make_home(), materials={"hr": "coated glass"}).signal(src, behind, "f1", "5", 23.0)[0]
    assert abs((plain - glass) - (MATERIALS["coated glass"]["5"] - BANDS["5"]["light"])) < 1e-6
    ctx = ToolContext(plans=lambda sid: make_home())
    base = run_tool("wifi_coverage", {"scan": "home", "router_room": "H"}, ctx)
    ducts = run_tool("wifi_coverage", {"scan": "home", "router_room": "H", "wall_materials": {"R": "metal ductwork"}}, ctx)
    m = lambda r: {c.id: c.measured for c in r.checks}["R"]
    assert m(ducts) < m(base) - 10
    assert any(a.id == "material.metal ductwork" for a in ducts.assumptions)


def test_a_detached_garage_thirty_feet_out():
    from threshold.tools.wifi_coverage.model import outbuilding
    assert outbuilding(20.0, "2.4", 3.0, 9.1, "metal ductwork") < outbuilding(20.0, "2.4", 3.0, 9.1)
    r = run_tool("wifi_coverage", {"scan": "home", "router_room": "H", "outbuilding_m": 9.1,
                                   "outbuilding_wall": "metal ductwork"}, ToolContext(plans=lambda sid: make_home()))
    c = {c.id: c for c in r.checks}["outbuilding"]
    assert c.rule.startswith("Detached building 9 m from the house") and c.status in ("warn", "fail")
    assert "The detached building gets about" in r.verdict.text
