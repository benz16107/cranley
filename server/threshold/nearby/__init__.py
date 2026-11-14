"""What is near a place, from OpenStreetMap: parks, playgrounds, schools, vets, courts, shops, transit, by category,
with walking and cycling distance along the street network.

One Overpass request per area (a ~440 m grid cell) fetches every category, the walkable street network around it and
the buildings next door; every profile and tool then reads that one cached answer. Answers live on disk under
$THRESHOLD_DATA_DIR/cache/nearby/ forever (delete a file to refresh it) and requests are at least 2 s apart.

    from threshold import nearby
    nearby.places_near(29.76, -95.37, ["playground", "park"])           # for map layers: [{id, category, name, lon, lat}]
    nearby.nearest(29.76, -95.37, nearby.PROFILES["kids"]["categories"]) # per category, nearest few with route and minutes

Distances: Dijkstra over OSM highways from the street node nearest the home to the node nearest each place, plus the
two straight snaps. A place outside the fetched network, or not connected to it, gets the straight line times
DETOUR, labelled as an estimate. OSM data is ODbL; it stays in the cache and every source note cites it.
"""
from __future__ import annotations

import functools
import hashlib
import heapq
import json
import math
import re
import threading
import time

import httpx
import numpy as np

from ..config import CACHE

URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter")
AGENT = "threshold-hackprinceton/0.1 (building tools; hackathon prototype)"
GAP_S = 2.0
CELL = 0.004            # degrees: homes within ~440 m share one fetch
R_PLACES = 2600         # m around the cell centre: places
R_NET = 2000            # m: street network (a 20-minute walk is 1.6 km)
R_VETS = 15000          # m: vets, emergency vets above all, are few and far
R_BUILDINGS = 90        # m: neighbouring buildings
MIN_BUILDINGS = 100     # fewer mapped in the fetched ~420 m (Houston has 5 to 25, LA 700): too thin to trust a gap
WALK_M_MIN = 80.0       # 4.8 km/h, an adult's usual pace
CYCLE_M_MIN = 250.0     # 15 km/h, an easy ride
DRIVE_M_MIN = 500.0     # 30 km/h, city driving with lights; for vets, which people drive to
DRIVE = {"vet", "emergency_vet"}
DETOUR = 1.4            # straight line to street distance in US suburbs is about 1.2 to 1.6
SNAP_MAX_M = 300        # a place farther than this from any street node is not routed
NOTE = "OpenStreetMap contributors (ODbL), via Overpass"
_lock = threading.Lock()
_last = [0.0]

# id: (label, profiles, test(tags) -> bool). A place can match several categories (a park with a playground tag).
_T = lambda k, *vs: (lambda t: t.get(k) in vs)
_SPORT = lambda *vs: (lambda t: bool(set(re.split(r"[;,]\s*", t.get("sport", ""))) & set(vs)))
_STREETY = re.compile(r"\b(drive|dr|street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|plaza|court|ct|place|pl)\.?$", re.IGNORECASE)
_NAMED = lambda t: bool(t.get("name"))
_PUBLIC = lambda t: t.get("access") not in ("private", "no", "customers") or t.get("leisure") == "sports_centre"
_LEVELS = {"elementary": r"elementary|primary|\bel\b|\bes\b", "middle": r"middle|intermediate|junior high|\bms\b",
           "high": r"\bhigh\b|\bhs\b|secondary|academy of"}


def school_level(t: dict) -> str | None:
    lvl = t.get("isced:level") or ""
    if lvl:
        return {"1": "elementary", "2": "middle", "3": "high"}.get(lvl[:1])
    name = (t.get("name") or "").lower()
    return next((k for k, pat in _LEVELS.items() if re.search(pat, name)), None)


CATEGORIES: dict[str, tuple[str, tuple[str, ...], object]] = {
    "dog_park": ("Dog park", ("pets",), _T("leisure", "dog_park")),
    "vet": ("Vet", ("pets",), _T("amenity", "veterinary")),
    "emergency_vet": ("Emergency vet", ("pets",), lambda t: t.get("amenity") == "veterinary" and (
        t.get("emergency") == "yes" or bool(re.search(r"emergenc|24|urgent|er\b", (t.get("name") or "").lower())))),
    "pet_store": ("Pet store", ("pets",), _T("shop", "pet")),
    "trail": ("Trail or greenway", ("pets", "sports"), lambda t: t.get("highway") in ("path", "track", "bridleway", "cycleway")
              and _NAMED(t) and not _STREETY.search(t["name"])),
    "park": ("Park", ("pets", "kids"), lambda t: t.get("leisure") in ("park", "nature_reserve") and _NAMED(t)),
    "playground": ("Playground", ("kids",), _T("leisure", "playground")),
    "school_elementary": ("Elementary school", ("kids",), lambda t: t.get("amenity") == "school" and school_level(t) == "elementary"),
    "school_middle": ("Middle school", ("kids",), lambda t: t.get("amenity") == "school" and school_level(t) == "middle"),
    "school_high": ("High school", ("kids",), lambda t: t.get("amenity") == "school" and school_level(t) == "high"),
    "library": ("Library", ("kids",), _T("amenity", "library")),
    "pool": ("Public pool", ("kids", "sports"), lambda t: (t.get("leisure") in ("swimming_pool", "water_park") and _NAMED(t)
                                                          and _PUBLIC(t)) or (t.get("leisure") == "sports_centre" and _SPORT("swimming")(t))),
    "childcare": ("Childcare", ("kids",), _T("amenity", "childcare", "kindergarten")),
    "tennis": ("Tennis court", ("sports",), _SPORT("tennis")),
    "pickleball": ("Pickleball court", ("sports",), _SPORT("pickleball")),
    "basketball": ("Basketball court", ("sports",), _SPORT("basketball")),
    "soccer": ("Soccer field", ("sports",), _SPORT("soccer", "football")),
    "baseball": ("Baseball or softball field", ("sports",), _SPORT("baseball", "softball")),
    "gym": ("Gym", ("sports",), lambda t: t.get("leisure") == "fitness_centre" or (t.get("leisure") == "sports_centre"
                                                                                  and _SPORT("fitness")(t))),
    "climbing": ("Climbing gym or wall", ("sports",), _SPORT("climbing", "bouldering")),
    "golf": ("Golf course", ("sports",), _T("leisure", "golf_course")),
    "skate_park": ("Skate park", ("sports",), _SPORT("skateboard")),
    "running_track": ("Running track", ("sports",), lambda t: t.get("leisure") == "track" and _SPORT("running", "athletics")(t)),
    "cycleway": ("Bike path", ("sports",), lambda t: t.get("highway") == "cycleway"),
    "ice_rink": ("Ice rink", ("sports",), lambda t: t.get("leisure") == "ice_rink" or _SPORT("ice_skating", "ice_hockey")(t)),
    "grocery": ("Grocery store", ("everyday",), _T("shop", "supermarket", "greengrocer")),
    "pharmacy": ("Pharmacy", ("everyday",), lambda t: t.get("amenity") == "pharmacy" or t.get("shop") == "chemist"),
    "transit": ("Transit stop", ("everyday",), lambda t: t.get("highway") == "bus_stop" or t.get("railway") in (
        "station", "halt", "tram_stop") or t.get("public_transport") == "station"),
    "coffee": ("Coffee", ("everyday",), _T("amenity", "cafe")),
}
SPORTS = [k for k, v in CATEGORIES.items() if "sports" in v[1]]
PROFILES = {
    "pets": {"label": "Pets", "categories": ["dog_park", "vet", "emergency_vet", "park", "trail", "pet_store"]},
    "kids": {"label": "Kids", "categories": ["playground", "park", "school_elementary", "school_middle", "school_high",
                                             "library", "pool", "childcare"]},
    "sports": {"label": "Sports", "categories": SPORTS},
    "everyday": {"label": "Everyday", "categories": ["grocery", "pharmacy", "transit", "coffee"]},
}
BUSY = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link"}
NO_WALK = {"motorway", "motorway_link", "construction", "proposed", "raceway", "bus_guideway", "platform", "elevator"}
NO_CYCLE = NO_WALK | {"steps", "corridor"}


# ---- fetching ----------------------------------------------------------------------------------------

def cell(lat: float, lon: float) -> tuple[float, float]:
    return round(round(lat / CELL) * CELL, 6), round(round(lon / CELL) * CELL, 6)


def query(lat: float, lon: float) -> str:
    """The one Overpass request for the cell around (lat, lon)."""
    a = lambda r: f"(around:{r},{lat},{lon})"
    rp, rn = R_PLACES, R_NET
    return (f"[out:json][timeout:120];"
            f"(nwr{a(rp)}[leisure~\"^(dog_park|playground|park|nature_reserve|swimming_pool|water_park|fitness_centre|"
            f"sports_centre|golf_course|ice_rink|track|pitch)$\"];"
            f"nwr{a(rp)}[amenity~\"^(school|library|childcare|kindergarten|pharmacy|cafe)$\"];"
            f"nwr{a(rp)}[shop~\"^(pet|supermarket|greengrocer|chemist)$\"];"
            f"node{a(rn)}[highway=bus_stop];nwr{a(rp)}[railway~\"^(station|halt|tram_stop)$\"];"
            f"nwr{a(R_VETS)}[amenity=veterinary];)->.p;.p out tags center qt;"
            f"way{a(rn)}[highway][highway!~\"^(construction|proposed|raceway|bus_guideway|platform|elevator)$\"]->.n;"
            f".n out body geom qt;"
            f"way{a(R_BUILDINGS + 330)}[building]->.b;.b out tags geom qt;")


def _post(q: str) -> bytes:
    err = None
    for url in URLS:
        for attempt in range(2):
            with _lock:
                wait = _last[0] + GAP_S * (1 + 2 * attempt) - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                _last[0] = time.monotonic()
            try:
                r = httpx.post(url, data={"data": q}, headers={"User-Agent": AGENT}, timeout=180)
                r.raise_for_status()
                if not r.json().get("elements") and "remark" in r.json():
                    raise ValueError(r.json()["remark"][:200])
                return r.content
            except (httpx.HTTPError, ValueError) as e:
                err = e
    raise RuntimeError(f"OpenStreetMap (Overpass) is unavailable right now: {str(err)[:160]}")


def raw(lat: float, lon: float, fetch: bool = True) -> dict | None:
    """The cached Overpass answer for the cell holding (lat, lon); fetched once when missing (None if fetch is False)."""
    c = cell(lat, lon)
    q = query(*c)
    f = CACHE / "nearby" / f"{c[0]:.6f},{c[1]:.6f}-{hashlib.sha256(q.encode()).hexdigest()[:10]}.json"
    if not f.exists():
        if not fetch:
            return None
        body = _post(q)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)
    return json.loads(f.read_text())


# ---- parsing --------------------------------------------------------------------------------------------

def _xy(lat0: float):
    k = 111320.0 * math.cos(math.radians(lat0))
    return lambda lon, lat: ((lon) * k, lat * 110574.0)


def dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Metres between two (lon, lat) points (flat, fine within a few km)."""
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * 111320.0 * k, (a[1] - b[1]) * 110574.0)


class Area:
    """One parsed Overpass answer: places, the street graph and buildings."""

    def __init__(self, data: dict):
        self.places: list[dict] = []
        self.ways: list[dict] = []
        self.buildings: list[list[tuple[float, float]]] = []
        seen = set()
        for e in data.get("elements") or []:
            t = e.get("tags") or {}
            if e["type"] == "way" and "nodes" in e and e.get("geometry") and t.get("highway") and "center" not in e:
                self.ways.append({"id": e["id"], "nodes": e["nodes"], "pts": [(g["lon"], g["lat"]) for g in e["geometry"]],
                                  "tags": t})
                continue
            if e["type"] == "way" and t.get("building") and e.get("geometry") and "center" not in e:
                self.buildings.append([(g["lon"], g["lat"]) for g in e["geometry"]])
                continue
            pos = e.get("center") or ({"lat": e["lat"], "lon": e["lon"]} if "lat" in e else None)
            key = f"{e['type']}/{e['id']}"
            if pos and key not in seen:
                seen.add(key)
                self.places.append({"id": key, "lon": pos["lon"], "lat": pos["lat"], "tags": t})
        # named paths and cycleways are places too (trail, bike path), at the way's middle point
        for w in self.ways:
            if any(test(w["tags"]) for k, (_, _, test) in CATEGORIES.items() if k in ("trail", "cycleway")):
                m = w["pts"][len(w["pts"]) // 2]
                self.places.append({"id": f"way/{w['id']}", "lon": m[0], "lat": m[1], "tags": w["tags"]})
        self._graphs: dict[str, tuple] = {}

    def of(self, category: str) -> list[dict]:
        test = CATEGORIES[category][2]
        return [p for p in self.places if test(p["tags"])]

    def graph(self, mode: str):
        """(node ids, coords array (lon, lat), adjacency {i: [(j, metres, busy)]}) for 'walk' or 'cycle'."""
        if mode in self._graphs:
            return self._graphs[mode]
        bad = NO_WALK if mode == "walk" else NO_CYCLE
        idx: dict[int, int] = {}
        coords: list[tuple[float, float]] = []
        adj: dict[int, list] = {}
        busy_nodes: set[int] = set()
        for w in self.ways:
            t = w["tags"]
            hw = t.get("highway")
            if hw in bad or t.get("access") in ("private", "no") and hw != "service":
                continue
            if mode == "walk" and t.get("foot") == "no":
                continue
            if mode == "cycle" and (t.get("bicycle") == "no" or hw in ("footway", "pedestrian") and t.get("bicycle") not in ("yes", "designated")):
                continue
            busy = hw in BUSY
            ids = []
            for nid, p in zip(w["nodes"], w["pts"]):
                if nid not in idx:
                    idx[nid] = len(coords)
                    coords.append(p)
                ids.append(idx[nid])
                if busy:
                    busy_nodes.add(idx[nid])
            for a, b in zip(ids, ids[1:]):
                d = dist_m(coords[a], coords[b])
                adj.setdefault(a, []).append((b, d, busy))
                adj.setdefault(b, []).append((a, d, busy))
        arr = np.array(coords, float) if coords else np.zeros((0, 2))
        main = _largest(adj, len(coords))
        g = (arr, adj, busy_nodes, main)
        self._graphs[mode] = g
        return g

    def busy_roads(self) -> list[dict]:
        return [w for w in self.ways if w["tags"].get("highway") in BUSY]


@functools.lru_cache(maxsize=16)
def _area_cached(lat: float, lon: float) -> Area:
    return Area(raw(lat, lon))


def area(lat: float, lon: float) -> Area:
    return _area_cached(*cell(lat, lon))


# ---- routing ----------------------------------------------------------------------------------------------

def _largest(adj: dict, n: int) -> np.ndarray:
    """Indices of the largest connected piece of the street graph: homes and places snap only to it, so a stray
    driveway or a footway mapped on its own cannot strand a route."""
    seen = np.zeros(n, bool)
    best: list[int] = []
    for s0 in range(n):
        if seen[s0] or s0 not in adj:
            continue
        comp, stack = [], [s0]
        seen[s0] = True
        while stack:
            u = stack.pop()
            comp.append(u)
            for v, _, _ in adj.get(u, ()):
                if not seen[v]:
                    seen[v] = True
                    stack.append(v)
        if len(comp) > len(best):
            best = comp
    return np.array(sorted(best), int)


def _snap(coords: np.ndarray, p: tuple[float, float], among: np.ndarray | None = None) -> tuple[int | None, float]:
    idx = among if among is not None else np.arange(len(coords))
    if not len(idx):
        return None, math.inf
    c = coords[idx]
    k = math.cos(math.radians(p[1]))
    d = np.hypot((c[:, 0] - p[0]) * 111320.0 * k, (c[:, 1] - p[1]) * 110574.0)
    i = int(np.argmin(d))
    return int(idx[i]), float(d[i])


def dijkstra(adj: dict, src: int, limit_m: float = 6000) -> tuple[dict[int, float], dict[int, int]]:
    dist, prev = {src: 0.0}, {}
    h = [(0.0, src)]
    while h:
        d, u = heapq.heappop(h)
        if d > dist.get(u, math.inf) or d > limit_m:
            continue
        for v, w, _ in adj.get(u, ()):
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v], prev[v] = nd, u
                heapq.heappush(h, (nd, v))
    return dist, prev


def crossings(path: list[int], adj: dict, busy_nodes: set[int]) -> int:
    """Busy roads crossed: a path node on a busy road reached and left by quiet streets (straight across an
    intersection). Walking along a busy road's sidewalk is not counted. shortcut: OSM in Houston and LA rarely maps
    sidewalks and crossings separately, so a crossing is read from the street graph; use crossing nodes if mapped."""
    n = 0
    for a, b, c in zip(path, path[1:], path[2:]):
        if b in busy_nodes:
            ab = next((x[2] for x in adj.get(a, ()) if x[0] == b), False)
            bc = next((x[2] for x in adj.get(b, ()) if x[0] == c), False)
            n += not ab and not bc
    return n


def nearest(lat: float, lon: float, categories: list[str], mode: str = "walk", k: int = 3,
            start: tuple[float, float] | None = None) -> dict:
    """For each category, the `k` nearest places by route distance: {category: [hit]}, plus `_meta`.
    A hit is {id, category, label, name, lon, lat, straight_m, route_m, minutes, method, path, busy_crossings}."""
    a = area(lat, lon)
    home = start or (lon, lat)
    coords, adj, busy_nodes, main = a.graph(mode)
    src, snap0 = _snap(coords, home, main)
    dist, prev = dijkstra(adj, src, 8000) if src is not None and snap0 <= SNAP_MAX_M else ({}, {})
    speed = WALK_M_MIN if mode == "walk" else CYCLE_M_MIN
    out: dict = {}
    for cat in categories:
        sp = DRIVE_M_MIN if cat in DRIVE else speed
        hits = []
        for p in a.of(cat):
            straight = dist_m(home, (p["lon"], p["lat"]))
            hits.append((straight, p))
        hits.sort(key=lambda x: x[0])
        best = []
        for straight, p in hits[:max(k * 4, 8)]:  # route the nearest few by straight line, keep the k shortest routes
            j, snap1 = _snap(coords, (p["lon"], p["lat"]), main)
            if j is not None and j in dist and snap1 <= SNAP_MAX_M:
                path = [j]
                while path[-1] != src:
                    path.append(prev[path[-1]])
                path.reverse()
                route_m = dist[j] + snap0 + snap1
                pts = [home] + [tuple(coords[i]) for i in path] + [(p["lon"], p["lat"])]
                hit = {"route_m": route_m, "method": "network", "path": _thin(pts),
                       "busy_crossings": crossings(path, adj, busy_nodes)}
            else:
                hit = {"route_m": straight * DETOUR, "method": "estimate", "path": [home, (p["lon"], p["lat"])],
                       "busy_crossings": None}
            t = p["tags"]
            name = t.get("name") or t.get("operator") or CATEGORIES[cat][0].lower()
            best.append({"id": p["id"], "category": cat, "label": CATEGORIES[cat][0], "name": name,
                         "lon": p["lon"], "lat": p["lat"], "straight_m": round(straight, 1),
                         **hit, "route_m": round(hit["route_m"], 1), "minutes": round(hit["route_m"] / sp, 1),
                         "by": "car" if cat in DRIVE else mode})
        best.sort(key=lambda h: h["route_m"])
        out[cat] = best[:k]
    out["_meta"] = {"mode": mode, "speed_m_min": speed, "snap_m": round(snap0, 1) if src is not None else None,
                    "network_nodes": len(coords), "radius_m": R_PLACES, "source": NOTE}
    return out


def _thin(pts: list, keep: int = 120) -> list[tuple[float, float]]:
    step = max(1, len(pts) // keep)
    out = pts[::step]
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return [(round(x, 7), round(y, 7)) for x, y in out]


def busy_road_m(lat: float, lon: float, start: tuple[float, float] | None = None) -> dict | None:
    """The nearest busy road (secondary or bigger) in a straight line: {name, highway, m, point}."""
    from shapely.geometry import LineString, Point
    from shapely.ops import nearest_points
    a = area(lat, lon)
    home = start or (lon, lat)
    to = _xy(home[1])
    hp = Point(to(*home))
    best = None
    for w in a.busy_roads():
        line = LineString([to(*p) for p in w["pts"]]) if len(w["pts"]) > 1 else None
        if line is None:
            continue
        d = line.distance(hp)
        if best is None or d < best[0]:
            q = nearest_points(line, hp)[0]
            best = (d, w, q)
    if not best:
        return None
    d, w, q = best
    k = 111320.0 * math.cos(math.radians(home[1]))
    return {"m": round(d, 1), "name": w["tags"].get("name") or w["tags"].get("ref") or "unnamed road",
            "highway": w["tags"]["highway"], "point": (round(q.x / k, 7), round(q.y / 110574.0, 7))}


def neighbour_m(lat: float, lon: float, footprint) -> dict | None:
    """Gap from a footprint (shapely, lon/lat) to the nearest other OSM building: {m, point}. None if OSM has none."""
    from shapely.geometry import Polygon
    from shapely.ops import nearest_points
    a = area(lat, lon)
    if len(a.buildings) < MIN_BUILDINGS:
        return None  # OSM has mapped too few buildings here for a gap to mean anything
    to = _xy(lat)
    from shapely import transform
    k = 111320.0 * math.cos(math.radians(lat))
    fp = transform(footprint, lambda c: c * (k, 110574.0))
    best = None
    for b in a.buildings:
        if len(b) < 4:
            continue
        g = Polygon([to(*p) for p in b]).buffer(0)
        if g.is_empty or g.intersection(fp).area > 0.3 * min(g.area, fp.area) or g.distance(fp) > R_BUILDINGS:
            continue
        d = g.distance(fp)
        if best is None or d < best[0]:
            best = (d, nearest_points(g, fp)[0])
    if not best:
        return None
    return {"m": round(best[0], 1), "point": (round(best[1].x / k, 7), round(best[1].y / 110574.0, 7))}


def places_near(lat: float, lon: float, categories: list[str] | None = None, radius_m: float = R_PLACES,
                fetch: bool = True) -> list[dict]:
    """For map layers: every place of these categories (default all) within `radius_m` of the point, straight-line
    distance only. [{id, category, label, name, lon, lat, m}]. Empty when the area is not cached and fetch is False."""
    if raw(lat, lon, fetch=fetch) is None:
        return []
    a = area(lat, lon)
    out = []
    for cat in categories or list(CATEGORIES):
        for p in a.of(cat):
            m = dist_m((lon, lat), (p["lon"], p["lat"]))
            if m <= radius_m:
                out.append({"id": p["id"], "category": cat, "label": CATEGORIES[cat][0],
                            "name": p["tags"].get("name"), "lon": p["lon"], "lat": p["lat"], "m": round(m, 1)})
    return sorted(out, key=lambda x: x["m"])


__all__ = ["CATEGORIES", "PROFILES", "SPORTS", "area", "busy_road_m", "cell", "nearest", "neighbour_m", "places_near", "raw"]


# ---- city-wide, for searches over many homes ----------------------------------------------------------------

CITY_BBOX = {"Houston": (29.45, -95.95, 30.15, -94.95), "Los Angeles": (33.65, -118.75, 34.40, -117.95)}
CITY_CATEGORIES = ("dog_park", "vet", "park", "playground", "school_elementary", "school_middle", "school_high", "library",
                   "pool", "childcare", "tennis", "pickleball", "basketball", "soccer", "baseball", "gym", "golf",
                   "skate_park", "running_track", "ice_rink")


def city_query(city: str) -> str:
    s, w, n, e = CITY_BBOX[city]
    return (f"[out:json][timeout:240][bbox:{s},{w},{n},{e}];"
            "(nwr[leisure~\"^(playground|park|dog_park|pitch|sports_centre|fitness_centre|track|ice_rink|golf_course|"
            "water_park)$\"];nwr[leisure=swimming_pool][name];"
            "nwr[amenity~\"^(school|library|childcare|kindergarten|veterinary)$\"];);out tags center qt;")


@functools.lru_cache(maxsize=2)
def city_places(city: str, fetch: bool = True) -> dict[str, np.ndarray] | None:
    """{category: array of (lon, lat)} for the whole city, from one cached Overpass request (no streets). None when
    not cached and fetch is False."""
    q = city_query(city)
    f = CACHE / "nearby" / f"city-{city.lower().replace(' ', '_')}-{hashlib.sha256(q.encode()).hexdigest()[:10]}.json"
    if not f.exists():
        if not fetch:
            return None
        body = _post(q)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)
    a = Area(json.loads(f.read_text()))
    return {c: np.array([(p["lon"], p["lat"]) for p in a.of(c)], float).reshape(-1, 2) for c in CITY_CATEGORIES}


def straight_nearest(pts: np.ndarray, lon: float, lat: float) -> float | None:
    """Straight-line metres from (lon, lat) to the nearest of `pts`."""
    if not len(pts):
        return None
    k = math.cos(math.radians(lat))
    return float(np.min(np.hypot((pts[:, 0] - lon) * 111320.0 * k, (pts[:, 1] - lat) * 110574.0)))
