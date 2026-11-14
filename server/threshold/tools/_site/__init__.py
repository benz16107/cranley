"""Shared parts of the site tools (roof_facts, loading_docks, truck_access, parking_count, path_to_water, risk_sheet,
daycare_capacity). They work from the outside in, so a site is a scan, a CoStar property or a bare lat and lon.

Not a tool: this package registers nothing. Engines are called through their modules (`aerial.site_facts`, ...)
so tests can replace them with hand-made answers.
"""
from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field

import shapely
from pydantic import BaseModel
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon, shape

from ...aerial import site as aerial
from ...sources import index
from .. import field as tool_field
from ..registry import NotApplicable, ToolError
from ..types import (
    AddressScope,
    Choke,
    GeoAnchor,
    Media,
    Metric,
    Pin,
    PinsOverlay,
    RouteOverlay,
    ScanScope,
    Source,
)

M_PER_FT = 0.3048
FT2_PER_M2 = 10.7639


class Where(BaseModel):
    """Every site tool takes one of these: a scan, a CoStar property, or a point."""
    scan: str | None = tool_field(None, source="selection.scan", description="Scan id, if the site has one")
    property_id: int | None = tool_field(None, description="CoStar PropertyId, for a commercial address")
    lat: float | None = tool_field(None, ge=-90, le=90, description="Latitude, for an address with no scan")
    lon: float | None = tool_field(None, ge=-180, le=180, description="Longitude, for an address with no scan")


@dataclass
class Site:
    lat: float
    lon: float
    sid: str | None = None
    property_id: int | None = None
    address: str | None = None
    how: str = "point"                   # where lat and lon came from
    _facts: dict | None = field(default=None, repr=False)

    @property
    def key(self) -> str:
        return self.sid or (f"p{self.property_id}" if self.property_id else f"{self.lat:.6f},{self.lon:.6f}")

    @property
    def scope(self):
        if self.sid:
            return ScanScope(sid=self.sid)
        return AddressScope(address=self.address or f"{self.lat:.6f}, {self.lon:.6f}")

    @property
    def state(self) -> str:
        # shortcut: the data covers Houston and Los Angeles only; use a real lookup if other cities arrive
        return "CA" if self.lon < -105 else "TX"


def not_for_homes(scan: str | None, what: str) -> None:
    """Truck tools on a house or an apartment unit: say so instead of reading docks off a home."""
    if scan and (index.rows().get(scan) or {}).get("kind") in ("house", "apartment_unit"):
        raise NotApplicable(f"This scan is a home, and {what} belong to warehouses and other commercial buildings. "
                            "Give a commercial property id or a point to check one.")


def locate(ctx, w: Where) -> Site:
    """Resolve the inputs to a point. A scan wins, then a property id, then lat and lon."""
    if w.scan:
        row = index.rows().get(w.scan) or {}
        lat, lon, how = _num(row.get("lat")), _num(row.get("lon")), "scan index"
        if lat is None:
            g = (ctx.plan(w.scan).get("geo") or {})
            lat, lon, how = g.get("lat"), g.get("lon"), "scan geocoordinates"
        if lat is None:
            raise NotApplicable(f"Scan {w.scan} has no location (a phone scan carries none), so the aerial photo cannot be "
                                "found. Give a latitude and longitude to run this on the site.")
        return Site(lat, lon, w.scan, _property_of_scan(w.scan) or w.property_id,
                    row.get("address") or row.get("name") or None, how)
    if w.property_id:
        rec = property_record(w.property_id)
        a = (rec or {}).get("primaryAddress") or {}
        if not rec or a.get("latitude") is None:
            raise NotApplicable(f"CoStar property {w.property_id} has no geocoded address in the kit, so the aerial photo "
                                "cannot be found.")
        return Site(a["latitude"], a["longitude"], None, w.property_id, address_of(rec), "CoStar primary address")
    if w.lat is None or w.lon is None:
        raise ToolError("Give a scan, a CoStar property id, or a latitude and longitude.")
    pid = nearest_property(w.lat, w.lon)
    a = (property_record(pid) or {}).get("primaryAddress") or {}
    if pid and (a.get("latitude") is None or dist_m((a["longitude"], a["latitude"]), (w.lon, w.lat)) > 35):
        pid = None  # warehouses stand side by side: a record geocoded farther off is likely the neighbour's
    return Site(w.lat, w.lon, None, pid, address_of(property_record(pid)) if pid else None, "point")


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


# ---- CoStar ---------------------------------------------------------------------------------------

def _costar():
    from ...sources import costar
    return costar


@functools.lru_cache(maxsize=64)
def property_record(pid: int | None) -> dict | None:
    if not pid:
        return None
    try:
        return _costar().get("commercial-property", int(pid))
    except LookupError:  # NotConfigured: the kit is not on this machine
        return None


def _property_of_scan(sid: str) -> int | None:
    try:
        return _costar().property_id_of(sid)
    except LookupError:
        return None


def nearest_property(lat: float, lon: float, within_m: float = 80) -> int | None:
    """The CoStar property whose scans sit nearest the point, within `within_m`; the index is the only spatial
    list of properties we have."""
    best, d_best = None, within_m
    for r in index.rows().values():
        pid, la, lo = r.get("costar_property_id"), _num(r.get("lat")), _num(r.get("lon"))
        if not pid or la is None:
            continue
        d = dist_m((lon, lat), (lo, la))
        if d < d_best:
            best, d_best = int(pid), d
    return best


def address_of(rec: dict | None) -> str | None:
    a = (rec or {}).get("primaryAddress") or {}
    street = " ".join(str(x) for x in (a.get("streetNumber"), a.get("streetName"), a.get("streetType")) if x)
    return ", ".join(x for x in (street, a.get("city"), a.get("state")) if x) or None


def record_claims(rec: dict | None) -> dict:
    """Checkable facts from the record with the field path each came from (the data workstream's `claims`), plus
    trailer parking, which `claims` leaves out."""
    if not rec:
        return {}
    out = _costar().claims({"property": rec})
    trailers = [p.get("totalSpaces") for p in rec.get("parking") or [] if p.get("parkingType") == 5 and p.get("totalSpaces")]
    if trailers:
        out["trailer_spaces"] = {"value": sum(trailers), "unit": None, "path": "parking[parkingType=5].totalSpaces"}
    cars = [p.get("totalSpaces") for p in rec.get("parking") or [] if p.get("parkingType") != 5 and p.get("totalSpaces")]
    if cars:
        out["car_spaces"] = {"value": sum(cars), "unit": None, "path": "parking[parkingType!=5].totalSpaces (sum)"}
    return out


def record_source(path: str, pid: int | None) -> Source:
    return Source(layer="costar", method="lookup", confidence="medium", note=f"CoStar property {pid}, field {path}")


# ---- Vexcel facts -----------------------------------------------------------------------------------

def facts(s: Site) -> dict:
    """site_facts once per run, with the facts keyed by id."""
    if s._facts is None:
        try:
            f = aerial.site_facts(s.lat, s.lon)
        except LookupError as e:  # VexcelError 404: no property at this point
            if getattr(e, "status", None) != 404:
                raise
            f = {"lat": s.lat, "lon": s.lon, "facts": [], "footprint": None, "parcel": None, "capture": None}
        s._facts = {**f, "by_id": {x["id"]: x for x in f.get("facts") or []}}
    return s._facts


def fact(s: Site, id: str, default=None):
    x = facts(s)["by_id"].get(id)
    return x["value"] if x else default


def metric(s: Site, id: str, label: str | None = None, *, scale: float = 1, unit: str | None = None,
           metric_id: str | None = None) -> Metric | None:
    """A numeric Vexcel fact as a Metric (None when Vexcel has no value)."""
    x = facts(s)["by_id"].get(id)
    if not x or not isinstance(x["value"], (int, float)) or isinstance(x["value"], bool):
        return None
    return Metric(id=metric_id or id, label=label or x["label"], value=round(x["value"] * scale, 2),
                  unit=unit if unit is not None else (x["unit"] or ""), source=Source(**x["source"]))


def src(s: Site, id: str) -> Source:
    x = facts(s)["by_id"].get(id)
    return Source(**x["source"]) if x else VEXCEL_LOOKUP


VEXCEL_LOOKUP = Source(layer="vexcel", method="lookup", confidence="medium", note="Vexcel Elements")


def capture(s: Site) -> str:
    c = facts(s).get("capture") or {}
    return f"{str(c.get('date') or '')[:10]} ({c.get('collection')})" if c.get("date") else "unknown date"


def footprint(s: Site) -> Polygon | None:
    w = facts(s).get("footprint")
    if not w:
        return None
    g = shapely_wkt.loads(w)
    # Vexcel sometimes returns a MultiPolygon (a building in parts): the largest part stands for the building
    return max(g.geoms, key=lambda p: p.area) if hasattr(g, "geoms") else g


def parcel(s: Site):
    g = facts(s).get("parcel")
    return shape(g) if g else None


# ---- local metres, anchors, overlays -----------------------------------------------------------------

def dist_m(a, b) -> float:
    """Metres between two (lon, lat) points (flat approximation, fine within a city block)."""
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * 111320.0 * k, (a[1] - b[1]) * 110574.0)


def to_m(lat0: float):
    """(lon, lat) -> (east, north) metres from (0, 0) longitude-latitude scaled at lat0, and back."""
    k = 111320.0 * math.cos(math.radians(lat0))
    return (lambda x, y, z=None: (x * k, y * 110574.0)), (lambda x, y, z=None: (x / k, y / 110574.0))


def metres(geom, lat0: float):
    return shapely.transform(geom, lambda c: c * (111320.0 * math.cos(math.radians(lat0)), 110574.0))


def lonlat(geom, lat0: float):
    return shapely.transform(geom, lambda c: c / (111320.0 * math.cos(math.radians(lat0)), 110574.0))


def geo(lon: float, lat: float) -> GeoAnchor:
    return GeoAnchor(geo=(round(lon, 7), round(lat, 7)))


def pin(id: str, lon: float, lat: float, label: str, status: str) -> Pin:
    return Pin(id=id, anchor=geo(lon, lat), label=label, status=status)


def geo_route(points: list[tuple[float, float]], label: str, chokes: list[tuple[tuple[float, float], float, str]] = ()) -> RouteOverlay:
    """A route on the map. Contract 4 has no geographic route, so this uses floor "geo" and points as
    [lon, lat, 0]; a scan renderer finds no floor called "geo" and skips it. Reported to the lead."""
    return RouteOverlay(floor="geo", label=label, points=[(round(x, 7), round(y, 7), 0.0) for x, y in points],
                        chokes=[Choke(point=(round(p[0], 7), round(p[1], 7), 0.0), width=round(w, 2), status=st)
                                for p, w, st in chokes])


def pins(items: list[Pin]) -> list[PinsOverlay]:
    return [PinsOverlay(pins=items)] if items else []


def ortho_media(s: Site, size_m: float = 120, box_geom=None) -> Media:
    """The orthophoto served by /api/aerial/ortho; `box` frames a shape as fractions of the image."""
    box = None
    if box_geom is not None:
        x0, y0, x1, y1 = metres(box_geom, s.lat).bounds
        cx, cy = to_m(s.lat)[0](s.lon, s.lat)
        h = size_m / 2
        f = lambda v: round(min(1, max(0, v)), 4)
        box = (f((x0 - cx + h) / size_m), f((cy + h - y1) / size_m), f((x1 - cx + h) / size_m), f((cy + h - y0) / size_m))
    return Media(kind="ortho", ref=f"/api/aerial/ortho?lat={s.lat:.7f}&lon={s.lon:.7f}&size_m={size_m:g}&px=1024", box=box)


def oblique_media(s: Site, direction: str, size_m: float, box=None) -> Media:
    """An oblique crop served by /api/site/oblique (api/site_media.py). Contract 3 has no oblique media kind, so
    it is an "ortho" item whose ref names the oblique; reported to the lead."""
    return Media(kind="ortho", ref=f"/api/site/oblique?lat={s.lat:.7f}&lon={s.lon:.7f}&size_m={size_m:g}&direction={direction}",
                 box=box)


def compass(az: float) -> str:
    return ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][int((az % 360 + 22.5) // 45) % 8]


def bearing(a, b) -> float:
    """Compass bearing in degrees from (lon, lat) a to b."""
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.degrees(math.atan2((b[0] - a[0]) * k, b[1] - a[1])) % 360


def heights(kind: str, pts: list[tuple[float, float]], batch: int = 60) -> list[float]:
    """Vexcel surface ("dsm") or ground ("dtm") heights at (lon, lat) points, in batches: a long MULTIPOINT makes the
    GET URL too long (HTTP 414 at about 190 points)."""
    out: list[float] = []
    for i in range(0, len(pts), batch):
        out += aerial._heights(kind, [(round(x, 7), round(y, 7)) for x, y in pts[i:i + batch]])[0]
    return out
