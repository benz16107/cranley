from tests.tools._site.fakes import LAT, LON, facts, offline  # noqa: F401

from threshold.aerial import site
from threshold.tools import run_tool


def test_low_ground_and_tarp(offline, tmp_path):  # noqa: F811
    import threshold.api.site_media as sm
    import threshold.tools.risk_sheet as rs
    offline.setattr(sm, "SHEETS", tmp_path)
    offline.setattr(site, "site_facts", lambda lat, lon: facts({
        "roof_material": "shingle", "roof_shape": "hip", "footprint_area": 180.0, "roof_defects": ["tarp"],
        "roof_defect_tarp": 3.0, "pool": True, "pool_in_ground_enclosed": 0, "roof_tree_cover": 5.0}))
    # the building sits 0.8 m below everything around it
    offline.setattr(rs, "heights", lambda kind, pts: [9.2] + [10.0] * (len(pts) - 1))
    r = run_tool("risk_sheet", {"lat": LAT, "lon": LON})
    c = {x.id: x for x in r.checks}
    assert c["flood_position"].measured == -0.8 and c["flood_position"].status == "warn"
    assert r.verdict.status == "fail" and "roof" in r.verdict.text.lower()
    sheet = r.findings[0].detail
    html = (tmp_path / sheet.rsplit("/", 1)[1]).read_text()
    assert "Flood position" in html and "<script" not in html
