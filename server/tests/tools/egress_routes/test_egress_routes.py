from threshold.tools import ToolContext, run_tool

from ..fire_plans import no_walls, plans, unit


def test_routes_one_way_rooms_windows_and_hose():
    r = run_tool("egress_routes", {"scan": "unit"}, ToolContext(plans=plans(unit())))
    m = {x.id: x.value for x in r.metrics}
    assert m["entrances"] == 1
    # bedroom B1's centre to the entrance: up the hall and across the living room, well over the 4 m straight run
    assert 8 < m["longest_route"] < 14
    titles = {f.title for f in r.findings}
    assert "One way out, Bedroom" in titles
    assert "One way in from outside" in titles
    windows = {c.id: c for c in r.checks if c.id.startswith("window:")}
    assert windows["window:B1"].status == "pass" and windows["window:B1"].measured == 0.9
    assert windows["window:B2"].status == "unknown"  # no window recorded, so nothing to judge
    hose = next(c for c in r.checks if c.id == "hose")
    assert hose.measured > m["longest_route"]  # the stretch runs to the far corner, past the room centre
    assert any(o.kind == "route" for o in r.overlays) and any(o.kind == "lens" for o in r.overlays)
    exit_check = next(c for c in r.checks if c.id == "exit")
    assert exit_check.measured == 0.85 and exit_check.status == "pass"


def test_no_wall_graph_answers_plainly():
    r = run_tool("egress_routes", {"scan": "flat"}, ToolContext(plans=plans(no_walls())))
    assert r.verdict.status == "unknown"
    assert "no wall graph" in r.verdict.text
    assert r.checks == []
