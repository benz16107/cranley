"""Bathroom clearance: turning circle, the door, clear floor space outside the door swing and at the toilet, wall
space for grab bars, and the tub or shower type, against the ADA 2010 Standards and the FHA Design Manual.

Geometry measures; the panorama only says where the toilet is, what the bathing fixture is and whether grab bars are
already up. Vanities and cabinets are not in the wall graph, so every clear space is the most there can be."""
from __future__ import annotations

import math

from pydantic import BaseModel
from shapely.geometry import Point

from ...geometry import free_wall_runs, turning_space
from ...geometry._plan import VERDICT_STATUS, clear_width, floor_z, judge
from .. import (Assumption, Check, Finding, Metric, OpeningAnchor, Pin, PinsOverlay, PointAnchor, RoomAnchor,
                ScanScope, Source, ToolResult, Verdict, field, tool)
from ..types import BoxOverlay, Media
from .._access import (GEO, GEO_LOW, IN, STD, face_polygon, fmt, graph, implausible, quality, rect_fit, room_angle,
                       rooms)
from .._access import look

WC_ADA = (60 * IN, 56 * IN)
WC_FHA = [(48 * IN, 56 * IN), (48 * IN, 66 * IN), (60 * IN, 56 * IN)]
DOOR_SPACE = (30 * IN, 48 * IN)
SIDE_BAR, REAR_BAR = 54 * IN, 36 * IN     # side wall run needed from the rear wall; rear bar length


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    door_width_m: float = field(0.815, pref="access.door_width_m", unit="m", gt=0.3, le=2.0,
                                description="Clear width you need through the bathroom door")
    diameter_m: float = field(1.525, pref="access.turning_diameter_m", unit="m", gt=0.3, le=3.0,
                              description="Turning circle you need")
    read_panoramas: bool = field(True, description="Find the toilet, tub or shower and grab bars in the panoramas")


def _status(ok: bool | None) -> str:
    return "unknown" if ok is None else "pass" if ok else "fail"


def _toilet(objs: list[dict], room_id: str):
    hits = [o for o in objs if o["label"] == "toilet" and o["room"] == room_id and o["point"] and
            o["surface"] == "floor"]
    return hits[0] if hits else None


def bath_one(ctx, plan, r, inputs, objs, name: str) -> dict:
    """Everything measured for one bathroom: a list of (check, finding|None) and overlays."""
    sid, rid = plan["sid"], r["id"]
    out = {"checks": [], "findings": [], "pins": [], "boxes": [], "fixtures": None}

    def add(cid, rule, measured, threshold, unit, status, std, title=None, detail=None, anchor=None, source=GEO,
            media=()):
        fid = f"bathroom_clearance:{sid}:{rid}:{cid}"
        has = status != "pass" and title
        if has:
            out["findings"].append(Finding(id=fid, title=title, status=status, detail=detail or "", source=source,
                                           anchor=anchor or RoomAnchor(sid=sid, room=rid),
                                           media=[Media(**m) for m in media]))
        out["checks"].append(Check(id=f"{rid}.{cid}", rule=f"{name}: {rule}", measured=measured, threshold=threshold,
                                   unit=unit, status=status, standard=std, findings=[fid] if has else []))

    t = turning_space(plan, rid, inputs.diameter_m)
    if t["available"]:
        add("turn", "turning circle in the empty room", round(t["diameter"], 3), inputs.diameter_m, "m", t["status"],
            STD["turn"], "Too tight to turn", f"Largest circle {fmt(t['diameter'])}; you need {fmt(inputs.diameter_m)}.")
    g = graph(plan)
    doors = [d for d in g["links"] + g["entrances"] if d["kind"] != "invisible" and rid in (d.get("rooms") or [d["room"]])]
    poly, face = None, face_polygon(plan, rid)
    from ...geometry._plan import polygons
    poly = polygons(plan).get(rid)
    for d in doors:
        cw, bad = clear_width(d), implausible(d)
        res = "measure on site" if bad else judge(cw, inputs.door_width_m)
        add(f"door.{d['opening']}", "door clear width", round(cw, 3) if cw is not None else None, inputs.door_width_m,
            "m", VERDICT_STATUS[res], STD["door"],
            "Door width is a data error" if bad else "Bathroom door narrower than you need",
            f"The scan records {d['width'] * 100:.0f} cm, narrower than any door: measure on site." if bad else
            f"Opening {fmt(d['width'])}, about {fmt(cw)} clear with the door hung.",
            OpeningAnchor(sid=sid, opening=d["opening"]))
    if face is not None:
        swing = face
        for d in doors:  # the door leaf sweeps a quarter circle as wide as the door; take the whole disc
            if d.get("width") and not implausible(d):
                swing = swing.difference(Point(d["center"]).buffer(d["width"]))
        rect = rect_fit(poly, *DOOR_SPACE, inside=swing)
        add("door_space", "30 x 48 in clear floor space outside the door swing", None, None, "", _status(rect is not None),
            STD["door_space"], "No 30 x 48 in space clear of the door swing",
            "Even in the empty room there is no 760 x 1220 mm rectangle clear of the door's swing.")
        if rect is not None:
            out["boxes"].append(_box(rect, plan, r, "30 x 48 in clear of the door", "pass"))
    # toilet: located by the panorama reader, clearance measured by geometry
    wc = _toilet(objs, rid) if objs is not None else None
    if face is not None and wc is not None:
        pt = wc["point"][:2]
        media = wc["finding"]["media"]
        a = rect_fit(poly, *WC_ADA, inside=face, contains=pt)
        f = next((s for s in WC_FHA if rect_fit(poly, *s, inside=face, contains=pt)), None)
        add("wc_ada", "60 x 56 in clearance around the toilet", None, None, "", _status(a is not None), STD["wc_ada"],
            "No ADA clearance at the toilet", "No 1525 x 1420 mm rectangle around the toilet fits between the walls, "
            "even in the empty room.", PointAnchor(sid=sid, point=tuple(wc["point"])), GEO_LOW, media)
        add("wc_fha", "FHA clear floor space at the toilet", None, None, "", _status(f is not None), STD["wc_fha"],
            "No FHA clear floor space at the toilet", "None of the three FHA rectangles around the toilet fits.",
            PointAnchor(sid=sid, point=tuple(wc["point"])), GEO_LOW, media)
        if a:
            out["boxes"].append(_box(a, plan, r, "60 x 56 in at the toilet", "pass"))
        out["pins"].append(Pin(id=f"{rid}.toilet", anchor=PointAnchor(sid=sid, point=tuple(wc["point"])),
                               label="Toilet (seen in panorama)", status="unknown"))
        # grab bars: free wall within reach of the toilet
        runs = free_wall_runs(plan, rid)
        near = sorted((x for x in runs.get("runs", []) if _dist_to_run(pt, x) < 0.9), key=lambda x: -x["length"])
        side = near[0]["length"] if near else 0.0
        rear = near[1]["length"] if len(near) > 1 else 0.0
        add("bar_side", "free wall beside the toilet for a side grab bar", round(side, 2), round(SIDE_BAR, 3), "m",
            judge_s(side, SIDE_BAR), STD["bar_side"], "Short wall for a side grab bar",
            f"Longest free wall near the toilet {fmt(side)}; a side bar needs wall to {fmt(SIDE_BAR)} from the rear wall.",
            source=GEO_LOW)
        add("bar_rear", "free wall behind the toilet for a rear grab bar", round(rear, 2), round(REAR_BAR, 3), "m",
            judge_s(rear, REAR_BAR), STD["bar_rear"], "Short wall for a rear grab bar",
            f"Second free wall near the toilet {fmt(rear)}; a rear bar is {fmt(REAR_BAR)} long.", source=GEO_LOW)
    elif face is not None:
        a = rect_fit(poly, *WC_ADA, inside=face)
        add("wc_any", "room could hold a 60 x 56 in toilet clearance somewhere", None, None, "", _status(a is not None),
            STD["wc_ada"], "Room too small for an ADA toilet clearance",
            "No 1525 x 1420 mm rectangle fits anywhere in the empty room. The toilet was not located in a panorama.")
    if inputs.read_panoramas:
        fx = look.bath_fixtures(plan, r)
        out["fixtures"] = fx
        if "error" not in fx:
            vsrc = Source(layer="model", method="vision", confidence=fx["confidence"],
                          note=f"Vision model on panorama {fx['pano']}")
            curbless = fx["bathing"] == "curbless walk-in shower"
            st = "pass" if curbless else "warn" if fx["bathing"] in ("bathtub with shower", "bathtub only",
                                                                     "shower with a curb or step-in lip") else "unknown"
            add("bathing", f"bathing fixture: {fx['bathing']}", None, None, "", st, STD["shower"],
                f"Bathing: {fx['bathing']}", f"{fx['reason']} A roll-in shower needs no step; a tub needs a transfer "
                "and 30 in of floor along it (ADA 607.2).", source=vsrc, media=fx["media"])
            bars = fx["grab_bars"]
            add("grab_bars", f"grab bars seen: {bars}", None, None, "",
                "pass" if bars == "at both" else "unknown" if bars == "cannot tell" else "warn", STD["bars_fha"],
                f"Grab bars: {bars}", "STEADI asks for grab bars next to and inside the tub and next to the toilet. "
                "Whether the walls are reinforced for them cannot be seen.", source=vsrc, media=fx["media"])
    return out


def judge_s(x, need) -> str:
    return VERDICT_STATUS[judge(x, need)]


def _dist_to_run(pt, run) -> float:
    from shapely.geometry import LineString
    return LineString([run["a"], run["b"]]).distance(Point(pt))


def _box(rect, plan, r, lab, status) -> BoxOverlay:
    xs, ys = [p[0] for p in rect], [p[1] for p in rect]
    w, d = math.dist(rect[0], rect[1]), math.dist(rect[1], rect[2])
    yaw = math.degrees(math.atan2(rect[1][1] - rect[0][1], rect[1][0] - rect[0][0]))
    z = floor_z(plan).get(r["floor"], 0.0)  # scan z of the room's floor, not its height above the lowest
    return BoxOverlay(center=(sum(xs) / 4, sum(ys) / 4, z + 0.01), size=(w, d, 0.02), yaw_deg=yaw, label=lab,
                      status=status)


@tool(id="bathroom_clearance", title="Bathroom clearance", icon="bath",
      summary="Checks each bathroom for a wheelchair: door, turning space, floor space at the toilet and clear of the "
              "door, wall for grab bars, and whether the shower has a step.",
      model_description="Wheelchair bathroom audit for one scan: per bathroom the door clear width, turning circle, "
                        "the FHA 30 x 48 in space outside the door swing, the ADA 60 x 56 in and FHA clear floor space "
                        "at the toilet (toilet located in the panorama), free wall for side and rear grab bars, and the "
                        "tub or shower type and visible grab bars from the panorama.",
      personas=["wheelchair_user", "older_adult_family", "wheelchair_home_search", "aging_in_place_planner"],
      requires=[{"layer": "matterport.walls"}, {"layer": "matterport.room_labels"},
                {"layer": "matterport.panos", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["pins", "box"], annotations={"cost": "slow"},
      examples=["Is the bathroom usable from a wheelchair?", "Is there room for grab bars by the toilet?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    scope = ScanScope(sid=sid)
    baths = [r for r in plan["rooms"] if r.get("label") == "Bathroom"]
    assumptions = [Assumption(id="access.door_width_m", label="Door clear width you need", value=inputs.door_width_m,
                              unit="m", editable=True),
                   Assumption(id="access.turning_diameter_m", label="Turning circle you need", value=inputs.diameter_m,
                              unit="m", editable=True),
                   Assumption(id="no_vanity", label="Vanities and cabinets are not in the scan: clear spaces are the "
                                                    "most there can be", value=True)]
    if not baths:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "No room in this scan is labelled a bathroom.")))
    if not quality(plan).get("walls"):
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "This scan has no wall graph, so bathroom doors and floor space cannot be measured.")))
    objs, err = [], None
    if inputs.read_panoramas:
        panos = [p["id"] for b in baths for p in [look.central_pano(plan, b)] if p]
        ctx.step(f"Reading {len(panos)} bathroom panoramas for the toilet, tub, shower and grab bars")
        objs, err = look.objects(plan, panos)
    parts = [bath_one(ctx, plan, b, inputs, objs if inputs.read_panoramas else None,
                      f"Bathroom {i + 1}" if len(baths) > 1 else "Bathroom") for i, b in enumerate(baths)]
    ctx.step(f"Measured {len(baths)} bathrooms")
    checks = [c for p in parts for c in p["checks"]]
    findings = [f for p in parts for f in p["findings"]]
    pins = [Pin(id=f.id, anchor=f.anchor, label=f.title, status=f.status) for f in findings if f.anchor] + \
        [p for x in parts for p in x["pins"]]
    overlays = ([PinsOverlay(pins=pins)] if pins else []) + [b for p in parts for b in p["boxes"]]
    scores = []
    for b, p in zip(baths, parts):
        st = [c.status for c in p["checks"]]
        scores.append("fail" if "fail" in st else "warn" if "warn" in st or "unknown" in st else "pass")
    best = min(scores, key=["pass", "warn", "unknown", "fail"].index)
    text = {"pass": "At least one bathroom passes every check on the scan geometry.",
            "warn": "No bathroom fails outright, but some checks need a look on site or could not be read.",
            "fail": "Every bathroom fails at least one check: " + "; ".join(sorted({
                c.rule.split(": ", 1)[1] for c in checks if c.status == "fail"}))[:200] + "."}[best]
    if err:
        text += " The panoramas could not be read, so the toilet, tub and grab bars are unknown."
    n_ok = sum(s == "pass" for s in scores)
    turn = [c.measured for c in checks if c.id.endswith(".turn") and c.measured is not None]
    return ToolResult(scope=scope, verdict=Verdict(status=best, text=text), checks=checks, findings=findings,
                      overlays=overlays, assumptions=assumptions,
                      metrics=[Metric(id="bathrooms", label="Bathrooms", value=len(baths), unit="", source=GEO),
                               Metric(id="bathrooms_ok", label="Bathrooms that pass", value=n_ok, unit="", source=GEO),
                               Metric(id="best_turn", label="Best turning circle", value=round(max(turn), 2)
                                      if turn else None, unit="m", source=GEO)])
