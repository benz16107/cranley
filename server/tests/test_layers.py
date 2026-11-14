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


def test_a_live_layer_is_fetched_again_when_its_file_is_old_and_keeps_its_last_answer_if_the_source_is_down(tmp_path):
    import os
    import time
    f, calls = tmp_path / "live" / "hou.json", []

    def make():
        calls.append(1)
        return b"answer %d" % len(calls)

    assert catalog._cached(f, make, 600) == b"answer 1" and catalog._cached(f, make, 600) == b"answer 1"  # young: kept
    old = time.time() - 700
    os.utime(f, (old, old))
    assert catalog._cached(f, make, 600) == b"answer 2"  # past its lifetime: made again
    assert catalog._cached(f, make) == b"answer 2" and len(calls) == 2  # no lifetime: a file is kept for good
    os.utime(f, (old, old))

    def down():
        raise OSError("the source is down")

    assert catalog._cached(f, down, 600) == b"answer 2"  # old, and the source fails: the last answer stands


def test_importing_a_source_first_still_gives_the_whole_catalogue():
    """`threshold.layers.sources` imported before the catalogue must not leave the catalogue without its layers."""
    import subprocess
    import sys
    code = ("import threshold.layers.sources as s; from threshold.layers import catalog; "
            "ids = {l.id for l in catalog.LAYERS}; assert all(l.id in ids for l in s.MORE), 'layers missing'; "
            "assert set(s.FETCH) <= set(catalog.FETCH); print(len(catalog.LAYERS), len(s.MORE))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-400:]
