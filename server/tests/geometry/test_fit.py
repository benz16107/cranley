import math

import pytest

from threshold.geometry import carry, corner_max_length, free_wall_runs, turning_space


def test_turning_circle_is_wall_face_to_wall_face(plan):
    assert turning_space(plan, "A")["diameter"] == pytest.approx(3.9)
    assert turning_space(plan, "C")["result"] == "likely pass"          # 1.9 m >= 1.525 m
    b = turning_space(plan, "B")
    assert b["diameter"] == pytest.approx(0.9) and b["result"] == "likely fail"
    assert not turning_space(plan, "D")["available"]


def test_corner_formula_matches_the_square_corridor_result():
    a, w = 1.0, 0.3
    assert corner_max_length(a, a, w) == pytest.approx(2 * math.sqrt(2) * a - 2 * w, abs=1e-4)
    assert corner_max_length(1.0, 1.0, 1.2) == 0.0


def test_carry_through_doors(plan):
    ok = carry(plan, "A", "C", (1.8, 0.6, 0.5))
    assert ok["result"] == "likely pass" and len(ok["doors"]) == 2
    bad = carry(plan, "A", "C", (1.8, 0.8, 0.75))
    assert bad["result"] == "likely fail"
    assert next(d for d in bad["doors"] if d["opening"] == "BC")["result"] == "likely fail"


def test_carry_flat_keeps_height_vertical(plan):
    # 0.62 wide fits the 0.65 door only on its side; flat it needs 0.62 across, which is within tolerance
    assert carry(plan, "A", "C", (2.0, 0.62, 0.3), flat=True)["doors"][1]["across"] == 0.62


def test_carry_checks_corners(plan):
    # an L route: from the hallway into the bathroom corner, then a long box
    r = carry(plan, "B", [9.7, 3.7], (2.6, 0.5, 0.5))
    assert r["available"] and r["corners"]


def test_free_wall_runs_skip_openings(plan):
    runs = free_wall_runs(plan, "A")
    assert runs["longest"] == pytest.approx(3.9)                     # north wall, no openings
    lengths = sorted(round(r["length"], 2) for r in runs["runs"])
    assert lengths.count(1.35) == 2                                  # south wall either side of the window
    assert lengths.count(1.5) == 2                                   # east wall either side of door AB


def test_corner_angle_generalises_the_right_angle():
    assert corner_max_length(1.0, 1.2, 0.5, 90) == pytest.approx(corner_max_length(1.0, 1.2, 0.5), abs=1e-9)
    # equal widths, no box width: the ladder is 2a / sin(phi/2)
    assert corner_max_length(1.0, 1.0, 0.0, 45) == pytest.approx(2 / math.sin(math.radians(22.5)), rel=1e-3)
    assert corner_max_length(1.0, 1.0, 0.4, 30) > corner_max_length(1.0, 1.0, 0.4, 60) > corner_max_length(1.0, 1.0, 0.4, 120)
