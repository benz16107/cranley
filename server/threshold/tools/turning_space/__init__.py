"""Turning space: the largest circle in each room, against the 60 in (1525 mm) wheelchair turning circle."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry import turning_spaces
from ...geometry._plan import VERDICT_STATUS, floor_z, judge
from .. import (Assumption, Check, Finding, Legend, LensOverlay, Metric, Pin, PinsOverlay, PointAnchor, RoomAnchor,
                ScanScope, ToolResult, Verdict, field, tool)
from .. import Source
from .._access import (GEO, STD, Chair, cannot, chair_list, face_polygon, floor_objects, fmt, graph, has_objects, quality, rooms)

OBJ = Source(layer="matterport", method="geometry", confidence="medium",
             note="Room outline less the objects the phone scan measured on the floor (Apple RoomPlan)")


def cluttered(plan: dict, rid: str, aisle_need: float) -> dict | None:
    """With the scanned floor objects taken out: the largest turning circle, and the aisle, the widest body that
    can still get from the room's doorway to that circle. None when the scan has no objects in the room."""
    import shapely
    from shapely.geometry import Point
    face = face_polygon(plan, rid)
    things = floor_objects(plan, rid, face)
    if face is None or not things:
        return None
    clear = face.difference(shapely.union_all([o["footprint"] for o in things]))
    parts = list(getattr(clear, "geoms", [clear]))
    g = graph(plan)
    doors = [d for d in g.get("links", []) + g.get("entrances", []) if d.get("kind") != "invisible"
             and rid in (d.get("rooms") or [d.get("room")])] if g["available"] else []
    best = max(parts, key=lambda q: shapely.maximum_inscribed_circle(q).length)
    line = shapely.maximum_inscribed_circle(best)
    centre, d = Point(line.coords[0]), 2 * line.length
    aisle = None
    if doors:
        def ok(w):  # can a body w wide get from some doorway to the circle's centre?
            er = clear.buffer(-w / 2)
            comp = next((c for c in getattr(er, "geoms", [er]) if c.buffer(1e-6).contains(centre)), None)
            return comp is not None and any(comp.distance(Point(x["center"])) <= w / 2 + 0.2 for x in doors)
        lo, hi = 0.0, min(d, 3.0)
        if ok(0.05):
            for _ in range(20):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if ok(mid) else (lo, mid)
            aisle = lo
        else:
            aisle = 0.0
    return {"diameter": d, "center": [centre.x, centre.y], "aisle": aisle, "objects": things,
            "aisle_result": None if aisle is None else judge(aisle, aisle_need)}

SKIP = {"Void", "Closet", "Pantry"}


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    diameter_m: float = field(1.525, pref="access.turning_diameter_m", unit="m", gt=0.3, le=3.0,
                              description="Turning circle you need")
    rooms: list[str] | None = field(None, description="Room types or ids to check; default every room but closets")
    aisle_width_m: float = field(0.915, pref="access.route_width_m", unit="m", gt=0.3, le=3.0,
                                 description="Clear aisle width you need between objects on the floor")
    chairs: list[Chair] = field([], pref="access.chairs", description="Each chair the person uses; each is checked "
                                                                     "with its own turning circle")


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
    for t in rows:  # objects on the floor (phone scans): they shrink the circle and the aisle, so they decide
        c = cluttered(plan, t["room"], inputs.aisle_width_m)
        if c:
            t.update(empty=t["diameter"], diameter=c["diameter"], center=c["center"], status=VERDICT_STATUS[
                judge(c["diameter"], need)], clutter=c)
    for t in sorted(rows, key=lambda t: t["diameter"]):
        fid = f"turning_space:{sid}:{t['room']}"
        bad = t["status"] != "pass"
        if bad:
            findings.append(Finding(id=fid, title=f"Too tight to turn, {t['label']}" if t["status"] == "fail"
                                    else f"Turning circle too close to call, {t['label']}", status=t["status"],
                                    anchor=RoomAnchor(sid=sid, room=t["room"]), source=GEO,
                                    detail=(f"Largest circle clear of the {len(t['clutter']['objects'])} objects on the "
                                            f"floor {fmt(t['diameter'])} across ({fmt(t['empty'])} in the empty room)"
                                            if "clutter" in t else f"Largest circle in the empty room "
                                            f"{fmt(t['diameter'])} across") + f", you need {fmt(need)}. A T-shaped turn "
                                           f"in a 60 in square may still work. {STD['turn']}."))
        clut = t.get("clutter")
        checks.append(Check(id=f"turn.{t['room']}", rule=f"Turning circle, {t['label']}" +
                            (f", objects on the floor counted ({fmt(t['empty'])} empty)" if clut else ""),
                            measured=round(t["diameter"], 3), threshold=need, unit="m", status=t["status"],
                            standard=STD["turn"], findings=[fid] if bad else []))
        if clut and clut["aisle"] is not None:
            ast = VERDICT_STATUS[clut["aisle_result"]]
            afid = f"turning_space:{sid}:aisle:{t['room']}"
            names = ", ".join(sorted({o["label"].lower() for o in clut["objects"]}))
            if ast != "pass":
                findings.append(Finding(id=afid, title=f"Narrow aisle between objects, {t['label']}", status=ast,
                                        anchor=RoomAnchor(sid=sid, room=t["room"]), source=OBJ,
                                        detail=f"From the doorway to the turning spot the clear path is "
                                               f"{fmt(clut['aisle'])} wide between walls and {names}; you need "
                                               f"{fmt(inputs.aisle_width_m)}. {STD['route']}."))
            checks.append(Check(id=f"aisle.{t['room']}", rule=f"Aisle from the doorway to the turning spot, "
                                f"{t['label']}, objects on the floor: {names}", measured=round(clut["aisle"], 3),
                                threshold=inputs.aisle_width_m, unit="m", status=ast, standard=STD["route"],
                                findings=[afid] if ast != "pass" else []))
        z = floor_z(plan).get(rs[t["room"]]["floor"], 0.0)  # scan z of the room's floor, not its height above the lowest
        pins.append(Pin(id=f"turn.{t['room']}", anchor=PointAnchor(sid=sid, point=(*t["center"], z)),
                        label=f"{t['diameter']:.2f} m circle", status=t["status"]))
    vals = {t["room"]: round(t["diameter"], 3) for t in rows}
    aisle_bad = [c for c in checks if c.id.startswith("aisle.") and c.status != "pass"]
    fails = [t for t in rows if t["status"] == "fail"] + [c for c in aisle_bad if c.status == "fail"]
    warns = [t for t in rows if t["status"] == "warn"] + [c for c in aisle_bad if c.status == "warn"]
    status = "fail" if fails else "warn" if warns else "pass"
    empty = "with the scanned objects on the floor" if any("clutter" in t for t in rows) else "in the empty room"
    nf = sum(1 for t in rows if t["status"] == "fail")
    text = (f"{nf} of {len(rows)} rooms cannot hold the turning circle {empty}." if nf else
            f"Every room holds the circle {empty}, {len(warns)} only just." if warns else
            f"Every room checked holds the turning circle {empty}.")
    named = [c for c in chair_list(inputs.chairs, 0.815, need) if c["name"]]
    for i, ch in enumerate(named):
        holds = [t for t in rows if judge(t["diameter"], ch["turn"]) == "likely pass"]
        st = "pass" if len(holds) == len(rows) else "fail" if not holds else "warn"
        checks.append(Check(id=f"chair{i}.turn", rule=f"{ch['name']} (needs a {fmt(ch['turn'])} circle): rooms that "
                            f"hold it: {', '.join(sorted({t['label'] for t in holds})) or 'none'}",
                            measured=len(holds), threshold=len(rows), unit="rooms", status=st, standard=STD["turn"]))
    if len(named) > 1:
        text += " By chair: " + "; ".join(f"{ch['name']} turns in {c.measured} of {len(rows)} rooms"
                                          for ch, c in zip(named, [c for c in checks if c.id.startswith("chair")])) + "."
    if aisle_bad:
        text += f" {len(aisle_bad)} room{'s have' if len(aisle_bad) > 1 else ' has'} an aisle narrower than you need."
    checks += ([] if has_objects(plan) else [cannot("floor_objects", "furniture, shelves and boxes on the floor: this "
                                                    "scan records walls only, so circles are for the empty room")]) + \
        [cannot("obstructions", "boxes, carts or stock left in an aisle on the day")]
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
