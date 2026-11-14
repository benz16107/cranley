import math

from tests.tools._site.fakes import FakeOrtho, facts, ll, offline  # noqa: F401
from shapely import wkt

from threshold.aerial import site
from threshold.tools._site import metres, osm
from threshold.tools.loading_docks import faces_of
from threshold.tools.truck_access import (
    TURN_SWEEP_M,
    Photo,
    court_depth,
    entrance,
    paved_run,
)


def test_parse_height():
    assert osm.parse_height("13'6\"") == 4.11
    assert osm.parse_height("12 ft") == 3.66
    assert osm.parse_height("4.2") == 4.2
    assert osm.parse_height("below_default") == 0.0
    assert osm.parse_height("default") is None


def test_turning_geometry_is_aashto_wb67():
    assert math.isclose(TURN_SWEEP_M, (45 - 4.4) * 0.3048)


def photo(offline, green_from_n):  # noqa: F811
    offline.setattr(site, "ortho", lambda lat, lon, size_m, px=1024: FakeOrtho(lat, lon, size_m, 256, green_from_n))
    return Photo(29.7, -95.4, 200)


def test_court_ends_at_vegetation(offline):  # noqa: F811
    p = photo(offline, green_from_n=60)  # grass starts 60 m north of the centre; the north wall is at 20 m
    fp_m = metres(wkt.loads(facts({})["footprint"]), 29.7)
    north = next(f for f in faces_of(fp_m) if f["side"] == "north")
    c = court_depth(p, north, 29.7, None, n_rays=3)
    assert 38 <= c["median_m"] <= 42 and c["rays"][0]["ended_by"] == "pavement ends at vegetation"


def test_court_ends_at_tall_things(offline):  # noqa: F811
    import threshold.tools.truck_access as ta
    p = photo(offline, green_from_n=1e9)
    # surface 10 m up from 30 m out: a building across the court
    offline.setattr(ta, "heights", lambda kind, pts: [20.0 if (lat - 29.7) * 110574 > 49.5 else 10.0 for lon, lat in pts])
    fp_m = metres(wkt.loads(facts({})["footprint"]), 29.7)
    north = next(f for f in faces_of(fp_m) if f["side"] == "north")
    c = court_depth(p, north, 29.7, 10.0, n_rays=3)
    assert 28 <= c["min_m"] <= 32


def test_paved_run_measures_a_strip(offline):  # noqa: F811
    p = photo(offline, green_from_n=1e9)
    # all pavement: the run is capped
    assert paved_run(p, 29.7, (-95.4, 29.7), (1.0, 0.0), cap_m=20) >= 19


def test_entrance_picks_the_driveway_nearest_the_court():
    street = {"tags": {"name": "Main Street", "highway": "residential"}, "points": [ll(-100, -60), ll(100, -60)]}
    cross = {"tags": {"name": "Cross Street", "highway": "residential"}, "points": [ll(-100, -100), ll(-100, 100)]}
    far = {"tags": {"highway": "service"}, "points": [ll(80, -60), ll(80, -30)]}
    near = {"tags": {"highway": "service"}, "points": [ll(-10, -60), ll(-10, -25)]}
    e = entrance({"streets": [street, cross], "service": [far, near], "gates": []}, ll(0, -30), 29.7)
    assert e["mapped"] and e["street"]["tags"]["name"] == "Main Street"
    assert abs(e["mouth_ll"][0] - ll(-10, -60)[0]) < 1e-6
    assert e["cross"]["name"] == "Cross Street" and e["cross"]["dist_m"] == 90 and e["cross"]["dir"] == "east"
