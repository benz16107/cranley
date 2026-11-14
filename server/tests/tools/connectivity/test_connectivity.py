"""connectivity: broadband, transit, bikeway and traffic from hand-made rows. No network."""
from tests.datalayers.conftest import by_url, fake_site, offline, row  # noqa: F401
from threshold.layers import lookup
from threshold.tools import run_tool

LON, LAT = -95.37, 29.76


def pt(dx_m, **props):
    return {"properties": props, "geometry": {"type": "Point", "coordinates": [LON + dx_m / 96700, LAT]}}


def test_connected_place(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({
        "FeatureServer/3": [row(TotalBSLs=200, ServedBSLs=196, UniqueProviders=8, UniqueProvidersFiber=2, UniqueProvidersCable=1)],
        "Stops": [pt(150, stop_name="Main @ 1st", stop_type_text="Bus"), pt(600, stop_name="Rail Stn", stop_type_text="Light rail")],
        "Transportation/MapServer/7": [{"properties": {"Full_Name": "LAMAR ST", "HC_Class": "Protected"},
                                        "geometry": {"type": "LineString", "coordinates": [[LON + 0.003, LAT - 1], [LON + 0.003, LAT + 1]]}}],
        "TxDOT": [pt(100, AADT_RPT_QTY=60000, AADT_RPT_YEAR=2025, ON_ROAD="IH0045")]}))
    r = run_tool("connectivity", {"place": {"geo": [LON, LAT]}}, fake_site(LON, LAT))
    m = {x.id: x.value for x in r.metrics}
    assert m["served_pct"] == 98.0 and m["fiber_providers"] == 2 and m["stops_400m"] == 1 and m["stops_walk"] == 2
    assert 140 <= m["nearest_stop_m"] <= 160 and 280 <= m["bikeway_m"] <= 300 and m["aadt"] == 60000
    assert {c.id: c.status for c in r.checks} == {"broadband": "pass", "transit": "pass", "bike": "pass"}
    assert r.verdict.status == "pass"


def test_nothing_nearby(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({}))
    r = run_tool("connectivity", {"place": {"geo": [LON, LAT]}}, fake_site(LON, LAT))
    assert {c.id: c.status for c in r.checks} == {"broadband": "unknown", "transit": "fail", "bike": "unknown"}
