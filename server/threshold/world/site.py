"""Everything the web scene needs to stand a scan in its surroundings, in one answer."""
from __future__ import annotations

import httpx

from ..config import DATA
from ..sources import footprint, matterport as mp
from ..sources.upstream import check
from . import frame, tiles3d

ORTHO = ((360, 2048), (90, 1536))  # (metres across, pixels): the neighbourhood, then the lot at close to native detail
FLOOR_ABOVE_GROUND_M = 0.2        # assumed: a slab-on-grade house floor sits about this far above the soil


def has_interior_splat(sid: str) -> bool:
    """Whether the splat workstream has written an interior splat for this scan (its files are
    `$THRESHOLD_DATA_DIR/splat/<sid>/interior.json` beside `interior.spz` or `interior.ply`)."""
    check(sid, "sid")
    d = DATA / "splat" / sid
    return (d / "interior.json").exists() and ((d / "interior.spz").exists() or (d / "interior.ply").exists())


def describe(sid: str) -> dict:
    plan = mp.plan(sid)
    fr = frame.scan_to_enu(plan)
    if fr is None:
        return {"sid": sid, "available": False, "note": "This scan has no geocoordinates, so it cannot be placed in its surroundings."}
    lat, lon = plan["geo"]["lat"], plan["geo"]["lon"]
    fit, ring = footprint.scan_fit(plan, fetch=False)
    try:
        cover = tiles3d.coverage(lat, lon)
    except (LookupError, KeyError, OSError, httpx.HTTPError):  # Vexcel down or no key: the terrain route may still be cached
        cover = None
    return {
        "sid": sid, "available": True, "anchor": {"lat": lat, "lon": lon},
        "scan_to_enu": fr,
        "georef": {"verified": fr["verified"], "iou": (fit or {}).get("iou"), "residual_m": (fit or {}).get("residual_m"),
                   "note": "Placed by fitting the plan to the aerial footprint." if fr["verified"] else
                   "Placed by the scan's own GPS, typically 2 m off."},
        "footprint_enu": ring,
        "floor_above_ground_m": FLOOR_ABOVE_GROUND_M,
        "tiles3d": cover and {"url": f"/api/world/{sid}/tiles", "capture": cover["capture"], "copyright": cover["copyright"]},
        "terrain": f"/api/world/{sid}/terrain",
        "splat": bool(plan["has"].get("splat")),
    }
