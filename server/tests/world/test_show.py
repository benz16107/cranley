"""The storm and smoke timelines: resampling and bookkeeping, on hand-made records. No network, no sponsor data."""
import itertools

from threshold.world import smoke, storm


def test_gauge_record_is_resampled_to_half_hours_and_a_gappy_gauge_is_passed_over(monkeypatch):
    near = {"site_no": "1", "name": "Near", "lat": 0, "lon": 0, "datum": "NAVD88", "distance_m": 100}
    far = {**near, "site_no": "2", "name": "Far", "distance_m": 900}
    full = [(i * 900.0, 1.0 + i * 0.01) for i in range(400)]                       # every 15 minutes, rising
    gappy = [(t, v) for t, v in full if not 100 < t / 900 < 130]                    # seven hours missing
    monkeypatch.setattr(storm, "gauges", lambda lat, lon: [near, far])
    monkeypatch.setattr(storm, "stage", lambda site: gappy if site == "1" else full)
    h = storm.hydrograph(0, 0)
    assert h["site_no"] == "2"
    assert h["time"][1] - h["time"][0] == storm.STEP_S
    assert abs(h["stage_m"][1] - 1.02) < 1e-9                                       # 30 minutes in: two readings later
    assert h["peak_m"] == max(h["stage_m"]) and h["peak_time"] == h["time"][-1]


def test_no_gauge_with_a_whole_record_gives_none(monkeypatch):
    monkeypatch.setattr(storm, "gauges", lambda lat, lon: [])
    assert storm.hydrograph(0, 0) is None


def test_what_got_wet_stays_counted():
    assert storm._so_far([0.1, 0.5, 0.3, 0.7, 0.2]) == [0.1, 0.5, 0.5, 0.7, 0.7]


def test_route_points_are_closer_than_the_step():
    pts = smoke._densify([[0, 0, 0], [2, 0, 0], [2, 1, 0]])
    assert pts[0] == [0, 0, 0] and pts[-1] == [2, 1, 0]
    assert all(abs(b[0] - a[0]) + abs(b[1] - a[1]) <= smoke.STEP_M + 1e-9 for a, b in itertools.pairwise(pts))


def test_layers_are_read_per_compartment(tmp_path):
    (tmp_path / "case_compartments.csv").write_text(
        "Time,ULT_1,HGT_1,ULOD_1,ULT_2,HGT_2,ULOD_2\n"
        "Simulation Time,Upper Layer Temperature,Layer Height,Optical Density,Upper Layer Temperature,Layer Height,Optical Density\n"
        "Time,C1,C1,C1,C2,C2,C2\ns,C,m,1/m,C,m,1/m\n"
        "0,20,2.4,0,20,2.5,0\n5,80,1.9,0.4,21,2.5,0\n")
    t, layers = smoke._layers(str(tmp_path))
    assert t == [0.0, 5.0]
    assert layers["C1"] == {"upper_c": [20.0, 80.0], "layer_m": [2.4, 1.9], "od": [0.0, 0.4]}
    assert layers["C2"]["layer_m"] == [2.5, 2.5]
