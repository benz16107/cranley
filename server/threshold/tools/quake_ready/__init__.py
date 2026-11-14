"""Earthquake readiness: a safe spot in each room, tall or heavy things near the beds, and what to check on site.

The advice follows Drop, Cover and Hold On (Earthquake Country Alliance, ready.gov): get under a sturdy table, or
crouch against an inside wall away from windows and from anything tall that can fall. The safe spot is found from
the plan: along a wall shared with another room, the point farthest from any window. Tall furniture comes from the
bedroom panoramas through the vision model; without it the bedrooms get a checklist. The gas meter is outside and
not in the scan, so finding its shutoff is a job for someone on site.
"""
from __future__ import annotations

import math

from pydantic import BaseModel
from shapely.geometry import LineString, Point

from ...geometry._plan import polygons, room_floor_z
from .. import (
    Assumption,
    Check,
    Finding,
    Metric,
    Pin,
    PinsOverlay,
    PointAnchor,
    RoomAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..types import Media

GEO = Source(layer="matterport", method="geometry", confidence="high", note="Wall graph: windows and walls shared with another room")
VISION = Source(layer="model", method="vision", confidence="low", note="Vision model reading the bedroom panoramas")
GUIDE = Source(layer="model", method="lookup", confidence="high", note="Earthquake Country Alliance and ready.gov guidance")
TALL = ["tall bookcase or shelf", "tall dresser or wardrobe", "television", "heavy mirror or framed picture"]
NEAR_BED_M = 1.8          # a tall piece this close to the bed can reach it when it falls
WALL_OFFSET_M = 0.5       # crouch this far out from the inside wall
SAMPLE_M = 0.25
SKIP = {"Closet", "Void", "Pantry", "Patio", "Balcony", "Garage"}
CHECKLIST = ("Nothing tall or heavy stands where it could fall on the bed; bookcases and dressers are strapped to "
             "wall studs; no heavy frame or mirror hangs over the headboard; shoes and a torch are under the bed.")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    look: bool = field(True, pref="quake.look", description="Read the bedroom panoramas for tall or heavy furniture")


def _names(plan: dict) -> dict[str, str]:
    rooms = plan.get("rooms") or []
    out = {}
    for r in rooms:
        lab = r.get("label") or "Unlabelled room"
        same = [x["id"] for x in rooms if (x.get("label") or "Unlabelled room") == lab]
        out[r["id"]] = f"{lab} {same.index(r['id']) + 1}" if len(same) > 1 else lab
    return out


def safe_spot(plan: dict, room: dict) -> dict | None:
    """{point, window_m, inside_wall} or None: along a wall shared with another room, the point farthest from glass."""
    poly = polygons(plan).get(room["id"])
    if poly is None:
        return None
    walls = {w["id"]: w for w in plan.get("walls") or []}
    windows = []
    for o in plan.get("openings") or []:
        w = walls.get(o["wall"])
        if o["type"] != "window" or o["floor"] != room["floor"] or w is None:
            continue
        dx, dy = w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]
        n, h = math.hypot(dx, dy) or 1, (o.get("width") or 0) / 2   # the whole pane, not just its centre
        windows.append(LineString([(o["center"][0] - dx / n * h, o["center"][1] - dy / n * h),
                                   (o["center"][0] + dx / n * h, o["center"][1] + dy / n * h)]))
    inner = poly.buffer(-0.3)
    if inner.is_empty:
        return None
    shared = [w for w in plan.get("walls") or [] if w["floor"] == room["floor"] and w.get("type") != "invisible"
              and room["id"] in (w.get("rooms") or []) and len(w.get("rooms") or []) >= 2]
    cands = []
    for w in shared:
        (ax, ay), (bx, by) = w["a"], w["b"]
        length = math.hypot(bx - ax, by - ay)
        if length < 0.6:
            continue
        nx, ny = -(by - ay) / length, (bx - ax) / length
        for k in range(1, int(length / SAMPLE_M)):
            t = k * SAMPLE_M / length
            for s in (1, -1):
                p = Point(ax + (bx - ax) * t + s * nx * WALL_OFFSET_M, ay + (by - ay) * t + s * ny * WALL_OFFSET_M)
                if inner.contains(p):
                    cands.append((p, True))
    if not cands:  # no inside wall: anywhere in the room
        x0, y0, x1, y1 = inner.bounds
        cands = [(Point(x0 + i * SAMPLE_M, y0 + j * SAMPLE_M), False) for i in range(int((x1 - x0) / SAMPLE_M) + 1)
                 for j in range(int((y1 - y0) / SAMPLE_M) + 1) if inner.contains(Point(x0 + i * SAMPLE_M, y0 + j * SAMPLE_M))]
    if not cands:
        return None
    dist = (lambda p: min(p.distance(w) for w in windows)) if windows else (lambda p: math.inf)
    p, inside = max(cands, key=lambda c: (dist(c[0]), c[1]))
    d = dist(p)
    return {"point": (p.x, p.y), "window_m": None if math.isinf(d) else d, "inside_wall": inside}


def _find(plan: dict, panos: list[str]) -> list[dict]:
    from ...vision.reader import find_objects
    return find_objects(plan, labels=TALL + ["bed"], panos=panos, max_panos=len(panos))


@tool(id="quake_ready", title="Earthquake readiness",
      summary="A safe spot in each room away from windows, tall or heavy furniture near the beds, and where to find "
              "the gas shutoff on site.",
      model_description="Earthquake preparation for one scanned home (Drop, Cover and Hold On): per room, the spot along "
                        "an inside wall farthest from windows; tall or heavy furniture near each bed from the bedroom "
                        "panoramas (a checklist when they cannot be read); and an on-site task to find the gas meter "
                        "shutoff. For Los Angeles households and anyone in an earthquake zone.",
      personas=["la_quake_prep"], requires=[{"layer": "matterport.walls"},
                                            {"layer": "matterport.panoramas", "need": "optional", "fallback": "a checklist per bedroom"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "Note", "StepLog"], overlays=["pins"],
      annotations={"read_only": True, "cost": "slow"},
      examples=["Where should we take cover in each room during an earthquake?", "Is anything tall near the kids' beds?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    scope = ScanScope(sid=sid)
    if not plan.get("walls"):
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text="This scan has no wall graph, so windows "
                                                                              "and inside walls are unknown."))
    names, rz = _names(plan), room_floor_z(plan)
    rooms = [r for r in plan.get("rooms") or [] if r.get("label") not in SKIP and r.get("walls")]
    checks, findings, pins = [], [], []
    ctx.step(f"Finding a safe spot in {len(rooms)} rooms, along an inside wall and away from windows")
    for r in rooms:
        s = safe_spot(plan, r)
        if s is None:
            continue
        pt = (*s["point"], rz.get(r["id"], 0.0))
        where = "against an inside wall" if s["inside_wall"] else "in the room (it has no wall shared with another room)"
        checks.append(Check(id=f"safe:{r['id']}", rule=f"{names[r['id']]}: safe spot, distance to the nearest window",
                            measured=round(s["window_m"], 2) if s["window_m"] is not None else None, threshold=None,
                            unit="m", status="pass" if s["inside_wall"] else "warn"))
        pins.append(Pin(id=f"safe:{r['id']}", anchor=PointAnchor(sid=sid, point=pt), label=f"Safe spot, {names[r['id']]}",
                        status="pass" if s["inside_wall"] else "warn"))
        findings.append(Finding(
            id=f"quake_ready:{sid}:safe:{r['id']}", title="Safe spot", status="pass" if s["inside_wall"] else "warn",
            anchor=PointAnchor(sid=sid, point=pt), source=GEO,
            detail=f"Crouch {where}, "
                   + (f"{s['window_m']:.1f} m from the nearest window" if s["window_m"] is not None else "with no window on this floor")
                   + ", or under a sturdy table if there is one. Keep this spot clear of anything tall."))

    beds = [r for r in rooms if r.get("label") == "Bedroom"]
    read = False
    if inputs.look and beds:
        from ...vision.reader import room_panos
        panos = {r["id"]: (room_panos(plan, r) or [None])[0] for r in beds}
        ids = [p["id"] for p in panos.values() if p]
        if ids:
            ctx.step(f"Reading {len(ids)} bedroom panoramas for tall or heavy furniture")
            try:
                found = _find(plan, ids)
                read = True
            except Exception as e:  # noqa: BLE001  the model or the panorama download failed: fall back to the checklist
                ctx.step(f"Could not read the panoramas ({type(e).__name__}); giving the checklist instead")
                found = []
            bed_pts = {o["room"]: o["point"] for o in found if o["label"] == "bed" and o.get("point")}
            for i, o in enumerate(x for x in found if x["label"] != "bed"):
                rid, f = o["room"], o["finding"]
                near = None
                if o.get("point") and bed_pts.get(rid):
                    near = math.dist(o["point"][:2], bed_pts[rid][:2])
                close = near is not None and near <= NEAR_BED_M
                findings.append(Finding(
                    id=f"quake_ready:{sid}:tall:{rid}:{i}", title=f"{o['label'].capitalize()} {'near the bed' if close else 'in the bedroom'}",
                    status="warn", anchor=f["anchor"], source=VISION, media=[Media(**m) for m in f["media"]],
                    detail=(f"About {near:.1f} m from the bed. " if near is not None else "")
                           + "Strap it to a wall stud or move it where it cannot fall on anyone sleeping."))
    seen = {f.id.split(":")[3] for f in findings if ":tall:" in f.id}
    for r in beds:
        if read and r["id"] in seen:
            continue
        findings.append(Finding(
            id=f"quake_ready:{sid}:bed:{r['id']}", title="Bedroom checklist" if not read else "Nothing tall seen",
            status="unknown" if not read else "pass", anchor=RoomAnchor(sid=sid, room=r["id"]),
            source=GUIDE if not read else VISION,
            detail=CHECKLIST if not read else "The panorama showed nothing tall or heavy in this bedroom; "
                                              "the checklist still applies: " + CHECKLIST))
    findings.append(Finding(
        id=f"quake_ready:{sid}:gas", title="Find the gas shutoff (on site)", status="unknown", anchor=None, source=GUIDE,
        detail="The gas meter is outside and not in the scan. On site, find the meter and its shutoff valve, photograph "
               "it with the phone, and keep a wrench beside it. Shut it off only if you smell gas or hear it hiss; "
               "the gas company must turn it back on. Also check the water heater is strapped, which California requires."))
    safe = [c for c in checks if c.status == "pass"]
    return ToolResult(
        scope=scope,
        verdict=Verdict(status="warn" if any(f.status == "warn" for f in findings) else "pass",
                        text=f"Safe spots found in {len(safe)} of {len(rooms)} rooms. "
                             + ("Tall or heavy furniture checked in the bedroom panoramas. " if read
                                else "Bedrooms get a checklist; the panoramas were not read. ")
                             + "The gas shutoff is a job for someone on site."),
        metrics=[Metric(id="rooms_safe", label="Rooms with a safe spot", value=len(safe), unit="", source=GEO),
                 Metric(id="tall_items", label="Tall items seen", value=sum(":tall:" in f.id for f in findings), unit="",
                        source=VISION)],
        checks=checks, findings=findings, overlays=[PinsOverlay(pins=pins)] if pins else [],
        assumptions=[Assumption(id="quake.look", label="Read bedroom panoramas", value=inputs.look, editable=True),
                     Assumption(id="near_bed", label="Near the bed", value=NEAR_BED_M, unit="m"),
                     Assumption(id="method", label="Safe spot", value="along an inside wall, farthest from any window; "
                                "furniture is not in the scan, so check the spot is clear")])
