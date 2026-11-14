"""Scan frame to east/north metres and lat/lon, window compass directions, and when the sun reaches each window.

The conversion is  ENU = Rz(YAW_SIGN * yaw_deg) p + t, with t = geo.translation in east/north metres.

Verified 2026-11-14 against Vexcel building footprints on 40 Houston and Los Angeles houses
(`server/scripts/check_compass.py`): this convention overlapped the footprint best in 25 of 40 (median IoU 0.57
against 0.16 to 0.30 for the other three), and fitted it in all 21 houses whose yaw is far enough from 0 and 180
degrees for the sign to matter. The footprint refit then needs a median 3.3 degree turn and a 1.9 m shift.
So the rotation is good to a few degrees but the position is off by about 2 m (GPS); a per-scan correction
is in `plan.geo.fit`, and `plan.quality.georef` is true only when that fit succeeded."""
from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

from shapely.geometry import Point
from shapely.ops import unary_union

from ._plan import (
    geo_source,
    polygons,
    rooms_by_id,
    unavailable,
    wall_normal,
    walls_by_id,
)

YAW_SIGN = 1                  # +1: yaw_deg turns scan axes onto east/north counter-clockwise (verified, see above)
TRANSLATION = "enu"           # "enu": ENU = R p + t, t in east/north metres. "scan" (R(p - t)) was 3.5x further off
VERIFIED = True
WGS84_A, WGS84_E2 = 6378137.0, 6.69437999014e-3
COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def _geo(plan: dict):
    g = plan.get("geo") or {}
    if g.get("lat") is None or g.get("lon") is None or g.get("yaw_deg") is None:
        return None
    t = g.get("translation") or {}
    return g["lat"], g["lon"], g["yaw_deg"], (t.get("x") or 0.0, t.get("y") or 0.0)


def _rot(x: float, y: float, deg: float) -> tuple[float, float]:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return x * c - y * s, x * s + y * c


def _fit(plan: dict, yaw_sign: int, translation: str, raw: bool) -> dict | None:
    """The verified footprint refit (plan.geo.fit), applied on top of the default convention only."""
    f = (plan.get("geo") or {}).get("fit")
    if raw or not f or not f.get("verified") or (yaw_sign, translation) != (YAW_SIGN, TRANSLATION):
        return None
    return f


def to_enu(plan: dict, x: float, y: float, yaw_sign: int = YAW_SIGN, translation: str = TRANSLATION, raw: bool = False):
    """Scan (x, y) to (east, north) metres from the geo anchor. None when the scan has no geocoordinates.
    Applies the verified footprint refit (plan.geo.fit) unless raw is set."""
    g = _geo(plan)
    if g is None:
        return None
    _, _, yaw, (tx, ty) = g
    if translation == "scan":
        return _rot(x - tx, y - ty, yaw_sign * yaw)
    e, n = _rot(x, y, yaw_sign * yaw)
    e, n = e + tx, n + ty
    f = _fit(plan, yaw_sign, translation, raw)
    if f:
        (px, py), (dx, dy) = f["pivot_enu"], f["shift_enu"]
        e, n = _rot(e - px, n - py, f["rotation_deg"])
        e, n = e + px + dx, n + py + dy
    return e, n


def from_enu(plan: dict, e: float, n: float, yaw_sign: int = YAW_SIGN, translation: str = TRANSLATION, raw: bool = False):
    g = _geo(plan)
    if g is None:
        return None
    _, _, yaw, (tx, ty) = g
    f = _fit(plan, yaw_sign, translation, raw)
    if f:
        (px, py), (dx, dy) = f["pivot_enu"], f["shift_enu"]
        e, n = _rot(e - px - dx, n - py - dy, -f["rotation_deg"])
        e, n = e + px, n + py
    if translation == "scan":
        x, y = _rot(e, n, -yaw_sign * yaw)
        return x + tx, y + ty
    return _rot(e - tx, n - ty, -yaw_sign * yaw)


def _radii(lat: float) -> tuple[float, float]:
    s2 = math.sin(math.radians(lat)) ** 2
    m = WGS84_A * (1 - WGS84_E2) / (1 - WGS84_E2 * s2) ** 1.5
    nr = WGS84_A / math.sqrt(1 - WGS84_E2 * s2)
    return m, nr


def to_latlon(plan: dict, x: float, y: float, **conv):
    """Scan (x, y) to (lat, lon) in degrees (local tangent plane; exact to millimetres across a building)."""
    enu = to_enu(plan, x, y, **conv)
    if enu is None:
        return None
    lat0, lon0, _, _ = _geo(plan)
    m, nr = _radii(lat0)
    return lat0 + math.degrees(enu[1] / m), lon0 + math.degrees(enu[0] / (nr * math.cos(math.radians(lat0))))


def from_latlon(plan: dict, lat: float, lon: float, **conv):
    g = _geo(plan)
    if g is None:
        return None
    lat0, lon0, _, _ = g
    m, nr = _radii(lat0)
    n = math.radians(lat - lat0) * m
    e = math.radians(lon - lon0) * nr * math.cos(math.radians(lat0))
    return from_enu(plan, e, n, **conv)


def azimuth_of(plan: dict, dx: float, dy: float, **conv) -> float | None:
    """Compass bearing (degrees clockwise from north) of a direction given in the scan frame."""
    g = _geo(plan)
    if g is None:
        return None
    sign = conv.get("yaw_sign", YAW_SIGN)
    f = _fit(plan, sign, conv.get("translation", TRANSLATION), conv.get("raw", False))
    e, n = _rot(dx, dy, sign * g[2] + (f["rotation_deg"] if f else 0.0))
    return math.degrees(math.atan2(e, n)) % 360


def compass(az: float) -> str:
    return COMPASS[int((az + 11.25) // 22.5) % 16]


def facing(plan: dict) -> dict:
    """Outward compass direction of every window and doorway with a room on one side only."""
    if _geo(plan) is None:
        return unavailable("This scan has no geocoordinates.")
    walls, rooms, polys = walls_by_id(plan), rooms_by_id(plan), polygons(plan)
    outline = unary_union([p for p in polys.values() if p is not None])
    out = []
    for o in plan.get("openings") or []:
        if len(o.get("rooms") or []) > 1:  # an interior window or door faces another room, not a direction
            continue
        w = walls.get(o["wall"])
        if w is None:
            continue
        nx, ny = wall_normal(w)
        probe = Point(o["center"][0] + 0.3 * nx, o["center"][1] + 0.3 * ny)
        room_poly = polys.get((o.get("rooms") or [None])[0])
        inside = room_poly.contains(probe) if room_poly is not None else \
            (not outline.is_empty and outline.contains(probe))
        if inside:
            nx, ny = -nx, -ny
        az = azimuth_of(plan, nx, ny)
        out.append({"opening": o["id"], "type": o["type"], "room": (o.get("rooms") or [None])[0],
                    "room_label": rooms.get((o.get("rooms") or [None])[0], {}).get("label"),
                    "azimuth_deg": az, "compass": compass(az), "width": o["width"], "height": o["height"],
                    "sill": o["sill"], "center": o["center"]})
    return {"available": True, "openings": out, "verified": VERIFIED,
            "source": geo_source("Wall normals turned by geo.yaw_deg (convention checked on 40 houses against "
                                 "Vexcel footprints; typical error 3 degrees).", "medium" if VERIFIED else "low")}


# ---- sun position (NOAA solar calculator equations) ----

def sun_position(when: dt.datetime, lat: float, lon: float) -> tuple[float, float]:
    """(azimuth clockwise from north, elevation) in degrees for an aware datetime. Accurate to about 0.1 deg
    for 1900-2100; no refraction correction."""
    u = when.astimezone(dt.UTC)
    jd = u.timestamp() / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + T * (36000.76983 + T * 0.0003032)) % 360
    M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
    ecc = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
    Mr = math.radians(M)
    C = (math.sin(Mr) * (1.914602 - T * (0.004817 + 0.000014 * T)) + math.sin(2 * Mr) * (0.019993 - 0.000101 * T)
         + math.sin(3 * Mr) * 0.000289)
    om = math.radians(125.04 - 1934.136 * T)
    lam = math.radians(L0 + C - 0.00569 - 0.00478 * math.sin(om))
    eps0 = 23 + (26 + (21.448 - T * (46.815 + T * (0.00059 - T * 0.001813))) / 60) / 60
    eps = math.radians(eps0 + 0.00256 * math.cos(om))
    decl = math.asin(math.sin(eps) * math.sin(lam))
    y = math.tan(eps / 2) ** 2
    L0r = math.radians(L0)
    eqt = 4 * math.degrees(y * math.sin(2 * L0r) - 2 * ecc * math.sin(Mr) + 4 * ecc * y * math.sin(Mr) * math.cos(2 * L0r)
                           - 0.5 * y * y * math.sin(4 * L0r) - 1.25 * ecc * ecc * math.sin(2 * Mr))
    minutes = u.hour * 60 + u.minute + u.second / 60
    ha = (minutes + eqt + 4 * lon) / 4 - 180
    ha = ha + 360 if ha < -180 else ha
    phi, har = math.radians(lat), math.radians(ha)
    cosz = max(-1.0, min(1.0, math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(decl) * math.cos(har)))
    z = math.acos(cosz)
    denom = math.cos(phi) * math.sin(z)
    if abs(denom) < 1e-9:
        az = 180.0
    else:
        a = math.degrees(math.acos(max(-1.0, min(1.0, (math.sin(phi) * cosz - math.sin(decl)) / denom))))
        az = (a + 180) % 360 if ha > 0 else (540 - a) % 360
    return az, 90 - math.degrees(z)


def guess_timezone(lon: float) -> str:
    # shortcut: the scans are Houston and Los Angeles only; use a real tz lookup if other cities arrive
    return "America/Los_Angeles" if lon < -105 else "America/Chicago"


def sun_on_windows(plan: dict, date: dt.date, tz: str | None = None, step_min: int = 10) -> dict:
    """For each window and exterior door: the local times on `date` when the sun is up and in front of it
    (within 90 degrees of its outward direction). Ignores trees, neighbours, eaves and overhangs."""
    f = facing(plan)
    if not f["available"]:
        return f
    lat, lon = plan["geo"]["lat"], plan["geo"]["lon"]
    zone = ZoneInfo(tz or guess_timezone(lon))
    start = dt.datetime.combine(date, dt.time(0, 0), zone)
    times = [start + dt.timedelta(minutes=m) for m in range(0, 24 * 60, step_min)]
    suns = [(t, *sun_position(t, lat, lon)) for t in times]
    out = []
    for o in f["openings"]:
        lit = [(t, az, el) for t, az, el in suns if el > 0 and abs((az - o["azimuth_deg"] + 180) % 360 - 180) < 90]
        spans, cur = [], None
        for t, _, _ in lit:
            if cur and t - cur[1] <= dt.timedelta(minutes=step_min):
                cur[1] = t
            else:
                cur = [t, t]
                spans.append(cur)
        out.append({**{k: o[k] for k in ("opening", "type", "room", "room_label", "azimuth_deg", "compass")},
                    "sun": [[a.strftime("%H:%M"), (b + dt.timedelta(minutes=step_min)).strftime("%H:%M")] for a, b in spans],
                    "hours": len(lit) * step_min / 60})
    rise = next((t for t, _, el in suns if el > 0), None)
    sets = next((t for t, _, el in reversed(suns) if el > 0), None)
    return {"available": True, "date": date.isoformat(), "timezone": zone.key, "openings": out,
            "sunrise": rise.strftime("%H:%M") if rise else None, "sunset": sets.strftime("%H:%M") if sets else None,
            "verified": VERIFIED,
            "source": geo_source("NOAA solar position; window directions from geo.yaw_deg (typical error 3 "
                                 "degrees); shading by trees, neighbours and eaves not counted.", "medium" if VERIFIED else "low")}
