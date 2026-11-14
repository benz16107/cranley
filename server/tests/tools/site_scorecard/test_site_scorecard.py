"""site_scorecard, commute_fit and the helpers of industrial_fit, retail_site and facility_audit, on hand-made records."""
import pytest

from threshold.tools import Site, ToolContext, ToolResult, run_tool
from threshold.tools.commute_fit import commute, minutes, parse_homes
from threshold.tools.facility_audit import fixes_for
from threshold.tools.industrial_fit import scan_doors, scan_height
from threshold.tools.market_comps import kit
from threshold.tools.retail_site import frontage
from threshold.tools.site_scorecard import lin, near
from threshold.tools.types import Check, Verdict


def row(pid, lat, *, rate, block, clear, docks, cls="B", ratio=1.0):
    return {"id": pid, "type_id": 2, "type": "Industrial", "class": cls, "address": f"{pid} Test St", "city": "Houston",
            "lat": lat, "lon": -95.4, "rba": 60000, "clear_ft": clear, "docks": docks, "parking_ratio": ratio,
            "rents": [{"rate": rate, "service": "Triple net (NNN)", "sf": block, "sublease": False, "listing": 1, "use": 7}],
            "available": {"sf": block, "max_contiguous_sf": block}, "sales": []}


ROWS = {1: row(1, 29.70, rate=9, block=50000, clear=32, docks=8, cls="A"),
        2: row(2, 29.71, rate=11, block=45000, clear=24, docks=4),
        3: row(3, 29.72, rate=14, block=55000, clear=28, docks=6),   # over budget
        4: row(4, 29.73, rate=8, block=48000, clear=14, docks=2)}    # too low: a deal-breaker


@pytest.fixture
def kit_rows(monkeypatch):
    monkeypatch.setattr(kit, "rows", lambda: ROWS)
    monkeypatch.setattr(kit, "row", lambda pid: ROWS.get(pid))
    monkeypatch.setattr(near, "transport", lambda lat, lon: {"nearest": {"highway": {"km": 1.0 + (lat - 29.7) * 100, "name": "I-10",
                                                                                     "lat": lat, "lon": -95.4, "id": "n/1"}},
                                                             "bus_stops_400m": 0, "bus_stops_800m": 0})
    import threshold.tools.flood_rehearsal.public as pub
    monkeypatch.setattr(pub, "fema_zone", lambda lat, lon: {"in_sfha": lat > 29.725, "zone": "AE" if lat > 29.725 else None})


def ctx():
    return ToolContext(sites=lambda p: Site(p, ROWS[p.property_id]["lat"], -95.4, ROWS[p.property_id]["address"], "Houston",
                                            p.property_id, [], "test"))


def test_lin_scores_both_directions():
    assert lin(10, 10, 20) == 100 and lin(15, 10, 20) == 50 and lin(25, 10, 20) == 0
    assert lin(20, 24, 16) == 50 and lin(30, 24, 16) == 100


def test_scorecard_ranks_and_flags_deal_breakers(kit_rows):
    res = run_tool("site_scorecard", {"profile": "industrial", "candidates": [{"property_id": k} for k in (4, 3, 2, 1)],
                                      "size_min_sf": 40000, "size_max_sf": 80000, "budget_sf_yr": 12, "clear_height_min_ft": 24,
                                      "docks_min": 4}, ctx())
    m = {x.id: x.value for x in res.metrics}
    order = [f.title for f in res.findings if f.id.endswith(":summary")]
    assert order[0] == "#1 1 Test St" and order[-1].endswith("4 Test St")
    assert m["deal_breakers"] == 1 and m["p1/rent"] == 9 and m["p1/clear_height"] == 32
    assert "4 Test St (clear height)" in res.verdict.text
    c3 = {c.id: c for c in res.checks}["p3.rent"]
    assert c3.measured == 14 and c3.threshold == 12 and c3.status == "warn"  # 17% over: weak, not a deal-breaker
    assert {c.id: c for c in res.checks}["p4.flood"].status == "fail"  # in the 1% zone in this fixture


def test_flood_avoid_makes_the_zone_a_deal_breaker(kit_rows):
    res = run_tool("site_scorecard", {"profile": "industrial", "candidates": [{"property_id": 1}, {"property_id": 4}],
                                      "flood": "avoid", "clear_height_min_ft": 10, "docks_min": 1}, ctx())
    assert "flood zone" in res.verdict.text


def test_search_finds_listings_in_the_city(kit_rows):
    res = run_tool("site_scorecard", {"profile": "industrial", "city": "Houston", "max_candidates": 3,
                                      "size_min_sf": 40000, "budget_sf_yr": 12, "use_osm": False}, ToolContext())
    assert {x.id: x.value for x in res.metrics}["candidates"] == 3 and "found" in next(
        a.value for a in res.assumptions if a.id == "search")


def test_an_unverified_must_have_costs_points(kit_rows):
    ROWS[5] = {**row(5, 29.70, rate=9, block=50000, clear=32, docks=8, cls="A"), "rents": []}
    try:
        res = run_tool("site_scorecard", {"profile": "industrial", "candidates": [{"property_id": 1}, {"property_id": 5}],
                                          "budget_sf_yr": 12, "use_osm": False}, ctx())
    finally:
        del ROWS[5]
    m = {x.id: x.value for x in res.metrics}
    assert m["p5/score"] < m["p1/score"]


def test_commute_estimates_and_zip_parsing():
    assert minutes(0) == 6 and minutes(10, 1.0) == pytest.approx(6 + 8 / 35 * 60 + 2 / 60 * 60, abs=0.1)
    homes = parse_homes(["77002:3", "-95.5,29.8"], lookup=lambda: {"77002": (29.75, -95.36)})
    assert [h["n"] for h in homes] == [3, 1]
    c = commute(homes, 29.75, -95.36, 1.3)
    assert c["people"] == 4 and c["median"] == 6.0 and c["max"] > 6


def test_scan_doors_and_height():
    plan = {"rooms": [{"id": "big", "area": 900, "height": 9.0}, {"id": "off", "area": 30, "height": 2.7}],
            "openings": [{"id": "d1", "type": "doorway", "rooms": ["big"], "width": 3.0, "height": 3.0},
                         {"id": "d2", "type": "doorway", "rooms": ["big"], "width": 0.9},
                         {"id": "d3", "type": "doorway", "rooms": ["big", "off"], "width": 3.0}]}
    assert [d["id"] for d in scan_doors(plan)] == ["d1"]
    assert scan_height(plan)["ft"] == 29.5
    plan["rooms"][0].pop("height")
    assert scan_height(plan) is None  # the office's 2.7 m is not the warehouse's clear height


def test_frontage_picks_the_biggest_road():
    roads = [{"kind": "residential", "km": 0.01, "name": "A"}, {"kind": "secondary", "km": 0.12, "name": "B"},
             {"kind": "primary_link", "km": 0.15, "name": "C"}]
    assert frontage(roads)["name"] == "C" and frontage([{"kind": "service", "km": 0.01, "name": "x"}]) is None


def test_fix_list_prices_from_the_cost_book():
    v = Verdict(status="fail", text="")
    doors = ToolResult(scope={"sid": "s"}, verdict=v, checks=[
        Check(id="a", rule="Doorway width", measured=0.78, threshold=0.813, unit="m", status="fail"),
        Check(id="b", rule="Doorway width", measured=0.70, threshold=0.813, unit="m", status="fail")])
    egress = ToolResult(scope={"sid": "s"}, verdict=v, checks=[
        Check(id="exit", rule="Widest doorway out", measured=0.75, threshold=0.813, unit="m", status="fail")])
    fixes = fixes_for(doors, None, egress, 0.813)
    assert [f["priority"] for f in fixes] == [1, 2, 2]
    assert {f["title"]: f["total"] for f in fixes}["Swing-clear hinges on doors just under 32 in"] == 250
