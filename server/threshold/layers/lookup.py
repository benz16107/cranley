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

from ..sources.upstream import one_flight, send, write_atomic
from .catalog import AGENT, DIR

LOOKUP = DIR / "_lookup"
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
              where: str = "1=1", limit: int = 200, ttl_s: float = WEEK) -> list[dict]:
    """Features of one ArcGIS layer that touch a point (or lie within `radius_m` of it), as GeoJSON-like dicts:
    `{"properties": {...}, "geometry": {...} | None}`."""
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
