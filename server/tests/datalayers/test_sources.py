"""The data layers added under threshold/layers/sources: every entry is complete, every fetcher is reachable, and the
small helpers that turn a source's attributes into what the map draws behave. No network."""
import pytest

from threshold.layers import catalog, lookup
from threshold.layers.sources import FETCH, MORE, census, federal, los_angeles
from threshold.layers.sources._arcgis import layer


def test_the_catalogue_holds_the_source_modules_whichever_is_imported_first():
    assert len(MORE) >= 45 and set(l.id for l in MORE) <= set(catalog.BY_ID)


@pytest.mark.parametrize("L", MORE, ids=lambda l: l.id)
def test_every_layer_says_where_it_comes_from(L):
    assert L.source and L.note and L.confidence in ("high", "medium", "low")
    assert L.group in catalog.GROUPS, L.group
    assert L.scope in ("city", "grid", "tiles")
    assert L.licence or L.source_url
    if L.scope in ("city", "grid"):
        assert L.id in FETCH
    if L.scope == "grid":
        assert L.grid_z >= 12  # never a whole county in one tile
    if L.scope == "tiles":
        assert L.tiles.startswith("https://") and ("{z}" in L.tiles or "{bbox-epsg-3857}" in L.tiles)
    stops = (L.extra.get("legend") or {}).get("stops", [])
    assert len({lv for lv, _ in stops}) == len(stops)  # the legend keys its rows on the level
    for level, label in stops:
        assert 0 <= level <= 5 and label


def test_non_commercial_licences_are_named():
    assert "non-commercial" in catalog.BY_ID["sentinel2"].licence


def test_census_levels_and_bands():
    edges = [1000, 2500, 5000, 10000, 20000]
    assert [census.level(v, edges) for v in (0, 999, 1000, 7000, 25000)] == [0, 0, 1, 3, 5]
    assert census.bands([10, 20], lambda v: f"{v}")[0] == [0, "under 10"] and census.bands([10, 20], str)[-1] == [2, "20 or more"]
    assert census.density({"B01001_001E": 5000, "ALAND": 2_000_000}) == 2500
    assert census.renters({"B25003_001E": 200, "B25003_003E": 50}) == 25.0


def test_broadband_gap_and_aqi_words():
    assert federal.gap({"TotalBSLs": 200, "ServedBSLs": 190}) == 5.0
    assert federal.gap({"TotalBSLs": 0}) is None
    assert [federal.aqi_word(v) for v in (10, 75, 120, 180, 250, 400)] == [
        "Good", "Moderate", "Unhealthy for sensitive groups", "Unhealthy", "Very unhealthy", "Hazardous"]


def test_la_zone_groups():
    g = los_angeles.zone_group
    assert g("[Q]C2-1VL") == "Commercial" and g("R1-1") == "Residential" and g("(T)(Q)M2-1") == "Industrial"
    assert g("[LF1-WH1-5][P2-FA][CPIO]") == "Chapter 1A (new code)" and g("OS-1XL") == "Open space"


def test_an_arcgis_layer_keeps_name_detail_and_style_values(monkeypatch):
    from threshold.layers.sources import _arcgis
    got = {}

    def fake(url, box, fields, offset, where):
        got["url"] = url
        return [{"geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {"N": "Ada", "V": 7}},
                {"geometry": None, "properties": {"N": "dropped"}}], False
    monkeypatch.setattr(_arcgis, "arcgis", fake)
    L, fetch = layer("t", "Test", "Rules", "point", ["https://x/rest/services/A/MapServer/0"], name="N",
                     detail=lambda a: f"v{a['V']}", props=lambda a: {"level": 2}, source="s", source_url="u", confidence="high", note="n")
    feats, cut = fetch((0, 0, 1, 1), "hou")
    assert got["url"].endswith("/MapServer/0/query") and not cut
    assert feats == [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2]},
                      "properties": {"name": "Ada", "detail": "v7", "level": 2}}]


def test_legend_colours_and_tiles():
    sw = [("45.0 - 49.9", (255, 193, 7)), ("55.0 - 59.9", (255, 0, 0))]
    assert lookup.nearest_colour((250, 5, 3, 255), sw) == "55.0 - 59.9"
    assert lookup.nearest_colour((250, 5, 3, 0), sw) is None  # transparent: nothing drawn here
    assert lookup.nearest_colour((0, 255, 0, 255), sw) is None  # no swatch is close
    x, y, px, py = lookup.tile_xy(-95.37, 29.76, 12)
    assert (x, y) == (962, 1693)  # the parent of the catalogue test's downtown tile 13/1925/3386 and 0 <= px < 256 and 0 <= py < 256
