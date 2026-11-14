"""area_profile on a hand-made tract and county: numbers come from the rows, words from the comparison. No network."""
from tests.datalayers.conftest import by_url, fake_site, offline, row  # noqa: F401
from threshold.layers import lookup
from threshold.tools import run_tool

TRACT = row(GEOID="48201310100", NAME="Census Tract 3101", County="Harris County", ALAND=1_000_000, B01001_001E=4000,
            B01001_001M=400, B19049_001E=95000, B19049_001M=9000, B01002_001E=41.0, B01001_calc_pctLT18E=20.0,
            B01001_calc_pctGE65E=15.0, B25003_001E=1600, B25003_003E=400, B25058_001E=1400, B25077_001E=350000)
COUNTY = row(NAME="Harris County", ALAND=4_400_000_000, B01001_001E=4_800_000, B19049_001E=70000, B01002_001E=34.0,
             B25003_001E=1_700_000, B25003_003E=760_000)


def test_profile_compares_the_tract_with_its_county(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({"FeatureServer/2": [TRACT], "FeatureServer/1": [COUNTY]}))
    offline.setattr(lookup, "service_date", lambda url: "2026-01-10")
    r = run_tool("area_profile", {"place": {"geo": [-95.4, 29.7]}}, fake_site(-95.4, 29.7))
    m = {x.id: x.value for x in r.metrics}
    assert m["population"] == 4000 and m["density"] == 4000 and m["income"] == 95000 and m["county.income"] == 70000
    assert m["renters"] == 25.0
    titles = {f.title for f in r.findings}
    assert {"Higher income than the county", "Older than the county", "Fewer renters than the county"} <= titles
    assert "Census Tract 3101" in r.verdict.text and "$" not in r.verdict.text  # measurements stay out of the verdict


def test_no_tract_is_not_applicable(offline):  # noqa: F811
    offline.setattr(lookup, "arcgis_at", by_url({}))
    r = run_tool("area_profile", {"place": {"geo": [-95.4, 29.7]}}, fake_site(-95.4, 29.7))
    assert r.verdict.status == "unknown" and "tract" in r.verdict.text
