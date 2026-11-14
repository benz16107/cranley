"""Daylight: per room, how many windows, how much glass, which way they face and how long the sun reaches them.

Window counts and glazed area come from the wall graph (geometry takeoff). Directions and sun hours come from
`geometry.sun_on_windows`, which turns the scan by its compass rotation; until that rotation is checked against an
aerial photo (`geometry.georef.VERIFIED`) every direction is low confidence and the wording says "if".
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from ... import geometry
from .. import (
    Assumption,
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    RoomAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..record_vs_reality import measure

HABITABLE = {"Bedroom", "Living Room", "Family Room", "Dining Room", "Kitchen", "Office", "Den", "Loft", "Bonus Room",
             "Game Room", "Exercise Room"}
GLASS = Source(layer="matterport", method="geometry", confidence="high", note="Window widths and heights in the wall graph")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    date: str | None = field(None, pref="daylight.date", description="Day to trace the sun on, YYYY-MM-DD; today if empty",
                             pattern=r"^\d{4}-\d{2}-\d{2}$")


def _minutes(span: list[str]) -> set[int]:
    a, b = (int(t[:2]) * 60 + int(t[3:]) for t in span)
    return set(range(a, b, 10))


def per_room(plan: dict, day: dt.date) -> dict:
    """{available, rooms: {room: {windows, glazed_m2, directions, hours, spans}}, verified, sunrise, sunset}."""
    wb = measure.windows_by_room(plan)
    if not wb["available"]:
        return {"available": False, "reason": wb["reason"]}
    if not wb["total"]["windows"]:
        return {"available": False, "reason": "This scan records doorways but no windows; marking windows is optional "
                                              "in Matterport, so a missing window here means an unmarked one."}
    sun = geometry.sun_on_windows(plan, day)
    rooms = {rid: {"windows": v["windows"], "glazed_m2": v["glazed_m2"], "directions": [], "minutes": set()}
             for rid, v in wb["rooms"].items()}
    if sun["available"]:
        for o in sun["openings"]:
            if o["type"] != "window" or o["room"] not in rooms:
                continue
            r = rooms[o["room"]]
            r["directions"].append(o["compass"])
            for span in o["sun"]:
                r["minutes"] |= _minutes(span)
    for r in rooms.values():
        r["hours"] = round(len(r.pop("minutes")) / 6, 1) if sun["available"] else None
        r["directions"] = sorted(set(r["directions"]))
    return {"available": True, "rooms": rooms, "sun": sun["available"], "sun_reason": sun.get("reason"),
            "verified": bool(sun.get("verified")), "sunrise": sun.get("sunrise"), "sunset": sun.get("sunset"),
            "total": wb["total"]}


@tool(id="daylight", title="Daylight", icon="sun",
      summary="Windows, glass area, the way each room faces and its hours of direct sun on a chosen day.",
      model_description="For one scan, per room: window count and glazed area from the wall graph, the compass "
                        "direction of each window and the hours of direct sun on a date. Returns a lens of sun hours "
                        "per room and findings for rooms with no window. Directions are low confidence until the "
                        "scan's compass rotation is verified.",
      personas=["renter_listing", "older_adult_family", "office_tenant"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.geo", "need": "optional",
                                                   "fallback": "window counts and glass area only"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "FloorPlanMini", "Controls", "AssumptionChips",
              "StepLog"],
      overlays=["lens"], examples=["Which bedroom gets morning sun?", "Is the living room bright in winter?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    day = dt.date.fromisoformat(inputs.date) if inputs.date else dt.date.today()
    d = per_room(plan, day)
    scope = ScanScope(sid=inputs.scan)
    if not d["available"]:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=d["reason"] + " Daylight cannot be read."))
    ctx.step(f"Read windows in {sum(1 for r in d['rooms'].values() if r['windows'])} rooms from the wall graph")
    sure = d["sun"] and d["verified"] and (plan.get("quality") or {}).get("georef")
    if d["sun"]:
        ctx.step(f"Traced the sun on {day.isoformat()} (sunrise {d['sunrise']}, sunset {d['sunset']})"
                 + ("" if sure else "; the compass rotation is not yet verified, so directions are low confidence"))
    else:
        ctx.step(f"No sun trace: {d['sun_reason']}")
    sun_src = Source(layer="matterport", method="simulation", confidence="medium" if sure else "low",
                     note=("NOAA sun position against window directions; " if d["sun"] else "") +
                     ("compass rotation verified" if sure else "compass rotation not verified against an aerial photo")
                     + "; trees, neighbours and eaves not counted")
    iff = "" if sure else "If the scan's compass rotation is right, "
    labels = {r["id"]: r.get("label") for r in plan["rooms"]}
    rooms = {k: v for k, v in d["rooms"].items() if labels.get(k) != "Void"}
    checks, findings, metrics = [], [], []
    for rid, r in sorted(rooms.items(), key=lambda kv: -(kv[1]["hours"] or kv[1]["glazed_m2"])):
        lab = labels.get(rid)
        dark = r["windows"] == 0 and lab in HABITABLE
        fid = f"daylight:{inputs.scan}:{rid}"
        name = lab or "Unlabelled room"
        if r["windows"]:
            sun = (f" {iff}{'they face' if len(r['directions']) > 1 else 'it faces'} {', '.join(r['directions'])} "
                   f"and get{'s' if len(r['directions']) == 1 and not iff else ''} {r['hours']:.1f} h of direct sun on "
                   f"{day.isoformat()}." if r["hours"] is not None else "")
            detail = f"{r['windows']} window{'s' if r['windows'] != 1 else ''}, {r['glazed_m2']:.1f} m² of glass.{sun}"
        else:
            detail = "No window in the wall graph: light comes only through doorways."
        checks.append(Check(id=rid, rule=f"Direct sun, {name}", measured=r["hours"] if r["hours"] is not None else None,
                            threshold=None, unit="h", status="warn" if dark else "pass" if r["windows"] else "unknown",
                            findings=[fid] if dark else []))
        if dark:
            findings.append(Finding(id=fid, title=f"{name} has no window", status="warn", detail=detail,
                                    anchor=RoomAnchor(sid=inputs.scan, room=rid), source=GLASS))
    lens_vals = {rid: (r["hours"] if r["hours"] is not None else round(r["glazed_m2"], 2)) for rid, r in rooms.items()}
    unit, title = ("h", f"Direct sun on {day.isoformat()}") if d["sun"] else ("m²", "Glazed area")
    best = max(rooms.items(), key=lambda kv: kv[1]["hours"] or 0, default=None)
    if d["sun"] and best and best[1]["hours"]:
        rid, r = best
        findings.insert(0, Finding(id=f"daylight:{inputs.scan}:sunniest", title=f"Sunniest room: {labels.get(rid) or 'unlabelled'}",
                                   status="pass", detail=f"{iff}its windows face {', '.join(r['directions'])} and get "
                                   f"{r['hours']:.1f} h of direct sun on {day.isoformat()}.",
                                   anchor=RoomAnchor(sid=inputs.scan, room=rid), source=sun_src))
    t = d["total"]
    metrics = [Metric(id="windows", label="Windows", value=t["windows"], unit="", source=GLASS),
               Metric(id="glazed_area", label="Glass area", value=round(t["glazed_area"], 1), unit="m²", source=GLASS),
               Metric(id="glazing_ratio", label="Glass to floor", value=round(100 * (t["glazing_ratio"] or 0)), unit="%",
                      source=GLASS),
               Metric(id="dark_rooms", label="Rooms with no window", value=sum(1 for f in findings if f.status == "warn"),
                      unit="", source=GLASS)]
    if d["sun"]:
        by_label: dict[str, float] = {}
        for rid, r in rooms.items():
            if r["hours"] is not None and labels.get(rid):
                by_label[labels[rid]] = max(by_label.get(labels[rid], 0), r["hours"])
        metrics += [Metric(id=f"sun.{k}", label=k, value=v, unit="h", source=sun_src) for k, v in sorted(by_label.items())]
    dark = [f for f in findings if f.status == "warn"]
    lit = len([r for r in rooms.values() if r["windows"]])
    text = f"{t['windows']} window{'' if t['windows'] == 1 else 's'} over {lit} room{'' if lit == 1 else 's'}"
    text += f"; {len(dark)} habitable room{'s have' if len(dark) != 1 else ' has'} no window." if dark else "."
    if d["sun"] and best and best[1]["hours"]:
        room = (labels.get(best[0]) or "unlabelled room").lower()
        text += f" {iff}the sunniest room is the {room}." if iff else f" The sunniest room is the {room}."
    elif not d["sun"]:
        text += f" {d.get('sun_reason') or 'The scan cannot be placed on a compass.'} Hours of sun cannot be traced."
    return ToolResult(
        scope=scope, verdict=Verdict(status="warn" if dark else "pass", text=text), metrics=metrics, checks=checks,
        findings=findings,
        overlays=[LensOverlay(values=lens_vals, ramp="sequential",
                              legend=Legend(title=title, unit=unit, min=min(lens_vals.values(), default=0),
                                            max=max(lens_vals.values(), default=0)))],
        assumptions=[Assumption(id="daylight.date", label="Day traced", value=day.isoformat(), editable=True),
                     Assumption(id="compass_verified", label="Compass rotation checked against an aerial photo",
                                value=bool(sure)),
                     Assumption(id="no_shading", label="Trees, neighbours, eaves and blinds are not counted", value=True)])
