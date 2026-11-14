"""Point lookups against the public sources behind the map layers, for the agent's tools: what is at or near one
address. Every answer is kept on disk under `$THRESHOLD_DATA_DIR/cache/layers/_lookup/` (a week by default, less for
live data), so asking twice costs nothing upstream. Requests go through `sources.upstream.send`, which rate limits
the whole process.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import UTC, datetime

from ..config import CACHE
from ..sources.upstream import one_flight, send, write_atomic

# not from .catalog: the catalogue's source modules import this one while the catalogue is still loading
AGENT = {"User-Agent": "building-explorer/0.1"}
LOOKUP = CACHE / "layers" / "_lookup"
WEEK = 7 * 86400


def cached(key: str, make, ttl_s: float = WEEK):
    """`make()`'s JSON answer, from disk while younger than `ttl_s`."""
    f = LOOKUP / f"{hashlib.sha1(key.encode()).hexdigest()[:20]}.json"
    if f.exists() and time.time() - f.stat().st_mtime < ttl_s:
        return json.loads(f.read_text())
    with one_flight(str(f)):
        if f.exists() and time.time() - f.stat().st_mtime < ttl_s:
            return json.loads(f.read_text())
        out = make()
        write_atomic(f, json.dumps(out).encode())
        return out


def arcgis_at(url: str, lon: float, lat: float, fields: str = "*", radius_m: float = 0, geometry: bool = False,
              where: str = "1=1", limit: int = 200, ttl_s: float = WEEK, via_box: float = 0) -> list[dict]:
    """Features of one ArcGIS layer that touch a point (or lie within `radius_m` of it), as GeoJSON-like dicts:
    `{"properties": {...}, "geometry": {...} | None}`.

    `via_box` (metres) asks for an envelope that size round the point instead and keeps what contains the point, or
    else the nearest shape within that distance, with `distance_m`: some services (ZIMAS) answer point queries with
    nothing, and a geocoded address often lands on the street in front of the lot."""
    if via_box:
        return _via_box(url, lon, lat, fields, via_box, where, ttl_s)
    params = {"where": where, "geometry": f"{lon:.6f},{lat:.6f}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": fields,
              "returnGeometry": "true" if geometry else "false", "f": "geojson", "resultRecordCount": limit}
    if radius_m:
        params |= {"distance": radius_m, "units": "esriSRUnit_Meter"}

    def make():
        body = send("GET", url.rstrip("/") + "/query", params=params, headers=AGENT, timeout=60).json()
        if "error" in body:
            raise LookupError(f"{url.split('/rest/services/')[-1]}: {body['error'].get('message', 'error')}")
        return [{"properties": f.get("properties") or {}, "geometry": f.get("geometry")} for f in body.get("features") or []]
    return cached(f"arcgis|{url}|{json.dumps(params, sort_keys=True)}", make, ttl_s)


def _via_box(url, lon, lat, fields, pad_m, where, ttl_s):
    from shapely.geometry import Point, shape
    dy, dx = pad_m / 111320, pad_m / (111320 * math.cos(math.radians(lat)))
    params = {"where": where, "geometry": f"{lon - dx:.6f},{lat - dy:.6f},{lon + dx:.6f},{lat + dy:.6f}",
              "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
              "outFields": fields, "returnGeometry": "true", "f": "geojson", "resultRecordCount": 500}

    def make():
        body = send("GET", url.rstrip("/") + "/query", params=params, headers=AGENT, timeout=60).json()
        if "error" in body:
            raise LookupError(f"{url.split('/rest/services/')[-1]}: {body['error'].get('message', 'error')}")
        return [{"properties": f.get("properties") or {}, "geometry": f.get("geometry")} for f in body.get("features") or []]
    p, k = Point(lon, lat), 111320 * math.cos(math.radians(lat))
    rows = []
    for f in cached(f"arcgis-box|{url}|{json.dumps(params, sort_keys=True)}", make, ttl_s):
        if not f["geometry"]:
            continue
        g = shape(f["geometry"])
        rows.append({**f, "distance_m": 0.0 if g.contains(p) else round(g.distance(p) * k, 1)})
    rows.sort(key=lambda r: r["distance_m"])
    inside = [r for r in rows if r["distance_m"] == 0]
    return inside or rows[:1]


def socrata(domain: str, dataset: str, params: dict, ttl_s: float = 86400) -> list[dict]:
    """Rows of a Socrata dataset (no app token: the shared anonymous limit, so keep queries small)."""
    url = f"https://{domain}/resource/{dataset}.json"
    return cached(f"socrata|{url}|{json.dumps(params, sort_keys=True)}",
                  lambda: send("GET", url, params=params, headers=AGENT, timeout=60).json(), ttl_s)


def geocode(address: str) -> dict | None:
    """The US Census Bureau's address geocoder (keyless, public domain): `{lon, lat, matched}` or None."""
    def make():
        body = send("GET", "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress", headers=AGENT, timeout=60,
                    params={"address": address, "benchmark": "Public_AR_Current", "format": "json"}).json()
        m = (body.get("result") or {}).get("addressMatches") or []
        return {"lon": m[0]["coordinates"]["x"], "lat": m[0]["coordinates"]["y"], "matched": m[0]["matchedAddress"]} if m else None
    return cached(f"geocode|{address.lower().strip()}", make, 30 * 86400)


def metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    k = math.cos(math.radians((lat1 + lat2) / 2))
    return 6371000 * math.hypot(math.radians(lat2 - lat1), math.radians(lon2 - lon1) * k)


def city_at(lon: float, lat: float) -> str | None:
    from .catalog import CITIES
    return next((c for c, (w, s, e, n) in CITIES.items() if w <= lon <= e and s <= lat <= n), None)


def day(ms) -> str:
    """An ArcGIS date (milliseconds since 1970) as YYYY-MM-DD, or ''."""
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%d") if isinstance(ms, (int, float)) else ""


def service_date(url: str) -> str:
    """The day an ArcGIS layer's data was last edited, as the service reports it ('' when it does not say)."""
    def make():
        body = send("GET", url.rstrip("/"), params={"f": "json"}, headers=AGENT, timeout=60).json()
        return day((body.get("editingInfo") or {}).get("lastEditDate") or (body.get("editingInfo") or {}).get("dataLastEditDate"))
    return cached(f"service-date|{url}", make)


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int, float, float]:
    """The web-mercator tile holding a point, and the point's pixel inside that 256-pixel tile."""
    n = 2 ** z
    fx = (lon + 180) / 360 * n
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(fx), int(fy), (fx % 1) * 256, (fy % 1) * 256


def pixel(template: str, lon: float, lat: float, z: int, ttl_s: float = 30 * 86400) -> tuple[int, int, int, int] | None:
    """The colour a raster tile service draws at a point (RGBA), or None where it has no tile. For hazard maps that
    are published only as pictures; the caller maps the colour to the publisher's legend."""
    import io

    from PIL import Image
    x, y, px, py = tile_xy(lon, lat, z)
    url = template.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
    f = LOOKUP / "tiles" / f"{hashlib.sha1(url.encode()).hexdigest()[:20]}.png"
    if not (f.exists() and time.time() - f.stat().st_mtime < ttl_s):
        try:
            data = send("GET", url, headers=AGENT, timeout=60, retries=2).content
        except Exception as e:  # a tile service answers 404 where it has nothing to draw
            if "404" in str(e):
                write_atomic(f, b"")
                return None
            raise
        write_atomic(f, data)
    data = f.read_bytes()
    if not data:
        return None
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    return im.getpixel((min(255, int(px)), min(255, int(py))))


def legend(url: str) -> list[tuple[str, tuple[int, int, int]]]:
    """An ArcGIS map service's legend as (label, colour of the swatch's centre)."""
    import base64
    import io

    from PIL import Image

    def make():
        body = send("GET", url.rstrip("/") + "/legend", params={"f": "json"}, headers=AGENT, timeout=60).json()
        out = []
        for lyr in body.get("layers") or []:
            for e in lyr.get("legend") or []:
                if not e.get("imageData") or not e.get("label"):
                    continue
                im = Image.open(io.BytesIO(base64.b64decode(e["imageData"]))).convert("RGBA")
                r, g, b, a = im.getpixel((im.width // 2, im.height // 2))
                if a:
                    out.append([e["label"], [r, g, b]])
        return out
    return [(lbl, tuple(c)) for lbl, c in cached(f"legend|{url}", make, 30 * 86400)]


def nearest_colour(rgba, swatches: list[tuple[str, tuple[int, int, int]]], tolerance: float = 60) -> str | None:
    """The legend label whose swatch is closest to a pixel, if close enough; None for a transparent pixel."""
    if not rgba or rgba[3] < 32 or not swatches:
        return None
    best = min(swatches, key=lambda s: sum((a - b) ** 2 for a, b in zip(rgba[:3], s[1], strict=True)))
    return best[0] if math.dist(rgba[:3], best[1]) <= tolerance else None


def locate(ctx, place):
    """A place as the tools' resolver finds it; an address it cannot place is tried with the Census geocoder."""
    from ..tools import ToolError
    from ..tools.types import Place
    try:
        site = ctx.site(place)
    except ToolError:
        if not place.address:
            raise
        site = None
    if not place.address:
        return site
    # an address the resolver matched by words alone can be far off (a one-letter index address matches anything),
    # so the geocoder's point wins when the two disagree by more than a block
    g = geocode(place.address)
    if not g:
        if site:
            return site
        raise ToolError(f"The Census Bureau's geocoder could not place \"{place.address}\". Give a point (longitude, "
                        "latitude) instead.") from None
    if site and site.lat is not None and metres(site.lat, site.lon, g["lat"], g["lon"]) < 300:
        return site
    site = ctx.site(Place(geo=(g["lon"], g["lat"])))
    site.place, site.address = place, g["matched"].title()
    site.located_by = "US Census Bureau geocoder (street address ranges)"
    return site


# Last, once this module is whole: importing the catalogue loads every source module, and those import this one. A tool
# that reached the source modules before the catalogue would leave the catalogue without them.
from . import catalog  # noqa: F401
