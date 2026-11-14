"""zoning_check: zone strings read into class and height district, a stated use judged against the class's list, and
Houston's no-zoning answer. No network."""
from tests.datalayers.conftest import by_url, fake_site, offline, row  # noqa: F401
from threshold.layers import lookup
from threshold.tools import run_tool
from threshold.tools.zoning_check import judge_use, parse_zone, use_key


def test_parse_zone():
    z = parse_zone("[Q]C2-1VL-O")
    assert (z["conditions"], z["class"], z["height_district"], z["suffixes"]) == (["Q"], "C2", "1VL", ["O"])
    assert parse_zone("(T)(Q)R3-1")["conditions"] == ["T", "Q"]
    assert parse_zone("[LF1-WH1-5][P2-FA][CPIO]")["chapter_1a"]


def test_uses():
    assert use_key("open a little cafe") == "restaurant" and use_key("a duplex") == "apartments" and use_key("daycare") == "daycare"
    assert use_key("something odd") is None
    assert judge_use("restaurant", "C2")[0] == "pass" and judge_use("restaurant", "R1")[0] == "fail"
    assert judge_use("daycare", "R1")[0] == "warn" and judge_use("industry", "M2")[0] == "pass"


def test_la_lot_with_a_height_district(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({"MapServer/1102": [row(ZONE_CMPLT="C2-1VL")],
                                                 "MapServer/1202": [row(**{"POLYS.DESCRIPTION": "General Commercial"})]}))
    r = run_tool("zoning_check", {"place": {"geo": [-118.3, 34.06]}, "use": "a cafe"}, fake_site(-118.3, 34.06))
    m = {x.id: x.value for x in r.metrics}
    assert m == {"far": 1.5, "height_ft": 45, "stories": 3}  # LAMC 12.21.1: 1VL, and FAR 1.5 in a C zone of district 1
    assert r.verdict.status == "pass" and r.checks[0].status == "pass"


def test_outside_the_city_of_la(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({}))
    r = run_tool("zoning_check", {"place": {"geo": [-118.38, 34.07]}}, fake_site(-118.38, 34.07))
    assert r.verdict.status == "unknown" and "outside the City of Los Angeles" in r.verdict.text


def test_houston_has_no_zoning_but_lot_size_rules(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({"MapServer/13": [row(LOTSIZE=5500, ORDINANCE="2006-1018", Status="Approved")]}))
    r = run_tool("zoning_check", {"place": {"geo": [-95.4, 29.75]}, "use": "duplex"}, fake_site(-95.4, 29.75))
    assert "no zoning" in r.verdict.text and {x.id: x.value for x in r.metrics} == {"min_lot_sqft": 5500}
    assert r.checks[0].status == "unknown"  # a use in Houston rests on deed restrictions nobody maps
