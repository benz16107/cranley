"""Does a scan's floor plan sit on its building footprint? The scan frame to lat/lon convention is settled
(geometry.georef: yaw +1, translation "enu", checked by the walls workstream on 40 houses), so this places the plan
outline under that one convention, with the plan's verified footprint refit when it has one, and reports how well
it overlaps Vexcel's footprint. A poor overlap means a wrong footprint or a bad anchor, not another convention.
"""
from __future__ import annotations

from shapely.geometry import Polygon

from ...geometry import georef
from ...geometry.check_georef import outline_corners
from . import metres

CONVENTIONS = [(georef.YAW_SIGN, georef.TRANSLATION)]  # the settled one; the other three were ruled out
GOOD_IOU = 0.55   # the plan covers only the scanned floor area, and footprints include garages and eaves
FAIR_IOU = 0.35


def outline_lonlat(plan: dict, yaw_sign: int, translation: str) -> Polygon | None:
    try:
        corners = outline_corners(plan)
    except (ValueError, AttributeError):
        return None
    pts = [georef.to_latlon(plan, x, y, yaw_sign=yaw_sign, translation=translation) for x, y in corners]
    if len(pts) < 3 or any(p is None for p in pts):
        return None
    return Polygon([(lon, lat) for lat, lon in pts])


def check(plan: dict, footprint: Polygon | None) -> dict:
    """{available, yaw_sign, translation, iou, offset_m, confidence, matches_engine, tried}. `confidence` is high when
    the best convention overlaps the footprint by GOOD_IOU, medium by FAIR_IOU, else low."""
    if footprint is None or (plan.get("geo") or {}).get("yaw_deg") is None:
        return {"available": False, "confidence": "low",
                "reason": "No footprint from Vexcel or no geocoordinates on the scan, so the plan cannot be placed."}
    lat0 = plan["geo"]["lat"]
    fp = metres(footprint, lat0)
    tried = []
    for sign, tr in CONVENTIONS:
        o = outline_lonlat(plan, sign, tr)
        if o is None:
            continue
        om = metres(o, lat0).buffer(0)
        iou = om.intersection(fp).area / max(om.union(fp).area, 1e-9)
        tried.append({"yaw_sign": sign, "translation": tr, "iou": round(iou, 3),
                      "offset_m": round(om.centroid.distance(fp.centroid), 2), "outline": o})
    if not tried:
        return {"available": False, "confidence": "low", "reason": "The plan has no room outlines to place."}
    best = max(tried, key=lambda t: t["iou"])
    conf = "high" if best["iou"] >= GOOD_IOU else "medium" if best["iou"] >= FAIR_IOU else "low"
    rival = max((t for t in tried if t["yaw_sign"] != best["yaw_sign"]), key=lambda t: t["iou"], default=None)
    if conf == "high" and rival and best["iou"] - rival["iou"] < 0.05 and abs(plan["geo"]["yaw_deg"]) > 10:
        conf = "medium"  # both rotations fit about as well, so door positions outside are uncertain by 2 * yaw
    return {"available": True, **{k: best[k] for k in ("yaw_sign", "translation", "iou", "offset_m", "outline")},
            "confidence": conf,
            "matches_engine": (best["yaw_sign"], best["translation"]) == (georef.YAW_SIGN, georef.TRANSLATION),
            "tried": [{k: t[k] for k in ("yaw_sign", "translation", "iou", "offset_m")} for t in tried]}


def to_lonlat(plan: dict, a: dict, x: float, y: float) -> tuple[float, float]:
    lat, lon = georef.to_latlon(plan, x, y, yaw_sign=a["yaw_sign"], translation=a["translation"])
    return lon, lat


def from_lonlat(plan: dict, a: dict, lon: float, lat: float) -> tuple[float, float]:
    return georef.from_latlon(plan, lat, lon, yaw_sign=a["yaw_sign"], translation=a["translation"])
