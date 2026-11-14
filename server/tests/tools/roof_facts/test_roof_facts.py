from _site.fakes import facts, offline  # noqa: F401

from threshold.aerial import site
from threshold.tools import run_tool


def test_serious_defect_fails_and_shares_are_kept(offline):  # noqa: F811
    offline.setattr(site, "site_facts", lambda lat, lon: facts({
        "roof_material": "shingle", "roof_shape": "gable", "footprint_area": 200.0, "roof_height": 6.2,
        "roof_defects": ["tarp", "discoloration", "water-pooling"], "roof_defect_tarp": 4.5,
        "roof_defect_water_pooling": 12.0, "roof_defect_discoloration": 12.0, "roof_tree_cover": 40.0, "solar": False}))
    r = run_tool("roof_facts", {"lat": 29.7, "lon": -95.4})
    assert r.verdict.status == "fail" and "tarp" in r.verdict.text
    checks = {c.id: c for c in r.checks}
    assert checks["defect.tarp"].measured == 4.5 and checks["defect.tarp"].status == "fail"
    assert "defect.discoloration" not in checks  # the subtype replaces its parent
    assert checks["tree_cover"].status == "warn"
    assert {m.id for m in r.metrics} >= {"roof_height", "footprint_area"}
    assert all(f.anchor.geo for f in r.findings)  # no scan: every anchor is geographic


def test_no_building_is_unknown(offline):  # noqa: F811
    offline.setattr(site, "site_facts", lambda lat, lon: {"lat": lat, "lon": lon, "facts": [], "footprint": None,
                                                          "parcel": None, "capture": None})
    assert run_tool("roof_facts", {"lat": 29.7, "lon": -95.4}).verdict.status == "unknown"
