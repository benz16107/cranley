from threshold.tools import ToolContext, run_tool
from threshold.tools.robot_fit import fit_scan


def test_one_scan_and_variants(ctx):
    r = run_tool("robot_fit", {"scan": "home", "body_width_m": 0.5, "turning_diameter_m": 0.7,
                               "step_height_m": 0.02}, ctx)
    assert len(r.checks) == 5
    lens = next(o for o in r.overlays if o.kind == "lens")
    assert lens.values["K"] == 0.0 and lens.values["T"] == 1.0   # the kitchen is behind a 15 cm step
    assert lens.values["U"] == 0.0                                # upstairs


def test_a_better_climber_reaches_the_kitchen():
    from tests.tools.conftest import make_home
    p = make_home()
    rooms = {x["room"]: x for x in fit_scan(p, 0.5, 0.7, 0.12)["rooms"]}
    assert rooms["K"]["usable"]


def test_many_scans(ctx):
    r = run_tool("robot_fit", {"scans": ["home", "home2", "bare"]}, ctx)
    m = {x.id: x.value for x in r.metrics}
    assert m["scans"] == 2 and r.scope.sids == ["home", "home2", "bare"]
