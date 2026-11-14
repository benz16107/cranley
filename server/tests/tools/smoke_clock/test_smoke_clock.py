import threshold.tools.smoke_clock as sc
from threshold.tools import ToolContext, run_tool

from ..fire_plans import no_walls, plans, unit


def test_input_file_from_rooms_and_doors():
    plan = unit()
    fire = next(r for r in plan["rooms"] if r["id"] == "L")
    text, comp = sc.write_input(plan, fire, doors_closed=False, growth=sc.GROWTH["fast"], peak_kw=2000)
    assert "K" not in comp                       # the 2 m² bathroom is below the size modelled
    assert text.count("&COMP ") == 4
    assert text.count("TYPE = 'WALL'") == 4      # L-H, H-B1, H-B2 and the entrance; the bathroom door is dropped
    assert text.count("&DEVC ") == 2             # one target per bedroom
    assert "COMP_ID = 'C1' FIRE_ID = 'Sofa'" in text and "DATA = 206, 1990" in text  # t² reaches 2 MW at 206 s
    closed, _ = sc.write_input(plan, fire, doors_closed=True, growth=sc.GROWTH["fast"], peak_kw=2000)
    assert closed.count(f"HEIGHT = {sc.UNDERCUT_M:.4f}") == 3   # two bedroom doors and the entrance leak underneath


def test_untenable_reads_cfast_columns():
    res = {"time": [0, 60, 120, 180],
           "cols": {"TRGFEDG_1|T_C3": [0, 0.1, 0.2, 0.4], "TRGFEDH_1|T_C3": [0, 0, 0, 0],
                    "TRGOBS_1|T_C3": [0, 0.1, 0.3, 0.9]}}
    u = sc.untenable(res, "C3")
    assert u["time_s"] == 120 and u["cause"] == "smoke too thick to see" and u["by"]["toxic gases"] == 180
    assert sc.untenable(res, "C9")["time_s"] is None


def test_no_walls_and_missing_cfast(monkeypatch):
    r = run_tool("smoke_clock", {"scan": "flat"}, ToolContext(plans=plans(no_walls())))
    assert r.verdict.status == "unknown" and "no wall graph" in r.verdict.text
    monkeypatch.setattr(sc, "cfast_bin", lambda: None)
    r = run_tool("smoke_clock", {"scan": "unit"}, ToolContext(plans=plans(unit())))
    assert r.verdict.status == "unknown" and "not installed" in r.verdict.text and not r.checks
