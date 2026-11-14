"""where_am_i: the nearest scanned address to a fix, or the aerial-only tools when there is none."""
import pytest

from threshold.tools import ToolContext, run_tool
from threshold.tools import where_am_i as w

ROWS = {"a1": {"sid": "a1", "name": "Unit 1", "address": "1 Test St, Houston", "city": "Houston", "lat": "29.76000", "lon": "-95.37000", "kind": "apartment_unit"},
        "a2": {"sid": "a2", "name": "Unit 2", "address": "1 Test St, Houston", "city": "Houston", "lat": "29.76000", "lon": "-95.37000", "kind": "apartment_unit"},
        "b1": {"sid": "b1", "name": "House", "address": "9 Far Rd, Houston", "city": "Houston", "lat": "29.76900", "lon": "-95.37000", "kind": "house"},
        "x": {"sid": "x", "name": "No place", "address": "", "city": "", "lat": "", "lon": "", "kind": "house"}}


@pytest.fixture(autouse=True)
def rows(monkeypatch):
    monkeypatch.setattr(w, "_rows", lambda: ROWS)


def run(lon, lat, acc=None):
    return run_tool("where_am_i", {"geo": [lon, lat], "accuracy_m": acc}, ToolContext())


def test_nearest_groups_scans_by_address_and_sorts_by_distance():
    near = w.nearest(-95.37, 29.7601)
    assert [b["address"] for b in near] == ["1 Test St, Houston", "9 Far Rd, Houston"]
    assert [s["sid"] for s in near[0]["scans"]] == ["a1", "a2"] and near[0]["distance_m"] == pytest.approx(11.1, abs=0.3)
    assert w.metres(29.76, -95.37, 29.769, -95.37) == pytest.approx(1000.8, abs=1)
    assert w.nearest(-74.66, 40.35) == []                              # Princeton: nothing within 2 km


def test_at_a_scanned_address():
    r = run(-95.37, 29.7601, acc=8)
    assert r.verdict.status == "pass" and r.verdict.text == "You are at 1 Test St, Houston, which has 2 scans."
    assert r.actions == [] and r.findings[0].status == "pass" and r.findings[0].anchor.geo == (-95.37, 29.76)
    assert r.findings[0].source.layer == "phone" and r.findings[0].source.confidence == "high"
    assert [p.id for p in r.overlays[0].pins][0] == "me" and r.scope.geo == (-95.37, 29.7601)


def test_a_poor_fix_reaches_further_and_says_so():
    r = run(-95.37, 29.7609, acc=120)                                  # 100 m off, but the fix is only good to 120 m
    assert r.verdict.status == "pass" and r.findings[0].source.confidence == "low"
    assert run(-95.37, 29.7609, acc=10).verdict.status == "warn"       # the same spot with a good fix is not "at" it


def test_no_scan_here_offers_the_aerial_tools_at_the_spot():
    r = run(-74.66, 40.35, acc=15)
    assert r.verdict.status == "unknown" and "aerial tools work at this spot" in r.verdict.text
    assert [a.tool for a in r.actions] == ["roof_facts", "truck_access", "parking_count", "risk_sheet"]
    assert all(a.inputs == {"place": {"geo": [-74.66, 40.35]}} for a in r.actions)
    assert next(m for m in r.metrics if m.id == "nearest_m").value is None
