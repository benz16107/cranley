"""Flood rehearsal: what a water level does inside one scanned house, with the floor-height error carried through."""
from __future__ import annotations

from .. import (
    Action,
    Assumption,
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    OpeningAnchor,
    Pin,
    PinsOverlay,
    RoomAnchor,
    RuleOverlay,
    ScanScope,
    SelectOpenings,
    Source,
    ToolResult,
    Verdict,
    tool,
)
from ..types import GeoAnchor, Media, WaterOverlay
from . import public
from .scenario import FloodInputs, check_plan, indoor, wet_rooms
from .scenario import run as flood_run

GEO = Source(layer="matterport", method="simulation", confidence="medium",
             note="Still water filling the rooms through openings by sill height; no flow, pressure or drainage")
LAYER = {"drone_pixels": "drone", "drone_laser_ground": "drone", "scan_outdoor": "matterport", "door_step": "matterport",
         "vexcel_eave": "vexcel", "measured": "model", "assumed": "model"}
METHOD_NAME = {"drone_pixels": "drone photos of the door threshold", "drone_laser_ground": "drone threshold against laser ground hits",
               "scan_outdoor": "the scan's outdoor panoramas", "vexcel_eave": "Vexcel surface model at the eave",
               "door_step": "the step at an exterior door", "measured": "your measurement",
               "assumed": "a typical Houston slab (assumed)"}


class Inputs(FloodInputs):
    pass


def floor_source(f: dict) -> Source:
    return Source(layer=LAYER.get(f["method"], "model"), method="vision" if f["method"].startswith("drone") else
                  "geometry", confidence=f["confidence"],
                  note=f"Floor height from {METHOD_NAME.get(f['method'], f['method'])}; range {f['lo_m']:.2f} to "
                       f"{f['hi_m']:.2f} m")


def rng(lo: float, hi: float, unit: str = "m") -> str:
    return f"{lo:.2f} {unit}" if abs(hi - lo) < 0.005 else f"{lo:.2f} to {hi:.2f} {unit}"


def floor_finding(sid: str, flood: dict) -> Finding:
    f = flood["floor"]
    lines = [f"{METHOD_NAME.get(e['method'], e['method'])}: {e['value_m']:.2f} m, give or take {e['err_m']:.2f} "
             f"({e['confidence']}). {e['note']}" for e in f["estimates"]]
    if f.get("bound"):
        lines.append(f"Lower bound from the step at an exterior door: {f['bound']['value_m']:.2f} m.")
    if f.get("widened_by"):
        lines.append("Range widened to take in: " + ", ".join(METHOD_NAME.get(m, m) for m in f["widened_by"]) + ".")
    media = []
    drone = (f.get("traces") or {}).get("drone") or {}
    for t in drone.get("tried", []):
        if t.get("ffh_m") is not None:
            media.append(Media(kind="drone", ref=f"{sid}/{t['photo']}", box=None))
    door = flood.get("entry_door")
    return Finding(id=f"flood_rehearsal:{sid}:floor_height", title="Floor height above the ground outside",
                   status="unknown" if f["method"] == "assumed" else "pass",
                   detail=(f"{f['value_m']:.2f} m (between {f['lo_m']:.2f} and {f['hi_m']:.2f} m), from "
                           f"{METHOD_NAME.get(f['method'], f['method'])}. " + " ".join(lines)),
                   anchor=OpeningAnchor(sid=sid, opening=door["id"]) if door else None,
                   source=floor_source(f), media=media)


@tool(id="flood_rehearsal", title="Flood rehearsal", icon="waves",
      summary="Shows what a flood does inside this house: how deep in each room, which doors and windows go under, "
              "and the order rooms flood, with the floor-height error carried through.",
      model_description="Simulate still water at a scenario depth above the ground outside one scanned house. Measures "
                        "the floor height above ground (drone photos of the door, the scan's outdoor panoramas, Vexcel "
                        "elevations) with a range, then returns per-room depth, wetted floor and wall area, flood order, "
                        "overtopped openings, a water overlay and a depth lens. Scenario harvey_2017 reads USGS marks.",
      personas=["houston_homeowner_storm", "insurance_underwriter"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.openings", "need": "optional",
                                                "fallback": "depths only, no flood order or openings"},
                {"layer": "drone.photos", "need": "optional"}, {"layer": "vexcel.elevation", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "Controls", "FloorPlanMini", "CheckList", "EvidenceStrip", "MiniChart",
              "AssumptionChips", "StepLog", "ActionBar"],
      overlays=["water", "lens", "rule", "pins"], annotations={"cost": "slow"},
      examples=["What happens inside if 60 cm of water comes up the street?", "Rehearse Harvey in this house"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    check_plan(plan)
    flood = flood_run(plan, inputs, ctx.step)
    return result(sid, plan, inputs, flood)


def result(sid: str, plan: dict, inputs: Inputs, flood: dict) -> ToolResult:
    f, sc, lv, ref = flood["floor"], flood["scenario"], flood["levels"], flood["ref_z"]
    walls = bool(plan.get("walls"))
    mid_run = flood["runs"]["mid"]
    rooms = indoor(flood)
    wet = {k: wet_rooms(flood, k) for k in ("lo", "mid", "hi")}
    n_lo, n_mid, n_hi = (len(wet[k]) for k in ("lo", "mid", "hi"))
    entry = {k: max(0.0, lv[k] - ref) for k in lv}
    fsrc = floor_source(f)
    scen_src = Source(**sc["source"])
    labels = {r["id"]: r.get("label") or "unlabelled room" for r in plan.get("rooms") or []}
    opens = {o["id"]: o for o in plan.get("openings") or []}

    # Verdict
    count = f"{n_mid}" if n_lo == n_hi else f"between {n_lo} and {n_hi}"
    head = (f"With {flood['label']}, water stands {entry['mid']:.2f} m on the entry floor ({rng(entry['lo'], entry['hi'])})"
            if entry["hi"] > 0 else f"With {flood['label']}, the water stays below the floor")
    text = f"{head}; {count} of {len(rooms)} rooms take water."
    if not walls:
        text += (" This scan has no wall graph: no doors, windows or wall lengths, so the order rooms flood, the "
                 "openings water comes through and wetted wall area cannot be worked out.")
    if _kind(sid) not in ("house", None):
        text += f" This scan is a{'n' if _kind(sid)[0] in 'aeio' else ''} {_kind(sid).replace('_', ' ')}: which storey " \
                "it sits on is not known, so depths assume its floor is at ground level."
    if f["method"] == "assumed":
        text += " The floor height is assumed, not measured."
    status = "unknown" if not walls else "fail" if n_mid else "warn" if n_hi else "pass"
    if flood["scenario_fallback"]:
        text = f"{flood['scenario_fallback']} " + text

    metrics = [
        Metric(id="depth_inside", label="Water on the entry floor", value=round(entry["mid"], 2), unit="m", source=GEO),
        Metric(id="rooms_wet", label="Rooms taking water", value=n_mid, unit="", source=GEO),
        Metric(id="floor_height", label="Floor above the ground", value=f["value_m"], unit="m", source=fsrc),
        Metric(id="wetted_wall", label="Wall below the water line", value=round(sum(r.get("wall_area_mid", 0) for r in rooms), 1)
               if walls else None, unit="m2", source=GEO),
        Metric(id="depth_inside_low", label="Water on the entry floor, low end", value=round(entry["lo"], 2), unit="m", source=GEO),
        Metric(id="depth_inside_high", label="Water on the entry floor, high end", value=round(entry["hi"], 2), unit="m", source=GEO),
        Metric(id="rooms_wet_low", label="Rooms taking water, low end", value=n_lo, unit="", source=GEO),
        Metric(id="rooms_wet_high", label="Rooms taking water, high end", value=n_hi, unit="", source=GEO),
        Metric(id="depth_outside", label="Water above the ground outside", value=round(sc["depth_m"], 2), unit="m", source=scen_src),
        Metric(id="floor_height_low", label="Floor above the ground, low end", value=f["lo_m"], unit="m", source=fsrc),
        Metric(id="floor_height_high", label="Floor above the ground, high end", value=f["hi_m"], unit="m", source=fsrc),
    ] + [Metric(id=f"depth.{r['room']}", label=r["label"], value=round(r.get("depth_mid", 0), 2), unit="m", source=GEO)
         for r in sorted(wet["hi"], key=lambda r: -r.get("depth_hi", 0))]

    order = [r for r in sorted(wet["hi"], key=lambda r: (r.get("floods_at") is None, r.get("floods_at") or 0))]
    checks, findings = [], [floor_finding(sid, flood)]
    for i, r in enumerate(order, 1):
        st = "fail" if r.get("depth_mid", 0) > 0 else "warn"
        fid = f"flood_rehearsal:{sid}:{r['room']}"
        via = opens.get(r.get("via") or "")
        how = ""
        if via is not None and r.get("floods_at") is not None:
            kind = {"doorway": "doorway", "window": "window", "opening": "opening"}.get(via["type"], "opening")
            where = "from outside" if len(via.get("rooms") or []) == 1 else "from the " + " / ".join(
                labels.get(x, "?") for x in via["rooms"] if x != r["room"])
            how = f" Water comes in through a {kind} {where} once it is {r['floods_at'] - ref:+.2f} m from the entry floor."
        step = f" This room sits {abs(r['step_m']):.2f} m {'below' if r['step_m'] < 0 else 'above'} the rest of its floor." \
            if abs(r.get("step_m") or 0) > 0.01 else ""
        findings.append(Finding(
            id=fid, title=f"Water in the {r['label']}", status=st, anchor=RoomAnchor(sid=sid, room=r["room"]), source=GEO,
            detail=(f"{r.get('depth_mid', 0):.2f} m deep ({rng(r.get('depth_lo', 0), r.get('depth_hi', 0))}). Floods "
                    f"{_nth(i)} of {len(order)}. Floor {r.get('floor_area_mid', 0):.1f} m2 wet"
                    + (f", {r.get('wall_area_mid', 0):.1f} m2 of wall below the line." if walls else ".") + how + step)))
        checks.append(Check(id=r["room"], rule=f"Water on the floor, {r['label']}", measured=round(r.get("depth_mid", 0), 3),
                            threshold=0.0, unit="m", status=st, findings=[fid]))
    for r in rooms:
        if r not in order:
            checks.append(Check(id=r["room"], rule=f"Water on the floor, {r['label']}", measured=0.0, threshold=0.0,
                                unit="m", status="pass"))

    over_mid = set(mid_run.get("openings_overtopped") or []) if walls else set()
    over_hi = set(flood["runs"]["hi"].get("openings_overtopped") or []) if walls else set()
    ext_mid = sorted(o for o in over_mid if len(opens[o].get("rooms") or []) == 1)
    for oid in ext_mid:
        o = opens[oid]
        findings.append(Finding(
            id=f"flood_rehearsal:{sid}:{oid}", title=f"{o['type'].capitalize()} to outside goes under, {labels.get(o['rooms'][0], '?')}",
            status="fail", anchor=OpeningAnchor(sid=sid, opening=oid), source=GEO,
            detail=f"Sill {o['sill'] - ref:+.2f} m from the entry floor; water {lv['mid'] - o['sill']:.2f} m above it "
                   f"({rng(max(0, lv['lo'] - o['sill']), max(0, lv['hi'] - o['sill']))})."))

    if flood["scenario"].get("marks"):
        m = flood["scenario"]["marks"][0]
        findings.append(Finding(id=f"flood_rehearsal:{sid}:harvey", title="Harvey high-water marks near this house",
                                status="unknown", anchor=GeoAnchor(geo=(m["lon"], m["lat"])), source=scen_src,
                                detail=f"{sc['depth_m']:.2f} m above the lot's ground ({rng(sc['lo_m'], sc['hi_m'])}). "
                                       f"{sc['note']} Nearest mark: {m['waterbody'] or 'unnamed water'}, "
                                       f"{m['distance_m']} m away, quality {m['quality']}."))
    grade = f.get("grade")
    if grade:
        findings.append(Finding(id=f"flood_rehearsal:{sid}:grade", title="How the ground falls around the house",
                                status="unknown", anchor=GeoAnchor(geo=tuple(grade["low_lonlat"])),
                                source=Source(layer="vexcel", method="lookup", confidence="medium",
                                              note="Vexcel bare-ground model 3 m around the footprint, relative heights"),
                                detail=f"The ground 3 m out from the walls varies by {grade['fall_m']:.2f} m; the low "
                                       f"side is the {grade['low_side']}. Water reaches that wall first."))
    ll = (flood["site"] or {}).get("lat"), (flood["site"] or {}).get("lon")
    if ll[0] is not None:
        try:
            z = public.fema_zone(*ll)
            findings.append(Finding(
                id=f"flood_rehearsal:{sid}:fema", title="FEMA flood zone", status="warn" if z["in_sfha"] else "unknown",
                anchor=GeoAnchor(geo=(ll[1], ll[0])),
                source=Source(layer="model", method="lookup", confidence="medium",
                              note="FEMA special flood hazard areas, Esri's hosted copy; hazards.fema.gov was unreachable"),
                detail=(f"Inside FEMA's mapped 1% annual chance floodplain (zone {z['zone']}"
                        f"{', ' + z['subtype'] if z.get('subtype') else ''})." if z["in_sfha"] else
                        "Outside FEMA's mapped 1% annual chance floodplain. That is not safety: the Harris County Flood "
                        "Control District counted most homes Harvey flooded as outside it.")))
        except Exception:  # noqa: BLE001, S110 - the flood zone is context; the result stands without it
            pass
    if not walls:
        findings.append(Finding(id=f"flood_rehearsal:{sid}:no_walls", title="What this scan cannot show", status="unknown",
                                anchor=None, source=GEO,
                                detail="No wall graph in this scan, so there are no doors, windows or wall lengths. "
                                       "Every room is taken to flood from its floor at once; flood order, openings "
                                       "overtopped and wetted wall area are not worked out."))

    pins = [Pin(id=f"order:{r['room']}", anchor=RoomAnchor(sid=sid, room=r["room"]), label=str(i),
                status="fail" if r.get("depth_mid", 0) > 0 else "warn") for i, r in enumerate(order, 1)]
    overlays = [WaterOverlay(level_m=round(lv["mid"], 3)),
                LensOverlay(values={r["room"]: round(r.get("depth_mid", 0), 3) for r in rooms}, ramp="sequential",
                            legend=Legend(title="Water depth", unit="m", min=0,
                                          max=round(max([r.get("depth_hi", 0) for r in rooms] + [0.01]), 2)))]
    if over_mid:
        overlays.append(RuleOverlay(select=SelectOpenings(openings=sorted(over_mid)), style="fail"))
    if over_hi - over_mid:
        overlays.append(RuleOverlay(select=SelectOpenings(openings=sorted(over_hi - over_mid)), style="warn"))
    if pins:
        overlays.append(PinsOverlay(pins=pins))

    assumptions = [
        Assumption(id="flood.depth_m", label="Water above the ground outside", value=inputs.depth_m, unit="m", editable=True),
        Assumption(id="flood.floor_height_m", label=f"Floor above the ground ({METHOD_NAME.get(f['method'], f['method'])})",
                   value=f["value_m"], unit="m", editable=True),
        Assumption(id="floor_height_range", label="Floor height range", value=rng(f["lo_m"], f["hi_m"]), unit=None),
        Assumption(id="still_water", label="Water stands level and fills through openings by sill height; walls and "
                                           "closed doors do not hold it back", value=True),
        Assumption(id="water_level_scan_z", label="Water level in the scan frame, low / middle / high",
                   value=" / ".join(f"{lv[k]:.2f}" for k in ("lo", "mid", "hi")), unit="m"),
    ]
    actions = [Action(id="deeper", label="Rehearse 0.3 m deeper", tool="flood_rehearsal",
                      inputs={"scan": sid, "depth_m": round(min(3.0, inputs.depth_m + 0.3), 2), "scenario": inputs.scenario}),
               Action(id="valuables", label="What sits below the water line", tool="valuables_height",
                      inputs={"scan": sid, "depth_m": inputs.depth_m, "scenario": inputs.scenario}),
               Action(id="plan", label="Plan the hours before the storm", tool="storm_plan",
                      inputs={"scan": sid, "depth_m": inputs.depth_m, "scenario": inputs.scenario})]
    if inputs.scenario != "harvey_2017":
        actions.append(Action(id="harvey", label="Rehearse Harvey 2017 here", tool="flood_rehearsal",
                              inputs={"scan": sid, "depth_m": inputs.depth_m, "scenario": "harvey_2017"}))
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), metrics=metrics,
                      checks=checks, findings=findings, overlays=overlays, assumptions=assumptions, actions=actions)


def _nth(i: int) -> str:
    return {1: "first", 2: "second", 3: "third"}.get(i, f"{i}th")


def _kind(sid: str) -> str | None:
    try:
        from ...sources import index
        return (index.rows().get(sid) or {}).get("kind")
    except Exception:  # noqa: BLE001 - the index is context only
        return None
