"""A flood scenario for one scanned house: floor height above the ground, depth above the ground, water levels in
scan z at the low, middle and high ends of the range, and the geometry engine's water at each.

Shared by flood_rehearsal, valuables_height and storm_plan, so all three tell the same story. The range carries
both uncertainties: the high water level uses the low floor height and the high scenario depth."""
from __future__ import annotations

import functools
import statistics
from typing import Literal

from pydantic import BaseModel

from ...geometry import water
from ...geometry._plan import room_floor_z
from .. import ToolError, field
from . import floor_height as fh
from . import public

Scenario = Literal["depth", "surge", "rainfall", "harvey_2017"]
TYPICAL_FFH_M, TYPICAL_FFH_ERR_M = 0.30, 0.20   # used only when no method measures the floor; said so in the result
HARVEY_RADIUS_M = 2000
DATUM_RADIUS_M = 6000

SCENARIO_TEXT = {
    "depth": "water {d:.2f} m above the ground outside",
    "surge": "a storm surge of {d:.2f} m above ground level (the National Hurricane Center gives surge as height above ground)",
    "rainfall": "rain flooding {d:.2f} m deep above the ground outside",
    "harvey_2017": "Hurricane Harvey's peak water, from USGS high-water marks",
}


class FloodInputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    depth_m: float = field(ask="How deep could the water get above the ground outside your house, in metres? "
                               "Use a storm-surge forecast (given as height above ground) or a street-flooding depth.",
                           pref="flood.depth_m", unit="m", ge=0, le=3, description="Water above the ground outside")
    scenario: Scenario = field("depth", pref="flood.scenario",
                               description="Where the depth comes from: typed depth, storm surge, rainfall, or Harvey "
                                           "2017 from USGS high-water marks (then depth_m is not used)")
    floor_height_m: float | None = field(None, pref="flood.floor_height_m", unit="m", ge=0, le=5,
                                         description="Floor height above the ground at the door, if you measured it")
    use_drone: bool = field(True, description="Measure the door threshold in the drone photos (vision model, cached)")


def where(plan: dict) -> tuple[float, float] | None:
    g = plan.get("geo") or {}
    if g.get("lat") is not None and g.get("lon") is not None:
        return g["lat"], g["lon"]
    try:
        from ...sources import index
        r = index.rows().get(plan["sid"]) or {}
        return (r["lat"], r["lon"]) if r.get("lat") is not None else None
    except Exception:  # noqa: BLE001 - the index is optional context
        return None


@functools.lru_cache(maxsize=64)
def _site(lat: float, lon: float) -> dict:
    from ...aerial import site
    return site.site_facts(lat, lon)


def _heights(kind: str, pts: list[tuple[float, float]]) -> list[float]:
    from ...aerial import site
    return site.heights(kind, pts)[0]


def site_facts(plan: dict, steps) -> dict | None:
    ll = where(plan)
    if ll is None:
        steps("The scan has no location, so the aerial and drone methods are off")
        return None
    try:
        s = _site(*ll)
        steps(f"Read the Vexcel footprint and parcel ({'found' if s.get('footprint') else 'no footprint'})")
        return s
    except Exception as e:  # noqa: BLE001 - aerial data is one of several methods
        steps(f"Vexcel site facts failed: {str(e)[:120]}")
        return {"lat": ll[0], "lon": ll[1], "facts": [], "footprint": None, "parcel": None}


def measure_floor(plan: dict, site: dict | None, *, use_drone: bool, override: float | None, steps,
                  drone_photos=None, drone_image=None, ask=None) -> dict:
    """Floor height above the ground at the entry: every method that can run, combined."""
    doors = fh.exterior_doors(plan)
    ests, traces = [], {}
    if plan.get("walls"):
        e = fh.scan_outdoor(plan, doors[0] if doors else None)
        steps("Scan outdoor panoramas: " + (f"{e['value_m']:.2f} m" if e else "none near an exterior door"))
        ests.append(e)
    bound = fh.door_step(plan) if plan.get("walls") else None
    fp = (site or {}).get("footprint")
    lat, lon = (site["lat"], site["lon"]) if site else (None, None)
    grade = None
    if fp:
        try:
            if _kind(plan.get("sid", "")) in ("house", None):
                e = fh.vexcel_eave(plan, fp, lat, lon, lambda pts: _heights("dsm", pts))
                steps("Vexcel eave method: " + (f"{e['value_m']:.2f} m" if e else "not used (more than one storey)"))
                ests.append(e)
            else:  # the roof belongs to the whole building, not to this unit
                steps("Vexcel eave method: not used (the scan is one unit, not the whole building)")
            grade = fh.ground_grade(fp, lat, lon, lambda pts: _heights("dtm", pts))
        except Exception as ex:  # noqa: BLE001
            steps(f"Vexcel elevations failed: {str(ex)[:120]}")
    if use_drone and fp and plan.get("has", {}).get("splat"):
        try:
            if drone_photos is None:
                from ...sources import hackathon
                from ...vision.model import ask as model_ask
                drone_photos = hackathon.drone_list(plan["sid"], n=60)["photos"]
                drone_image = functools.partial(hackathon.drone_image, plan["sid"])
                ask = model_ask
            d, traces["drone"] = fh.drone_threshold(plan["sid"], fp, lat, lon, photos=drone_photos, image=drone_image,
                                                    ask=ask)
            steps("Drone threshold: " + (", ".join(f"{x['method']} {x['value_m']:.2f} m" for x in d) or
                                         traces["drone"].get("reason", "nothing found")))
            ests += d
        except Exception as ex:  # noqa: BLE001
            steps(f"Drone method failed: {str(ex)[:120]}")
            traces["drone"] = {"reason": str(ex)[:200]}
    out = fh.combine([e for e in ests if e], bound, override)
    if not out["available"]:
        out = fh.combine([fh._est("assumed", TYPICAL_FFH_M, TYPICAL_FFH_ERR_M, "low",
                                  "No method could measure this house, so a typical Houston slab-on-grade floor "
                                  "height is assumed. Measure the step at your door to replace it.")], bound)
    out["grade"] = grade
    out["traces"] = traces
    out["entry_door"] = doors[0]["id"] if doors else None
    return out


def harvey_depth(lat: float, lon: float, steps) -> dict:
    """Harvey's peak water above this lot's ground: nearby USGS marks' water elevation (NAVD88) minus the ground,
    with Vexcel's bare-ground model tied to NAVD88 by marks that record their own height above ground."""
    try:
        near = public.marks_near("harvey_2017", lat, lon, HARVEY_RADIUS_M)
        calib = [m for m in public.marks_near("harvey_2017", lat, lon, DATUM_RADIUS_M)
                 if m["height_above_ground_m"] is not None][:12]
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"USGS high-water marks could not be read: {str(e)[:120]}"}
    steps(f"USGS Harvey marks: {len(near)} within {HARVEY_RADIUS_M / 1000:.0f} km, {len(calib)} to tie the datum")
    if not near:
        return {"available": False, "reason": f"No good-quality USGS Harvey high-water mark within "
                                              f"{HARVEY_RADIUS_M / 1000:.0f} km of this house."}
    if len(calib) < 2:
        return {"available": False, "reason": "Too few Harvey marks with a height above ground nearby to tie "
                                              "Vexcel's ground model to the marks' datum."}
    try:
        z = _heights("dtm", [(lon, lat)] + [(m["lon"], m["lat"]) for m in calib])
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"Vexcel ground elevations failed: {str(e)[:120]}"}
    offs = [zm - (m["water_navd88_m"] - m["height_above_ground_m"]) for zm, m in zip(z[1:], calib)]
    off, off_sd = statistics.median(offs), statistics.pstdev(offs)
    ground = z[0] - off
    use = near[:5]
    wse = [m["water_navd88_m"] for m in use]
    mid = statistics.median(wse) - ground
    lo, hi = min(wse) - ground - off_sd, max(wse) + off_sd - ground
    return {"available": True, "depth_m": max(mid, 0.0), "lo_m": max(lo, 0.0), "hi_m": max(hi, 0.0), "raw_m": mid,
            "marks": use, "ground_navd88_m": round(ground, 2), "datum_offset_m": round(off, 2),
            "datum_offset_sd_m": round(off_sd, 2),
            "note": (f"Median water elevation of the {len(use)} nearest USGS Harvey marks ({use[0]['distance_m']} to "
                     f"{use[-1]['distance_m']} m away) minus the lot's ground. Vexcel's ground model was tied to NAVD88 "
                     f"by {len(calib)} marks that record their height above ground (offset {off:.2f} m, spread "
                     f"{off_sd:.2f} m). Water surfaces slope along a bayou and streets drain unevenly, so this is a "
                     "rough guide, not the depth Harvey reached at this door.")}


def scenario_depth(inputs: FloodInputs, lat_lon, steps) -> dict:
    if inputs.scenario != "harvey_2017":
        return {"available": True, "depth_m": inputs.depth_m, "lo_m": inputs.depth_m, "hi_m": inputs.depth_m,
                "note": "Typed in; no error of its own.", "source": {"layer": "model", "method": "lookup",
                                                                    "confidence": "high", "note": "Your number"}}
    if lat_lon is None:
        return {"available": False, "reason": "The scan has no location, so Harvey's marks cannot be matched to it."}
    h = harvey_depth(*lat_lon, steps)
    if h["available"]:
        h["source"] = {"layer": "model", "method": "lookup", "confidence": "low",
                       "note": "USGS Short-Term Network high-water marks, event 180 (Harvey 2017), and Vexcel DTM"}
    return h


def run(plan: dict, inputs: FloodInputs, steps, **drone) -> dict:
    """Everything the three tools need about the water in this house."""
    site = site_facts(plan, steps)
    floor = measure_floor(plan, site, use_drone=inputs.use_drone, override=inputs.floor_height_m, steps=steps, **drone)
    scen = scenario_depth(inputs, (site["lat"], site["lon"]) if site else where(plan), steps)
    fallback = None
    if not scen["available"]:
        fallback = scen["reason"]
        steps(f"Named event unavailable: {fallback} Using the typed depth instead.")
        scen = scenario_depth(inputs.model_copy(update={"scenario": "depth"}), None, steps)
    rz = room_floor_z(plan)
    door = next((o for o in plan.get("openings") or [] if o["id"] == floor["entry_door"]), None)
    if door is not None:
        ref_z = rz[door["rooms"][0]]
    else:
        zs = [z for r, z in rz.items()]
        ref_z = statistics.median(zs) if zs else 0.0
    levels = {"lo": ref_z - floor["hi_m"] + scen["lo_m"], "mid": ref_z - floor["value_m"] + scen["depth_m"],
              "hi": ref_z - floor["lo_m"] + scen["hi_m"]}
    runs = {k: water(plan, v) for k, v in levels.items()}
    steps("Water levels in the scan: " + ", ".join(f"{k} {v - ref_z:+.2f} m from the entry floor" for k, v in levels.items()))
    rooms = {}
    walled = {r["id"]: r.get("walls") for r in plan["rooms"]}
    if runs["mid"]["available"]:
        for k, w in runs.items():
            for r in w["rooms"]:
                x = rooms.setdefault(r["room"], {"room": r["room"], "label": r["label"], "floor": r["floor"],
                                                 "floor_z": r["floor_z"], "step_m": r.get("step_m", 0.0),
                                                 "walled": bool(walled.get(r["room"]))})
                x[f"depth_{k}"] = r["depth"]
                x[f"floor_area_{k}"] = r["wetted_floor_area"]
                x[f"wall_area_{k}"] = r["wetted_wall_area"]
                if k == "mid":
                    x.update(via=r["via"], floods_at=r["floods_at"], openings=r["openings_overtopped"])
    return {"walls": bool(plan.get("walls")), "site": site, "floor": floor, "scenario": scen, "scenario_fallback": fallback, "ref_z": ref_z,
            "entry_door": door, "levels": levels, "runs": runs, "rooms": rooms,
            "kind": inputs.scenario if fallback is None else "depth",
            "label": SCENARIO_TEXT[inputs.scenario if fallback is None else "depth"].format(d=scen["depth_m"])}


def indoor(flood: dict) -> list[dict]:
    """Rooms of the house: not voids, and in a scan with walls, not the wall-less yard and porch captures."""
    return [r for r in flood["rooms"].values() if (r["label"] or "") != "Void" and (r["walled"] or not flood["walls"])]


def wet_rooms(flood: dict, k: str) -> list[dict]:
    return [r for r in indoor(flood) if r.get(f"depth_{k}", 0) > 0]


def room_depth_at(flood: dict, room: str | None, k: str) -> float:
    r = flood["rooms"].get(room or "")
    return r.get(f"depth_{k}", 0.0) if r else 0.0


def check_plan(plan: dict) -> None:
    if not plan.get("rooms"):
        raise ToolError("This scan has no rooms, so there is nothing to flood.")


def _kind(sid: str) -> str | None:
    try:
        from ...sources import index
        return (index.rows().get(sid) or {}).get("kind")
    except Exception:  # noqa: BLE001 - the index is context only
        return None
