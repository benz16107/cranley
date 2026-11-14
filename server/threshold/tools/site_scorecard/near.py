"""What is near a business site, from OpenStreetMap (through the cached, rate-limited `_site.osm` queue) and a short
list of cargo hubs: highway on-ramps, rail lines, power substations, transit stops, shops and restaurants.

Distances are straight lines. A road trip is longer; callers that turn a distance into a time say it is an estimate.
"""
from __future__ import annotations

import math

from .._site import osm

NOTE = osm.NOTE
# Cargo airports and container ports of the two kit cities. Points are approximate terminal centres (public maps).
HUBS = [
    ("airport", "George Bush Intercontinental (IAH)", 29.9902, -95.3368),
    ("airport", "William P. Hobby (HOU)", 29.6454, -95.2789),
    ("port", "Port Houston, Barbours Cut terminal", 29.6851, -95.0004),
    ("port", "Port Houston, Bayport terminal", 29.6106, -95.0181),
    ("airport", "Los Angeles International (LAX)", 33.9416, -118.4085),
    ("airport", "Ontario International (ONT)", 34.0560, -117.6012),
    ("airport", "Long Beach (LGB)", 33.8177, -118.1516),
    ("airport", "Hollywood Burbank (BUR)", 34.2007, -118.3587),
    ("port", "Port of Los Angeles", 33.7361, -118.2626),
    ("port", "Port of Long Beach", 33.7542, -118.2165),
]
HUB_NOTE = "Terminal centre points from public maps, straight-line distance"


def km(lat1, lon1, lat2, lon2) -> float:
    k = math.cos(math.radians((lat1 + lat2) / 2))
    return 6371 * math.hypot(math.radians(lat2 - lat1), math.radians(lon2 - lon1) * k)


def _nearest_pt(lat, lon, pts) -> float:
    return min(km(lat, lon, y, x) for x, y in pts)


def _pts(e) -> list[tuple[float, float]]:
    if e.get("geometry"):
        return [(g["lon"], g["lat"]) for g in e["geometry"] if g]
    if "lon" in e:
        return [(e["lon"], e["lat"])]
    c = e.get("center")
    return [(c["lon"], c["lat"])] if c else []


def _query_transport(lat: float, lon: float) -> list[dict]:
    q = (f"[out:json][timeout:60];("
         f"node(around:12000,{lat},{lon})[highway=motorway_junction];"
         f"node(around:3000,{lat},{lon})[power=substation];way(around:3000,{lat},{lon})[power=substation];"
         f"way(around:2500,{lat},{lon})[railway=rail][!service];"
         f"node(around:1000,{lat},{lon})[highway=bus_stop];"
         f"node(around:2000,{lat},{lon})[railway~\"^(station|halt|tram_stop)$\"];"
         f"node(around:2000,{lat},{lon})[public_transport=station];"
         f");out geom tags;")
    return osm._query(q).get("elements") or []


def classify(elements: list[dict], lat: float, lon: float) -> dict:
    """The nearest of each kind with its distance in km, and transit stop counts. Pure, so tests pass elements."""
    best: dict[str, dict] = {}
    bus_400 = bus_800 = 0
    for e in elements:
        t = e.get("tags") or {}
        pts = _pts(e)
        if not pts:
            continue
        d = _nearest_pt(lat, lon, pts)
        if t.get("highway") == "motorway_junction":
            kind = "highway"
        elif t.get("power") == "substation":
            kind = "substation"
        elif t.get("railway") == "rail":
            kind = "rail"
        elif t.get("highway") == "bus_stop":
            kind = "bus"
            bus_400 += d <= 0.4
            bus_800 += d <= 0.8
        elif t.get("railway") in ("station", "halt", "tram_stop") or t.get("public_transport") == "station":
            kind = "rail_transit"
        else:
            continue
        name = t.get("name") or t.get("ref") or t.get("exit_to") or t.get("destination") or None
        if kind not in best or d < best[kind]["km"]:
            best[kind] = {"km": round(d, 2), "name": name, "lon": pts[0][0], "lat": pts[0][1], "id": f"{e.get('type')}/{e.get('id')}"}
    for kind, name, hl, ho in HUBS:
        d = km(lat, lon, hl, ho)
        if d < 150 and (kind not in best or d < best[kind]["km"]):
            best[kind] = {"km": round(d, 1), "name": name, "lat": hl, "lon": ho, "id": name}
    return {"nearest": best, "bus_stops_400m": bus_400, "bus_stops_800m": bus_800}


def transport(lat: float, lon: float) -> dict:
    """{nearest: {highway, substation, rail, bus, rail_transit, airport, port}, bus_stops_400m, bus_stops_800m, source}."""
    out = classify(_query_transport(round(lat, 5), round(lon, 5)), lat, lon)
    return {**out, "source": NOTE}


ANCHOR_SHOPS = {"supermarket", "department_store", "wholesale", "mall", "doityourself", "hardware", "electronics",
                "furniture", "variety_store", "general"}
FOOD = {"restaurant", "cafe", "fast_food", "bar", "pub", "ice_cream", "food_court"}
SERVICES = {"bank", "pharmacy", "fuel", "clinic", "dentist", "doctors", "post_office", "car_wash"}


def _query_retail(lat: float, lon: float, r: int) -> list[dict]:
    q = (f"[out:json][timeout:60];("
         f"nwr(around:{r},{lat},{lon})[shop];"
         f"nwr(around:{r},{lat},{lon})[amenity];"
         f"nwr(around:1500,{lat},{lon})[shop~\"^(supermarket|department_store|wholesale|mall|doityourself|hardware)$\"];"
         f"way(around:200,{lat},{lon})[highway~\"^(motorway|trunk|primary|secondary|tertiary)(_link)?$\"];"
         f"node(around:{r},{lat},{lon})[highway=bus_stop];"
         f"nwr(around:{r},{lat},{lon})[building~\"^(apartments|residential|house|office|commercial)$\"];"
         f");out center tags;")
    return osm._query(q).get("elements") or []


def retail_mix(elements: list[dict], lat: float, lon: float, r_km: float) -> dict:
    """Businesses near a shop site, by group, the named anchors within 1.5 km, roads beside the site and building
    counts (a walk-in proxy). Pure."""
    shops, food, services, anchors, roads, bus, homes, offices = [], [], [], [], [], 0, 0, 0
    for e in elements:
        t = e.get("tags") or {}
        pts = _pts(e)
        if not pts:
            continue
        d = _nearest_pt(lat, lon, pts)
        item = {"name": t.get("name") or t.get("brand"), "kind": t.get("shop") or t.get("amenity"), "km": round(d, 3),
                "lon": pts[0][0], "lat": pts[0][1], "id": f"{e.get('type')}/{e.get('id')}"}
        if t.get("highway") == "bus_stop":
            bus += d <= r_km
        elif t.get("highway"):
            roads.append({**item, "kind": t["highway"], "name": t.get("name") or t.get("ref"), "lanes": t.get("lanes")})
        elif t.get("building") and not t.get("shop") and not t.get("amenity"):
            if t["building"] == "office" or t["building"] == "commercial":
                offices += d <= r_km
            else:
                homes += d <= r_km
        elif t.get("shop") in ANCHOR_SHOPS and t.get("name"):
            anchors.append(item)
            if d <= r_km:
                shops.append(item)
        elif d > r_km:
            continue
        elif t.get("shop"):
            shops.append(item)
        elif t.get("amenity") in FOOD:
            food.append(item)
        elif t.get("amenity") in SERVICES:
            services.append(item)
    uniq = {}
    for a in sorted(anchors, key=lambda x: x["km"]):
        uniq.setdefault(a["name"], a)
    return {"shops": shops, "food": food, "services": services, "anchors": list(uniq.values()),
            "roads": sorted(roads, key=lambda x: x["km"]), "bus_stops": bus, "home_buildings": homes,
            "office_buildings": offices}


def retail(lat: float, lon: float, r_m: int = 400) -> dict:
    out = retail_mix(_query_retail(round(lat, 5), round(lon, 5), r_m), lat, lon, r_m / 1000)
    return {**out, "source": NOTE}
