"""Apparatus access from the air: the orthophoto with the Vexcel footprint drawn on it, read once by the vision model
for the street side (side A), driveways, gates, overhead obstructions and where the first engine parks. The model
only picks and boxes; every position comes from the ortho's pixel transform, every distance from geometry."""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw
from shapely import wkt as shapely_wkt
from shapely.geometry import Point

from ...aerial import site as aerial

COMPASS = ["N", "E", "S", "W"]          # clockwise, as seen from above
SIDE_NAMES = ["A", "B", "C", "D"]       # A is the address side, then clockwise: B is on your left facing A
ACCESS_SRC = {"layer": "vexcel", "method": "vision", "confidence": "low",
              "note": "Vision model on the Vexcel orthophoto chose and boxed these; positions from the ortho transform"}

BOX = {"type": "object", "additionalProperties": False, "required": ["x0", "y0", "x1", "y1"],
       "properties": {k: {"type": "integer"} for k in ("x0", "y0", "x1", "y1")}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["front_side", "street_sides", "engine_spot", "driveways", "gates_and_fences", "overhead", "note",
                 "confidence"],
    "properties": {
        "front_side": {"type": "string", "enum": COMPASS, "description": "Side of the outlined building facing the "
                       "street it is addressed on"},
        "street_sides": {"type": "array", "items": {"type": "string", "enum": COMPASS}},
        "engine_spot": BOX,
        "driveways": {"type": "array", "items": BOX},
        "gates_and_fences": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                         "required": ["kind", "box"], "properties": {
                                                             "kind": {"type": "string", "enum": ["gate", "fence", "wall"]},
                                                             "box": BOX}}},
        "overhead": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                 "required": ["kind", "box"], "properties": {
                                                     "kind": {"type": "string", "enum": ["tree canopy over the drive",
                                                                                         "power lines", "carport or canopy",
                                                                                         "other"]},
                                                     "box": BOX}}},
        "note": {"type": "string", "description": "One sentence on apparatus access, no measurements"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    }}


def side_of(bearing_deg: float, front: str) -> str:
    """Side letter (A to D) for a compass bearing from the building's centre."""
    quad = round((bearing_deg % 360) / 90) % 4
    return SIDE_NAMES[(quad - COMPASS.index(front)) % 4]


def sides(front: str) -> dict[str, str]:
    """{"A": "S", "B": "W", ...}: each side letter and the compass face it is."""
    i = COMPASS.index(front)
    return {SIDE_NAMES[k]: COMPASS[(i + k) % 4] for k in range(4)}


def bearing(lat0: float, lon0: float, lat: float, lon: float) -> float:
    e = (lon - lon0) * 111320.0 * math.cos(math.radians(lat0))
    n = (lat - lat0) * 110574.0
    return math.degrees(math.atan2(e, n)) % 360


def metres(lat0: float, lon0: float, lat: float, lon: float) -> float:
    return math.hypot((lon - lon0) * 111320.0 * math.cos(math.radians(lat0)), (lat - lat0) * 110574.0)


def _draw(o, footprint) -> bytes:
    im = Image.open(io.BytesIO(o.image)).convert("RGB")
    if footprint is not None:
        d = ImageDraw.Draw(im)
        for g in getattr(footprint, "geoms", [footprint]):
            d.line([o.to_px(x, y) for x, y in g.exterior.coords], fill=(255, 40, 40), width=3)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def access(lat: float, lon: float, size_m: float = 80) -> dict:
    """Facts, footprint, ortho (with its transform) and the access reading for a building at lat, lon."""
    from ...vision.model import ask
    facts = aerial.site_facts(lat, lon)
    fp = shapely_wkt.loads(facts["footprint"]) if facts.get("footprint") else None
    if fp is not None:  # centre on the building, not the address point, and fit all of it
        c = fp.centroid
        w, s, e, n = fp.bounds
        size_m = max(size_m, metres(s, w, n, e) + 30)
        lat, lon = c.y, c.x
    o = aerial.ortho(lat, lon, size_m, 1024)
    marked = _draw(o, fp)
    prompt = (f"A north-up aerial photo, {o.width} by {o.height} pixels; north is up. The building of interest is "
              "outlined in red. You are planning a fire department response. Say which compass side of the outlined "
              "building faces the street it is addressed on, which sides touch a street, and box: where the first "
              "fire engine should park (on the street or drive, beside the front), each driveway onto the lot, each "
              "gate, fence or wall that limits access, and anything overhead that would stop a ladder truck (trees "
              "over the drive, power lines, carports). Return empty lists when none are visible.")
    a = ask([marked], prompt, SCHEMA, key=f"fire_access/{lat:.6f},{lon:.6f},{size_m}")

    def geo(b) -> tuple[float, float]:
        return o.to_lonlat((b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2)

    centre = fp.centroid if fp is not None else Point(lon, lat)
    eng = geo(a["engine_spot"])
    out = {"lat": lat, "lon": lon, "facts": facts, "footprint": fp, "ortho": o, "image": marked,
           "front": a["front_side"], "street_sides": a["street_sides"], "sides": sides(a["front_side"]),
           "engine": {"lonlat": eng, "from_building_m": None if fp is None else
                      _to_m(lat, fp.boundary.distance(Point(*eng)))},
           "driveways": [geo(b) for b in a["driveways"]],
           "barriers": [{"kind": g["kind"], "lonlat": geo(g["box"])} for g in a["gates_and_fences"]],
           "overhead": [{"kind": g["kind"], "lonlat": geo(g["box"])} for g in a["overhead"]],
           "note": a["note"], "confidence": a["confidence"], "centre": (centre.x, centre.y)}
    return out


def _to_m(lat: float, deg: float) -> float:
    # shortcut: degrees to metres with the mean of the two axis scales; fine at lot scale (< 1% at these latitudes)
    return deg * (111320.0 * math.cos(math.radians(lat)) + 110574.0) / 2
