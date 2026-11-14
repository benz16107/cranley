"""Path to water: every route a small child could take from each bedroom to the pool, through the house and across
the yard, each door on the way inspected in the panoramas, and the missing barrier named against the US Consumer
Product Safety Commission's pool barrier guidance.

Standard: CPSC Publication 362, "Safety Barrier Guidelines for Residential Pools" (2015),
https://www.cpsc.gov/s3fs-public/pdfs/blk_media_SafetyBarrierGuidelinesResPools.pdf . Page 15, item 1: the barrier is at
least 48 in high. Item 10: pedestrian gates open outward, self-close and self-latch, with the release at least 54 in up
(or shielded). Item 11: where a wall of the house is part of the barrier, every door with direct access to the pool has
(a) an alarm that sounds within 7 s and lasts 30 s or more (UL 2017; deactivation switch at least 54 in up, page 13),
or (b) the pool has a power safety cover (ASTM F1346-91), or (c) other means as good, such as self-closing, self-latching
doors. Page 14: never a pet door that leads to the pool unless an isolation fence surrounds the pool.
"""
from __future__ import annotations

import math

import numpy as np
from shapely import wkt as shapely_wkt
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union

from ...aerial import detect as aerial_detect
from ...aerial import site as aerial
from ...geometry import room_graph, route
from ...geometry._plan import polygons
from .. import Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from .._site import (
    Where,
    capture,
    fact,
    footprint,
    geo,
    geo_route,
    locate,
    metres,
    ortho_media,
    parcel,
    pin,
    pins,
    src,
    to_m,
)
from .._site import align as al
from ..types import Media, PanoAnchor, RouteOverlay

CPSC = "CPSC Pub. 362 (2015), Safety Barrier Guidelines for Residential Pools"
DOOR_Q = ["self_closing", "latch_high", "pet_door", "alarm"]
YES = ("yes", "no", "unclear")


class Inputs(Where):
    max_doors: int = field(3, ge=1, le=6, description="Pool-side doors to inspect in the panoramas")
    use_vision: bool = field(True, description="Inspect doors and the yard with the vision model (cached)")


# ---- the house in the scan ----------------------------------------------------------------------------

def exterior_doors(plan: dict) -> list[dict]:
    """Doorways with a room on one side that lead outside: a probe 0.6 m out lands in no scanned room."""
    g = room_graph(plan)
    if not g.get("available"):
        return []
    polys = polygons(plan)
    inside = unary_union([p for p in polys.values() if p is not None]) if polys else None
    walls = {w["id"]: w for w in plan["walls"]}
    out = []
    for e in g["entrances"]:
        if (e.get("width") or 0) < 0.5:
            continue
        w = walls.get(e["wall"])
        if not w:
            continue
        (ax, ay), (bx, by) = w["a"], w["b"]
        L = math.hypot(bx - ax, by - ay) or 1
        nx, ny = -(by - ay) / L, (bx - ax) / L
        cx, cy = e["center"]
        outs = [(sx, sy) for sx, sy in ((nx, ny), (-nx, -ny))
                if inside is None or not inside.buffer(0.05).contains(Point(cx + 0.6 * sx, cy + 0.6 * sy))]
        if len(outs) != 1:
            continue  # both sides scanned (or neither): an interior door or an unscanned room
        ox, oy = outs[0]
        out.append({**e, "out": (ox, oy), "inner": (cx - 0.35 * ox, cy - 0.35 * oy), "outer": (cx + 0.8 * ox, cy + 0.8 * oy)})
    return out


def bedrooms(plan: dict) -> list[dict]:
    return [r for r in plan["rooms"] if (r.get("label") or "").lower().startswith("bedroom") or (r.get("label") or "") == "Nursery"]


def ground_floor(plan: dict) -> str | None:
    fl = sorted(plan.get("floors") or [], key=lambda f: f.get("sequence", 0))
    return fl[0]["id"] if fl else None


def stair_foot(plan: dict, fl: str) -> dict | None:
    """Where an upper-floor child arrives downstairs. Stairs are not in the scan data, so: a ground-floor room
    labelled Staircase or Entrance, else the ground-floor hallway nearest the upper hallway."""
    rooms = [r for r in plan["rooms"] if r["floor"] == fl and r.get("polygon")]
    for lab in ("Staircase", "Entrance"):
        hit = [r for r in rooms if r.get("label") == lab]
        if hit:
            return hit[0]
    up = [r for r in plan["rooms"] if r["floor"] != fl and r.get("label") == "Hallway" and r.get("polygon")]
    halls = [r for r in rooms if r.get("label") in ("Hallway", "Living Room", "Family Room")]
    if not up or not halls:
        return None
    ux, uy = np.mean(np.array(up[0]["polygon"], float), axis=0)
    return min(halls, key=lambda r: float(np.hypot(*(np.mean(np.array(r["polygon"], float), axis=0) - (ux, uy)))))


# ---- the yard from the air ------------------------------------------------------------------------------

def find_pool(s, fp, pc) -> dict | None:
    """The pool on this parcel. A neighbour's pool is often nearer the house centroid than a shaded pool of its own,
    so only detections that overlap the parcel count."""
    c = fp.centroid if fp is not None else Point(s.lon, s.lat)
    det = aerial_detect.detect(c.y, c.x, 80, ["swimming pool"], threshold=0.3)
    pools = [shapely_wkt.loads(d["polygon"]) for d in det["detections"] if d["image"] == "spherical-ortho"]
    if pc is not None:
        pools = [g for g in pools if g.intersection(pc).area > 0.5 * g.area]
    if not pools:
        return None
    p = max(pools, key=lambda g: g.area)
    return {"polygon": p, "source": Source(layer="vexcel", method="vision", confidence="medium",
                                           note="Vexcel SAM 3 'swimming pool' box on the orthophoto")}


def yard_vision(s, pool) -> dict | None:
    from ...vision.model import CONFIDENCE, ask
    c = pool.centroid
    o = aerial.ortho(c.y, c.x, 40, 1024)
    q = {"type": "string", "enum": list(YES)}
    schema = {"type": "object", "additionalProperties": False,
              "required": ["pool_fence", "safety_cover", "note", "confidence"],
              "properties": {"pool_fence": q, "safety_cover": q, "note": {"type": "string"}, "confidence": CONFIDENCE}}
    prompt = ("North-up aerial photo, 40 m across, centred on a backyard pool of a house. pool_fence: is there a fence "
              "or wall that separates the pool from the house itself (an isolation fence around the pool), not only a "
              "fence around the whole yard? safety_cover: is a solid pool cover visible over the water? A note of a "
              "few words says what you see.")
    return ask([o.image], prompt, schema, key=f"path_to_water/yard/{c.y:.6f},{c.x:.6f}")


# ---- doors in the panoramas ---------------------------------------------------------------------------

def inspect_door(plan: dict, door: dict) -> dict | None:
    """Ask the vision model about one door from the nearest panorama inside the house."""
    from ...sources import matterport as mp
    from ...vision import projection as pj
    from ...vision.locate import floor_z
    from ...vision.model import BOX, CONFIDENCE, ask, jpeg
    cands = [p for p in plan["panos"] if p.get("rotation") and p.get("floor") == door["floor"]]
    if not cands:
        return None
    cx, cy = door["center"]
    z = floor_z(plan, door["floor"]) + 1.0
    # a panorama 1.2 to 7 m away, inside, that sees the door on a side face; about 3 m away is best
    views = []
    for p in cands:
        dist = math.hypot(p["position"][0] - cx, p["position"][1] - cy)
        if not 1.2 <= dist <= 7:
            continue
        face, u, v = pj.point_to_face_pixel([cx, cy, z], p["position"], 1000, p["rotation"])
        if face in (0, 5) or not (120 < u < 880):
            continue
        views.append((abs(dist - 3) + (0 if p.get("room") == door.get("room") else 1), p, dist, face, u, v))
    if not views:
        return None
    _, pano, dist, face, u, v = min(views, key=lambda t: t[0])
    img = jpeg(mp.pano_face(plan["sid"], pano["id"], face, "2k"), 1000)
    q = {"type": "string", "enum": list(YES)}
    schema = {"type": "object", "additionalProperties": False,
              "required": ["door_type", *DOOR_Q, "box", "confidence", "note"],
              "properties": {"door_type": {"type": "string", "enum": ["sliding glass door", "hinged door", "french doors",
                                                                     "garage door", "no door visible"]},
                             **{k: q for k in DOOR_Q}, "box": BOX, "confidence": CONFIDENCE, "note": {"type": "string"}}}
    prompt = (f"One face of a 360 panorama inside a house, 1000 by 1000 pixels. An exterior door that leads to the "
              f"backyard is near pixel ({u:.0f}, {v:.0f}), about {dist:.1f} m from the camera. Look at that door. "
              "self_closing: a closer arm, spring hinges or other self-closing hardware. latch_high: a latch or lock "
              "mounted high, out of a small child's reach (about 54 in, 1.4 m, or more above the floor). pet_door: a pet "
              "or doggy door in it. alarm: a door alarm or contact sensor with a sounder on it. Box the door. Say "
              "'unclear' when you cannot see; a note of a few words says what you see.")
    a = ask([img], prompt, schema, key=f"path_to_water/door/{plan['sid']}/{pano['id']}/{door['id']}")
    yaw, pitch = pj.yaw_pitch(np.array([cx, cy, z]) - np.array(pano["position"]))
    return {**a, "pano": pano["id"], "face": face, "yaw_deg": yaw, "pitch_deg": pitch,
            "box_frac": tuple(round(a["box"][k] / 1000, 4) for k in ("x0", "y0", "x1", "y1"))}


# ---- judging --------------------------------------------------------------------------------------------

def door_barrier(insp: dict | None, cover: bool) -> tuple[str, str]:
    """(status, what is missing) for one door with direct access to the pool, per CPSC item 11."""
    if cover:
        return "pass", ""
    if not insp:
        return "unknown", "door alarm or self-closing, self-latching hardware (door not seen in a panorama)"
    if insp.get("pet_door") == "yes":
        return "fail", "the pet door must go or the pool needs an isolation fence"
    if insp.get("alarm") == "yes":
        return "pass", ""
    if insp.get("self_closing") == "yes" and insp.get("latch_high") == "yes":
        return "pass", ""
    if "unclear" in (insp.get("alarm"), insp.get("self_closing"), insp.get("latch_high")) and insp.get("alarm") != "no":
        return "unknown", "door alarm (none seen clearly)"
    return "fail", "door alarm (UL 2017, sounds within 7 s), or self-closing, self-latching hardware with a high latch"


@tool(id="path_to_water", title="Path to water", icon="waves",
      summary="Traces every route a small child could take from each bedroom to the pool and names the missing barrier.",
      model_description="For a scanned house with a pool: places the floor plan on the aerial footprint (checked per house), "
                        "finds exterior doors that open toward the pool, traces routes from each bedroom through the wall "
                        "graph and across the yard, inspects each pool-side door in the panoramas (self-closing, high latch, "
                        "pet door, alarm), checks the yard for a pool fence or cover from the air, and judges each route "
                        "against CPSC Pub. 362. Returns routes (scan frame and map), pins, checks and a fix list.",
      personas=["pool_safety_parent", "older_adult_family", "houston_homeowner_storm", "insurance_underwriter"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.room_labels"}, {"layer": "matterport.panos"},
                {"layer": "vexcel.property"}, {"layer": "vexcel.ortho"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "Note", "StepLog"],
      overlays=["route", "pins"], annotations={"cost": "slow"},
      examples=["Could my toddler get from the bedroom to the pool?", "Which door needs an alarm?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    k = s.key
    pool_fact = fact(s, "pool")
    ctx.step(f"Vexcel pool fact: {pool_fact}")
    if not pool_fact:
        return ToolResult(scope=s.scope, verdict=Verdict(status="pass" if pool_fact is False else "unknown",
                          text="Vexcel sees no pool on this parcel, so there is no path to water to trace."
                          if pool_fact is False else "Vexcel has no pool fact here."))
    enclosed = sum(fact(s, f"pool_{t}_enclosed", 0) or 0 for t in ("in_ground", "above_ground", "hot_tub"))
    fp = footprint(s)
    pool = find_pool(s, fp, parcel(s))
    if not s.sid:
        return ToolResult(scope=s.scope, verdict=Verdict(status="unknown",
                          text="There is a pool, but without a scan of the house the routes inside cannot be traced."),
                          findings=[Finding(id=f"path_to_water:{k}:pool", title="Pool on the parcel", status="unknown",
                                            anchor=geo(*(pool["polygon"].centroid.coords[0])) if pool else geo(s.lon, s.lat),
                                            source=src(s, "pool"), detail=f"Enclosed per Vexcel: {enclosed > 0}.",
                                            media=[ortho_media(s, 60)])])
    plan = ctx.plan(s.sid)
    a = al.check(plan, fp)
    conf = a["confidence"]
    ctx.step(f"Plan on the footprint: {a.get('tried') or a.get('reason')}; using {a.get('yaw_sign')}/{a.get('translation')}, "
             f"overlap {a.get('iou')} ({conf})")
    lat0 = s.lat
    fwd = to_m(lat0)[0]
    fp_m = metres(fp, lat0) if fp is not None else None
    pool_m = metres(pool["polygon"], lat0) if pool else None

    doors = exterior_doors(plan)
    ctx.step(f"{len(doors)} doors lead outside")
    # a door opens to the pool when the line from just outside it to the pool crosses no part of the house
    for d in doors:
        d["ll"] = al.to_lonlat(plan, a, *d["outer"]) if a["available"] else None
        if d["ll"] and pool_m is not None:
            p = Point(fwd(*d["ll"]))
            q = nearest_points(pool_m, p)[0]
            line = LineString([p, q])
            d["yard_m"] = line.length
            d["pool_ll"] = to_m(lat0)[1](q.x, q.y)
            d["direct"] = fp_m is None or line.intersection(fp_m.buffer(-0.5)).length < 0.5
        else:
            d["direct"] = None
    pool_doors = sorted([d for d in doors if d["direct"]], key=lambda d: d["yard_m"])
    if pool is None or not a["available"]:
        pool_doors = doors  # cannot tell which side the pool is on: every exterior door counts, low confidence
        conf = "low"

    yard = yard_vision(s, pool["polygon"]) if inputs.use_vision and pool else None
    seen = (yard or {}).get("pool_fence")
    fence = (enclosed > 0 and seen != "no") or seen == "yes"
    disputed = enclosed > 0 and seen == "no"  # Vexcel's enclosure flag against a photo that shows open water
    cover = (yard or {}).get("safety_cover") == "yes"
    insp: dict[str, dict | None] = {}
    if inputs.use_vision:
        for d in pool_doors[:inputs.max_doors]:
            try:
                insp[d["id"]] = inspect_door(plan, d)
            except Exception as e:  # noqa: BLE001  the door stays "not inspected"
                ctx.step(f"Door {d['id']} not inspected: {str(e)[:100]}")
                insp[d["id"]] = None
    ctx.step(f"{len(pool_doors)} doors open toward the pool; inspected {sum(1 for v in insp.values() if v)} in the panoramas")

    gf = ground_floor(plan)
    starts = [(r["id"], r.get("label") or "Bedroom", False) for r in bedrooms(plan) if r["floor"] == gf]
    upper = [r for r in bedrooms(plan) if r["floor"] != gf]
    foot = stair_foot(plan, gf) if upper else None
    if foot:
        starts.append((foot["id"], f"foot of the stairs, for {len(upper)} upstairs bedrooms", True))
    names = {}
    for r in plan["rooms"]:
        names[r["id"]] = r.get("label") or "room"

    findings, checks, overlays, ps = [], [], [], []
    routes, untraced = [], []
    geo_src = Source(layer="matterport", method="geometry", confidence=conf,
                     note=f"Wall-graph route, then a straight line across the yard; plan placed on the Vexcel footprint "
                          f"with overlap {a.get('iou')} ({a.get('yaw_sign')}, {a.get('translation')})")
    for rid, label, via_stairs in starts:
        for d in pool_doors[:inputs.max_doors]:
            if d["floor"] != plan_room(plan, rid)["floor"]:
                continue
            r = route(plan, rid, list(d["inner"]), min_width=0.3)
            if not r.get("available"):
                untraced.append((label, d["id"], r.get("reason")))
                continue
            st, missing = ("pass", "") if fence else door_barrier(insp.get(d["id"]), cover)
            pts = [tuple(p[:2]) for p in r["points"]] + [tuple(d["center"]), d["outer"]]
            z = r["points"][0][2]
            overlays.append(RouteOverlay(floor=r["floor"], label=f"{label} to the pool",
                                         points=[(x, y, z) for x, y in pts], chokes=[]))
            if a["available"] and d.get("pool_ll"):
                overlays.append(geo_route([al.to_lonlat(plan, a, x, y) for x, y in pts] + [d["pool_ll"]],
                                          f"{label} to the pool", [(d["ll"], 0.0, st)]))
            routes.append({"from": label, "door": d["id"], "inside_m": r["length_m"], "yard_m": d.get("yard_m"),
                           "status": st, "missing": missing, "doors": len(r["doors"]) + 1, "stairs": via_stairs})
    # per door: the check, the finding, the fix
    fixes = []
    for d in pool_doors[:inputs.max_doors]:
        i = insp.get(d["id"])
        st, missing = ("pass", "") if fence else door_barrier(i, cover)
        n = sum(1 for r in routes if r["door"] == d["id"])
        fid = f"path_to_water:{k}:door:{d['id']}"
        room = names.get(d["room"], "room")
        seen = ", ".join(f"{q.replace('_', ' ')} {i[q]}" for q in DOOR_Q) if i else "not seen in a panorama"
        media = [Media(kind="pano", ref=f"{plan['sid']}/{i['pano']}/{i['face']}", box=i["box_frac"])] if i else []
        anchor = PanoAnchor(sid=plan["sid"], pano=i["pano"], yaw_deg=round(i["yaw_deg"], 1), pitch_deg=round(i["pitch_deg"], 1)) \
            if i else geo(*d["ll"]) if d.get("ll") else geo(s.lon, s.lat)
        checks.append(Check(id=f"door.{d['id']}", rule=f"Door from the {room} to the pool has a barrier", measured=n,
                            threshold=None, unit="routes", status=st, standard=f"{CPSC}, p. 15 item 11", findings=[fid]))
        findings.append(Finding(id=fid, title=f"{(i or {}).get('door_type', 'Door').capitalize()} from the {room} toward the pool",
                                status=st, anchor=anchor, media=media,
                                source=Source(layer="model", method="vision", confidence=(i or {}).get("confidence", "low"),
                                              note="Vision model on the nearest panorama face") if i else geo_src,
                                detail=(f"{n} routes pass through it; the pool is {d['yard_m']:.0f} m from the door. " if d.get("yard_m") else "")
                                + f"Seen: {seen}." + (f" Missing: {missing}." if missing else "")
                                + (f" ({i['note']})" if i else "")))
        if d.get("ll"):
            ps.append(pin(f"door_{d['id']}", *d["ll"], f"{room} door", st))
        if st in ("fail", "unknown") and missing:
            fixes.append((n, f"Add a {missing} on the door from the {room}"))
    fixes.sort(reverse=True)
    pst = "pass" if fence else "warn"
    if disputed:
        pst = "warn"
    fid = f"path_to_water:{k}:pool_fence"
    checks.insert(0, Check(id="pool_fence", rule="Isolation fence around the pool (48 in or more)", measured=1 if fence else 0,
                           threshold=1, unit="", status=pst, standard=f"{CPSC}, p. 15 items 1 and 10", findings=[fid]))
    findings.insert(0, Finding(
        id=fid, title="Pool fence" if fence else "No fence seen between the house and the pool", status=pst,
        anchor=geo(*pool["polygon"].centroid.coords[0]) if pool else geo(s.lon, s.lat),
        source=src(s, "pool") if enclosed else Source(layer="model", method="vision", confidence=(yard or {}).get("confidence", "low"),
                                                      note="Vision model on a 40 m orthophoto crop"),
        media=[ortho_media(s, 60, pool["polygon"] if pool else None)],
        detail=("Vexcel reports the pool enclosed, but the photo shows no fence between house and pool, so each door is "
                "judged as if the house wall is the barrier. " if disputed else
                "Vexcel reports the pool enclosed. " if enclosed else "Vexcel reports the pool not enclosed. ")
        + (f"From the air: fence {yard['pool_fence']}, safety cover {yard['safety_cover']} ({yard['note']}). " if yard else "")
        + ("The gate's self-closing latch and its height cannot be seen from above; check it (CPSC item 10)." if fence else
           "The back wall of the house is part of the barrier, so every door on it needs an alarm, a safety cover on the "
           "pool, or self-closing, self-latching hardware (CPSC item 11).")))
    if pool:
        ps.append(pin("pool", *pool["polygon"].centroid.coords[0], "pool", pst))
    if fixes:
        findings.append(Finding(id=f"path_to_water:{k}:fixes", title="Fixes, most routes cut first", status="warn",
                                anchor=geo(*pool["polygon"].centroid.coords[0]) if pool else geo(s.lon, s.lat), source=geo_src,
                                detail="; ".join(f"{t} (cuts {n} routes)" for n, t in fixes) + "."))
    open_routes = [r for r in routes if r["status"] in ("fail", "unknown")]
    metrics = [Metric(id="routes", label="Routes from a bedroom to the pool", value=len(routes), unit="", source=geo_src),
               Metric(id="unguarded", label="Routes with no barrier seen", value=len(open_routes), unit="", source=geo_src),
               Metric(id="pool_doors", label="Doors that open toward the pool", value=len(pool_doors), unit="", source=geo_src),
               Metric(id="plan_fit", label="Plan overlap with the footprint", value=a.get("iou"), unit="IoU",
                      source=Source(layer="vexcel", method="geometry", confidence=conf, note="Scan outline against Vexcel footprint"))]
    if untraced:
        metrics.append(Metric(id="untraced", label="Bedroom-door pairs the wall graph does not connect", value=len(untraced),
                              unit="", source=geo_src))
        findings.append(Finding(id=f"path_to_water:{k}:untraced", title="Routes the wall graph cannot trace", status="unknown",
                                anchor=geo(s.lon, s.lat), source=geo_src,
                                detail=f"{len(untraced)} bedroom-to-door pairs have no connection in the scan's wall graph "
                                       "(a door missing from the graph, or stairs). Treat them as open until checked."))
    shortest = min(routes, key=lambda r: r["inside_m"] + (r["yard_m"] or 0), default=None)
    if shortest:
        metrics.append(Metric(id="shortest", label="Shortest route", value=round(shortest["inside_m"] + (shortest["yard_m"] or 0), 1),
                              unit="m", source=geo_src))
    if not routes:
        status = "unknown"
        text = ("A pool is on the parcel, but no route from a bedroom to a pool-side door could be traced in the wall graph."
                if pool_doors else "A pool is on the parcel, but no door was found that opens toward it.")
    else:
        status = "fail" if any(r["status"] == "fail" for r in routes) else "unknown" if open_routes else "pass"
        text = (f"{len(open_routes)} of {len(routes)} routes from a bedroom reach the pool with no barrier seen."
                if open_routes else f"Every one of {len(routes)} routes meets a barrier ({'pool fence' if fence else 'door hardware'}).")
        if fixes:
            text += f" First fix: {fixes[0][1].lower()}."
    if conf == "low":
        text += " Low confidence: the plan does not sit well on the aerial footprint."
    return ToolResult(scope=s.scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays + pins(ps),
                      assumptions=[{"id": "standard", "label": "Standard", "value": CPSC},
                                   {"id": "alignment", "label": "Plan placed with", "value": f"yaw sign {a.get('yaw_sign')}, translation {a.get('translation')}"},
                                   {"id": "stairs", "label": "Stairs are not in the scan; upstairs bedrooms start at the foot of the stairs",
                                    "value": bool(upper)},
                                   {"id": "capture", "label": "Aerial capture", "value": capture(s)}])


def plan_room(plan: dict, rid: str) -> dict:
    return next(r for r in plan["rooms"] if r["id"] == rid)
