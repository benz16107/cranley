"""Wildfire defensible space: vegetation and tree canopy in California's three zones round a house (0 to 5 ft, 5 to 30
ft, 30 to 100 ft), with a verdict per zone and what to clear first; roof material, slope, the nearest fire station and
the CAL FIRE Fire Hazard Severity Zone. Houston houses get the same rings, with a note that the zones are California's.

Canopy is surface minus ground above 2 m where the orthophoto is green (or in shadow and still faintly green);
low vegetation is green under 2 m. All of it on a 0.5 m grid from one Vexcel ortho, DSM and DTM request each.
"""
from __future__ import annotations

import io
import math

import numpy as np
import shapely
from PIL import Image

from ...aerial import site as aerial
from ...aerial.vexcel import VexcelError
from ...geometry import georef
from ...geometry._plan import floor_z
from ...world import terrain
from ...world.frame import enu_to_lonlat, lonlat_to_enu
from .. import Assumption, Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from .._site import Where, capture, compass, fact, footprint, geo, geo_route, locate, parcel, pin, pins, src
from .._site import osm
from ..types import RouteOverlay
from . import calfire

FT = 0.3048
ZONES = (("zone0", "Zone 0", "0 to 5 ft", 0.0, 5 * FT), ("zone1", "Zone 1", "5 to 30 ft", 5 * FT, 30 * FT),
         ("zone2", "Zone 2", "30 to 100 ft", 30 * FT, 100 * FT))
# Screening thresholds of this tool, (pass up to, warn up to) in % of the zone; above warn fails. CAL FIRE's guidance
# (readyforwildfire.org) is qualitative: Zone 0 ember-resistant (nothing that burns), Zone 1 lean, clean and green,
# Zone 2 reduce fuel with spacing between plants.
LIMITS = {"zone0": {"canopy": (5, 15), "veg": (10, 25)}, "zone1": {"canopy": (30, 50), "veg": (60, 80)},
          "zone2": {"canopy": (50, 70), "veg": (80, 95)}}
TREE_M, GREEN, DARK = 2.0, 0.05, 70   # canopy height, excess-green index, brightness below which green is faint
GRID_M, CELLS = 100.0, 200            # 0.5 m cells
BURNS = ("wood", "shake")
VEG = Source(layer="vexcel", method="vision", confidence="medium",
             note="Green in the orthophoto (excess-green index); dry grass and bare dirt both read as not green")
CANOPY = Source(layer="vexcel", method="geometry", confidence="medium",
                note="Surface minus ground model above 2 m where green; the two models' offset removed by the 10th "
                     "percentile of their difference round the house")


class Inputs(Where):
    station_radius_km: float = field(8, pref="wildfire.station_radius_km", unit="km", gt=0, le=20,
                                     description="How far to look for a fire station")


def ortho_grid(o, lat0: float, lon0: float, bounds) -> np.ndarray:
    """The orthophoto as (rows, cols, 3) float32 on the analysis grid: box-downsampled to the grid's cell size first,
    so nothing larger than a few hundred pixels across is held as floats."""
    img = Image.open(io.BytesIO(o.image)).convert("RGB")
    w0, s0 = lonlat_to_enu(lat0, lon0, o.bounds[0], o.bounds[1])
    e0, n0 = lonlat_to_enu(lat0, lon0, o.bounds[2], o.bounds[3])
    cell = (bounds[2] - bounds[0]) / CELLS
    small = np.asarray(img.resize((max(1, round((e0 - w0) / cell)), max(1, round((n0 - s0) / cell))),
                                  Image.Resampling.BOX), np.float32)
    ce = bounds[0] + (np.arange(CELLS) + 0.5) * cell
    cn = bounds[3] - (np.arange(CELLS) + 0.5) * (bounds[3] - bounds[1]) / CELLS
    c = np.clip(((ce - w0) / (e0 - w0) * small.shape[1]).astype(int), 0, small.shape[1] - 1)
    r = np.clip(((n0 - cn) / (n0 - s0) * small.shape[0]).astype(int), 0, small.shape[0] - 1)
    return small[r[:, None], c[None, :]]


def classify(rgb: np.ndarray, ndsm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(green, canopy) masks. Shadowed crowns are dark with only a trace of green, so a dark cell counts as green at
    a lower excess-green index."""
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    exg = (2 * G - R - B) / (R + G + B + 1)
    green = (exg > GREEN) | (((R + G + B) / 3 < DARK) & (exg > 0.0))
    return green, green & (ndsm > TREE_M)


def cover(s, outline, lat0, lon0, land=None) -> dict:
    """Per zone: cells, canopy and vegetation % and the compass side with most canopy, over the zone's part of the
    parcel (`land`, east/north) when given. Also the slope of the ground and the masks for pins."""
    dsm = terrain.grid(lat0, lon0, GRID_M, CELLS)
    dtm = terrain.grid(lat0, lon0, GRID_M, CELLS, kind="dtm")
    o = aerial.ortho(lat0, lon0, GRID_M, 1024)
    b = dsm["bounds_enu"]
    cell = (b[2] - b[0]) / CELLS
    ce = (b[0] + (np.arange(CELLS) + 0.5) * cell)[None, :].repeat(CELLS, 0)
    cn = (b[3] - (np.arange(CELLS) + 0.5) * (b[3] - b[1]) / CELLS)[:, None].repeat(CELLS, 1)
    diff = dsm["heights"] - dtm["heights"]
    house = shapely.contains_xy(outline.buffer(0.5), ce, cn)
    off = float(np.nanpercentile(diff[~house], 10))
    ndsm = np.nan_to_num(diff - off, nan=0.0)
    green, canopy = classify(ortho_grid(o, lat0, lon0, b), ndsm)
    green &= ~house
    canopy &= ~house
    cx, cy = outline.centroid.x, outline.centroid.y
    side = (np.degrees(np.arctan2(ce - cx, cn - cy)) % 360 + 22.5) // 45 % 8
    out = {}
    for key, _, _, r0, r1 in ZONES:
        ring = outline.buffer(r1).difference(outline.buffer(r0)) if r0 else outline.buffer(r1).difference(outline)
        m = shapely.contains_xy(ring, ce, cn)
        mine = m & shapely.contains_xy(land, ce, cn) if land is not None else m
        if mine.sum() < 4:
            mine = m
        n = int(mine.sum())
        by_side = np.bincount(side[mine & canopy].astype(int), minlength=8)
        worst = int(by_side.argmax())
        sel = mine & canopy & (side == worst)
        out[key] = {"cells": n, "area_m2": round(n * cell * cell, 1),
                    "canopy_pct": round(100 * (mine & canopy).sum() / max(n, 1), 1),
                    "veg_pct": round(100 * (mine & green).sum() / max(n, 1), 1),
                    "on_parcel_pct": round(100 * mine.sum() / max(m.sum(), 1), 1),
                    "outside_canopy_pct": round(100 * (m & ~mine & canopy).sum() / max((m & ~mine).sum(), 1), 1)
                    if land is not None and (m & ~mine).any() else None,
                    "side": compass(worst * 45) if by_side.any() else None,
                    "hotspot": (float(ce[sel].mean()), float(cn[sel].mean())) if sel.any() else None,
                    "ring": ring}
    near = shapely.contains_xy(outline.buffer(100 * FT), ce, cn) & np.isfinite(dtm["heights"])
    A = np.c_[ce[near], cn[near], np.ones(near.sum())]
    (gx, gy, _), *_ = np.linalg.lstsq(A, dtm["heights"][near], rcond=None)
    slope = {"pct": round(100 * math.hypot(gx, gy), 1), "downhill": compass(math.degrees(math.atan2(-gx, -gy)))}
    return {"zones": out, "slope": slope, "offset_m": round(off, 2)}


def judge(key: str, z: dict) -> str:
    st = "pass"
    for what in ("canopy", "veg"):
        ok, warn = LIMITS[key][what]
        v = z[f"{what}_pct"]
        st = "fail" if v > warn else ("warn" if v > ok and st == "pass" else st)
    return st


def stations(lat: float, lon: float, radius_km: float) -> list[dict]:
    """Fire stations from OpenStreetMap within the radius, nearest first: {name, lat, lon, km}."""
    r = int(radius_km * 1000)
    q = (f'[out:json][timeout:40];(node(around:{r},{lat},{lon})["amenity"="fire_station"];'
         f'way(around:{r},{lat},{lon})["amenity"="fire_station"];);out center 40;')
    out = []
    for el in osm._query(q).get("elements") or []:
        la, lo = el.get("lat", (el.get("center") or {}).get("lat")), el.get("lon", (el.get("center") or {}).get("lon"))
        if la is None:
            continue
        e, n = lonlat_to_enu(lat, lon, lo, la)
        out.append({"name": (el.get("tags") or {}).get("name") or "Fire station", "lat": la, "lon": lo,
                    "km": round(math.hypot(e, n) / 1000, 2)})
    return sorted(out, key=lambda x: x["km"])


def _scan_rings(ctx, sid: str, rings) -> list[RouteOverlay]:
    """The zone edges in the scan's frame, on its lowest floor, so the 3D view draws them round the building."""
    plan = ctx.plan(sid)
    if not (plan.get("geo") or {}).get("lat") or not plan.get("floors"):
        return []
    fz = floor_z(plan)
    low = min(plan["floors"], key=lambda f: fz.get(f["id"], 0))["id"]
    out = []
    for label, pts in rings:
        xy = [georef.from_latlon(plan, la, lo) for lo, la in pts]
        out.append(RouteOverlay(floor=low, label=label, points=[(round(x, 2), round(y, 2), round(fz.get(low, 0), 2))
                                                                for x, y in xy]))
    return out


@tool(id="wildfire_space", title="Wildfire defensible space", icon="flame",
      summary="Vegetation and tree canopy in California's 5, 30 and 100 ft zones round the house, what to clear first, "
              "roof material, slope, the nearest fire station and the CAL FIRE hazard zone.",
      model_description="Defensible space for a house at a scan or a point: tree canopy (surface minus ground above "
                        "2 m, green in the orthophoto) and low vegetation in California's Zone 0 (0-5 ft), Zone 1 "
                        "(5-30 ft) and Zone 2 (30-100 ft), each with a verdict and the side with the most canopy; roof "
                        "material from Vexcel; ground slope; nearest fire station from OpenStreetMap; and whether the "
                        "point is in a CAL FIRE Fire Hazard Severity Zone. Draws the zone edges on the map and round the "
                        "building in 3D. Houston houses get the same rings with a note that the zones are California's.",
      personas=["la_fire_homeowner", "insurance_underwriter"],
      requires=[{"layer": "vexcel.ortho"}, {"layer": "vexcel.dsm"}, {"layer": "vexcel.property"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      overlays=["route", "pins"],
      examples=["Is my defensible space good enough?", "What should I clear first before fire season?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    fp = footprint(s)
    if fp is None:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text="Vexcel has no building footprint at this point, so the zones cannot be drawn."))
    c = fp.centroid
    lat0, lon0 = c.y, c.x
    to_enu = lambda g: shapely.transform(g, lambda xy: np.array([lonlat_to_enu(lat0, lon0, x, y) for x, y in xy]))  # noqa: E731
    outline = to_enu(fp)
    pa = parcel(s)
    land = to_enu(pa) if pa is not None else None
    ca = s.state == "CA"
    try:
        ctx.step("Reading Vexcel's orthophoto, surface and ground models round the house")
        cv = cover(s, outline, lat0, lon0, land)
    except (VexcelError, KeyError, OSError, ValueError) as e:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text=f"Vexcel's imagery could not be read ({str(e)[:80]}), so vegetation cannot be measured."))
    ctx.step("Measured canopy and vegetation in each zone" + (" on the parcel" if land is not None else ""))
    k = s.key
    findings, checks, metrics, ps = [], [], [], []
    statuses = {}
    for key, name, span, _, _ in ZONES:
        z = cv["zones"][key]
        st = statuses[key] = judge(key, z)
        fid = f"wildfire_space:{k}:{key}"
        vx = fact(s, {"zone0": "defensible_zone1_tree", "zone1": "defensible_zone2_tree",
                      "zone2": "defensible_zone3_tree"}[key])
        what = "trees" if z["canopy_pct"] >= z["veg_pct"] - z["canopy_pct"] else "shrubs and grass"
        detail = (f"{span} from the walls: {z['canopy_pct']:.0f}% under tree canopy, {z['veg_pct']:.0f}% green in all, "
                  f"over {z['area_m2']:.0f} m²" + (f" of the parcel ({z['on_parcel_pct']:.0f}% of the zone is yours)" if land is not None else "")
                  + "." + (f" Most canopy on the {z['side']} side." if z["side"] else "")
                  + (f" Beyond your property line the zone is {z['outside_canopy_pct']:.0f}% canopy: a talk with the neighbour."
                     if (z["outside_canopy_pct"] or 0) > LIMITS[key]["canopy"][0] else "")
                  + (f" Vexcel's own estimate of tree cover here: {vx:.0f}%." if isinstance(vx, (int, float)) else ""))
        todo = {"zone0": f"clear the {what} within 5 ft of the walls" + (f", starting on the {z['side']} side" if z["side"] else "")
                + "; nothing that burns belongs here, including wood mulch",
                "zone1": f"thin the {what}" + (f" on the {z['side']} side" if z["side"] else "")
                + ", remove dead plants and keep branches 10 ft from the roof and chimney",
                "zone2": f"space out the {what}" + (f" on the {z['side']} side" if z["side"] else "")
                + " and cut grass to 4 in"}[key]
        findings.append(Finding(id=fid, title=f"{name}, {span}", status=st, anchor=geo(*enu_to_lonlat(lat0, lon0, *(z["hotspot"] or (outline.centroid.x, outline.centroid.y)))),
                                detail=detail + ("" if st == "pass" else f" To do: {todo}."), source=CANOPY,
                                media=[{"kind": "ortho", "ref": f"/api/aerial/ortho?lat={lat0:.7f}&lon={lon0:.7f}&size_m=100&px=1024"}]))
        for what_id, label, src_ in (("canopy", "Tree canopy", CANOPY), ("veg", "Vegetation", VEG)):
            ok, warn = LIMITS[key][what_id]
            v = z[f"{what_id}_pct"]
            checks.append(Check(id=f"{key}.{what_id}", rule=f"{label}, {name} ({span})", measured=v, threshold=ok,
                                unit="%", status="pass" if v <= ok else "warn" if v <= warn else "fail", findings=[fid],
                                standard="CAL FIRE defensible space zones (PRC 4291); limits are this tool's screening values"))
        metrics.append(Metric(id=f"canopy.{name}", label=f"{name} canopy", value=z["canopy_pct"], unit="%", source=CANOPY))
        z["todo"] = todo
        if z["hotspot"] and st != "pass":
            ps.append(pin(key, *enu_to_lonlat(lat0, lon0, *z["hotspot"]), f"{name}: {what}, {z['side']}", st))

    material = fact(s, "roof_material")
    roof_st = "unknown" if not material else "fail" if any(w in material.lower() for w in BURNS) else "pass"
    findings.append(Finding(id=f"wildfire_space:{k}:roof", title=f"Roof: {material or 'material unknown'}", status=roof_st,
                            anchor=geo(lon0, lat0), source=src(s, "roof_material"),
                            detail=("A wood or shake roof catches embers; replacing it with a Class A roof matters more "
                                    "than any clearing." if roof_st == "fail" else
                                    f"Vexcel classifies the roof as {material}, which is usually sold as Class A fire rated; "
                                    "the rating itself is not visible from the air." if material else
                                    "Vexcel does not classify this roof's material.")))
    slope = cv["slope"]
    findings.append(Finding(id=f"wildfire_space:{k}:slope", title="Slope round the house",
                            status="warn" if slope["pct"] > 20 else "pass", anchor=geo(lon0, lat0),
                            source=Source(layer="vexcel", method="geometry", confidence="medium",
                                          note="Plane fitted to Vexcel's ground model within 100 ft"),
                            detail=f"The ground falls {slope['pct']:.0f}% toward the {slope['downhill']}."
                            + (" Fire runs uphill faster, so clear further than 100 ft on the downhill side." if slope["pct"] > 20 else "")))
    metrics.insert(0, Metric(id="slope", label="Ground slope", value=slope["pct"], unit="%",
                             source=Source(layer="vexcel", method="geometry", confidence="medium", note="Ground model plane fit")))

    near = None
    try:
        st_list = stations(lat0, lon0, inputs.station_radius_km)
        near = st_list[0] if st_list else None
        ctx.step(f"Found {len(st_list)} fire stations within {inputs.station_radius_km:g} km in OpenStreetMap")
    except RuntimeError as e:
        ctx.step(f"OpenStreetMap did not answer: {e}")
    osm_src = Source(layer="model", method="lookup", confidence="medium",
                     note=f"{osm.NOTE}; straight-line distance, not drive time")
    metrics.insert(1, Metric(id="station_km", label="Nearest fire station", value=near["km"] if near else None, unit="km",
                             source=osm_src))
    if near:
        ps.append(pin("station", near["lon"], near["lat"], near["name"], "pass"))
        findings.append(Finding(id=f"wildfire_space:{k}:station", title=f"Nearest fire station: {near['name']}",
                                status="pass", anchor=geo(near["lon"], near["lat"]), source=osm_src,
                                detail=f"{near['km']:.1f} km in a straight line."))

    hz = calfire.zone(lat0, lon0) if ca else None
    if hz:
        hz_st = "unknown" if not hz["available"] else "pass" if not hz["zone"] else "fail" if hz["zone"] == "Very High" else "warn"
        findings.append(Finding(id=f"wildfire_space:{k}:fhsz", status=hz_st, anchor=geo(lon0, lat0),
                                title=f"Fire Hazard Severity Zone: {hz['zone'] or ('none' if hz['available'] else 'unknown')}",
                                source=Source(layer="model", method="lookup", confidence="high" if hz["available"] else "low",
                                              note=hz["note"]),
                                detail=(f"{hz['zone']} hazard ({hz['responsibility']}). In a Very High zone, Zone 0 rules "
                                        "apply as the Board of Forestry adopts them, and a home sale needs a defensible "
                                        "space inspection." if hz["zone"] else hz["note"] + ".")))
    order = ["zone0", "zone1", "zone2"]
    first = next((z for z in order if statuses[z] == "fail"), None) or next((z for z in order if statuses[z] == "warn"), None)
    worst = "fail" if "fail" in statuses.values() or roof_st == "fail" else "warn" if "warn" in statuses.values() else "pass"
    names = {key: f"{name} ({span})" for key, name, span, _, _ in ZONES}
    text = ("Every zone is clear enough." if not first else
            f"{names[first]} needs work first: {cv['zones'][first]['todo']}.")
    text += " " + "; ".join(f"{names[z]} {statuses[z]}" for z in order) + "."
    if roof_st == "fail":
        text = "The roof is wood or shake, the first thing to replace. " + text
    if hz and hz["zone"]:
        text += f" CAL FIRE maps this house in a {hz['zone']} Fire Hazard Severity Zone."
    if not ca:
        text += " These are California's zones; Texas has no state defensible space law, but the same rings apply to a grass or brush fire."
    edges = [(f"{name} edge, {span.split(' to ')[1]}", [enu_to_lonlat(lat0, lon0, x, y) for x, y in
              outline.buffer(r1).exterior.coords]) for key, name, span, _, r1 in ZONES]
    overlays = [geo_route(pts, label) for label, pts in edges] + pins(ps)
    if s.sid:
        overlays += _scan_rings(ctx, s.sid, edges)
    return ToolResult(
        scope=s.scope, verdict=Verdict(status=worst, text=text), metrics=metrics, checks=checks, findings=findings,
        overlays=overlays,
        assumptions=[Assumption(id="zones", label="Zones measured from the building footprint's walls", value="5 / 30 / 100 ft"),
                     Assumption(id="tree_height", label="Canopy counted above", value=TREE_M, unit="m"),
                     Assumption(id="limits", label="Pass up to: canopy 5 / 30 / 50 %, vegetation 10 / 60 / 80 % by zone; "
                                "screening values, not law", value=True),
                     Assumption(id="dry_grass", label="Dry grass and dead plants read as bare ground in the photo", value=True),
                     Assumption(id="imagery", label="Aerial capture", value=capture(s)),
                     Assumption(id="wildfire.station_radius_km", label="Fire station search radius",
                                value=inputs.station_radius_km, unit="km", editable=True),
                     Assumption(id="california_only", label="Zones are California's (PRC 4291)", value=True)])
