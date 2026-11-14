from threshold.tools import run_tool


def test_stretcher_to_each_bedroom(ctx):
    r = run_tool("stretcher_route", {"scan": "home"}, ctx)
    assert r.verdict.status == "warn"                   # R is reachable flat; U is upstairs, so on site
    assert next(c for c in r.checks if c.id == "R.door.RB").status == "pass"   # 0.65 clear, 0.61 stretcher
    assert {m.id: m.value for m in r.metrics}["rooms"] == 2
    assert next(c for c in r.checks if c.id == "U.route").status == "warn"   # upstairs: reported, not dropped
