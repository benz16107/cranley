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


def test_a_small_hall_between_rooms_stays_in_the_model():
    from ..conftest import make_plan
    p = make_plan("hall", [("lr", 0, 0, 5, 4, "Living Room"), ("h", 5, 1, 6, 2, "Hallway"), ("b", 6, 0, 9, 4, "Bedroom"),
                           ("cl", 5, 3, 6, 4, "Closet")],
                  doors=[("lr", "h", 0.9), ("h", "b", 0.8), ("b", "cl", 0.6)])
    comp, _ = sc.compartments(p)
    assert comp["h"] == comp["lr"] and comp["b"] != comp["lr"] and "cl" not in comp   # the closet joins nothing
    text, _ = sc.write_input(p, next(r for r in p["rooms"] if r["id"] == "lr"), False, 0.047, 2000)
    assert f"COMP_IDS = '{comp['lr']}', '{comp['b']}'" in text or f"COMP_IDS = '{comp['b']}', '{comp['lr']}'" in text


def test_a_stalled_cfast_is_stopped_and_its_timeline_kept(monkeypatch, tmp_path):
    exe = tmp_path / "fake_cfast"   # writes 2 min of output, then crawls forever like a stiff plan
    exe.write_text("#!/bin/sh\nprintf 'ID,TRGFEDG_1\\n,\\n,T_C3\\n,\\n0,0\\n60,0.1\\n120,0.5\\n' > case_devices.csv\n"
                   "echo 'Status at T =    1.20E+02 DT = 4.8E-02' > case.status\nsleep 30\n")
    exe.chmod(0o755)
    monkeypatch.setattr(sc, "cfast_bin", lambda: str(exe))
    monkeypatch.setattr(sc, "RUNS", tmp_path / "runs")
    res = sc.run_cfast("case a", stall_s=0.5, poll_s=0.1)
    assert res["stopped_s"] == 120 and res["time"][-1] == 120
    assert sc.run_cfast("case a")["stopped_s"] == 120          # cached: the stall is not waited out twice
    exe.write_text("#!/bin/sh\nprintf 'ID,X\\n,\\n,T_C3\\n,\\n0,0\\n5,0\\n' > case_devices.csv\nsleep 30\n")
    import pytest
    with pytest.raises(sc.NotApplicable):                      # stalled before a minute: no timeline at all
        sc.run_cfast("case b", stall_s=0.5, poll_s=0.1)


def test_a_bedroom_with_no_path_from_the_fire_is_not_applicable(monkeypatch):
    from ..conftest import make_plan
    p = make_plan("island", [("lr", 0, 0, 5, 4, "Living Room"), ("b", 6, 0, 9, 4, "Bedroom"), ("h", 9, 0, 11, 4, "Hallway")],
                  doors=[("b", "h", 0.8), ("lr", None, 0.9)])
    monkeypatch.setattr(sc, "cfast_bin", lambda: "/bin/false")
    r = run_tool("smoke_clock", {"scan": "island", "fire_room": "Living Room"}, ToolContext(plans=lambda s: p))
    assert r.verdict.status == "unknown" and "no doorway joins" in r.verdict.text


def test_the_default_fire_room_is_one_whose_smoke_reaches_a_bedroom():
    from ..conftest import make_plan
    p = make_plan("upstairs", [("lr", 0, 0, 8, 6, "Living Room"), ("fam", 10, 0, 14, 4, "Family Room"),
                               ("b", 14, 0, 17, 4, "Bedroom")], doors=[("fam", "b", 0.8), ("lr", None, 0.9)])
    comp, _ = sc.compartments(p)
    beds = {comp["b"]}
    pick = sc._pick_fire(p, None, lambda r: len(sc.reachable(p, comp, comp[r["id"]]) & beds))
    assert pick["id"] == "fam" and sc._pick_fire(p, None)["id"] == "lr"
