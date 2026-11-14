"""Camera coverage: what indoor security cameras see through the wall graph, which entry points and entry paths
they cover, and the blind spots.

Each camera's view is a 2D visibility polygon (isovist): rays one degree apart across its field of view, each
stopped by the first wall or window, out to the range a typical camera's night vision reaches. Doorways are open.
An entry point (an exterior door, or a window on the ground floor) is covered when its centre is in some camera's
view. With no cameras given, the tool proposes them greedily: from candidate corner mounts in the ground-floor rooms,
it keeps the camera that covers the most uncovered entry points (doors count double) until all are covered or the
camera budget runs out. Each exterior door's walking route to the bedrooms (or the stairs, or the biggest room) is
sampled every 25 cm to say how much of it is on camera.
"""
from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, Field
from shapely.geometry import Point
from shapely.ops import unary_union

from ... import geometry
from ...geometry._plan import wall_normal, walls_by_id
from ...signals.isovist import isovist, sees
from ..types import RouteOverlay
from ...signals.plan2d import floor_order, room_names, room_polys, segments
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
    PointAnchor,
    RuleOverlay,
    ScanScope,
    SelectOpenings,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

FOV_DEG = 110.0      # horizontal field of view of a typical wide-angle home camera (most sell at 100 to 130 degrees)
RANGE_M = 9.0        # "night vision up to 30 ft", the common rating for home cameras
MOUNT_H_M = 2.2      # high on a wall, out of reach
INSET_M = 0.3
PATH_STEP_M = 0.25
SKIP = {"Closet", "Void", "Bathroom", "Staircase"}  # no camera in a closet or a bathroom
GEO = Source(layer="matterport", method="geometry", confidence="medium",
             note="2D sight lines through the scan's walls; doors assumed open, furniture not modelled")


class Camera(BaseModel):
    x: float
    y: float
    floor: str | None = Field(None, description="Floor id; the ground floor when empty")
    heading_deg: float | None = Field(None, description="Where it points, degrees counter-clockwise from the scan's +x; "
                                                         "toward the room's middle when empty")
    label: str | None = None


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    cameras: list[Camera] | None = field(None, description="Camera positions; empty to let the tool propose them")
    max_cameras: int = field(4, pref="security.max_cameras", ge=1, le=12,
                             description="How many cameras the proposal may use")
    fov_deg: float = field(FOV_DEG, pref="security.camera_fov_deg", unit="deg", gt=10, le=360)
    range_m: float = field(RANGE_M, pref="security.camera_range_m", unit="m", gt=1, le=30)


def _inward(o: dict, wall: dict, poly) -> tuple[float, float]:
    nx, ny = wall_normal(wall)
    cx, cy = o["center"]
    for s in (1, -1):
        p = (cx + s * nx * INSET_M, cy + s * ny * INSET_M)
        if poly is not None and poly.contains(Point(p)):
            return p
    return (cx + nx * INSET_M, cy + ny * INSET_M)


PRIVATE = ("bathroom", "closet", "toilet", "powder")  # windows there are not watched: no camera goes in them


def entries(plan: dict, ground: str) -> list[dict]:
    """Exterior doors (doorways with a room on one side) and ground-floor windows to outside, except windows in
    bathrooms and closets."""
    g = geometry.room_graph(plan)
    label = {r["id"]: (r.get("label") or "").lower() for r in plan.get("rooms") or []}
    doors = {e["opening"] for e in g.get("entrances") or [] if e.get("opening")}
    out = []
    for o in plan.get("openings") or []:
        if o["floor"] != ground:
            continue
        if o["id"] in doors:
            out.append({**o, "entry": "door"})
        elif o["type"] == "window" and len(o.get("rooms") or []) <= 1 and \
                not any(w in label.get(r, "") for r in o.get("rooms") or [] for w in PRIVATE):
            out.append({**o, "entry": "window"})
    return out


@tool(id="camera_coverage", title="Camera coverage", icon="cctv",
      summary="Shows what indoor security cameras would see, which doors, windows and entry paths they cover, and the "
              "blind spots; proposes camera spots if you have none.",
      model_description="Indoor security camera coverage through the scan's wall graph: a visibility polygon per camera "
                        "(field of view and range), which exterior doors and ground-floor windows are in view, how "
                        "much of each door's walking route to the bedrooms is on camera, and coverage per room. Give "
                        "cameras, or leave empty to propose up to max_cameras spots. Returns a coverage lens, camera "
                        "pins, uncovered openings highlighted, entry routes.",
      personas=["home_security_family"],
      requires=[{"layer": "matterport.walls"}, {"layer": "matterport.openings"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "Controls", "AssumptionChips", "StepLog"],
      overlays=["lens", "rule", "pins", "route"],
      examples=["Where should I put security cameras?", "Which doors does this camera miss?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    scope = ScanScope(sid=inputs.scan)
    polys = room_polys(plan)
    if not plan.get("walls") or not polys:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "This scan has no wall graph with room outlines, so what a camera sees cannot be traced.")))
    rooms = {r["id"]: r for r in plan["rooms"]}
    names = room_names(plan, polys)
    storey = floor_order(plan)
    ground = min(storey, key=storey.get)
    segs = {f: segments(plan, f) for f in storey}
    walls = walls_by_id(plan)
    ents = entries(plan, ground)
    ctx.step(f"{sum(e['entry'] == 'door' for e in ents)} exterior doors and "
             f"{sum(e['entry'] == 'window' for e in ents)} ground-floor windows to watch")
    pts = np.array([e["center"] for e in ents]).reshape(-1, 2)
    weight = np.array([2.0 if e["entry"] == "door" else 1.0 for e in ents])
    fov, rng = inputs.fov_deg, inputs.range_m

    def view(c):
        return sees((c["x"], c["y"]), pts, segs[c["floor"]], heading_deg=c["heading"], fov_deg=fov, max_range=rng) \
            if c["floor"] == ground and len(pts) else np.zeros(len(pts), bool)

    def aim(room_id, x, y):
        cen = polys[room_id].centroid
        return math.degrees(math.atan2(cen.y - y, cen.x - x))

    cams: list[dict] = []
    proposed = not inputs.cameras
    if inputs.cameras:
        for i, c in enumerate(inputs.cameras):
            fl = c.floor or ground
            if fl not in segs:
                return ToolResult(scope=scope, verdict=Verdict(status="unknown", text="A camera names a floor the scan does not have."))
            rid = next((k for k, p in polys.items() if rooms[k]["floor"] == fl and p.covers(Point(c.x, c.y))), None)
            head = c.heading_deg if c.heading_deg is not None else (aim(rid, c.x, c.y) if rid else 0.0)
            cams.append({"x": c.x, "y": c.y, "floor": fl, "heading": head, "room": rid, "label": c.label or f"Camera {i + 1}"})
    elif len(pts):
        cands = []
        for k, p in polys.items():
            if rooms[k]["floor"] != ground or rooms[k].get("label") in SKIP:
                continue
            inner = p.buffer(-INSET_M)
            for g in getattr(inner, "geoms", [inner]):
                if g.is_empty:
                    continue
                for x, y in list(g.simplify(0.2).exterior.coords)[:-1]:
                    heads = {round(aim(k, x, y))}
                    for e in pts[np.hypot(pts[:, 0] - x, pts[:, 1] - y) <= rng]:
                        heads.add(round(math.degrees(math.atan2(e[1] - y, e[0] - x))))
                    for h in heads:
                        cands.append({"x": x, "y": y, "floor": ground, "heading": float(h), "room": k})
        ctx.step(f"Trying {len(cands)} corner mounts and aims")
        vis = [view(c) for c in cands]
        covered = np.zeros(len(pts), bool)
        while len(cams) < inputs.max_cameras and not covered.all():
            gains = [float(weight[v & ~covered].sum()) for v in vis]
            if not gains or max(gains) == 0:
                break
            i = int(np.argmax(gains))
            covered |= vis[i]
            cams.append({**cands[i], "label": f"Camera {len(cams) + 1}"})
    for c in cams:
        c["poly"] = isovist((c["x"], c["y"]), segs[c["floor"]], heading_deg=c["heading"], fov_deg=fov, max_range=rng)
        c["sees"] = view(c)

    # ---- coverage ----
    seen = {f: unary_union([c["poly"] for c in cams if c["floor"] == f]) for f in storey}
    cover = {}
    for k, p in polys.items():
        u = seen.get(rooms[k]["floor"])
        cover[k] = 0.0 if u is None or u.is_empty else min(1.0, u.intersection(p).area / p.area)
    in_view = np.zeros(len(pts), bool)
    for c in cams:
        in_view |= c["sees"]
    ctx.step(f"{len(cams)} camera{'s' if len(cams) != 1 else ''}: {int(in_view.sum())} of {len(ents)} entry points in view")

    # ---- entry routes ----
    ground_rooms = [k for k in polys if rooms[k]["floor"] == ground]
    beds = [k for k in ground_rooms if "bedroom" in (rooms[k].get("label") or "").lower()]
    stairs = [k for k in ground_rooms if (rooms[k].get("label") or "") == "Staircase"]
    goal = beds or stairs or [max(ground_rooms, key=lambda k: polys[k].area)] if ground_rooms else []
    routes = []
    u = seen.get(ground)
    for e in [e for e in ents if e["entry"] == "door"]:
        rid = next((r for r in e.get("rooms") or [] if r in polys), None)
        start = _inward(e, walls[e["wall"]], polys.get(rid)) if e["wall"] in walls else tuple(e["center"])
        for g in goal:
            if g == rid:
                continue
            r = geometry.route(plan, list(start), g, min_width=0.0, floor=ground)
            if not r.get("available"):
                continue
            line = [tuple(p[:2]) for p in r["points"]]
            samp = _along(line, PATH_STEP_M)
            frac = float(np.mean([u is not None and not u.is_empty and u.covers(Point(p)) for p in samp])) if samp else 0.0
            routes.append({"door": e, "to": g, "length": r["length_m"], "frac": frac, "overlay": r["overlay"]})

    # ---- result ----
    door_name = {e["id"]: f"{'Door' if e['entry'] == 'door' else 'Window'} in {names.get((e.get('rooms') or [None])[0], 'unscanned space')}"
                 for e in ents}
    checks, findings = [], []
    for e, ok in zip(ents, in_view):
        fid = f"camera_coverage:{inputs.scan}:{e['id']}"
        checks.append(Check(id=e["id"], rule=f"On camera, {door_name[e['id']].lower()}", measured=1.0 if ok else 0.0,
                            threshold=1.0, unit="", status="pass" if ok else "fail" if e["entry"] == "door" else "warn",
                            findings=[] if ok else [fid]))
        if not ok:
            findings.append(Finding(id=fid, title=f"Not on camera: {door_name[e['id']].lower()}",
                                    status="fail" if e["entry"] == "door" else "warn", source=GEO,
                                    anchor=OpeningAnchor(sid=inputs.scan, opening=e["id"]),
                                    detail=f"No camera within {rng:.0f} m and its {fov:.0f} degree view has a clear line to "
                                           f"this {e['entry']} ({e.get('width') or 0:.2f} m wide)."))
    for r in sorted(routes, key=lambda r: r["frac"]):
        if r["frac"] < 0.5:
            findings.append(Finding(
                id=f"camera_coverage:{inputs.scan}:route:{r['door']['id']}:{r['to']}",
                title=f"Blind route: {door_name[r['door']['id']].lower()} to the {names[r['to']].lower()}",
                status="warn", source=GEO, anchor=OpeningAnchor(sid=inputs.scan, opening=r["door"]["id"]),
                detail=f"{r['frac']:.0%} of the {r['length']:.1f} m walk is in a camera's view."))
    for c in cams:
        findings.append(Finding(
            id=f"camera_coverage:{inputs.scan}:{c['label'].lower().replace(' ', '_')}",
            title=f"{c['label']}: {names.get(c['room'], 'outside the rooms')}", status="pass", source=GEO,
            anchor=PointAnchor(sid=inputs.scan, point=(c["x"], c["y"], _z(plan, c["floor"]))),
            detail=f"At x {c['x']:.1f}, y {c['y']:.1f} m, {MOUNT_H_M} m up, aimed {c['heading'] % 360:.0f} degrees from the "
                   f"scan's x axis; sees {int(c['sees'].sum())} entry points and {c['poly'].area:.0f} m² of floor."))
    blind = [k for k in ground_rooms if cover[k] < 0.25 and rooms[k].get("label") not in SKIP]
    doors_out = [e for e, ok in zip(ents, in_view) if e["entry"] == "door" and not ok]
    win_out = [e for e, ok in zip(ents, in_view) if e["entry"] == "window" and not ok]
    gf_area = sum(polys[k].area for k in ground_rooms)
    gf_seen = sum(cover[k] * polys[k].area for k in ground_rooms)
    metrics = [
        Metric(id="cameras", label="Cameras", value=len(cams), unit="", source=GEO),
        Metric(id="entries_covered", label="Entry points on camera", value=int(in_view.sum()), unit=f"of {len(ents)}", source=GEO),
        Metric(id="doors_uncovered", label="Exterior doors not on camera", value=len(doors_out), unit="", source=GEO),
        Metric(id="ground_covered", label="Ground floor in view", value=round(100 * gf_seen / gf_area) if gf_area else 0,
               unit="%", source=GEO),
        *[Metric(id=f"cover.{names[k]}", label=names[k], value=round(100 * cover[k]), unit="%", source=GEO)
          for k in sorted(ground_rooms, key=lambda k: -cover[k])]]
    if not ents:
        text = "The scan shows no exterior doors or ground-floor windows, so there are no entry points to watch."
        status = "unknown"
    else:
        text = (f"{'The proposed ' if proposed else ''}{len(cams)} camera{'s' if len(cams) != 1 else ''} "
                f"{'see' if len(cams) != 1 else 'sees'} {int(in_view.sum())} of {len(ents)} entry points.")
        if doors_out:
            text += f" {len(doors_out)} exterior door{'s are' if len(doors_out) != 1 else ' is'} not on camera."
        if win_out:
            text += f" {len(win_out)} ground-floor window{'s are' if len(win_out) != 1 else ' is'} not on camera."
        if blind:
            text += f" {len(blind)} ground-floor room{'s are' if len(blind) != 1 else ' is'} mostly blind."
        status = "fail" if doors_out else "warn" if win_out else "pass"
    text += " Doors assumed open; furniture not modelled."
    pins = [Pin(id=f"cam{i + 1}", anchor=PointAnchor(sid=inputs.scan, point=(c["x"], c["y"], _z(plan, c["floor"]))),
                label=c["label"], status="pass") for i, c in enumerate(cams)]
    pins += [Pin(id=f"open:{e['id']}", anchor=OpeningAnchor(sid=inputs.scan, opening=e["id"]),
                 label=door_name[e["id"]], status="fail") for e in doors_out]
    vals = {k: round(100 * v) for k, v in cover.items() if rooms[k]["floor"] == ground or v > 0}
    overlays = [LensOverlay(values=vals, ramp="sequential",
                            legend=Legend(title="Floor area in a camera's view", unit="%", min=0, max=100)),
                PinsOverlay(pins=pins)]
    if doors_out or win_out:
        overlays.append(RuleOverlay(select=SelectOpenings(openings=[e["id"] for e in doors_out + win_out]), style="fail"))
    if in_view.any():
        overlays.append(RuleOverlay(select=SelectOpenings(openings=[e["id"] for e, ok in zip(ents, in_view) if ok]), style="pass"))
    for r in routes:
        overlays.append(RouteOverlay(floor=r["overlay"]["floor"], points=r["overlay"]["points"],
                                     label=f"{door_name[r['door']['id']]} to {names[r['to']]}: {r['frac']:.0%} on camera"))
    return ToolResult(
        scope=scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks, findings=findings,
        overlays=overlays,
        assumptions=[Assumption(id="security.camera_fov_deg", label="Camera field of view", value=fov, unit="deg", editable=True),
                     Assumption(id="security.camera_range_m", label="Camera range (night vision)", value=rng, unit="m", editable=True),
                     Assumption(id="security.max_cameras", label="Cameras the proposal may use", value=inputs.max_cameras, editable=True),
                     Assumption(id="doors_open", label="Interior doors open; windows block the view", value=True),
                     Assumption(id="private", label="Bathroom and closet windows not counted: no camera goes there", value=True),
                     Assumption(id="flat", label="Sight lines are 2D: furniture and mounting height not modelled", value=True)])


def _along(line, step):
    out = []
    for (ax, ay), (bx, by) in zip(line, line[1:]):
        n = max(1, int(math.hypot(bx - ax, by - ay) / step))
        out += [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(n)]
    return out + list(line[-1:])


def _z(plan, floor):
    from ...geometry._plan import floor_z
    return round(floor_z(plan).get(floor, 0.0) + MOUNT_H_M, 2)
