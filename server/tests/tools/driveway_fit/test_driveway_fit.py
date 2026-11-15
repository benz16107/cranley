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
