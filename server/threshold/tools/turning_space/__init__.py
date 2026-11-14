"""Turning space: the largest circle in each room, against the 60 in (1525 mm) wheelchair turning circle."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry import turning_spaces
from .. import (Assumption, Check, Finding, Legend, LensOverlay, Metric, Pin, PinsOverlay, PointAnchor, RoomAnchor,
                ScanScope, ToolResult, Verdict, field, tool)
from .._access import GEO, STD, fmt, quality, rooms

SKIP = {"Void", "Closet", "Pantry"}


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    diameter_m: float = field(1.525, pref="access.turning_diameter_m", unit="m", gt=0.3, le=3.0,
                              description="Turning circle you need")
    rooms: list[str] | None = field(None, description="Room types or ids to check; default every room but closets")


@tool(id="turning_space", title="Turning space", icon="rotate",
      summary="Finds the largest clear circle in each room and checks it against the turning circle you need.",
      model_description="Largest turning circle that fits in each room of one scan (empty room, wall face to wall "
                        "face) against a diameter, default the ADA 60 in (1.525 m). Returns a lens of diameters, a "
                        "check per room and pins at each circle's centre.",
      personas=["wheelchair_user", "wheelchair_home_search", "robot_maker"], requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.walls"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "Controls", "AssumptionChips", "StepLog"],
      overlays=["lens", "pins"], examples=["Can I turn my wheelchair around in the bathroom?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid, need = inputs.scan, inputs.diameter_m
    plan = ctx.plan(sid)
    scope = ScanScope(sid=sid)
    assumptions = [Assumption(id="access.turning_diameter_m", label="Turning circle you need", value=need, unit="m",
                              editable=True),
                   Assumption(id="empty", label="Empty room: fixtures and furniture shrink the circle", value=True)]
    if not quality(plan).get("polygons"):
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "This scan has no room outlines (no wall graph), so turning space cannot be measured.")))
    ts = turning_spaces(plan, need)
    rs = rooms(plan)
    want = inputs.rooms
    rows = [t for t in (ts["rooms"] if ts["available"] else [])
            if (rs[t["room"]].get("label") not in SKIP) and
            (not want or t["room"] in want or rs[t["room"]].get("label") in want)]
    ctx.step(f"Fitted the largest circle in {len(rows)} rooms")
    if not rows:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "None of the rooms asked for has a floor outline in this scan.")))
    checks, findings, pins = [], [], []
    for t in sorted(rows, key=lambda t: t["diameter"]):
        fid = f"turning_space:{sid}:{t['room']}"
        bad = t["status"] != "pass"
        if bad:
            findings.append(Finding(id=fid, title=f"Too tight to turn, {t['label']}" if t["status"] == "fail"
                                    else f"Turning circle too close to call, {t['label']}", status=t["status"],
                                    anchor=RoomAnchor(sid=sid, room=t["room"]), source=GEO,
                                    detail=f"Largest circle in the empty room {fmt(t['diameter'])} across, you need "
                                           f"{fmt(need)}. A T-shaped turn in a 60 in square may still work. {STD['turn']}."))
        checks.append(Check(id=f"turn.{t['room']}", rule=f"Turning circle, {t['label']}", measured=round(t["diameter"], 3),
                            threshold=need, unit="m", status=t["status"], standard=STD["turn"],
                            findings=[fid] if bad else []))
        z = next((f.get("elevation") or 0.0 for f in plan["floors"] if f["id"] == rs[t["room"]]["floor"]), 0.0)
        pins.append(Pin(id=f"turn.{t['room']}", anchor=PointAnchor(sid=sid, point=(*t["center"], z)),
                        label=f"{t['diameter']:.2f} m circle", status=t["status"]))
    lens = ts["lens"]
    vals = {k: v for k, v in lens["values"].items() if k in {t["room"] for t in rows}}
    fails = [t for t in rows if t["status"] == "fail"]
    warns = [t for t in rows if t["status"] == "warn"]
    status = "fail" if fails else "warn" if warns else "pass"
    text = (f"{len(fails)} of {len(rows)} rooms cannot hold the turning circle in the empty room." if fails else
            f"Every room holds the circle, {len(warns)} only just." if warns else
            "Every room checked holds the turning circle in the empty room.")
    by = lambda lab: max((t["diameter"] for t in rows if t["label"] == lab), default=None)
    metrics = [Metric(id="rooms_ok", label="Rooms that hold the circle", value=sum(t["status"] == "pass" for t in rows),
                      unit="", source=GEO),
               Metric(id="bathroom", label="Best bathroom circle", value=_r(by("Bathroom")), unit="m", source=GEO),
               Metric(id="kitchen", label="Kitchen circle", value=_r(by("Kitchen")), unit="m", source=GEO),
               Metric(id="largest", label="Largest circle", value=_r(max(t["diameter"] for t in rows)), unit="m",
                      source=GEO)]
    metrics += [Metric(id=f"circle.{t['room']}", label=t["label"], value=_r(t["diameter"]), unit="m", source=GEO)
                for t in rows]
    return ToolResult(scope=scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, assumptions=assumptions,
                      overlays=[LensOverlay(values=vals, ramp="sequential",
                                            legend=Legend(title="Largest turning circle", unit="m", min=0,
                                                          max=max(vals.values()))), PinsOverlay(pins=pins)])


def _r(x):
    return round(x, 2) if x is not None else None
