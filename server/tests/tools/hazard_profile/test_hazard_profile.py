"""hazard_profile: each map's answer becomes one row; a source that fails becomes 'unknown', not an error. No network."""
import json

from tests.datalayers.conftest import by_url, fake_site, offline, row  # noqa: F401
from threshold.layers import catalog, lookup
from threshold.tools import run_tool


def test_la_fault_zone_and_a_failed_source(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({"Alquist_Priolo_Fault_Zones": [row(QUAD_NAME="Beverly Hills")],
                                                 "FHSZSRA": [row(FHSZ_Description="Very High", FHSZ=3)]}))
    offline.setattr(lookup, "pixel", lambda *a, **k: (255, 0, 0, 255))
    offline.setattr(lookup, "legend", lambda url: [("60.0 - 69.9", (255, 0, 0))])
    offline.setattr(lookup, "cached", lambda key, make, ttl_s=0: {"value": "NoData", "features": []})
    empty = json.dumps({"type": "FeatureCollection", "features": []}).encode()
    offline.setattr(catalog, "city_geojson", lambda layer, city: empty if layer != "wildfires" else (_ for _ in ()).throw(OSError("down")))
    r = run_tool("hazard_profile", {"place": {"geo": [-118.4, 34.07]}}, fake_site(-118.4, 34.07))
    st = {c.id: c.status for c in r.checks}
    assert st["fault"] == "fail" and st["fire"] == "fail" and st["noise"] == "warn" and st["flood"] == "pass"
    assert st["liquefaction"] == "pass" and st["wildfires"] == "unknown" and st["sea"] == "fail"  # every tile pixel is red here
    assert r.verdict.status == "fail" and "not read" in r.verdict.text
    assert [c.status for c in r.checks][:1] == ["fail"]  # worst first
