"""signals helpers on the hand-made home (tests/tools/conftest.py): wall pieces, crossings, isovists, noise classes."""
import numpy as np

from tests.tools.conftest import make_home
from threshold.signals import noise_map
from threshold.signals.isovist import isovist, sees
from threshold.signals.plan2d import crossings, grid, room_names, segments


def test_segments_cut_doorways_and_keep_windows():
    s = segments(make_home(), "f1")
    on_h1 = [i for i, w in enumerate(s.wall) if w == "h1"]
    assert len(on_h1) == 2 and all(s.kind[i] == "wall" for i in on_h1)  # the 1 m entrance is a gap
    gap = sum(np.hypot(*(s.b[i] - s.a[i])) for i in on_h1)
    assert abs(gap - 3.0) < 1e-6
    assert "window" in {s.kind[i] for i, w in enumerate(s.wall) if w == "l2"}


def test_crossings_through_wall_not_through_door():
    s = segments(make_home(), "f1")
    hall = (2.0, 1.5)
    through_wall, through_door = (6.5, 4.5), (2.0, -1.0)  # bathroom behind the solid part of ht; out the entrance
    hits = crossings(hall, np.array([through_wall, through_door]), s).sum(axis=1)
    assert hits[0] == 1 and hits[1] == 0


def test_isovist_of_a_closed_room_is_the_room():
    s = segments(make_home(), "f1")
    v = isovist((2.0, 4.5), s, fov_deg=360, max_range=50)  # bedroom R, its door to the hallway is 0.70 m
    assert v.area > 12.0  # the room, plus a slice of hallway and, out the front door in line, the street
    side = isovist((1.0, 5.5), s, fov_deg=90, heading_deg=0, max_range=50)  # looking along the north wall: room only
    assert side.area < 12.0
    assert sees((2.0, 4.5), np.array([[6.0, 4.5]]), s)[0] == False  # noqa: E712  the bathroom is behind a wall


def test_grid_and_names():
    p = make_home()
    from threshold.signals.plan2d import room_polys
    polys = room_polys(p)
    assert len(grid(polys["R"], 0.75)) >= 12
    assert room_names(p, ["R", "U"]) == {"R": "Bedroom", "U": "Bedroom 2"}


def test_noise_classes():
    assert noise_map.parse_class("60.0 - 69.9") == (60.0, 70)
    assert noise_map.parse_class("> 90.0") == (90.0, 100.0)
    legend = [(45.0, 50, (255, 193, 7)), (60.0, 70, (255, 51, 153))]
    assert noise_map.classify((250, 55, 150, 255), legend) == (60.0, 70)
    assert noise_map.classify((0, 0, 0, 0), legend) is None
