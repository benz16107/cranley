"""Public flood data reachable without a key: USGS high-water marks (Short-Term Network) and the FEMA flood zone.

Both are fetched once and cached under `$THRESHOLD_DATA_DIR/cache/public/`. Checked 2026-11-13:
- `https://api.waterdata.usgs.gov/stnservices/hwms.json` answers with every mark of every event (28 MB, filters
  ignored); the old `stn.wim.usgs.gov/STNServices` redirects to a web page. Harvey is event 180 (799 marks in
  the Houston box, 665 with a height above ground). Elevations are feet, vertical datum 2 = NAVD88.
- `hazards.fema.gov` (the NFHL map service) resets the TLS connection from this machine. Esri's hosted copy of
  FEMA's flood hazard areas (`USA_Flood_Hazard_Reduced_Set_gdb`) answers; it holds the special flood hazard
  areas only, so no feature means "outside the mapped 1% annual chance floodplain", not "no risk".
"""
from __future__ import annotations

import json
import math

import httpx

from ...config import CACHE

DIR = CACHE / "public"
HWM_URL = "https://api.waterdata.usgs.gov/stnservices/hwms.json"
EVENTS = {"harvey_2017": (180, "Hurricane Harvey, August 2017")}
FT = 0.3048
FEMA_URL = ("https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/USA_Flood_Hazard_Reduced_Set_gdb/"
            "FeatureServer/0/query")
# HWM quality codes: 1 excellent (+-0.05 ft) ... 4 poor (+-0.40 ft), 5 very poor, 6 unknown
GOOD_QUALITY = (1, 2, 3)


def metres_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return math.hypot((lat2 - lat1) * 110574.0, (lon2 - lon1) * 111320.0 * math.cos(math.radians(lat1)))


def event_marks(event: str) -> list[dict]:
    """High-water marks of one named event, Texas only, cached after the first (large) download."""
    eid, _ = EVENTS[event]
    f = DIR / f"usgs_hwm_{eid}.json"
    if not f.exists():
        r = httpx.get(HWM_URL, timeout=180, follow_redirects=True)
        r.raise_for_status()
        marks = [m for m in r.json() if m.get("event") == eid and 25.5 < (m.get("latitude_dd") or 0) < 36.6]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(marks))
    return json.loads(f.read_text())


def marks_near(event: str, lat: float, lon: float, radius_m: float) -> list[dict]:
    """Usable marks within `radius_m`: NAVD88 elevation, quality fair or better, nearest first, in metres."""
    out = []
    for m in event_marks(event):
        if m.get("vdatum") != 2 or m.get("elev_ft") in (None, "") or m.get("hwm_quality") not in GOOD_QUALITY:
            continue
        d = metres_between(lat, lon, m["latitude_dd"], m["longitude_dd"])
        if d <= radius_m:
            hag = m.get("height_above_ground")
            out.append({"id": m["id"], "lat": m["latitude_dd"], "lon": m["longitude_dd"], "distance_m": round(d),
                        "water_navd88_m": float(m["elev_ft"]) * FT,
                        "height_above_ground_m": float(hag) * FT if hag not in (None, "") else None,
                        "quality": m["hwm_quality"], "environment": m.get("environment"),
                        "waterbody": m.get("waterbody"), "description": m.get("location_description")})
    return sorted(out, key=lambda m: m["distance_m"])


def fema_zone(lat: float, lon: float) -> dict:
    """The FEMA flood zone at a point from Esri's hosted copy of the special flood hazard areas."""
    f = DIR / "fema" / f"{lat:.6f}_{lon:.6f}.json"
    if not f.exists():
        r = httpx.get(FEMA_URL, timeout=60, params={
            "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326, "returnGeometry": "false",
            "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DEPTH,DFIRM_ID", "f": "json"})
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise LookupError(f"Esri flood layer: {body['error']}")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(body))
    feats = json.loads(f.read_text()).get("features") or []
    if not feats:
        return {"in_sfha": False, "zone": None}
    a = feats[0]["attributes"]
    return {"in_sfha": a.get("SFHA_TF") == "T", "zone": a.get("FLD_ZONE"), "subtype": a.get("ZONE_SUBTY"),
            "bfe_ft": a.get("STATIC_BFE"), "depth_ft": a.get("DEPTH"), "dfirm": a.get("DFIRM_ID")}
