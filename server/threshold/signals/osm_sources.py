"""Transport noise sources near a point from OpenStreetMap: highways, major roads, railways and airports.

One Overpass query per point, cached on disk under $THRESHOLD_DATA_DIR/cache/osm_noise/, 1.5 s between requests,
public mirrors tried in turn. OSM data is ODbL and stays in the cache.
shortcut: the pets thread's `nearby/` OSM engine was not on main when this was written; switch to it once it is.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time

import httpx
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from ..config import CACHE

URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter")
AGENT = "threshold-hackprinceton/0.1 (noise sources)"
NOTE = "OpenStreetMap contributors (ODbL), via Overpass"
GAP_S = 1.5
_lock = threading.Lock()
_last = [0.0]


def _query(q: str) -> dict:
    f = CACHE / "osm_noise" / f"{hashlib.sha256(q.encode()).hexdigest()[:24]}.json"
    if f.exists():
        return json.loads(f.read_text())
    err = None
    for url in URLS:
        with _lock:
            wait = _last[0] + GAP_S - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.monotonic()
        try:
            r = httpx.post(url, data={"data": q}, headers={"User-Agent": AGENT}, timeout=90)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            err = e
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(r.content)
        return data
    raise RuntimeError(f"Overpass unavailable: {err}")

KINDS = {  # kind: (Overpass filter, search radius m)
    "highway": ('way["highway"~"^(motorway|trunk)$"]', 2000),
    "major_road": ('way["highway"~"^(primary|secondary)$"]', 800),
    "rail": ('way["railway"~"^(rail|light_rail)$"]["service"!~"."]', 1500),
    "airport": ('nwr["aeroway"="aerodrome"]["iata"]', 15000),
}
LABEL = {"highway": "highway", "major_road": "major road", "rail": "railway", "airport": "airport"}


def _local(lat0: float, lon0: float, lat: float, lon: float) -> tuple[float, float]:
    return (lon - lon0) * 111320.0 * math.cos(math.radians(lat0)), (lat - lat0) * 110574.0


def nearest(lat: float, lon: float) -> dict[str, dict | None]:
    """Per kind, the nearest feature: {name, distance_m, bearing_deg (clockwise from north), lat, lon}."""
    q = "[out:json][timeout:60];(" + "".join(f"{f}(around:{r},{lat},{lon});" for f, r in KINDS.values()) + ");out geom tags;"
    els = _query(q).get("elements") or []
    out: dict[str, dict | None] = {k: None for k in KINDS}
    for e in els:
        t = e.get("tags") or {}
        kind = ("airport" if t.get("aeroway") == "aerodrome" else "rail" if t.get("railway") else
                "highway" if t.get("highway") in ("motorway", "trunk") else "major_road")
        if e["type"] == "node":
            pts = [(e["lat"], e["lon"])]
        else:
            pts = [(g["lat"], g["lon"]) for g in e.get("geometry") or [] if g]
        if not pts:
            continue
        xy = [_local(lat, lon, a, b) for a, b in pts]
        if kind == "airport" and len(xy) > 2:  # an aerodrome outline: its nearest edge is where the runways start
            geom = LineString(xy + xy[:1])
        else:
            geom = LineString(xy) if len(xy) > 1 else Point(xy[0])
        d = geom.distance(Point(0, 0))
        if out[kind] is not None and out[kind]["distance_m"] <= d:
            continue
        p = nearest_points(geom, Point(0, 0))[0]
        out[kind] = {"kind": kind, "name": t.get("name") or t.get("ref") or LABEL[kind], "ref": t.get("ref"),
                     "distance_m": d, "bearing_deg": math.degrees(math.atan2(p.x, p.y)) % 360 if d > 0 else 0.0,
                     "lat": lat + p.y / 110574.0, "lon": lon + p.x / (111320.0 * math.cos(math.radians(lat))),
                     "osm": f"{e['type']}/{e['id']}"}
    return out

