"""Aerial site reader: Vexcel property facts, orthophotos with a pixel transform, elevations, obliques."""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field

import shapely
from PIL import Image
from shapely import wkt as shapely_wkt
from shapely.affinity import scale
from shapely.geometry import shape

from . import vexcel

LAYERS = "urban,urban-r,wide-area,urban-g"
R = 6378137.0  # Web Mercator sphere radius; Vexcel orthos come back in this projection
OBLIQUES = ("oblique-north", "oblique-south", "oblique-east", "oblique-west")


def source(method: str, confidence: str, note: str, layer: str = "vexcel") -> dict:
    return {"layer": layer, "method": method, "confidence": confidence, "note": note}


def point(lat: float, lon: float) -> str:
    return f"POINT({lon} {lat})"


def square(lat: float, lon: float, size_m: float) -> str:
    """A WKT square `size_m` across, centred on the point (lon lat order)."""
    dlat = size_m / 2 / 110574.0
    dlon = size_m / 2 / (111320.0 * math.cos(math.radians(lat)))
    w, e, s, n = lon - dlon, lon + dlon, lat - dlat, lat + dlat
    return f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"


def area_m2(geom, lat: float) -> float:
    """Area of a lon/lat shape in square metres (local flat approximation, fine at lot scale)."""
    return scale(geom, 111320.0 * math.cos(math.radians(lat)), 110574.0, origin=(0, 0)).area


# ---- property facts -------------------------------------------------------

def _fact(id: str, label: str, value, unit: str | None, src: dict) -> dict:
    return {"id": id, "label": label, "value": value, "unit": unit, "source": src}


def property_raw(lat: float, lon: float) -> dict:
    return vexcel.get_json("property/extract", wkt=point(lat, lon), srid=4326, include="precomputed,calculated")


def site_facts(lat: float, lon: float) -> dict:
    """The useful `/property/extract` fields as Contract 3 metrics, plus the footprint and parcel shapes."""
    feats = property_raw(lat, lon).get("features") or []
    if not feats:
        return {"lat": lat, "lon": lon, "facts": [], "footprint": None, "parcel": None, "capture": None}
    f = feats[0]
    p = f["properties"]
    structs = p.get("structures") or []
    s = next((x for x in structs if x.get("primary-structure")), structs[0] if structs else {})
    cap = f"capture {str(p.get('metadata.ortho-date-estimate') or '')[:10]}, {p.get('metadata.collection')}"
    look = source("lookup", "high", f"Vexcel Elements precomputed; {cap}")
    model = source("lookup", "medium", f"Vexcel Elements model output; Vexcel publishes no accuracy figures; {cap}")
    calc = source("lookup", "medium", f"Vexcel calculated from its surface model; {cap}")
    parcel = shape(f["geometry"]) if f.get("geometry") else None
    out: list[dict] = []

    def add(id, label, value, unit, src):
        if value is not None:
            out.append(_fact(id, label, value, unit, src))

    add("building_type", "Building type", s.get("building-type.class"), None, model)
    add("structures", "Structures on the parcel", p.get("structure.count"), "count", look)
    add("footprint_area", "Building footprint", _r(s.get("footprint.area")), "m2", look)
    add("roof_height", "Roof height above ground", _r(s.get("roof-characteristics.height")), "m", calc)
    add("roof_elevation", "Roof elevation", _r(s.get("roof-characteristics.elevation")), "m", calc)
    add("ground_elevation", "Ground elevation at the building", _r(s.get("ground-elevation.value")), "m", calc)
    add("roof_material", "Roof material", s.get("roof-characteristics.material.class"), None, model)
    add("roof_shape", "Roof shape", s.get("roof-characteristics.shape.value"), None, model)
    add("roof_condition", "Roof condition", s.get("roof-characteristics.condition.precise-value"), "score",
        source("lookup", "low", f"Vexcel model score; Vexcel does not publish the scale; {cap}"))
    add("roof_tree_cover", "Tree cover over the roof", s.get("roof-characteristics.tree-cover.percent"), "%", model)
    add("solar", "Solar panels", s.get("roof-objects.solar.value"), None, model)
    for obj in ("ac-unit", "chimney", "roof-vent", "satellite-dish", "skylight"):
        add(f"roof_{obj.replace('-', '_')}", f"Roof {obj.replace('-', ' ')}s", s.get(f"roof-objects.{obj}.count"), "count", model)
    defects = [k[len("roof-defects."):-len(".detected")] for k, v in s.items() if k.startswith("roof-defects.") and k.endswith(".detected") and v]
    defects = [d.split(".")[-1] for d in defects]  # discoloration subtypes come as "discoloration.types.water-pooling"
    add("roof_defects", "Roof defects detected", defects, None, model)
    for d in defects:  # the share of the roof each defect covers
        pct = s.get(f"roof-defects.{d}.percent", s.get(f"roof-defects.discoloration.types.{d}.percent"))
        add(f"roof_defect_{d.replace('-', '_')}", f"Roof {d.replace('-', ' ')}", _r(pct), "%", model)
    add("pool", "Pool", p.get("pool.detected"), None, model)
    add("pool_area", "Pool area", _r(p.get("pool.total-area")), "m2", model)
    for kind in ("in-ground", "above-ground", "hot-tub"):
        if p.get(f"pool.types.{kind}.detected"):
            add(f"pool_{kind.replace('-', '_')}", f"Pool type {kind}", True, None, model)
            k = kind.replace("-", "_")
            add(f"pool_{k}_enclosed", f"Pool {kind}, enclosed (fenced)", p.get(f"pool.types.{kind}.enclosed.count"), "count", model)
            add(f"pool_{k}_open", f"Pool {kind}, not enclosed", p.get(f"pool.types.{kind}.non-enclosed.count"), "count", model)
            add(f"pool_{k}_distance", f"Pool {kind}, distance to the building", _r(p.get(f"pool.types.{kind}.distance")), "m", model)
    add("vehicles", "Vehicles on the parcel on capture day", p.get("vehicles.count") or 0 if p.get("vehicles.detected") is not None else None, "count", model)
    add("paved_percent", "Paved (hardscape) share of the parcel", p.get("hardscapes.percent"), "%", model)
    if parcel is not None:
        pa = area_m2(parcel, lat)
        add("parcel_area", "Parcel area", round(pa, 1), "m2", source("geometry", "medium", f"Area of Vexcel's parcel polygon (parcel source {p.get('parcel-source')})"))
        if p.get("hardscapes.percent") is not None:
            add("paved_area", "Paved area (estimated)", round(pa * p["hardscapes.percent"] / 100, 1), "m2",
                source("geometry", "low", "Vexcel paved share times parcel area; Vexcel's own hardscapes.area field has an unstated unit"))
    add("parcel_tree_cover", "Tree cover on the parcel", p.get("parcel-tree-cover.percent"), "%", model)
    for thing in ("deck", "enclosure", "sport-court", "trampoline", "playground"):
        if p.get(f"{thing}.detected"):
            add(thing.replace("-", "_"), thing.replace("-", " ").capitalize(), True, None, model)
    for z, ft in zip(range(1, 5), (5, 30, 100, 200)):
        add(f"defensible_zone{z}_tree", f"Tree cover within {ft} ft of the building", s.get(f"defensible-space.zone{z}-tree"), "%", model)
    return {
        "lat": lat, "lon": lon, "facts": out,
        "footprint": s.get("footprint.wkt"),
        "parcel": f.get("geometry"),
        "inside_parcel": p.get("request-information.inside-parcel"),
        "capture": {"date": p.get("metadata.ortho-date-estimate"), "collection": p.get("metadata.collection"),
                    "gsd_m": p.get("metadata.gsd")},
    }


def _r(x, nd: int = 2):
    return None if x is None else round(float(x), nd)


# ---- orthophoto -------------------------------------------------------------

def _merc(lon: float, lat: float) -> tuple[float, float]:
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def _unmerc(x: float, y: float) -> tuple[float, float]:
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)


def _xmp(img: Image.Image) -> dict[str, str]:
    raw = img.info.get("xmp", b"")
    raw = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
    return dict(re.findall(r"<Vexcel:([\w-]+)>([^<]*)</Vexcel:", raw))


@dataclass
class Ortho:
    """A north-up orthophoto and the exact transform between its pixels and lon, lat.

    Vexcel returns the image in Web Mercator and writes its true bounds into the XMP metadata, so the
    transform is linear in Mercator metres across those bounds.
    """
    image: bytes
    width: int
    height: int
    bounds: tuple[float, float, float, float]  # west, south, east, north
    meta: dict = field(default_factory=dict)

    def to_px(self, lon: float, lat: float) -> tuple[float, float]:
        w, s, e, n = self.bounds
        (x0, y0), (x1, y1), (x, y) = _merc(w, n), _merc(e, s), _merc(lon, lat)
        return (x - x0) / (x1 - x0) * self.width, (y0 - y) / (y0 - y1) * self.height

    def to_lonlat(self, px: float, py: float) -> tuple[float, float]:
        w, s, e, n = self.bounds
        (x0, y0), (x1, y1) = _merc(w, n), _merc(e, s)
        return _unmerc(x0 + px / self.width * (x1 - x0), y0 - py / self.height * (y0 - y1))

    @property
    def metres_per_px(self) -> float:
        w, s, e, n = self.bounds
        lat = (s + n) / 2
        return (e - w) * 111320.0 * math.cos(math.radians(lat)) / self.width

    def transform(self) -> dict:
        return {"crs": "EPSG:3857 linear over bounds", "bounds": self.bounds, "width": self.width,
                "height": self.height, "metres_per_px": round(self.metres_per_px, 4)}


def ortho(lat: float, lon: float, size_m: float = 60, px: int = 1024) -> Ortho:
    body = {"wkt": square(lat, lon, size_m), "srid": 4326, "layer": LAYERS, "crop": "bounding_box",
            "image-format": "jpeg", "destination-dimensions": f"{px},{px}"}
    data, _ = vexcel.call("POST", "ortho/extract", body=body)
    img = Image.open(io.BytesIO(data))
    meta = _xmp(img)
    g = shapely_wkt.loads(meta["geometry"]).bounds  # minx, miny, maxx, maxy = w, s, e, n
    return Ortho(data, img.width, img.height, g, {k: meta.get(k) for k in
                 ("collection", "first-capture-date", "last-capture-date", "min-gsd", "max-gsd", "layer")})


# ---- elevation --------------------------------------------------------------

def _heights(kind: str, lonlats: list[tuple[float, float]]) -> tuple[list[float], dict]:
    w = "MULTIPOINT(" + ",".join(f"({lo} {la})" for lo, la in lonlats) + ")"
    r = vexcel.get_json(f"{kind}/elevation", wkt=w, srid=4326)
    zs = [float(z) for z in shapely.get_coordinates(shapely_wkt.loads(r["wkt"]), include_z=True)[:, 2]]
    return zs,{"collection": (r.get("collection") or [None])[0], "layer": (r.get("layer") or [None])[0]}


GROUND_NOTE = ("Vexcel's bare-ground model (DTM) is a wide-area collection and its surface model (DSM) a city collection. "
               "On open ground they disagreed by 0.6 m (a Houston warehouse lot) to 1.6 m (a Houston house), DTM higher, "
               "so DSM minus DTM is not a reliable height. For a building's height use site_facts roof_height")


def ground_and_surface(lat: float, lon: float) -> dict:
    (dsm,), dm = _heights("dsm", [(lon, lat)])
    (dtm,), tm = _heights("dtm", [(lon, lat)])
    return {
        "lat": lat, "lon": lon,
        "surface_m": round(dsm, 2), "ground_m": round(dtm, 2), "height_above_ground_m": round(dsm - dtm, 2),
        "sources": {
            "surface_m": source("lookup", "high", f"Vexcel DSM {dm['collection']} ({dm['layer']})"),
            "ground_m": source("lookup", "medium", f"Vexcel DTM {tm['collection']} ({tm['layer']})"),
            "height_above_ground_m": source("geometry", "low", GROUND_NOTE),
        },
    }


def elevation_profile(a: tuple[float, float], b: tuple[float, float], n: int = 50) -> dict:
    """Surface and ground heights at `n` evenly spaced points from a=(lat, lon) to b=(lat, lon)."""
    n = max(2, min(n, 200))
    pts = [(a[1] + (b[1] - a[1]) * i / (n - 1), a[0] + (b[0] - a[0]) * i / (n - 1)) for i in range(n)]
    dsm, dm = _heights("dsm", pts)
    dtm, tm = _heights("dtm", pts)
    length = math.hypot((b[1] - a[1]) * 111320.0 * math.cos(math.radians((a[0] + b[0]) / 2)), (b[0] - a[0]) * 110574.0)
    return {
        "length_m": round(length, 2),
        "points": [{"d_m": round(length * i / (n - 1), 2), "lon": lo, "lat": la, "surface_m": round(s, 2), "ground_m": round(g, 2)}
                   for i, ((lo, la), s, g) in enumerate(zip(pts, dsm, dtm))],
        "sources": {"surface_m": source("lookup", "high", f"Vexcel DSM {dm['collection']}"),
                    "ground_m": source("lookup", "medium", f"Vexcel DTM {tm['collection']}; " + GROUND_NOTE)},
    }


# ---- obliques ---------------------------------------------------------------

def oblique_directions(lat: float, lon: float) -> tuple[str | None, list[str]]:
    """Newest collection with obliques over the point, and which directions it has."""
    r = vexcel.get_json("oriented/collections", wkt=point(lat, lon), srid=4326, **{
        "product-type": "oblique", "order-by": "first-capture-date-desc", "total-records": 16,
        "include": "product-type,collection"})
    items = [f["properties"] for f in r.get("features") or []]
    # The newest collection may hold only some directions; take the newest one that has the most.
    by: dict[str, list[str]] = {}
    for it in items:
        by.setdefault(it["collection"], []).append(it["product-type"])
    best = max(by, key=lambda c: len(set(by[c]) & set(OBLIQUES)), default=None)
    return best, [d for d in OBLIQUES if best and d in by[best]]


def obliques(lat: float, lon: float, size_m: float = 60) -> list[dict]:
    """One oblique crop per side. `oblique-north` looks north, so it shows the building's south face."""
    coll, dirs = oblique_directions(lat, lon)
    out = []
    for d in dirs:
        try:
            data, _ = vexcel.call("GET", "oriented/extract", params={
                "wkt": square(lat, lon, size_m), "srid": 4326, "layer": LAYERS, "product-type": d,
                "collection": coll, "image-format": "jpeg", "rotation": "natural",
                "dem-priority": "vexcel-dsm,vexcel-dtm,public-dtm,flat-dtm"})
        except vexcel.VexcelError:
            continue
        img = Image.open(io.BytesIO(data))
        meta = _xmp(img)
        face = {"oblique-north": "south", "oblique-south": "north", "oblique-east": "west", "oblique-west": "east"}[d]
        out.append({"direction": d, "shows_face": face, "image": data, "width": img.width, "height": img.height,
                    "image_name": meta.get("image-name"), "capture_date": meta.get("capture-date"), "collection": coll})
    return out
