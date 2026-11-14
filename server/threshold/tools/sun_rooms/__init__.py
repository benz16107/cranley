"""Sun rooms: which rooms get direct sun, for how many hours, on a day and at the solstices and equinoxes, with
neighbours and trees from Vexcel's surface model in the way; and the best room for plants, for a home office without
glare and for a bedroom that stays cool.

Windows, their sills and heights come from the wall graph; their facing from the scan's compass rotation
(geometry.georef, checked against Vexcel footprints); the sun from the NOAA algorithm; obstruction from the skyline
the surface model makes from each window (threshold.sun).
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from ... import sun
from ...aerial.vexcel import VexcelError
from .. import (
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
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

NOT_ROOMS = ("void", "closet", "garage", "hallway", "staircase", "stairs", "pantry", "laundry", "utility", "storage",
             "patio", "porch", "balcony", "entry", "foyer")
NOT_OFFICE = NOT_ROOMS + ("bathroom", "kitchen", "dining")
WORK = (9 * 60, 17 * 60)       # working hours for glare
AFTERNOON = 12 * 60            # summer afternoon sun heats a bedroom for the night
WIN = Source(layer="matterport", method="geometry", confidence="high",
             note="Window positions, sills and heights from the wall graph")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    date: str | None = field(None, pref="sun_rooms.date", pattern=r"^\d{4}-\d{2}-\d{2}$",
                             description="Day to trace the sun on, YYYY-MM-DD; today if empty. The equinoxes and "
                                         "solstices of its year are always traced too.")


def _is(label: str | None, words) -> bool:
    return any(w in (label or "").lower() for w in words)


def names(plan: dict, dirs: dict[str, list[str]]) -> dict[str, str]:
    """A name per room that tells same-label rooms apart: "Bedroom 2 (SSE)", numbered largest first, with the way
    the room's windows face."""
    rooms = sorted((r for r in plan["rooms"] if r.get("label") != "Void"), key=lambda r: -(r.get("area") or 0))
    base = {r["id"]: r.get("label") or "Unlabelled room" for r in rooms}
    count, seen, out = {}, {}, {}
    for n in base.values():
        count[n] = count.get(n, 0) + 1
    for r in rooms:
        n = base[r["id"]]
        if count[n] > 1:
            seen[n] = seen.get(n, 0) + 1
            n = f"{n} {seen[n]}" + (f" ({'/'.join(dirs[r['id']])})" if dirs.get(r["id"]) else "")
        out[r["id"]] = n
    return out


def per_room(trace: dict, days: list[tuple[str, str, dt.date]]) -> dict[str, dict]:
    """room -> {dirs, glass_m2, windows, days: {day id: {hours, lost_h, work_h, pm_glass_m2h}}}. A room's hours are the
    union of its windows' sunlit minutes; `lost_h` is time the sun was in front of a window but behind a neighbour or
    a tree; `pm_glass_m2h` is sunlit glass area times hours after noon."""
    step = trace["step_min"] / 60
    out: dict[str, dict] = {}
    for w in trace["windows"]:
        r = out.setdefault(w["room"], {"dirs": [], "glass_m2": 0.0, "windows": 0, "_d": {}})
        r["dirs"].append(w["compass"])
        r["glass_m2"] += w["glass_m2"]
        r["windows"] += 1
        for key, _, d in days:
            x = w["days"][d.isoformat()]
            acc = r["_d"].setdefault(key, {"lit": set(), "front": set(), "pm": 0.0})
            acc["lit"] |= x["minutes"]
            acc["front"] |= x["front"]
            acc["pm"] += w["glass_m2"] * sum(1 for m in x["minutes"] if m >= AFTERNOON) * step
    for r in out.values():
        r["dirs"] = sorted(set(r["dirs"]), key=r["dirs"].index)
        r["glass_m2"] = round(r["glass_m2"], 2)
        r["days"] = {k: {"hours": round(len(a["lit"]) * step, 1), "lost_h": round(len(a["front"] - a["lit"]) * step, 1),
                         "work_h": round(sum(1 for m in a["lit"] if WORK[0] <= m < WORK[1]) * step, 1),
                         "pm_glass_m2h": round(a["pm"], 1)} for k, a in r.pop("_d").items()}
    return out


def _mean(r: dict, key: str, seasons: list[str]) -> float:
    return sum(r["days"][s][key] for s in seasons) / len(seasons)


@tool(id="sun_rooms", title="Sun by room", icon="sun",
      summary="Hours of direct sun in each room on a day and at the solstices and equinoxes, with neighbours and trees "
              "in the way, and the best room for plants, a home office and a cool bedroom.",
      model_description="For one scan with windows and geocoordinates: per room, hours of direct sun through its "
                        "windows on a date (default today) and on the two solstices and equinoxes, with obstruction by "
                        "neighbouring buildings and trees from Vexcel's surface model along each window's sight line. "
                        "Picks the best room for plants (most sun across the year), for a home office (daylight with "
                        "the least direct sun in working hours, so the least glare) and for a bedroom that stays cool "
                        "(least sunlit glass on summer afternoons). Lens of sun hours per room, pins on the windows.",
      personas=["room_chooser", "renter_listing"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.geo"},
                {"layer": "vexcel.dsm", "need": "optional", "fallback": "sun hours with nothing in the way"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "RankedTable", "CheckList", "FloorPlanMini", "Controls",
              "AssumptionChips", "StepLog"],
      overlays=["lens", "pins"],
      examples=["Which room is best for my plants?", "Where should my home office go to avoid glare?",
                "Which bedroom stays coolest in summer?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    scope = ScanScope(sid=inputs.scan)
    day = dt.date.fromisoformat(inputs.date) if inputs.date else dt.date.today()
    days = sun.key_days(day)
    if not (plan.get("geo") or {}).get("lat"):
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text="This scan has no geocoordinates, so its "
                          "windows cannot be placed on a compass and the sun cannot be traced."))
    g, why = None, None
    try:
        ctx.step("Reading Vexcel's surface model round the building (roofs, trees, ground)")
        g = sun.horizon.grid(plan["geo"]["lat"], plan["geo"]["lon"])
    except (VexcelError, KeyError, OSError, ValueError) as e:  # no key, Vexcel down, an unreadable raster
        why = f"the surface model could not be read ({str(e)[:80]})"
    trace = sun.window_sun(plan, [d for _, _, d in days], g)
    if not trace["available"]:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=trace["reason"] + " Sun by room needs "
                          "windows; marking them is optional in Matterport, so a scan can have none."))
    ctx.step(f"Traced {len(trace['windows'])} windows over {len(days)} days, every 10 minutes"
             + ("; skyline from the surface model" if g is not None else f"; nothing in the way, since {why}"))
    rooms = per_room(trace, days)
    labels = {r["id"]: r.get("label") for r in plan["rooms"]}
    name = names(plan, {k: v["dirs"] for k, v in rooms.items()})
    rooms = {k: v for k, v in rooms.items() if k in name}
    sure = bool((plan.get("quality") or {}).get("georef"))
    sun_src = Source(layer="vexcel" if g is not None else "matterport", method="simulation",
                     confidence="medium" if sure and g is not None else "low",
                     note="NOAA sun position against window facings from the scan's compass rotation "
                          + ("(fitted to the Vexcel footprint, typically within 3 degrees)" if sure else "(not checked against an aerial footprint)")
                          + ("; neighbours and trees from Vexcel's surface model at 0.6 m, trees as solid all year"
                             if g is not None else "; neighbours and trees not counted")
                          + "; eaves, awnings and blinds not counted")
    seasons = [k for k, _, _ in days if k != "day"] or [days[0][0]]
    sel = days[0][0]
    dlabel = dict((k, lab) for k, lab, _ in days)

    plants = [k for k in rooms if not _is(labels.get(k), NOT_ROOMS)]
    office = [k for k in rooms if not _is(labels.get(k), NOT_OFFICE)]
    beds = [k for k in rooms if _is(labels.get(k), ("bedroom",))]
    picks = []
    if plants:
        k = max(plants, key=lambda k: (_mean(rooms[k], "hours", seasons), rooms[k]["glass_m2"]))
        picks.append(("plants", "Best room for plants", k,
                      f"The most direct sun across the year: {_mean(rooms[k], 'hours', seasons):.1f} h a day on "
                      f"average over the solstices and equinoxes, {rooms[k]['days']['december_solstice']['hours'] if 'december_solstice' in rooms[k]['days'] else rooms[k]['days'][sel]['hours']:.1f} h "
                      f"at midwinter, through {rooms[k]['glass_m2']:.1f} m² of glass facing {', '.join(rooms[k]['dirs'])}."))
    if office:
        k = min(office, key=lambda k: (_mean(rooms[k], "work_h", seasons), -rooms[k]["glass_m2"]))
        picks.append(("office", "Best room for a home office", k,
                      f"Daylight through {rooms[k]['glass_m2']:.1f} m² of glass facing {', '.join(rooms[k]['dirs'])}, "
                      f"with {_mean(rooms[k], 'work_h', seasons):.1f} h of direct sun between 9:00 and 17:00 on an "
                      "average solstice or equinox day: the least glare on a screen of the rooms with windows."))
    if beds:
        hot = "june_solstice" if "june_solstice" in rooms[beds[0]]["days"] else sel
        k = min(beds, key=lambda k: (rooms[k]["days"][hot]["pm_glass_m2h"], rooms[k]["days"][hot]["hours"]))
        picks.append(("bedroom", "Coolest bedroom in summer", k,
                      f"The least afternoon sun at midsummer: {rooms[k]['days'][hot]['pm_glass_m2h']:.1f} m²·h of "
                      f"sunlit glass after noon on the {dlabel[hot]} (glass area times hours of sun on it), windows "
                      f"facing {', '.join(rooms[k]['dirs'])}."))

    findings = [Finding(id=f"sun_rooms:{inputs.scan}:{key}", title=f"{title}: {name[k]}", status="pass", detail=detail,
                        anchor=RoomAnchor(sid=inputs.scan, room=k), source=sun_src) for key, title, k, detail in picks]
    checks = []
    order = sorted(rooms, key=lambda k: -rooms[k]["days"][sel]["hours"])
    for k in order:
        r = rooms[k]
        by_day = "; ".join(f"{dlabel[d]} {r['days'][d]['hours']:.1f} h" for d, _, _ in days)
        lost = sum(r["days"][d]["lost_h"] for d in seasons) / len(seasons)
        fid = f"sun_rooms:{inputs.scan}:{k}"
        findings.append(Finding(id=fid, title=f"Sun in {name[k]}", status="pass" if r["days"][sel]["hours"] else "unknown",
                                anchor=RoomAnchor(sid=inputs.scan, room=k), source=sun_src,
                                detail=f"{r['windows']} window{'s' if r['windows'] != 1 else ''} facing {', '.join(r['dirs'])}, "
                                       f"{r['glass_m2']:.1f} m² of glass. Direct sun: {by_day}."
                                       + (f" Neighbours and trees take {lost:.1f} h a day on average." if lost >= 0.2 else "")))
        checks.append(Check(id=k, rule=f"Direct sun, {name[k]}, {dlabel[sel]}", measured=r["days"][sel]["hours"],
                            threshold=None, unit="h", status="pass" if r["days"][sel]["hours"] else "unknown", findings=[fid]))

    pins = []
    for w in trace["windows"]:
        x = w["days"][day.isoformat()]
        front_h = len(x["front"]) * trace["step_min"] / 60
        st = "unknown" if not front_h else "warn" if x["blocked_hours"] >= x["hours"] else "pass"
        pins.append(Pin(id=w["opening"], anchor=OpeningAnchor(sid=inputs.scan, opening=w["opening"]), status=st,
                        label=f"{w['compass']}, {x['hours']:.1f} h" + (f" ({x['blocked_hours']:.1f} h shaded)" if x["blocked_hours"] >= 0.2 else "")))
    lens = {r["id"]: rooms[r["id"]]["days"][sel]["hours"] if r["id"] in rooms else 0.0
            for r in plan["rooms"] if r["id"] in name and r.get("polygon")}
    sr = trace["sunrise_sunset"].get(day.isoformat())
    total_lost = sum(rooms[k]["days"][sel]["lost_h"] for k in rooms)
    metrics = [Metric(id="windows", label="Windows traced", value=len(trace["windows"]), unit="", source=WIN),
               Metric(id="sunny_rooms", label=f"Rooms with direct sun, {dlabel[sel]}", unit="", source=sun_src,
                      value=sum(1 for k in rooms if rooms[k]["days"][sel]["hours"] > 0)),
               Metric(id="best_hours", label=f"Most sun in one room, {dlabel[sel]}", unit="h", source=sun_src,
                      value=max((rooms[k]["days"][sel]["hours"] for k in rooms), default=0)),
               Metric(id="lost_hours", label=f"Room-hours lost to neighbours and trees, {dlabel[sel]}", unit="h",
                      value=round(total_lost, 1), source=sun_src)]
    metrics += [Metric(id=f"sun.{name[k]}", label=name[k], value=rooms[k]["days"][sel]["hours"], unit="h", source=sun_src)
                for k in order]
    text = " ".join(f"{t}: {name[k]}." for _, t, k, _ in picks) or "No room with windows is a living space."
    if g is None:
        text += f" Neighbours and trees are not counted, because {why}."
    if not sure:
        text += " The compass rotation is not checked against an aerial footprint, so facings may be off."
    ctx.step(f"Ranked {len(rooms)} rooms; sunrise {sr[0] if sr else '-'}, sunset {sr[1] if sr else '-'} on {day.isoformat()}")
    return ToolResult(
        scope=scope, verdict=Verdict(status="pass", text=text), metrics=metrics, checks=checks, findings=findings,
        overlays=[LensOverlay(values=lens, ramp="sequential",
                              legend=Legend(title=f"Direct sun, {dlabel[sel]}", unit="h", min=0,
                                            max=max(lens.values(), default=0))),
                  PinsOverlay(pins=pins)],
        assumptions=[Assumption(id="sun_rooms.date", label="Day traced", value=day.isoformat(), editable=True),
                     Assumption(id="seasons", label="Also traced", value=", ".join(lab for k, lab, _ in days if k != "day")),
                     Assumption(id="compass_checked", label="Compass rotation fitted to the aerial footprint", value=sure),
                     Assumption(id="obstruction", label="Neighbours and trees from Vexcel's surface model", value=g is not None),
                     Assumption(id="trees_solid", label="Trees block sun all year, as captured (leaves on)", value=True),
                     Assumption(id="floor_above_ground", label="Lowest floor above the soil", value=0.2, unit="m"),
                     Assumption(id="not_counted", label="Eaves, awnings, blinds and window glass type not counted", value=True),
                     Assumption(id="office_hours", label="Glare counted between", value="09:00-17:00")])
