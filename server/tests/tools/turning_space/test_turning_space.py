from threshold.tools import run_tool


def test_circles_against_the_diameter(ctx):
    r = run_tool("turning_space", {"scan": "home", "diameter_m": 2.92}, ctx)
    st = {c.id: c.status for c in r.checks}
    assert st["turn.L"] == "pass"                       # 4 x 6 m: about 3.9 m
    assert st["turn.T"] == "warn"                       # 2.90 against 2.92: within the scan tolerance
    assert st["turn.H"] == "warn"
    lens = next(o for o in r.overlays if o.kind == "lens")
    assert abs(lens.values["T"] - 2.9) < 0.01           # 3 m wide less half a wall each side


def test_no_outlines_is_unknown(ctx):
    assert run_tool("turning_space", {"scan": "bare"}, ctx).verdict.status == "unknown"


def test_a_small_circle_fails(ctx):
    st = {c.id: c.status for c in run_tool("turning_space", {"scan": "home", "diameter_m": 3.0}, ctx).checks}
    assert st["turn.T"] == "fail" and st["turn.L"] == "pass"
