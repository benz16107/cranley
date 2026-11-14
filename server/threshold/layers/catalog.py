"""The layer catalogue and its fetchers.

A layer is drawn from one of three places:
- `city`: one GeoJSON file per city, fetched once (fire stations, hospitals, schools, high-water marks);
- `grid`: one GeoJSON file per map tile at the layer's own zoom, fetched as the map looks there (parcels, hydrants,
  transit stops, flood zones up close), so nobody downloads a county to look at a street;
- `client`: drawn in the browser from data it already has (the scanned buildings) or computes (the sun).

Checked 2026-11-14 from this machine: every source below answered without a key. Overpass (OpenStreetMap) was at
capacity on all three mirrors, so nothing here depends on it.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ..config import CACHE
from ..sources.upstream import one_flight, send, write_atomic

DIR = CACHE / "layers"
AGENT = {"User-Agent": "building-explorer/0.1"}
# west, south, east, north. Generous boxes round the scanned buildings of each city; nothing is fetched outside them.
CITIES: dict[str, tuple[float, float, float, float]] = {
    "hou": (-95.85, 29.45, -94.95, 30.15),
    "la": (-118.75, 33.65, -117.85, 34.40),
}
PAGE = 2000
MAX_PAGES = 60


@dataclass(frozen=True)
class Layer:
    id: str
    title: str
    group: str
    shape: str                 # point | line | area | raster | readout
    scope: str                 # city | grid | client | tiles
    source: str                # who publishes it
    source_url: str
    confidence: str            # high | medium | low: how far to trust what is drawn
    note: str                  # what it is and what it leaves out, one or two sentences
    data_date: str = ""        # the date the source gives for the data, when it gives one
    cities: tuple[str, ...] = ("hou", "la")
    grid_z: int = 0            # grid layers: the tile zoom one file covers
    minzoom: float = 0         # the map zoom from which it is drawn
    on: bool = False           # shown by default
    coarse: bool = False       # grid layers that also have a generalised whole-city file for far zooms
    tiles: str = ""            # raster layers: an XYZ template the browser loads itself
    extra: dict = field(default_factory=dict)  # hue, legend, tile_maxzoom: see layers/sources/__init__.py
    licence: str = ""          # the licence the source publishes under, when it names one
    attribution: str = ""      # the credit line the source asks for; without it `source` is the credit
    maxzoom: float = 24        # the map zoom up to which it is drawn


# The sections of the layer list, in order. A layer whose group is not here is listed after them.
GROUPS = ("Coverage", "Live", "People", "Rules", "Hazards", "Getting around", "Services", "Imagery")


LAYERS: tuple[Layer, ...] = (
    Layer("scans", "Scanned buildings", "Coverage", "point", "client", "Matterport scan index (CoStar kit)", "",
          "high", "One mark per address that has at least one scan. The kind of space is read from the scan's name.", on=True),
    Layer("records", "With a CoStar property record", "Coverage", "point", "client", "CoStar property records (hackathon kit)", "",
          "high", "Scanned addresses matched to a CoStar property record. Homes with a listing and no property record are left out."),
    Layer("drone", "With a drone capture", "Coverage", "point", "client", "Matterport scan index (CoStar kit)", "",
          "high", "Scanned addresses that also have an exterior drone capture."),
    Layer("mesh3d", "3D city mesh coverage", "Imagery", "area", "city", "Vexcel 3D Cities", "https://vexceldata.com/products/3d-cities/",
          "medium", "The outer box of each 3D collection. The mesh inside it is irregular, so the edge is approximate."),
    Layer("fema", "FEMA flood hazard areas", "Hazards", "area", "grid", "FEMA National Flood Hazard Layer, Esri's hosted copy",
          "https://www.arcgis.com/home/item.html?id=11955f1b47ec41a3af86650824e0c634", "medium",
          "Special flood hazard areas only (the 1% annual chance floodplain and floodway). Outside a shape means outside the mapped floodplain, not no risk.",
          grid_z=13, minzoom=9, coarse=True),
    Layer("harvey", "Hurricane Harvey high-water marks", "Hazards", "point", "city", "USGS Short-Term Network, event 180",
          "https://stn.wim.usgs.gov/STNDataPortal/", "medium",
          "Surveyed marks of the peak water, August to September 2017. Height above ground is given where the surveyor recorded it.",
          data_date="2017-09", cities=("hou",)),
    Layer("fire_stations", "Fire and EMS stations", "Services", "point", "city", "USGS National Structures Dataset",
          "https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer", "medium",
          "Federal inventory, last loaded by USGS in the year shown on each station. A station built since then is missing."),
    Layer("hydrants", "Fire hydrants", "Services", "point", "grid", "City of Houston GIS",
          "https://cohgis-mycity.opendata.arcgis.com/", "medium",
          "The city's own hydrant inventory, inside Houston's city limits only. Los Angeles publishes no hydrant map without a sign-in.",
          cities=("hou",), grid_z=15, minzoom=14.5),
    Layer("hospitals", "Hospitals", "Services", "point", "city", "USGS National Structures Dataset",
          "https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer", "medium",
          "Hospitals and medical centres from the federal inventory. Clinics and urgent care are not included."),
    Layer("schools", "Schools and colleges", "Services", "point", "city", "USGS National Structures Dataset",
          "https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer", "medium",
          "Public and private schools, colleges and universities from the federal inventory."),
    Layer("parcels", "Property parcels", "Rules", "line", "grid", "Harris Central Appraisal District; Los Angeles County Assessor",
          "https://hcad.org/hcad-online-services/pdata/", "medium",
          "Parcel outlines from each county's appraisal map. Lines are the county's drawing, not a survey, and stop at the county line.",
          grid_z=16, minzoom=15.5),
    Layer("transit", "Transit stops", "Getting around", "point", "grid", "US DOT National Transit Map",
          "https://www.bts.gov/national-transit-map", "medium",
          "Stops of agencies that publish a schedule feed to the federal transit map. Rail and bus are told apart by the feed's own type.",
          grid_z=13, minzoom=12.5),
    Layer("ev", "EV chargers", "Getting around", "point", "city", "US DOE Alternative Fuels Data Center",
          "https://afdc.energy.gov/stations", "medium",
          "Public charging stations that were open when fetched. Home and workplace chargers are not listed."),
    Layer("weather", "Weather now", "Live", "readout", "client", "Open-Meteo (NOAA HRRR and GFS models)", "https://open-meteo.com/",
          "medium", "Model analysis for the city centre, refreshed every ten minutes. It is a forecast model's present, not a station reading."),
    Layer("radar", "Rain radar", "Live", "raster", "tiles", "NOAA NEXRAD composite, Iowa Environmental Mesonet",
          "https://mesonet.agron.iastate.edu/ogc/", "high",
          "Base reflectivity from the national radar network, redrawn every five minutes. Clear air shows nothing.",
          tiles="https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png", extra={"tile_maxzoom": 10}),
    Layer("sun", "Sun and shadows", "Live", "readout", "client", "Computed here (NOAA solar position equations)", "https://gml.noaa.gov/grad/solcalc/",
          "high", "Where the sun stands for the chosen day and hour. Shadows are cast by the 3D city mesh, trees included, so they stop where the mesh does."),
)
BY_ID = {l.id: l for l in LAYERS}

# ---- ArcGIS feature services --------------------------------------------------------------------------------------

NSD = "https://carto.nationalmap.gov/arcgis/rest/services/structures/MapServer/{}/query"
ESRI_FEMA = "https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Flood_Hazard_Reduced_Set_gdb/FeatureServer/0/query"
ARCGIS: dict[str, dict] = {
    # layer id -> {urls: one or more service layers (per city where they differ), fields kept, how a feature is named}
    "fire_stations": {"urls": [NSD.format(16)], "fields": "name,address,city,loaddate"},
    "hospitals": {"urls": [NSD.format(14)], "fields": "name,address,city,loaddate"},
    "schools": {"urls": [NSD.format(23), NSD.format(21)], "fields": "name,address,city,loaddate"},
    "fema": {"urls": [ESRI_FEMA], "fields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF", "offset": 0.00003, "coarse_offset": 0.0004},
    "transit": {"urls": ["https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_National_Transit_Map_Stops/FeatureServer/0/query"],
                "fields": "stop_name,stop_type_text,download_date"},
    # Los Angeles: the city's and the water department's hydrant services both ask for a sign-in (checked 2026-11-14)
    "hydrants": {"urls": ["https://mycity2.houstontx.gov/gisweb02/rest/services/HoustonMap/Public_safety/MapServer/9/query"], "fields": ""},
    "parcels": {"city_urls": {
        "hou": "https://www.gis.hctx.net/arcgis/rest/services/HCAD/Parcels/MapServer/0/query",
        "la": "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0/query"},
        "fields": "", "offset": 0.000005},
}


def arcgis(url: str, box: tuple[float, float, float, float], fields: str = "", offset: float | None = None,
           where: str = "1=1") -> tuple[list[dict], bool]:
    """Features of one ArcGIS layer inside a box, as GeoJSON features in WGS84, and whether the answer was cut short."""
    out: list[dict] = []
    for _ in range(MAX_PAGES):
        # the next page starts after what has arrived: a service may hand back fewer than asked for (FEMA's sends 500
        # of its heavier shapes), and stepping by the asked-for size would skip the rest
        params = {"where": where, "geometry": ",".join(f"{v:.6f}" for v in box), "geometryType": "esriGeometryEnvelope",
                  "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects", "outFields": fields or "OBJECTID",
                  "returnGeometry": "true", "geometryPrecision": 6, "f": "geojson", "resultOffset": len(out),
                  "resultRecordCount": PAGE}
        if offset:
            params["maxAllowableOffset"] = offset
        body = send("GET", url, params=params, headers=AGENT, timeout=120).json()
        if "error" in body:
            raise LookupError(f"{url.split('/rest/services/')[-1].split('/')[0]}: {body['error'].get('message', 'error')}")
        feats = body.get("features") or []
        out += feats
        more = (body.get("properties") or {}).get("exceededTransferLimit") or body.get("exceededTransferLimit")
        if not more or not feats:
            return out, False
    return out, True


def _tidy(layer: str, f: dict) -> dict | None:
    """One feature with only what the map shows: a name, a line of detail, and the few values a style reads."""
    g, a = f.get("geometry"), f.get("properties") or {}
    if not g:
        return None
    p: dict = {}
    if layer in ("fire_stations", "hospitals", "schools"):
        loaded = a.get("loaddate")
        p = {"name": a.get("name") or "", "detail": ", ".join(x for x in (a.get("address"), a.get("city")) if x),
             "as_of": datetime.fromtimestamp(loaded / 1000, UTC).strftime("%Y") if isinstance(loaded, (int, float)) else ""}
    elif layer == "fema":
        zone, sub = a.get("FLD_ZONE") or "", (a.get("ZONE_SUBTY") or "").strip()
        p = {"name": f"Zone {zone}" if zone else "Flood hazard area", "detail": sub.capitalize(), "zone": zone,
             "floodway": "FLOODWAY" in sub.upper()}
    elif layer == "transit":
        kind = (a.get("stop_type_text") or "").strip('"')
        p = {"name": a.get("stop_name") or "", "detail": kind, "rail": kind.lower() not in ("bus", ""), "as_of": a.get("download_date") or ""}
    elif layer == "hydrants":
        p = {"name": "Fire hydrant"}
    elif layer == "parcels":
        p = {}
    return {"type": "Feature", "geometry": g, "properties": p}


# ---- other sources ------------------------------------------------------------------------------------------------

def _harvey(_city: str) -> tuple[list[dict], bool]:
    from ..tools.flood_rehearsal import (
        public,  # the flood tool already keeps the marks; one copy on disk
    )
    feats = []
    for m in public.event_marks("harvey_2017"):
        if m.get("latitude_dd") is None or m.get("longitude_dd") is None:
            continue
        hag = m.get("height_above_ground")
        depth = round(float(hag) * public.FT, 2) if hag not in (None, "") else None
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [m["longitude_dd"], m["latitude_dd"]]},
                      "properties": {"name": "High-water mark" + (f", {depth} m above ground" if depth is not None else ""),
                                     "detail": (m.get("location_description") or "")[:140], "depth_m": depth,
                                     "quality": m.get("hwm_quality")}})
    return feats, False


def _mesh3d(_city: str) -> tuple[list[dict], bool]:
    from ..world import tiles3d
    feats = []
    for r in tiles3d.regions(29.76, -95.37):  # the answer is every collection, whatever the point
        w, s, e, n = r["bounds"]
        cover = tiles3d.coverage((s + n) / 2, (w + e) / 2) or {}
        cap = [c[:7].replace("/", "-") for c in (cover.get("capture") or []) if c]
        feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]},
                      "properties": {"name": "3D city mesh", "detail": f"Flown {' to '.join(dict.fromkeys(cap))}" if cap else ""}})
    return feats, False


AFDC = "https://developer.nlr.gov/api/alt-fuel-stations/v1/nearest.json"  # the lab was renamed; nrel.gov no longer answers


def _ev(city: str) -> tuple[list[dict], bool]:
    w, s, e, n = CITIES[city]
    lat, lon = (s + n) / 2, (w + e) / 2
    # the public demo key of api.data.gov: one request per city, then the file on disk answers
    body = send("GET", AFDC, headers=AGENT, timeout=120, params={
        "api_key": "DEMO_KEY", "fuel_type": "ELEC", "status": "E", "access": "public", "latitude": lat, "longitude": lon,
        "radius": 45, "limit": "all"}).json()
    feats = []
    for st in body.get("fuel_stations") or []:
        if st.get("latitude") is None or not (w <= st["longitude"] <= e and s <= st["latitude"] <= n):
            continue
        fast, l2 = st.get("ev_dc_fast_num") or 0, st.get("ev_level2_evse_num") or 0
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [st["longitude"], st["latitude"]]},
                      "properties": {"name": st.get("station_name") or "Charging station", "fast": fast > 0,
                                     "detail": ", ".join(x for x in (f"{fast} fast" if fast else "", f"{l2} level 2" if l2 else "",
                                                                    st.get("ev_network") or "") if x)}})
    return feats, False


OTHER = {"harvey": _harvey, "mesh3d": _mesh3d, "ev": _ev}


# ---- cached answers -----------------------------------------------------------------------------------------------

def _collection(layer: str, feats: list[dict], cut: bool) -> bytes:
    L = BY_ID[layer]
    return json.dumps({"type": "FeatureCollection", "features": feats,
                       "meta": {"layer": layer, "source": L.source, "fetched": datetime.now(UTC).strftime("%Y-%m-%d"),
                                "count": len(feats), "truncated": cut}}, separators=(",", ":")).encode()


def _fetch(layer: str, box: tuple[float, float, float, float], city: str, coarse: bool = False) -> bytes:
    if layer in FETCH:  # a source module (layers/sources/) brings its own fetcher, features already tidied
        return _collection(layer, *FETCH[layer](box, city))
    spec = ARCGIS[layer]
    urls = spec.get("urls") or [spec["city_urls"][city]]
    feats, cut = [], False
    for u in urls:
        got, c = arcgis(u, box, spec.get("fields", ""), spec.get("coarse_offset" if coarse else "offset"))
        feats += got
        cut = cut or c
    return _collection(layer, [t for t in (_tidy(layer, f) for f in feats) if t], cut)


def _cached(path: Path, make) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        pass
    with one_flight(str(path)):
        try:
            return path.read_bytes()
        except FileNotFoundError:
            data = make()
            write_atomic(path, data)
            return data


def city_geojson(layer: str, city: str) -> bytes:
    """The whole-city file of a layer: a `city` layer, or the generalised copy of a `grid` layer that has one."""
    L = BY_ID.get(layer)
    if L is None or city not in CITIES or not (L.scope == "city" or L.coarse):
        raise LookupError("no such layer for a whole city")
    if city not in L.cities:
        return _collection(layer, [], False)

    def make() -> bytes:
        if layer in OTHER:
            return _collection(layer, *OTHER[layer](city))
        return _fetch(layer, CITIES[city], city, coarse=L.coarse)
    return _cached(DIR / layer / f"{city}.json", make)


def tile_box(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    n = 2 ** z
    lat = lambda t: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * t / n))))
    return x / n * 360 - 180, lat(y + 1), (x + 1) / n * 360 - 180, lat(y)


def city_of(box: tuple[float, float, float, float]) -> str | None:
    """The city whose box this one touches, so nothing is fetched for a tile out at sea or in another state."""
    w, s, e, n = box
    return next((c for c, (cw, cs, ce, cn) in CITIES.items() if w < ce and e > cw and s < cn and n > cs), None)


def tile_geojson(layer: str, z: int, x: int, y: int) -> bytes:
    L = BY_ID.get(layer)
    if L is None or L.scope != "grid" or z != L.grid_z:
        raise LookupError(f"this layer is served in tiles of zoom {L.grid_z}" if L and L.scope == "grid" else "no such tiled layer")
    box = tile_box(z, x, y)
    city = city_of(box)
    if city is None or city not in L.cities:
        return _collection(layer, [], False)
    return _cached(DIR / layer / str(z) / f"{x}_{y}.json", lambda: _fetch(layer, box, city))


def fetched(layer: str, city: str) -> str:
    """The day a layer's file for this city was fetched, or '' when nothing is on disk yet."""
    f = DIR / layer / f"{city}.json"
    if not f.exists():
        d = DIR / layer / str(BY_ID[layer].grid_z)
        f = next(iter(sorted(d.glob("*.json"))), f) if d.exists() else f
    return time.strftime("%Y-%m-%d", time.gmtime(f.stat().st_mtime)) if f.exists() else ""


def catalogue(city: str) -> list[dict]:
    """Every layer as the web list reads it, in the order of GROUPS (so a new layer needs no change on the page)."""
    order = {g: i for i, g in enumerate(GROUPS)}
    out = []
    for L in sorted(LAYERS, key=lambda l: order.get(l.group, len(order))):  # stable: a group keeps its layers' own order
        out.append({"id": L.id, "title": L.title, "group": L.group, "shape": L.shape, "scope": L.scope, "source": L.source,
                    "source_url": L.source_url, "licence": L.licence, "attribution": L.attribution, "confidence": L.confidence,
                    "note": L.note, "data_date": L.data_date, "available": city in L.cities, "grid_z": L.grid_z,
                    "minzoom": L.minzoom, "maxzoom": L.maxzoom, "on": L.on, "coarse": L.coarse, "tiles": L.tiles,
                    "hue": L.extra.get("hue", ""), "legend": L.extra.get("legend"), "tile_maxzoom": L.extra.get("tile_maxzoom", 18),
                    "fetched": fetched(L.id, city) if L.scope in ("city", "grid") else ""})
    return out


# ---- weather ------------------------------------------------------------------------------------------------------

METEO = "https://api.open-meteo.com/v1/forecast"
WMO = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Freezing fog", 51: "Light drizzle",
       53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow",
       75: "Heavy snow", 80: "Light showers", 81: "Showers", 82: "Heavy showers", 95: "Thunderstorm", 96: "Thunderstorm with hail",
       99: "Thunderstorm with hail"}


def weather(city: str) -> dict:
    """Conditions now at the centre of a city, from Open-Meteo, kept for ten minutes."""
    if city not in CITIES:
        raise LookupError("no such city")
    f = DIR / "weather" / f"{city}.json"
    if f.exists() and time.time() - f.stat().st_mtime < 600:
        return json.loads(f.read_text())
    w, s, e, n = CITIES[city]
    cur = send("GET", METEO, headers=AGENT, timeout=30, params={
        "latitude": round((s + n) / 2, 3), "longitude": round((w + e) / 2, 3), "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,cloud_cover,weather_code"}).json()
    c = cur["current"]
    out = {"time": c["time"], "timezone": cur.get("timezone_abbreviation") or "", "utc_offset_s": cur.get("utc_offset_seconds", 0),
           "sky": WMO.get(c.get("weather_code"), ""), "temperature_c": c.get("temperature_2m"), "feels_c": c.get("apparent_temperature"),
           "humidity_pct": c.get("relative_humidity_2m"), "wind_kmh": c.get("wind_speed_10m"), "gust_kmh": c.get("wind_gusts_10m"),
           "wind_from_deg": c.get("wind_direction_10m"), "rain_mm": c.get("precipitation"), "cloud_pct": c.get("cloud_cover"),
           "source": BY_ID["weather"].source}
    write_atomic(f, json.dumps(out).encode())
    return out



# ---- more layers, one file per source ---------------------------------------------------------------------------
# Last, so a source module can import Layer, arcgis, send and CITIES from here while this module is still loading.
from .sources import FETCH, MORE

LAYERS = (*LAYERS, *MORE)
BY_ID = {l.id: l for l in LAYERS}
