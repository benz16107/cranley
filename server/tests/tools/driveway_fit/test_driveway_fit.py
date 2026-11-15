from shapely.geometry import box

from threshold.tools.driveway_fit import _run_inside


def test_run_inside_stops_at_the_edge_and_bridges_small_gaps():
    lot = box(0, 0, 4, 12)
    assert abs(_run_inside(lot, (2, 0.5), (0, 1)) - 11.5) < 0.3
    paved = box(0, 0, 4, 5).union(box(0, 5.6, 4, 9))  # a 0.6 m joint in the paving is bridged
    assert abs(_run_inside(paved, (2, 0.5), (0, 1)) - 8.5) < 0.3


def test_a_truck_towing_a_camper_must_fit_end_to_end():
    from threshold.tools.driveway_fit import Inputs, long_checks, long_vehicle
    alone = long_vehicle(Inputs(scan="x", vehicle="ford_f150"))
    rig = long_vehicle(Inputs(scan="x", vehicle="ford_f150", towing="travel_trailer_25ft"))
    assert alone[0] == 5.89 and rig[0] == round(5.89 + 0.3 + 7.60, 2) and rig[2] == 3.20
    assert rig[3] == "Ford F-150 SuperCrew towing a 25 ft travel trailer"
    st = {c.id: c.status for c in long_checks(11.0, 3.0, *rig[:2], rig[3])}   # an 11 m driveway, 3 m wide
    assert st == {"long_length": "fail", "long_width": "pass"}
    assert long_checks(11.0, 3.0, *alone[:2], alone[3])[0].status == "pass"


def test_grade_change_at_the_road_against_an_overhang():
    # an RV owner: the driveway's angle at the road makes long overhangs drag; photos flatten it
    import numpy as np
    from threshold.tools.driveway_fit import departure_deg, grade_change, road_profile
    d = list(np.arange(6.0, 14.01, 0.5))
    h = [(x - 10) * 0.12 if x < 10 else 0.0 for x in d]   # 12% down to the parcel line at 10 m, flat beyond
    assert abs(grade_change(d, h, 10.0) - 6.84) < 0.05
    assert grade_change(d[:4], h[:4], 10.0) is None        # no ground beyond the lot line
    dep = departure_deg(3.0, 0.3)                           # a 3 m overhang 0.3 m up: 5.7 degrees
    assert abs(dep - 5.71) < 0.01 and grade_change(d, h, 10.0) > dep


def test_road_profile_reads_the_ground_model_along_the_axis(monkeypatch):
    import numpy as np
    from threshold.tools.driveway_fit import road_profile
    from threshold.world import terrain
    n = 200
    east = (np.arange(n) + 0.5) * 0.5 - 50
    H = np.tile(np.where(east < 0, -0.1 * east, 0.0), (n, 1)).astype(np.float32)   # sloping west of the point
    monkeypatch.setattr(terrain, "grid", lambda lat, lon, size, n_, kind="dsm": {
        "heights": H, "bounds_enu": (-50.0, -50.0, 50.0, 50.0)})
    from types import SimpleNamespace
    from threshold.tools._site import to_m
    lat, lon = 29.76, -95.37
    p0 = to_m(lat)[0](lon, lat)
    dist, hs = road_profile(SimpleNamespace(lat=lat, lon=lon), (p0[0] - 10, p0[1]), (1.0, 0.0), 10.0, lat)
    from threshold.tools.driveway_fit import grade_change
    assert abs(grade_change(dist, hs, 10.0) - 5.7) < 0.3   # 10% slope meets flat ground at the point
