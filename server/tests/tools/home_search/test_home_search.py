"""home_search over a hand-made table of homes and hand-made city places: no kit, no network."""
import numpy as np
import pytest

from threshold import nearby
from threshold.tools import ToolError, run_tool
from threshold.tools import home_search as hs
from threshold.tools.pet_fit import yard

APTS = [
    {"sid": "a1", "name": "One", "lat": 34.0, "lon": -118.3, "property_id": 1, "no_pets": False, "has_policy": True,
     "dog": True, "dog_lb": 75, "dog_rent": 50, "cat": True, "cat_rent": 25, "path": "p"},
    {"sid": "a2", "name": "One again", "lat": 34.0, "lon": -118.3, "property_id": 1, "no_pets": False, "has_policy": True,
     "dog": True, "dog_lb": 75, "dog_rent": 50, "cat": True, "cat_rent": 25, "path": "p"},
    {"sid": "b1", "name": "Two", "lat": 34.1, "lon": -118.3, "property_id": 2, "no_pets": False, "has_policy": True,
     "dog": True, "dog_lb": 25, "dog_rent": 30, "cat": True, "cat_rent": 30, "path": "p"},
    {"sid": "c1", "name": "Three", "lat": 34.2, "lon": -118.3, "property_id": 3, "no_pets": True, "has_policy": False,
     "dog": False, "dog_lb": None, "dog_rent": None, "cat": False, "cat_rent": None, "path": "p"},
]
HOUSES = [
    {"sid": "h1", "name": "Flat", "lat": 29.7, "lon": -95.4, "listing": True, "fenced": "yes", "pool_listed": False,
     "pet_friendly": None, "no_pets": False, "dog_park": False},
    {"sid": "h2", "name": "Pool", "lat": 29.8, "lon": -95.4, "listing": True, "fenced": "yes", "pool_listed": True,
     "pet_friendly": None, "no_pets": False, "dog_park": False},
    {"sid": "h3", "name": "Unknown", "lat": 29.9, "lon": -95.4, "listing": False, "fenced": None, "pool_listed": False,
     "pet_friendly": None, "no_pets": False, "dog_park": False},
]


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(hs, "table", lambda city, kind: APTS if kind == "apartment_unit" else HOUSES)
    monkeypatch.setattr(hs, "cached_facts", lambda lat, lon: None)
    monkeypatch.setattr(yard, "measures", lambda: {"h1": {"back_m2": 150.0, "flat_share": 0.8}, "h2": {"back_m2": 90.0, "flat_share": 0.9}})
    pts = {c: np.zeros((0, 2)) for c in nearby.CITY_CATEGORIES}
    pts["playground"] = np.array([[-95.4, 29.7 + 300 / 110574.0]])   # 300 m north of h1: 300 x 1.4 / 80 = 5.25 min
    monkeypatch.setattr(nearby, "city_places", lambda city, fetch=True: pts)


def test_apartments_by_dog_weight_one_row_per_community(fake):
    r = run_tool("home_search", {"city": "Los Angeles", "kind": "apartment_unit", "dog_lb": 50})
    assert [c.rule.split(":")[0] for c in r.checks] == ["#1 One"]
    assert r.verdict.text.startswith("1 of 2 scanned communities")


def test_houses_fenced_flat_no_pool(fake):
    r = run_tool("home_search", {"city": "Houston", "fenced": True, "no_pool": True, "min_yard_m2": 100, "min_flat_pct": 60})
    assert [f.id for f in r.findings] == ["home_search:h1:match"]
    assert "2 could answer the fence criterion" in r.verdict.text   # h3 has no listing


def test_near_a_playground(fake):
    r = run_tool("home_search", {"city": "Houston", "near": ["playground"], "walk_min": 10})
    assert [f.id for f in r.findings] == ["home_search:h1:match"]
    assert r.checks[0].measured == pytest.approx(300 * nearby.DETOUR / nearby.WALK_M_MIN, abs=0.2)


def test_mixed_criteria_are_refused(fake):
    r = run_tool("home_search", {"city": "Houston", "kind": "house", "dog_lb": 50})
    assert r.verdict.status == "unknown" and "apartment criteria" in r.verdict.text
    with pytest.raises(ToolError):
        run_tool("home_search", {"city": "Paris"})


def test_a_near_set_is_the_same_as_its_categories(fake):
    a = run_tool("home_search", {"city": "Houston", "near_set": "playground and park"})
    b = run_tool("home_search", {"city": "Houston", "near": ["playground", "park"]})
    assert a.verdict.text == b.verdict.text
