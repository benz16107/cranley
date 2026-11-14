"""record_vs_reality on hand-made plans and records: verdicts, scope, evidence, the no-walls case."""
import copy

from tests.tools.truth_fixtures import (
    HOME_RECORD,
    INDUSTRIAL_RECORD,
    UNIT_RECORD,
    make_home,
    site,
)
from threshold.tools import ToolContext, run_tool
from threshold.tools.record_vs_reality import audit
from threshold.tools.record_vs_reality import claims as cl
from threshold.tools.record_vs_reality import compare as cmp
from threshold.tools.record_vs_reality import measure as ms


def by_key(comps):
    return {c["key"]: c for c in comps}


def test_measure_area_rooms_counted_and_left_out():
    fa = ms.floor_area(make_home())
    assert round(fa["m2"], 1) == 63.8
    left = {x["room"]: x["why"] for x in fa["excluded"]}
    assert "garage" in left["G"] and "no walls" in left["P"] and "V" in left
    assert {r["room"] for r in fa["counted"]} == {"L", "B1", "B2", "T1", "T2", "C1"}


def test_bathrooms_full_and_half_by_size_then_by_fixtures():
    plan = make_home()
    b = ms.bathrooms(plan)
    assert (b["full"], b["half"]) == (1, 1)
    seen = ms.bathrooms(plan, {"T2": {"toilet", "shower"}, "T1": {"toilet"}})  # panoramas overrule size
    assert (seen["full"], seen["half"], seen["seen"]) == (1, 1, 2)
    assert next(g for g in seen["groups"] if g["rooms"] == ["T1"])["half"]


def test_home_claims_verdicts():
    plan = make_home()
    c = by_key(audit(plan, HOME_RECORD)["comparisons"])
    assert c["beds"]["verdict"] == "confirmed" and c["baths"]["verdict"] == "confirmed"
    assert c["living_area"]["verdict"] == "confirmed" and c["living_area"]["measured"]["value"] == 687
    assert c["stories"]["verdict"] == "contradicted" and c["stories"]["confidence"] == "low"  # a floor may be unscanned
    assert c["walk_in_closet"]["verdict"] == "confirmed"
    assert c["garage"]["verdict"] == "confirmed"
    assert c["fireplace"]["verdict"] == "cannot verify"  # needs the panoramas
    assert c["year_built"]["verdict"] == "context"
    assert "pool" not in c  # "Community Pool" is not the home's


def test_area_contradicted_names_what_was_left_out():
    rec = copy.deepcopy(HOME_RECORD)
    rec["claims"]["living_area"]["value"] = 1200
    c = by_key(audit(make_home(), rec)["comparisons"])["living_area"]
    assert c["verdict"] == "contradicted" and "Garage" in c["reason"]
    assert c["rooms"]["excluded"] and round(c["ratio"], 2) == 0.57
    assert c["confidence"] == "low"  # under 60%: a partial scan more than a wrong figure


def test_no_walls_area_cannot_run_but_labels_still_count():
    plan = make_home(walls=False)
    c = by_key(audit(plan, HOME_RECORD)["comparisons"])
    assert c["living_area"]["verdict"] == "cannot verify" and "no wall graph" in c["living_area"]["reason"]
    assert c["beds"]["verdict"] == "confirmed"


def test_unit_scan_never_compared_with_building_area():
    plan = make_home()
    scan = cl.scan_scope(plan, UNIT_RECORD)
    assert scan["scope"] == "unit"
    c = by_key(cmp.compare(plan, scan, cl.from_record(plan, UNIT_RECORD)))
    assert c["unit_area"]["verdict"] == "confirmed"
    assert c["gross_area"]["verdict"] == "cannot verify"  # building figure, unit scan, no aerial
    assert c["unit_beds"]["verdict"] == "confirmed"


def test_title_claims_and_scope():
    t = cl.parse_title("2BR, 1.5BA - 1,055SF")
    assert t == {"beds": 2, "baths": 1.5, "area": 1055}
    assert cl.parse_title("Studio - 500 SF")["beds"] == 0
    plan = make_home()
    plan["name"] = "Suite 200 - 690SF"
    assert cl.scan_scope(plan, INDUSTRIAL_RECORD | {"scope": "unknown"})["scope"] == "suite"


def test_zero_means_unknown():
    rec = copy.deepcopy(HOME_RECORD)
    rec["claims"]["stories"]["value"] = 0
    assert "stories" not in {c["key"] for c in cl.from_record(make_home(), rec)}


def test_industrial_aerial_and_lower_bound_counts():
    plan = make_home()
    scan = cl.scan_scope(plan, INDUSTRIAL_RECORD)
    claims = cl.from_record(plan, INDUSTRIAL_RECORD)
    ev = {"site": site(roof_height=5.0, footprint_area=65.0, structures=1), "stories": 3,
          "docks": {"count": 7}, "ortho_media": [{"kind": "ortho", "ref": "aerial/ortho?x", "box": None}]}
    c = by_key(cmp.compare(plan, scan, claims, ev))
    assert c["stories"]["verdict"] == "contradicted" and "too low" in c["stories"]["reason"]
    assert c["gross_area"]["verdict"] == "confirmed"  # whole-building scan: measured interior against GBA
    assert c["ceiling_height"]["verdict"] == "cannot verify"  # 24 ft is past the camera's reach
    assert c["dock_doors"]["verdict"] == "contradicted"  # more doors than the record
    ev["docks"]["count"] = 1
    assert by_key(cmp.compare(plan, scan, claims, ev))["dock_doors"]["verdict"] == "cannot verify"  # lower bound
    assert c["construction_material"]["verdict"] == "context"


def test_unlisted_pool_and_feature_seen_in_panorama():
    plan = make_home()
    scan = cl.scan_scope(plan, HOME_RECORD)
    det = {"label": "fireplace", "room": "L", "finding": {
        "detail": "brick fireplace on the east wall", "anchor": {"sid": "home1", "pano": "pL", "yaw_deg": 10, "pitch_deg": -5},
        "media": [{"kind": "pano", "ref": "home1/pL/2", "box": [0.1, 0.2, 0.3, 0.4]}],
        "source": {"layer": "model", "method": "vision", "confidence": "high", "note": "test"}}}
    ev = {"site": site(pool=True, pool_area=30.0) | {"lat": 34.0, "lon": -118.3}, "objects": [det], "objects_rooms": ["L"]}
    c = by_key(cmp.compare(plan, scan, cl.from_record(plan, HOME_RECORD), ev))
    assert c["fireplace"]["verdict"] == "confirmed" and c["fireplace"]["media"][0]["ref"] == "home1/pL/2"
    assert c["pool"]["verdict"] == "contradicted" and c["pool"]["claim"]["value"] is False


def test_tool_result_shape(records):
    ctx = ToolContext(plans=lambda sid: make_home())
    r = run_tool("record_vs_reality", {"scan": "home1"}, ctx)
    assert r.verdict.status in ("fail", "warn")
    assert {c.id for c in r.checks} >= {"beds", "baths", "living_area"}
    area = next(c for c in r.checks if c.id == "living_area")
    assert area.threshold == 720 and area.measured == 687 and area.standard.startswith("residential-listings")
    f = next(f for f in r.findings if f.id == "record_vs_reality:home1:living_area")
    assert "confirmed" in f.title and "686" not in f.title  # numbers stay out of titles
    assert any(o.kind == "rule" for o in r.overlays)
    assert any(a.id == "deep" for a in r.actions)


def test_unlabelled_room_named_from_panorama_leaves_living_area():
    plan = make_home()
    deck = next(r for r in plan["rooms"] if r["id"] == "B2")
    deck["label"] = None  # a 12 m2 walled room Matterport did not name
    fa = ms.floor_area(plan, {"B2": "Patio"})
    assert "B2" in {x["room"] for x in fa["excluded"]} and round(fa["m2"], 1) == 51.8
    assert "named from its panorama" in next(x["why"] for x in fa["excluded"] if x["room"] == "B2")


def test_condo_stories_are_the_buildings():
    rec = copy.deepcopy(HOME_RECORD)
    rec["residential_listing"]["property"]["address"]["unitNumber"] = "108"
    rec["claims"]["stories"]["value"] = 4
    c = by_key(audit(make_home(), rec)["comparisons"])["stories"]
    assert c["verdict"] == "cannot verify" and "building" in c["reason"]


def test_merged_rooms_make_room_counts_unverifiable():
    plan = make_home()
    next(r for r in plan["rooms"] if r["id"] == "L")["label"] = "Bathroom"  # a 30 m2 "bathroom"
    c = by_key(audit(plan, HOME_RECORD)["comparisons"])
    assert c["beds"]["verdict"] == "cannot verify" and "merged" in c["beds"]["reason"]
    assert c["baths"]["verdict"] == "cannot verify"
