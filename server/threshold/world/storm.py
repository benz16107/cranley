"""Hurricane Harvey played through one scanned house, half hour by half hour.

Three real records are joined, and each keeps its own reliability:
- the peak: USGS high-water marks near the house, through the flood tool's own `harvey_depth` (low confidence);
- the timing: the stage record of the nearest USGS stream gauge for the storm week. The water at the house is taken
  to rise and fall by the same amount as at the gauge, with its peak set to the marks' peak (low confidence: water
  out of its banks in a street does not follow the channel exactly);
- the house: the flood tool's floor height above the ground and its still-water filling of rooms by sill height.

Nothing here invents a level. `timeline` is what the scene plays; `belongings` is the valuables tool's inventory with
the water level at which each item gets wet.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import math
from datetime import datetime

import httpx
import numpy as np
import shapely

from ..config import CACHE
from ..geometry._plan import polygons
from ..tools.flood_rehearsal import METHOD_NAME, floor_source
from ..tools.flood_rehearsal import public
from ..tools.flood_rehearsal.scenario import FloodInputs, indoor
from ..tools.flood_rehearsal.scenario import run as flood_run

DIR = CACHE / "public" / "nwis"
SITES = "https://waterservices.usgs.gov/nwis/site/"
IV = "https://nwis.waterservices.usgs.gov/nwis/iv/"      # the historical service; waterservices redirects old dates here
AGENT = {"User-Agent": "building-flood-rehearsal/0.1"}
WINDOW = ("2017-08-25T00:00-05:00", "2017-09-01T00:00-05:00")
EVENT = "Hurricane Harvey, 25 August to 1 September 2017"
FT = 0.3048
BOX_DEG = 0.14        # about 15 km each way
STEP_S = 1800
GRID_M, GRID_N = 192.0, 96       # the ground round the house the water is drawn on: 2 m cells
GRID_BELOW, GRID_RANGE = 3.0, 5.0  # heights are kept from 3 m under the lot's ground to 2 m over it, in 2 cm steps
COVER_M = 1.5                    # surface this far above the ground is a roof or a tree: water under it is not drawn


def gauges(lat: float, lon: float) -> list[dict]:
    """USGS stream gauges round a point that recorded stage during the storm, nearest first."""
    f = DIR / f"sites_{lat:.2f}_{lon:.2f}.rdb"
    if not f.exists():
        r = httpx.get(SITES, timeout=60, headers=AGENT, follow_redirects=True, params={
            "format": "rdb", "bBox": f"{lon - BOX_DEG:.4f},{lat - BOX_DEG:.4f},{lon + BOX_DEG:.4f},{lat + BOX_DEG:.4f}",
            "parameterCd": "00065", "hasDataTypeCd": "iv", "siteType": "ST", "siteOutput": "expanded",
            "startDT": WINDOW[0][:10], "endDT": WINDOW[1][:10]})
        r.raise_for_status()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(r.text)
    rows = list(csv.DictReader(io.StringIO("\n".join(x for x in f.read_text().splitlines() if not x.startswith("#"))),
                               delimiter="\t"))[1:]  # the first row after the header gives column widths
    out = []
    for x in rows:
        try:
            la, lo = float(x["dec_lat_va"]), float(x["dec_long_va"])
        except (KeyError, ValueError):
            continue
        out.append({"site_no": x["site_no"], "name": x["station_nm"], "lat": la, "lon": lo,
                    "datum": (x.get("alt_datum_cd") or "").strip(),
                    "distance_m": round(public.metres_between(lat, lon, la, lo))})
    return sorted(out, key=lambda g: g["distance_m"])


def stage(site_no: str) -> list[tuple[float, float]]:
    """(unix seconds, stage in metres) for the storm week at one gauge, as USGS recorded it."""
    f = DIR / f"iv_{site_no}_harvey.json"
    if not f.exists():
        r = httpx.get(IV, timeout=90, headers=AGENT, follow_redirects=True, params={
            "format": "json", "sites": site_no, "parameterCd": "00065", "startDT": WINDOW[0], "endDT": WINDOW[1]})
        r.raise_for_status()
        ts = r.json()["value"]["timeSeries"]
        vals = [(x["dateTime"], float(x["value"])) for x in (ts[0]["values"][0]["value"] if ts else [])
                if float(x["value"]) > -9000]
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(vals))
    return [(datetime.fromisoformat(t).timestamp(), v * FT) for t, v in json.loads(f.read_text())]


def hydrograph(lat: float, lon: float) -> dict | None:
    """The nearest gauge whose record holds through the storm (no gap over three hours), resampled to half hours."""
    for g in gauges(lat, lon)[:4]:
        s = stage(g["site_no"])
        if len(s) < 200 or max(b[0] - a[0] for a, b in zip(s, s[1:])) > 3 * 3600:
            continue
        t0 = math.ceil(s[0][0] / STEP_S) * STEP_S
        times, vals, i = [], [], 0
        for t in range(int(t0), int(s[-1][0]) + 1, STEP_S):
            while i + 1 < len(s) and s[i + 1][0] <= t:
                i += 1
            a, b = s[i], s[min(i + 1, len(s) - 1)]
            k = 0.0 if b[0] == a[0] else min(1.0, max(0.0, (t - a[0]) / (b[0] - a[0])))
            times.append(t)
            vals.append(a[1] + (b[1] - a[1]) * k)
        return {**g, "time": times, "stage_m": vals, "peak_m": max(vals), "peak_time": times[vals.index(max(vals))]}
    return None


def ground(plan: dict, lat: float, lon: float, ground_z: float) -> dict | None:
    """Vexcel's bare-ground model round the house as a grid in the scan frame, in scan z, with the lot's ground at
    `ground_z` (the flood tool's own reference). Cells under a roof or a tree (Vexcel's surface model well above
    the ground) are marked covered, except round the scanned house itself, where the water meets the walls."""
    from . import frame, terrain
    fr = frame.scan_to_enu(plan)
    polys = [p for p in polygons(plan).values() if p is not None]
    if fr is None or not polys:
        return None
    try:
        dtm = terrain.grid(lat, lon, GRID_M * 1.5, 96, kind="dtm")
        dsm = terrain.grid(lat, lon, GRID_M * 1.5, 192)
    except Exception:  # noqa: BLE001 - without the ground model the scene falls back to the drawn surroundings
        return None
    house = shapely.unary_union(polys)
    cx, cy = house.centroid.x, house.centroid.y
    x0, y0, cell = cx - GRID_M / 2, cy - GRID_M / 2, GRID_M / GRID_N
    ys, xs = np.mgrid[0:GRID_N, 0:GRID_N]
    x, y = x0 + (xs + 0.5) * cell, y0 + (ys + 0.5) * cell          # row 0 is the low-y edge
    a = math.radians(fr["rot_deg"])
    e = math.cos(a) * x - math.sin(a) * y + fr["t"][0]
    n = math.sin(a) * x + math.cos(a) * y + fr["t"][1]
    g = terrain.bilinear(dtm, e, n)
    above = terrain.sample(dsm, e, n) - g
    above -= np.nanpercentile(above, 10)     # the two models sit on different datums; open ground is where they agree
    z = ground_z + (g - float(terrain.bilinear(dtm, np.array([0.0]), np.array([0.0]))[0]))
    covered = (above > COVER_M) & ~shapely.contains_xy(house.buffer(2.5), x, y)
    v = np.clip(np.round((z - (ground_z - GRID_BELOW)) / GRID_RANGE * 254), 0, 254)
    v[covered | ~np.isfinite(z)] = 255
    return {"n": GRID_N, "rect": [round(x0, 3), round(y0, 3), GRID_M, GRID_M], "z0": round(ground_z - GRID_BELOW, 3),
            "range": GRID_RANGE, "b64": base64.b64encode(v.astype(np.uint8).tobytes()).decode(),
            "lowest_z": round(float(np.nanmin(np.where(covered, np.nan, z))), 2)}


def _flood(plan: dict) -> dict:
    return flood_run(plan, FloodInputs(scan=plan["sid"], depth_m=0.0, scenario="harvey_2017"), lambda _t: None)


def timeline(plan: dict) -> dict:
    """The storm at this house: a water level in the scan frame for every half hour, the level at which each room
    takes water, and where each number came from."""
    flood = _flood(plan)
    if flood["scenario_fallback"]:
        return {"sid": plan["sid"], "available": False, "reason": flood["scenario_fallback"]}
    site = flood["site"] or {}
    g = hydrograph(site["lat"], site["lon"])
    if g is None:
        return {"sid": plan["sid"], "available": False,
                "reason": "No USGS stream gauge within 15 km kept a whole stage record through Harvey."}
    sc, fl, lv, ref = flood["scenario"], flood["floor"], flood["levels"], flood["ref_z"]
    drop = [g["peak_m"] - v for v in g["stage_m"]]   # how far below its own peak the gauge stood
    rooms = [{"id": r["room"], "label": r["label"], "floor_z": round(r["floor_z"], 3),
              "floods_at": None if r.get("floods_at") is None else round(r["floods_at"], 3), "via": r.get("via")}
             for r in indoor(flood)]
    fsrc = floor_source(fl)
    ground_z = ref - fl["value_m"]
    grid = ground(plan, site["lat"], site["lon"], ground_z)
    # the part of the week worth playing: from two hours before the water reaches the lowest open ground near the
    # house to two hours after it leaves
    low = grid["lowest_z"] if grid else ground_z - 1.0
    wet = [i for i, d in enumerate(drop) if lv["hi"] - d > low]
    window = [max(0, wet[0] - 4), min(len(drop) - 1, wet[-1] + 4)] if wet else [0, len(drop) - 1]
    return {
        "sid": plan["sid"], "available": True, "event": EVENT,
        "time": g["time"], "tz_offset_h": -5,
        "level": [round(lv["mid"] - d, 3) for d in drop],
        "level_lo": [round(lv["lo"] - d, 3) for d in drop], "level_hi": [round(lv["hi"] - d, 3) for d in drop],
        "outside_m": [round(max(0.0, lv["mid"] - d - ground_z), 2) for d in drop],
        "inside_m": [round(max(0.0, lv["mid"] - d - ref), 2) for d in drop],
        "rooms_wet": [sum(1 for r in rooms if r["floods_at"] is not None and lv["mid"] - d > max(r["floods_at"], r["floor_z"]))
                      for d in drop],
        "ground_z": round(ground_z, 3), "floor_z": round(ref, 3), "peak_time": g["peak_time"],
        "window": window, "ground": grid,
        "peak": {"depth_m": round(sc["depth_m"], 2), "lo_m": round(sc["lo_m"], 2), "hi_m": round(sc["hi_m"], 2),
                 "inside_m": round(max(0.0, lv["mid"] - ref), 2)},
        "rooms": rooms,
        "marks": [{"lon": m["lon"], "lat": m["lat"], "distance_m": m["distance_m"], "quality": m["quality"]}
                  for m in sc.get("marks", [])],
        "sources": [
            {"what": "Peak water at the house", "confidence": sc["source"]["confidence"],
             "text": f"{sc['depth_m']:.2f} m above the lot's ground ({sc['lo_m']:.2f} to {sc['hi_m']:.2f} m). {sc['note']}"},
            {"what": "Hour by hour", "confidence": "low",
             "text": f"Stage record of USGS gauge {g['site_no']}, {g['name']}, {g['distance_m'] / 1000:.1f} km away. "
                     "The water at the house is taken to rise and fall by the same amount as at the gauge, with its "
                     "peak set to the high-water marks. Water out of its banks in a street does not follow the "
                     "channel exactly, so the hours are a guide."},
            {"what": "Floor above the ground", "confidence": fsrc.confidence,
             "text": f"{fl['value_m']:.2f} m ({fl['lo_m']:.2f} to {fl['hi_m']:.2f} m), from "
                     f"{METHOD_NAME.get(fl['method'], fl['method'])}."},
            {"what": "Water in the rooms", "confidence": "medium",
             "text": "Still water filling the rooms through doors and windows by sill height, from the scan's "
                     "measured openings. No flow, pressure or drainage; closed doors do not hold it back."},
            {"what": "Water in the street", "confidence": "medium",
             "text": "Drawn where Vexcel's bare-ground model is lower than the water level, on 2 m cells, with the "
                     "lot's ground set to the flood tool's own. Under roofs and trees it is not drawn. The ground "
                     "model is a wide-area survey: trust the pattern, not a single puddle."},
        ],
    }


def belongings(plan: dict) -> dict:
    """The valuables tool's inventory, with the water level (scan z) at which each item gets wet, and the loss range
    of what is under water at every step of the storm. Slow the first time: a vision model reads the rooms."""
    from ..tools.valuables_height import WICK_M, inventory
    flood = _flood(plan)
    tl = timeline(plan)
    if not tl["available"]:
        return {"sid": plan["sid"], "available": False, "reason": tl["reason"]}
    inv = inventory(plan, flood, 8, lambda _t: None)
    floods_at = {r["id"]: r["floods_at"] for r in tl["rooms"]}
    floor_z = {r["id"]: r["floor_z"] for r in tl["rooms"]}
    labels = {r["id"]: r["label"] for r in tl["rooms"]}
    items = []
    for x in inv["items"] + inv["utilities"]:
        at = floods_at.get(x["room"])
        point = (x.get("anchor") or {}).get("point")
        if x["height_m"] is None or at is None or point is None:
            continue  # an item with no measured height has no level to light at; the tool lists it as unknown
        cost = x.get("cost")
        items.append({"id": x["id"], "name": x["name"], "room": x["room"], "room_label": labels.get(x["room"], ""),
                      "point": [round(v, 3) for v in point], "height_m": round(x["height_m"], 2),
                      "wet_at": round(max(at, floor_z[x["room"]] + x["height_m"] + WICK_M), 3),
                      "cost_usd": list(cost) if cost else None, "cost_class": x.get("cost_class"),
                      "fixture": bool(x.get("fixture", "label" in x)), "utility": "label" in x})
    items.sort(key=lambda i: i["wet_at"])
    priced = [i for i in items if i["cost_usd"] and not i["fixture"]]
    loss = [[sum(i["cost_usd"][k] for i in priced if i["wet_at"] <= lvl) for k in (0, 1)] for lvl in tl["level"]]
    return {"sid": plan["sid"], "available": True, "items": items, "loss_usd": loss,
            "wet_count": [sum(1 for i in items if i["wet_at"] <= lvl) for lvl in tl["level"]],
            "skipped_no_height": sum(1 for x in inv["items"] + inv["utilities"] if x["height_m"] is None),
            "source": {"confidence": "low",
                       "text": "Items and their cost classes are a vision model's reading of the furnished panoramas "
                               "(the listing's furniture, not the owner's). Heights come from the scan geometry. The "
                               "dollar range sums the cost classes of belongings under water at that hour."}}
