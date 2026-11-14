"""Furniture fit: carry a named object from the entrance to a room. The path, each doorway and turn with its margin,
where it sticks (a Contract 4 box at the tightest point), and whether it fits along a wall once there.
`carry_audit` is shared with stretcher_route."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel

from ...geometry import carry, free_wall_runs
from ...geometry._plan import VERDICT_STATUS, clear_width, judge
from ...geometry.fit import _door_fit
from .. import (Assumption, Check, Finding, Metric, OpeningAnchor, PointAnchor, RoomAnchor, ScanScope, Source,
                ToolResult, Verdict, field, tool)
from ..types import BoxOverlay, RouteOverlay
from .._access import GEO, fmt, implausible, label, pick_entrance, quality, rooms, start_point

# length x depth x height in metres; `upright` keeps the height vertical (pianos and fridges travel standing)
PRESETS = {
    "sofa": ((2.13, 0.97, 0.86), False, "Living Room", "84 in three-seat sofa"),
    "loveseat": ((1.60, 0.90, 0.86), False, "Living Room", "63 in loveseat"),
    "king mattress": ((2.03, 1.93, 0.30), False, "Bedroom", "US king, 76 x 80 in, rigid"),
    "queen mattress": ((2.03, 1.52, 0.30), False, "Bedroom", "US queen, 60 x 80 in, rigid"),
    "upright piano": ((1.52, 0.64, 1.27), True, "Living Room", "60 in wide studio upright, travels standing"),
    "refrigerator": ((0.91, 0.86, 1.78), True, "Kitchen", "36 in French-door fridge, doors on, travels standing"),
    "washer": ((0.69, 0.76, 0.97), True, "Laundry", "27 in front-loader"),
    "wardrobe": ((1.20, 0.60, 2.00), False, "Bedroom", "assembled two-door wardrobe"),
    "dining table": ((1.83, 0.91, 0.76), False, "Dining Room", "72 in table, legs on"),
}
Obj = Literal[tuple(PRESETS)]


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    object: Obj = field("sofa", ask="What are you moving?", pref="furniture.object",
                        description="A named object; its size is an editable assumption")
    room: str | None = field(None, description="Room id or type to carry it to; default the usual room for it")
    length_m: float | None = field(None, pref="furniture.length_m", unit="m", gt=0.1, le=4,
                                   description="Longest side, if not the preset's")
    depth_m: float | None = field(None, pref="furniture.depth_m", unit="m", gt=0.1, le=3, description="Depth")
    height_m: float | None = field(None, pref="furniture.height_m", unit="m", gt=0.1, le=3, description="Height")
    entrance: str | None = field(None, description="Opening id of the door to come in by; default the main entrance")


def _yaw_near(route_pts: list, pt) -> float:
    best, yaw = math.inf, 0.0
    for a, b in zip(route_pts, route_pts[1:]):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        d = math.dist((mx, my), pt[:2])
        if d < best and math.dist(a[:2], b[:2]) > 1e-6:
            best, yaw = d, math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    return yaw


def carry_audit(ctx, plan: dict, tool_id: str, box: tuple, flat: bool, target: dict, entrance: str | None,
                what: str, name: str | None = None) -> dict:
    """carry() from the main entrance (its door checked too) to `target`. Returns checks, findings, overlays,
    the overall result and the tightest point."""
    sid = plan["sid"]
    ent = pick_entrance(plan, entrance)
    out = {"checks": [], "findings": [], "overlays": [], "result": "not available", "tight": None, "reason": None,
           "length": None}
    if ent is None:
        out["reason"] = "No doorway in this scan has a room on one side only, so there is no entrance to start from."
        return out
    if ent["floor"] != target["floor"]:
        out["reason"] = f"The {label(target).lower()} is on another floor; stairs are not in the scan data."
        out["result"] = "measure on site"
        return out
    c = carry(plan, start_point(plan, ent), target["id"], box, floor=target["floor"], flat=flat)
    if not c["available"]:
        out["reason"] = c["reason"]
        return out
    # the entrance door itself: carry starts just inside it
    cw = clear_width(ent) or 0.0
    h = ent.get("height") or 2.03
    slack, across, up = _door_fit(box, cw, h, flat)
    doors = [{"opening": ent["opening"], "clear_width": cw, "height": h, "slack": slack, "center": ent["center"],
              "implausible": implausible(ent),
              "result": "measure on site" if implausible(ent) else judge(slack, 0.0)}] + \
        [d for d in c["doors"] if d["opening"] != ent["opening"]]
    parts = []
    tname = name or label(target)
    for i, d in enumerate(doors):
        status = VERDICT_STATUS[d["result"]]
        fid = f"{tool_id}:{sid}:{target['id']}:door:{d['opening']}"
        where = "Entrance door" if i == 0 else f"Doorway {i}"
        detail = (f"The scan records {d['clear_width'] * 100 + 5:.0f} cm here, narrower than any door: a data error. "
                  "Measure on site." if d["implausible"] else
                  f"{fmt(d['clear_width'])} clear, {fmt(d['height'])} high; {what} goes through end first with "
                  f"{d['slack'] * 100:+.0f} cm to spare.")
        if status != "pass":
            out["findings"].append(Finding(id=fid, title=f"{where}: {d['result']}", status=status, detail=detail,
                                           anchor=OpeningAnchor(sid=sid, opening=d["opening"]), source=GEO))
        out["checks"].append(Check(id=f"{target['id']}.door.{d['opening']}", rule=f"To {tname}, {where.lower()}: margin",
                                   measured=None if d["implausible"] else round(d["slack"], 3), threshold=0, unit="m",
                                   status=status, standard="Geometry: wall opening less 5 cm for a hung door",
                                   findings=[fid] if status != "pass" else []))
        if not d["implausible"]:
            parts.append((d["slack"], [*d["center"], c["route"]["points"][0][2]], where, status))
    for k, t in enumerate(c["corners"]):
        fid = f"{tool_id}:{sid}:{target['id']}:turn:{k}"
        status = t["status"]
        s = t["slack"]
        detail = (f"A {t['angle_deg']:.0f} degree turn between {fmt(t['a'])} and {fmt(t['b'])} wide: "
                  + (f"{s * 100:+.0f} cm to spare" if s is not None else "does not fit under the ceiling any way up")
                  + ". Corner formula, no tilting: real moves sometimes gain a little by tilting.")
        if status != "pass":
            out["findings"].append(Finding(id=fid, title=f"Turn {k + 1}: {t['result']}", status=status, detail=detail,
                                           anchor=PointAnchor(sid=sid, point=(*t["point"][:2], c["route"]["points"][0][2])),
                                           source=Source(layer="matterport", method="geometry", confidence="medium",
                                                         note="Right-angle corner formula on empty-room widths")))
        out["checks"].append(Check(id=f"{target['id']}.turn.{k}", rule=f"To {tname}, turn {k + 1} ({t['angle_deg']:.0f} "
                                   "degrees): margin", measured=round(s, 3) if s is not None else None, threshold=0,
                                   unit="m", status=status, standard="L = min over angle of a/sin + b/cos - w/(sin cos)",
                                   findings=[fid] if status != "pass" else []))
        parts.append((s if s is not None else -math.inf, [*t["point"][:2], c["route"]["points"][0][2]],
                      f"turn {k + 1}", status))
    results = [d["result"] for d in doors] + [t["result"] for t in c["corners"]]
    out["result"] = "likely fail" if "likely fail" in results else "measure on site" if "measure on site" in results \
        else "likely pass"
    route_pts = c["route"]["points"]
    out["length"] = c["route"]["length_m"]
    out["overlays"].append(RouteOverlay(floor=c["route"]["floor"], points=[tuple(p) for p in route_pts], label=(
        f"{what} to {tname}"), chokes=[]))
    if parts:
        slack, pt, where, status = min(parts, key=lambda p: p[0])
        out["tight"] = {"slack": slack, "where": where, "status": status}
        out["overlays"].append(BoxOverlay(center=(pt[0], pt[1], pt[2] + box[2] / 2), size=tuple(box),
                                          yaw_deg=_yaw_near(route_pts, pt), status=status,
                                          label=f"Tightest: {where}"))
    return out


def room_fit(plan: dict, target: dict, box: tuple) -> tuple[str, float | None]:
    runs = free_wall_runs(plan, target["id"])
    longest = runs.get("longest") if runs.get("available") else None
    return ("unknown" if longest is None else VERDICT_STATUS[judge(longest, box[0])]), longest


def pick_target(plan: dict, want: str | None, default_label: str) -> dict | None:
    rs = rooms(plan)
    if want and want in rs:
        return rs[want]
    lab = want or default_label
    cands = [r for r in plan["rooms"] if r.get("label") == lab]
    from ...geometry._plan import polygons
    polys = polygons(plan)
    return max(cands, key=lambda r: polys[r["id"]].area if polys.get(r["id"]) is not None else 0, default=None)


@tool(id="furniture_fit", title="Furniture fit", icon="sofa",
      summary="Checks whether a sofa, bed, piano or fridge can be carried from the entrance to a room: each door "
              "and turn with its margin, and where it would stick.",
      model_description="Carry one named object (sofa, loveseat, king or queen mattress, upright piano, refrigerator, "
                        "washer, wardrobe, dining table; sizes editable) from the main entrance to a room in one scan. "
                        "Returns the route, a check per doorway and turn with its margin, a box overlay at the tightest "
                        "point, and whether the object fits along a wall in the room.",
      personas=["furniture_mover"], requires=[{"layer": "matterport.walls"}, {"layer": "matterport.openings"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "Controls", "AssumptionChips", "StepLog",
              "ActionBar"],
      overlays=["route", "box"], examples=["Will my sofa fit into the living room?", "Can we get a piano in here?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    (pl, pd, ph), upright, default_room, desc = PRESETS[inputs.object]
    box = (inputs.length_m or pl, inputs.depth_m or pd, inputs.height_m or ph)
    assumptions = [Assumption(id="furniture.length_m", label=f"{inputs.object.capitalize()} length", value=box[0],
                              unit="m", editable=True),
                   Assumption(id="furniture.depth_m", label="Depth", value=box[1], unit="m", editable=True),
                   Assumption(id="furniture.height_m", label="Height", value=box[2], unit="m", editable=True),
                   Assumption(id="preset", label=f"Preset size: {desc}", value=inputs.object),
                   Assumption(id="upright", label="Kept standing the whole way", value=upright),
                   Assumption(id="hung_doors", label="Doors stay on their hinges (taking one off adds about 5 cm)",
                              value=True)]
    scope = ScanScope(sid=sid)
    if not quality(plan).get("walls"):
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "This scan has no wall graph, so doors and turns cannot be measured.")))
    target = pick_target(plan, inputs.room, default_room)
    if target is None:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            f"No {(inputs.room or default_room).lower()} in this scan; name the room to carry it to.")))
    a = carry_audit(ctx, plan, "furniture_fit", box, upright, target, inputs.entrance, f"The {inputs.object}")
    ctx.step(f"Carried a {box[0]:.2f} x {box[1]:.2f} x {box[2]:.2f} m {inputs.object} toward the {label(target).lower()}")
    if a["reason"]:
        return ToolResult(scope=scope, assumptions=assumptions,
                          verdict=Verdict(status=VERDICT_STATUS[a["result"]], text=a["reason"]))
    rf, longest = room_fit(plan, target, box)
    fid = f"furniture_fit:{sid}:{target['id']}:wall"
    checks = a["checks"] + [Check(id=f"{target['id']}.wall", rule=f"Free wall in the {label(target).lower()} as long as "
                                  f"the {inputs.object}", measured=round(longest, 3) if longest else None,
                                  threshold=box[0], unit="m", status=rf,
                                  findings=[fid] if rf not in ("pass", "unknown") else [])]
    findings = a["findings"] + ([Finding(id=fid, title="No wall long enough once inside", status=rf,
                                         anchor=RoomAnchor(sid=sid, room=target["id"]), source=GEO,
                                         detail=f"Longest stretch of wall with no door or window {fmt(longest)}.")]
                                if rf not in ("pass", "unknown") else [])
    t = a["tight"]
    status = VERDICT_STATUS[a["result"]]
    text = {"pass": f"The {inputs.object} makes it to the {label(target).lower()}; tightest at the {t['where'].lower()}."
            if t else f"The {inputs.object} makes it to the {label(target).lower()}.",
            "warn": f"Too close to call at the {t['where'].lower() if t else 'route'}: measure before moving.",
            "fail": f"The {inputs.object} sticks at the {t['where'].lower() if t else 'route'}."}[status]
    return ToolResult(
        scope=scope, verdict=Verdict(status=status, text=text), checks=checks, findings=findings,
        overlays=a["overlays"], assumptions=assumptions,
        metrics=[Metric(id="tightest", label="Least room to spare", value=round(t["slack"], 2) if t and
                        t["slack"] != -math.inf else None, unit="m", source=GEO),
                 Metric(id="doors", label="Doorways on the way", value=sum(1 for c in checks if ".door." in c.id),
                        unit="", source=GEO),
                 Metric(id="turns", label="Turns on the way", value=sum(1 for c in checks if ".turn." in c.id), unit="",
                        source=GEO),
                 Metric(id="route_m", label="Carry distance", value=round(a["length"], 1), unit="m", source=GEO)])
