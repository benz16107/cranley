"""OpenStreetMap around a site, from the public Overpass API: street names, driveways and service roads, gates,
and posted height limits. Vexcel names no streets, so arrival directions need this.

Each answer is cached on disk under $THRESHOLD_DATA_DIR/cache/osm/ and requests are at least 1.5 s apart, as the
public Overpass servers ask. OSM data is ODbL; it stays in the cache and is cited in each source note.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time

import httpx

from ...config import CACHE

URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter")  # the main server returns 502s under load; mirrors next
AGENT = "threshold-hackprinceton/0.1 (site tools; contact benz16107@gmail.com)"
GAP_S = 1.5
TRUCK_HEIGHT_M = 4.11  # 13 ft 6 in, the usual US limit for a van trailer
_lock = threading.Lock()
_last = [0.0]
NOTE = "OpenStreetMap contributors (ODbL), via Overpass"


def _query(q: str) -> dict:
    f = CACHE / "osm" / f"{hashlib.sha256(q.encode()).hexdigest()[:24]}.json"
    if f.exists():
        return json.loads(f.read_text())
    err = None
    for url in URLS:
        for attempt in range(2):
            with _lock:
                wait = _last[0] + GAP_S * (1 + 2 * attempt) - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                _last[0] = time.monotonic()
            try:
                r = httpx.post(url, data={"data": q}, headers={"User-Agent": AGENT}, timeout=90)
                r.raise_for_status()
                r.json()
                break
            except (httpx.HTTPError, ValueError) as e:
                err, r = e, None
        if r is not None:
            break
    if r is None:
        raise RuntimeError(f"Overpass unavailable: {err}")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(r.content)
    return r.json()


def parse_height(v: str | None) -> float | None:
    """A maxheight tag in metres: "4.1", "13'6\"", "12 ft", "4.2 m". None for "default", "none" and the like;
    "below_default" means lower than the legal limit, returned as 0."""
    if not v:
        return None
    v = v.strip().lower()
    if v == "below_default":
        return 0.0
    m = re.fullmatch(r"(\d+)\s*'\s*(?:(\d+(?:\.\d+)?)\s*\"?)?", v) or re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:ft|feet)", v)
    if m:
        return round(float(m.group(1)) * 0.3048 + float((m.groups() + (None,))[1] or 0) * 0.0254, 2)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*m?", v)
    return float(m.group(1)) if m else None


DRIVABLE = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service",
            "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link", "living_street"}


def around(lat: float, lon: float, streets_m: int = 250, limits_m: int = 1500) -> dict:
    """{streets, service, gates, low_limits, no_trucks} near the point; ways carry `points` as [(lon, lat)]."""
    q = (f"[out:json][timeout:40];("
         f"way(around:{streets_m},{lat},{lon})[highway];"
         f"node(around:{streets_m},{lat},{lon})[barrier];"
         f"way(around:{streets_m},{lat},{lon})[barrier~\"gate|lift_gate|fence|wall\"];"
         f"way(around:{limits_m},{lat},{lon})[highway][maxheight];"
         f"node(around:{limits_m},{lat},{lon})[maxheight];"
         f"way(around:{limits_m},{lat},{lon})[highway][hgv=no];"
         f");out geom tags;")
    els = _query(q).get("elements") or []
    streets, service, gates, low, no_trucks = [], [], [], [], []
    for e in els:
        t = e.get("tags") or {}
        pts = [(g["lon"], g["lat"]) for g in e.get("geometry") or []] if e["type"] == "way" else [(e["lon"], e["lat"])]
        item = {"id": f"{e['type']}/{e['id']}", "tags": t, "points": pts}
        hw = t.get("highway")
        if e["type"] == "way" and hw in DRIVABLE:
            (service if hw == "service" else streets).append(item)
        if t.get("barrier") in ("gate", "lift_gate", "swing_gate", "sliding_gate"):
            gates.append(item)
        h = parse_height(t.get("maxheight"))
        drive_through = t.get("service") == "drive-through" or t.get("tunnel") == "building_passage"
        if h is not None and h < TRUCK_HEIGHT_M and not drive_through and (hw in DRIVABLE or t.get("barrier") or t.get("railway")):
            low.append({**item, "maxheight_m": h, "raw": t.get("maxheight")})
        if t.get("hgv") == "no" and hw in DRIVABLE:
            no_trucks.append(item)
    return {"streets": streets, "service": service, "gates": gates, "low_limits": low, "no_trucks": no_trucks,
            "source": NOTE}
