import pytest

from threshold.geometry import takeoff


def test_room_and_plan_quantities(plan):
    t = takeoff(plan)
    a = next(r for r in t["rooms"] if r["room"] == "A")
    assert a["floor_area"] == pytest.approx(16) and a["perimeter"] == pytest.approx(16)
    assert a["wall_area_gross"] == pytest.approx(40)                   # 16 m of wall x 2.5 m
    assert a["wall_area_net"] == pytest.approx(40 - 1.44 - 0.9 * 2.03 - 1.0 * 2.03)
    assert (a["doors"], a["windows"], a["glazed_area"]) == (2, 1, pytest.approx(1.44))
    assert t["total"]["windows"] == 1 and t["total"]["doors"] == 3
    assert t["total"]["floor_area"] == pytest.approx(16 + 4 + 8)        # D has no walls, so it is set apart
    assert t["total"]["floor_area_unwalled"] == 5.0
