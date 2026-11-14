"""listing_claims: parsing free text, the claims only text makes, and what a listing leaves out."""
from tests.tools.conftest import make_home
from threshold.tools import ToolContext, run_tool
from threshold.tools.listing_claims import parse, unsaid


def test_parse_free_text():
    c = {x["key"]: x["value"] for x in parse(
        "Sun-drenched 3 bed / 2.5 bath, 1,250 sq ft. Two-story townhome with 10 ft ceilings! South-facing patio. "
        "Kitchen island, hardwood floors, in-unit washer and dryer. 2-car garage. Community pool.")}
    assert c["beds"] == 3 and c["baths"] == 2.5 and c["area"] == 1250 and c["stories"] == 2
    assert c["ceiling_ft"] == 10 and c["natural_light"] and c["facing"] == "south"
    assert c["kitchen_island"] and c["wood_floors"] and c["laundry_in_unit"] and c["garage"]
    assert c["parking_spaces"] == 2
    assert "pool" not in c  # a community pool is not the home's


def test_unsaid_windowless_bedroom_no_closet_low_ceiling():
    plan = make_home(b2_height=2.05)
    got = {x["key"].split(":")[0]: x for x in unsaid(plan)}
    assert got["windowless"]["room"] == "B2"
    assert got["no_closet"]["title"] == "1 bedroom has no closet"
    assert got["low_ceiling"]["status"] == "fail"
    assert "through_bedroom" not in got  # the half bath opens off the living room


def test_bathroom_only_through_a_bedroom():
    plan = make_home()
    plan["openings"] = [o for o in plan["openings"] if o["id"] != "d4"]  # the half bath loses its door
    plan["rooms"] = [r for r in plan["rooms"] if r["id"] != "T2"]
    keys = {x["key"].split(":")[0] for x in unsaid(plan)}
    assert "through_bedroom" in keys


def test_windowless_scan_says_nothing_about_windows():
    keys = {x["key"].split(":")[0] for x in unsaid(make_home(windows=False))}
    assert "windowless" not in keys


def test_pasted_listing(records):
    ctx = ToolContext(plans=lambda sid: make_home())
    r = run_tool("listing_claims", {"scan": "home1", "text": "Cozy 3 bedroom, 2 bath, 950 sq ft with high ceilings."}, ctx)
    checks = {c.id: c for c in r.checks}
    assert checks["title_beds"].status == "fail" and checks["title_beds"].threshold == 3
    assert checks["title_area"].status == "fail"
    assert checks["high_ceilings"].status == "fail"  # 2.5 m is not high
    assert any(f.title.startswith("Not in the listing") for f in r.findings)
    assert "does not mention" in r.verdict.text


def test_own_listing_does_not_repeat_record_claims(records):
    ctx = ToolContext(plans=lambda sid: make_home())
    r = run_tool("listing_claims", {"scan": "home1"}, ctx)
    ids = [c.id for c in r.checks]
    assert "beds" in ids and "title_beds" not in ids  # the remarks' "2 bed" equals the record's
    assert "ceiling_ft" in ids and "natural_light" in ids
