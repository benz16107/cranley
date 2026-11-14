"""The nearby engine on a hand-made Overpass answer: a residential street east-west, a secondary road north-south
crossing it at 200 m east, a footway island beside the home, a playground on the street, a park off the network."""
import math

import pytest

from threshold import nearby

LAT, LON = 29.7, -95.4
KX, KY = 111320.0 * math.cos(math.radians(LAT)), 110574.0


def ll(e, n):
    return LON + e / KX, LAT + n / KY


def way(wid, hw, pts, name=None, **tags):
    nodes = [nid for nid, _ in pts]
    geom = [{"lon": ll(*p)[0], "lat": ll(*p)[1]} for _, p in pts]
    return {"type": "way", "id": wid, "nodes": nodes, "geometry": geom, "tags": {"highway": hw, **({"name": name} if name else {}), **tags}}


def place(pid, e, n, **tags):
    lon, lat = ll(e, n)
    return {"type": "node", "id": pid, "lon": lon, "lat": lat, "tags": tags}


DATA = {"elements": [
    way(1, "residential", [(1, (0, 0)), (2, (100, 0)), (3, (200, 0)), (4, (300, 0)), (5, (400, 0))], "Elm Street"),
    way(2, "secondary", [(10, (200, -200)), (3, (200, 0)), (11, (200, 200))], "Big Road"),
    way(3, "footway", [(20, (5, -8)), (21, (15, -8))]),            # an island nearer the home than the street
    way(4, "path", [(30, (400, 0)), (31, (400, 150))], "Bayou Trail"),
    way(5, "path", [(40, (100, 0)), (41, (100, 50))], "Tiverton Drive"),
    place(100, 300, 5, leisure="playground"),
    place(101, 0, 2000, leisure="park", name="Far Park"),
    place(102, 120, 20, amenity="school", name="Oak Elementary School"),
    place(103, 150, 10, amenity="veterinary", name="Pet ER 24 Hours"),
]}


@pytest.fixture
def area(monkeypatch):
    monkeypatch.setattr(nearby, "raw", lambda lat, lon, fetch=True: DATA)
    nearby._area_cached.cache_clear()
    yield
    nearby._area_cached.cache_clear()


def test_route_follows_the_street_and_counts_the_busy_crossing(area):
    r = nearby.nearest(LAT, LON, ["playground"], start=ll(10, -8))
    h = r["playground"][0]
    assert h["method"] == "network"
    assert 300 < h["route_m"] < 325           # 300 m of street plus the two snaps, not the footway island
    assert h["busy_crossings"] == 1           # straight across Big Road at 200 m
    assert h["minutes"] == pytest.approx(h["route_m"] / nearby.WALK_M_MIN, abs=0.1)
    assert r["_meta"]["snap_m"] == pytest.approx(math.hypot(10, 8), abs=0.5)


def test_off_network_place_is_a_labelled_estimate(area):
    h = nearby.nearest(LAT, LON, ["park"])["park"][0]
    assert h["method"] == "estimate" and h["busy_crossings"] is None
    assert h["route_m"] == pytest.approx(2000 * nearby.DETOUR, rel=0.01)


def test_categories_read_tags():
    assert nearby.school_level({"name": "Oak Elementary School"}) == "elementary"
    assert nearby.school_level({"isced:level": "3", "name": "X"}) == "high"
    trail = nearby.CATEGORIES["trail"][2]
    assert trail({"highway": "path", "name": "Bayou Trail"}) and not trail({"highway": "path", "name": "Tiverton Drive"})
    assert nearby.CATEGORIES["pickleball"][2]({"leisure": "pitch", "sport": "tennis;pickleball"})


def test_vets_are_driving_minutes_and_the_emergency_one_is_found(area):
    r = nearby.nearest(LAT, LON, ["vet", "emergency_vet"])
    assert r["emergency_vet"][0]["name"] == "Pet ER 24 Hours" and r["emergency_vet"][0]["by"] == "car"
    assert r["vet"][0]["minutes"] == pytest.approx(r["vet"][0]["route_m"] / nearby.DRIVE_M_MIN, abs=0.1)


def test_busy_road_and_places_near(area):
    b = nearby.busy_road_m(LAT, LON)
    assert b["name"] == "Big Road" and b["m"] == pytest.approx(200, abs=1)
    near = nearby.places_near(LAT, LON, ["playground", "park"], radius_m=500)
    assert [p["category"] for p in near] == ["playground"]
    assert nearby.neighbour_m(LAT, LON, None) is None  # too few mapped buildings to say anything
