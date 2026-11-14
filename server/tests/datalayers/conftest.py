import pytest


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """No network and an empty cache: every upstream call fails loudly, lookups cache into a temp folder."""
    from threshold.layers import lookup

    def refuse(*a, **k):
        raise AssertionError(f"network call in a test: {a[:2]}")
    monkeypatch.setattr(lookup, "send", refuse)
    monkeypatch.setattr(lookup, "LOOKUP", tmp_path / "lookup")
    return monkeypatch


def fake_site(lon, lat, address=None):
    from threshold.tools import Site
    from threshold.tools.registry import ToolContext
    return ToolContext(sites=lambda place: Site(place, lat, lon, address=address, located_by="test point"))


def by_url(table: dict):
    """A stand-in for lookup.arcgis_at: the rows of the first table key found in the url."""
    def at(url, lon, lat, fields="*", **kw):
        return next((rows for key, rows in table.items() if key in url), [])
    return at


def row(**props):
    return {"properties": props, "geometry": None}
