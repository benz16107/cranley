"""Hand-made aerial answers for the site tool tests: no network, no sponsor data. A site is a square building on a
square parcel near (29.7, -95.4); everything is built from those numbers."""
from __future__ import annotations

import io
import math

import pytest
from PIL import Image

LAT, LON = 29.7, -95.4
KX, KY = 111320.0 * math.cos(math.radians(LAT)), 110574.0


def ll(e: float, n: float) -> tuple[float, float]:
    """(lon, lat) of a point e metres east and n metres north of the site."""
    return LON + e / KX, LAT + n / KY


def square_wkt(cx: float, cy: float, w: float, h: float | None = None) -> str:
    h = h or w
    pts = [ll(cx - w / 2, cy - h / 2), ll(cx + w / 2, cy - h / 2), ll(cx + w / 2, cy + h / 2), ll(cx - w / 2, cy + h / 2)]
    return "POLYGON((" + ",".join(f"{x} {y}" for x, y in pts + pts[:1]) + "))"


def square_geojson(cx: float, cy: float, w: float) -> dict:
    pts = [ll(cx - w / 2, cy - w / 2), ll(cx + w / 2, cy - w / 2), ll(cx + w / 2, cy + w / 2), ll(cx - w / 2, cy + w / 2)]
    return {"type": "Polygon", "coordinates": [[list(p) for p in pts + pts[:1]]]}


SRC = {"layer": "vexcel", "method": "lookup", "confidence": "medium", "note": "test"}


def facts(values: dict, footprint_m: float = 40, parcel_m: float = 120) -> dict:
    return {"lat": LAT, "lon": LON, "footprint": square_wkt(0, 0, footprint_m), "parcel": square_geojson(0, 0, parcel_m),
            "capture": {"date": "2026-01-01", "collection": "test", "gsd_m": 0.075},
            "facts": [{"id": k, "label": k, "value": v, "unit": None, "source": SRC} for k, v in values.items()]}


class FakeOrtho:
    """A north-up image `size_m` across: grey pavement everywhere except a green band north of `green_from_n`."""

    def __init__(self, lat, lon, size_m, px=256, green_from_n: float = 1e9):
        self.width = self.height = px
        h = size_m / 2
        w0, s0 = LON + (-h) / KX, LAT + (-h) / KY
        e0, n0 = LON + h / KX, LAT + h / KY
        self.bounds = (w0, s0, e0, n0)
        im = Image.new("RGB", (px, px), (150, 150, 150))
        for y in range(px):
            n = h - (y + 0.5) * size_m / px
            if n > green_from_n:
                for x in range(px):
                    im.putpixel((x, y), (60, 120, 50))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        self.image = buf.getvalue()
        self.meta = {}

    def to_px(self, lon, lat):
        w, s, e, n = self.bounds
        return (lon - w) / (e - w) * self.width, (n - lat) / (n - s) * self.height

    def to_lonlat(self, px, py):
        w, s, e, n = self.bounds
        return w + px / self.width * (e - w), n - py / self.height * (n - s)

    @property
    def metres_per_px(self):
        return (self.bounds[2] - self.bounds[0]) * KX / self.width


@pytest.fixture
def offline(monkeypatch):
    """No index, no CoStar, no network: each test then patches the engines it needs."""
    from threshold.sources import index
    from threshold.tools import _site
    monkeypatch.setattr(index, "rows", dict)
    monkeypatch.setattr(_site, "property_record", lambda pid: None)

    def boom(*a, **k):
        raise AssertionError("network call in a unit test")
    from threshold.aerial import detect, site, vexcel
    monkeypatch.setattr(vexcel, "call", boom)
    monkeypatch.setattr(detect, "detect", boom)
    monkeypatch.setattr(site, "obliques", boom)
    return monkeypatch
