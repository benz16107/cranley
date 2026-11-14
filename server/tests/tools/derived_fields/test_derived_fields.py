"""derived_fields: proposed fields with method, confidence and what the record already holds."""
from tests.tools.truth_fixtures import HOME_RECORD, make_home, site
from threshold.tools import ToolContext, run_tool
from threshold.tools.derived_fields import _agree, propose


def test_propose_from_plan_and_aerial():
    ev = {"site": site(roof_height=6.0, roof_shape="gable", roof_material="shingle", footprint_area=80.0, pool=False)
          | {"lat": 34.0, "lon": -118.3}}
    props = {p["field"]: p for p in propose(make_home(), HOME_RECORD, ev)}
    assert props["measured_interior_area"]["value"] == 687 and props["measured_interior_area"]["record"] == 720
    assert props["bedrooms"]["record"] == 2 and _agree(props["bedrooms"]) == "same"
    assert props["area.Garage"]["value"] == round(36 * 10.7639)
    assert props["walk_in_closets"]["value"] == 1 and props["windows"]["value"] == 2
    assert props["roof_material"]["value"] == "shingle" and props["pool"]["value"] is False
    assert props["stories_estimate"]["value"] == 1  # 6 m less 2 m of pitched roof over 3 m a storey
    assert _agree(props["stories_estimate"]) == "differs"  # the record says 2
    assert "Garage" in props["amenities"]["value"] and "Walk-in closet" in props["amenities"]["value"]


def test_tool_without_aerial(records):
    r = run_tool("derived_fields", {"scan": "home1", "aerial": False}, ToolContext(plans=lambda sid: make_home()))
    ids = {c.id for c in r.checks}
    assert "measured_interior_area" in ids and "building_height" not in ids
    assert any(m.id == "area.Living Room" for m in r.metrics)
    assert r.verdict.status == "warn" and "floors scanned" in r.verdict.text  # one floor; the record says 2 stories
