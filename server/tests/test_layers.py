"""The layer catalogue: paging through an ArcGIS service, the tile grid, and what each layer is served as. No network."""
from threshold.layers import catalog


class _Answer:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def test_paging_steps_by_what_arrived(monkeypatch):
    """A service that sends 500 at a time when asked for 2000 must still be read to its end, with nothing skipped."""
    total, asked = 1234, []

    def fake(method, url, params=None, **kw):
        start = params["resultOffset"]
        asked.append(start)
        rows = list(range(start, min(total, start + 500)))
        return _Answer({"features": [{"id": i} for i in rows], "properties": {"exceededTransferLimit": start + 500 < total}})

    monkeypatch.setattr(catalog, "send", fake)
    feats, cut = catalog.arcgis("https://example.test/rest/services/X/FeatureServer/0/query", (0, 0, 1, 1))
    assert [f["id"] for f in feats] == list(range(total)) and not cut
    assert asked == [0, 500, 1000]


def test_a_tile_covers_its_own_box_and_names_its_city():
    w, s, e, n = catalog.tile_box(13, 1925, 3386)
    assert w < -95.37 < e and s < 29.76 < n  # downtown Houston
    assert catalog.city_of((w, s, e, n)) == "hou"
    assert catalog.city_of(catalog.tile_box(13, 0, 0)) is None  # nothing is fetched for a tile in the Arctic


def test_every_layer_says_where_it_comes_from_and_how_far_to_trust_it():
    for layer in catalog.LAYERS:
        assert layer.source and layer.note and layer.confidence in ("high", "medium", "low"), layer.id
        assert layer.scope in ("city", "grid", "client", "tiles"), layer.id
        if layer.scope == "grid":
            assert layer.grid_z and (layer.id in catalog.ARCGIS or layer.id in catalog.FETCH), layer.id
    assert [l.id for l in catalog.LAYERS if l.on] == ["scans"]  # everything else starts off


def test_a_source_module_adds_a_layer_with_its_own_fetcher(monkeypatch, tmp_path):
    """What layers/sources/ promises: an entry and a fetcher are enough for the catalogue and for the GeoJSON."""
    extra = catalog.Layer("demo_noise", "Road noise", "Hazards", "area", "city", "A source", "https://example.test", "low",
                          "A made-up layer for this test.", extra={"hue": "--tool-3", "legend": {"title": "Noise", "unit": "dB", "stops": [[0, "50"], [5, "75"]]}})
    feature = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-95.37, 29.76]}, "properties": {"name": "x", "level": 3}}
    monkeypatch.setattr(catalog, "LAYERS", (*catalog.LAYERS, extra))
    monkeypatch.setitem(catalog.BY_ID, extra.id, extra)
    monkeypatch.setitem(catalog.FETCH, extra.id, lambda box, city: ([feature], False))
    monkeypatch.setattr(catalog, "DIR", tmp_path)
    import json
    body = json.loads(catalog.city_geojson("demo_noise", "hou"))
    assert body["features"] == [feature] and body["meta"]["count"] == 1
    row = next(r for r in catalog.catalogue("hou") if r["id"] == "demo_noise")
    assert row["hue"] == "--tool-3" and row["legend"]["unit"] == "dB" and row["fetched"]
    groups = [r["group"] for r in catalog.catalogue("hou")]
    assert groups == sorted(groups, key=catalog.GROUPS.index)  # the list comes out in the order of the sections
