"""Egress routes: from every room the route out, its length and narrowest point; rooms with one way out, dead ends,
bedroom escape windows, and the hose stretch from each entrance to the farthest point."""
from __future__ import annotations

import math

from pydantic import BaseModel

from ...geometry import room_graph, route
from ...geometry._plan import VERDICT_STATUS, clear_width, floor_z, judge, polygons, rooms_by_id
from .. import (
    Assumption,
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    OpeningAnchor,
    Pin,
    PointAnchor,
    PinsOverlay,
    RoomAnchor,
    RuleOverlay,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..fire_preplan.common import BEDROOM, HALL_LABELS, floor_label, live_rooms, name, room_at, walls_ok
from ..types import RouteOverlay, SelectRooms

ROUTE = Source(layer="matterport", method="geometry", confidence="medium",
               note="Shortest walkable route over the wall graph in empty rooms; furniture is not counted")
STAIR = Source(layer="matterport", method="geometry", confidence="low",
               note="Stairs are not in the scan data: the flight is placed at the Staircase room and its length "
                    "estimated from the floor-to-floor rise at a 7.75 in riser and 10 in tread")
WINDOW = Source(layer="matterport", method="geometry", confidence="medium",
                note="Window sill from the wall graph; the openable clear area needs a tape measure")
RISER_ANGLE = math.atan(7.75 / 10)            # IRC R311.7.5 maximum riser over minimum tread
MAX_HOSE_ENTRANCES = 4
GRAZE_M = 0.45
HALL_M = 0.914                                 # IRC R311.6, 36 in
EERO_SILL_M = 1.118                            # IRC R310.2.2, 44 in to the bottom of the clear opening
STAIR_LABELS = ("Staircase",)


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    min_width_m: float = field(0.813, pref="access.door_width_m", unit="m", gt=0.3, le=3.0,
                               description="Clear width an exit door needs: 32 in (0.813 m)")
    long_route_m: float = field(22.9, pref="fire.long_route_m", unit="m", gt=1,
                                description="Routes longer than this are flagged (75 ft, IBC 2021 Table 1006.2.1 "
                                            "common path of egress travel, Group R-2 without sprinklers)")
    hose_m: float = field(61.0, pref="fire.preconnect_m", unit="m", gt=5,
                          description="Hose length to compare the stretch with (a 200 ft preconnect)")


# ---- walking, with stairs between floors ------------------------------------------------------

def _order(plan: dict) -> list[str]:
    return [f["id"] for f in sorted(plan.get("floors") or [], key=lambda f: f.get("sequence") or 0)]


def _stairs(plan: dict, f: str, nf: str) -> tuple[str, str] | None:
    """A Staircase room on floor f and the room above or below it on floor nf, matched by position."""
    polys, rooms = polygons(plan), plan["rooms"]
    on = lambda fl: [r for r in rooms if r["floor"] == fl and r.get("label") in STAIR_LABELS and polys.get(r["id"])]  # noqa: E731
    here, there = on(f), on(nf)
    if here and there:
        a, b = min(((a, b) for a in here for b in there),
                   key=lambda ab: polys[ab[0]["id"]].centroid.distance(polys[ab[1]["id"]].centroid))
        return a["id"], b["id"]
    for src, dst_floor, flip in ((here, nf, False), (there, f, True)):
        for s in src:
            c = polys[s["id"]].centroid
            other = room_at(plan, (c.x, c.y), dst_floor)
            if other:
                return (other, s["id"]) if flip else (s["id"], other)
    return None


def _rise(plan: dict, f: str, nf: str) -> float:
    el = {x["id"]: x.get("elevation") for x in plan.get("floors") or []}
    if el.get(f) is not None and el.get(nf) is not None:
        return abs(el[nf] - el[f])
    z = floor_z(plan)
    return abs(z.get(nf, 0) - z.get(f, 0)) or 2.9


def walk(plan: dict, a, fa: str, b, fb: str, min_width: float) -> dict:
    """Route from a (room id, [x, y] or "entrance") on floor fa to b on floor fb, climbing the Staircase rooms
    between floors. Returns {available, length_m, legs, narrowest, reason}."""
    order = _order(plan)
    i, j = order.index(fa), order.index(fb)
    step = 1 if j > i else -1
    legs, cur = [], a
    for k in range(i, j, step):
        f, nf = order[k], order[k + step]
        pair = _stairs(plan, f, nf)
        if pair is None:
            return {"available": False, "reason": f"No stairs between {floor_label(plan, f)} and "
                                                  f"{floor_label(plan, nf)} could be placed (no Staircase room)."}
        if cur != pair[0]:
            r = route(plan, cur, pair[0], min_width=min_width, floor=f)
            if not r["available"]:
                return r
            legs.append(r)
        rise = _rise(plan, f, nf)
        legs.append({"stairs": True, "floor": f, "to_floor": nf, "room": pair[0], "rise_m": rise,
                     "length_m": rise / math.sin(RISER_ANGLE)})
        cur = pair[1]
    if cur != b:
        r = route(plan, cur, b, min_width=min_width, floor=fb)
        if not r["available"]:
            return r
        legs.append(r)
    # under GRAZE_M is a route grazing a wall end or a sliver opening in the data, not a real pinch
    chokes = [c for r in legs if not r.get("stairs") for c in r["chokes"]
              if c["width"] is not None and c["width"] >= GRAZE_M]
    return {"available": True, "legs": legs, "length_m": sum(r["length_m"] for r in legs),
            "narrowest": min(chokes, key=lambda c: c["width"]) if chokes else None,
            "stairs": any(r.get("stairs") for r in legs)}


def far_corner(plan: dict, room_id: str) -> float:
    """Straight distance from the room's route point (centre of its largest inscribed circle) to its far corner."""
    import shapely
    poly = polygons(plan).get(room_id)
    if poly is None:
        return 0.0
    c = shapely.maximum_inscribed_circle(poly).coords[0]
    return max(math.dist(c, v) for v in poly.exterior.coords)


def analyse(plan: dict, min_width: float) -> dict:
    """Everything this tool measures, as plain data, for egress_routes and fire_preplan."""
    g = room_graph(plan)
    rooms = rooms_by_id(plan)
    order = _order(plan)
    ent_floors = [f for f in order if any(e["floor"] == f for e in g["entrances"])]
    exit_floor = ent_floors[0] if ent_floors else None
    exits = [e for e in g["entrances"] if e["floor"] == exit_floor]
    upper = [e for e in g["entrances"] if e["floor"] != exit_floor]
    degree = {r: 0 for r in rooms}
    for link in g["links"]:
        for r in link["rooms"]:
            degree[r] = degree.get(r, 0) + 1
    for e in g["entrances"]:
        degree[e["room"]] = degree.get(e["room"], 0) + 1
    polys = polygons(plan)
    routed = {}
    for r in live_rooms(plan):
        if polys.get(r["id"]) is None or exit_floor is None:
            continue
        routed[r["id"]] = walk(plan, r["id"], r["floor"], "entrance", exit_floor, min_width)
    hose = []
    # shortcut: an open office floor can have dozens of openings to unscanned space; stretch from the 4 widest only
    for e in sorted(exits, key=lambda e: -(e.get("width") or 0))[:MAX_HOSE_ENTRANCES]:
        best = None
        for r in live_rooms(plan):
            if polys.get(r["id"]) is None or r.get("label") in STAIR_LABELS:
                continue
            w = walk(plan, list(e["center"]), e["floor"], r["id"], r["floor"], min_width)
            if w["available"]:
                total = w["length_m"] + far_corner(plan, r["id"])
                if best is None or total > best["length_m"]:
                    best = {"entrance": e, "room": r["id"], "length_m": total, "walk": w}
        if best:
            hose.append(best)
    z = floor_z(plan)
    windows = {}
    for r in live_rooms(plan):
        if r.get("label") != BEDROOM:
            continue
        ws = [o for o in plan.get("openings") or [] if o["type"] == "window" and r["id"] in (o.get("rooms") or [])]
        sills = [(o, (o["sill"] - z.get(o["floor"], 0)) if o.get("sill") is not None else None) for o in ws]
        windows[r["id"]] = sills
    return {"graph": g, "exit_floor": exit_floor, "exits": exits, "upper_openings": upper, "degree": degree,
            "routes": routed, "hose": hose, "windows": windows}


# ---- the tool ---------------------------------------------------------------------------------

def _no_walls(plan: dict, sid: str) -> ToolResult:
    rooms = live_rooms(plan)
    labels = sorted({name(r) for r in rooms})
    return ToolResult(
        scope=ScanScope(sid=sid),
        verdict=Verdict(status="unknown", text=(
            f"This scan has {len(rooms)} rooms and {len(plan.get('panos') or [])} panoramas but no wall graph, so "
            "doors, routes and widths cannot be measured. Use the floor plan image for the layout and walk the "
            "route on site.")),
        metrics=[Metric(id="rooms", label="Rooms", value=len(rooms), unit="", source=ROUTE)],
        findings=[Finding(id=f"egress_routes:{sid}:no_walls", title="No wall graph in this scan", status="unknown",
                          detail="Rooms in the scan: " + ", ".join(labels) + ". Matterport has no walls or doorways "
                                 "for it, so nothing here can say which way is out.", anchor=None, source=ROUTE)])


def _m(x: float | None) -> str:
    return "?" if x is None else f"{x:.1f} m"


@tool(id="egress_routes", title="Egress routes", icon="route",
      summary="The way out of every room: how far, how narrow, which rooms have one way out, and the hose stretch.",
      model_description="For one scan: the walking route from every room to the nearest entrance (length, narrowest "
                        "point, doors), rooms with a single way out, dead-end hallways, bedroom escape windows by sill "
                        "height, and the hose stretch from each entrance to the farthest point. Returns route "
                        "overlays and a travel-distance lens.",
      personas=["fire_captain", "older_adult_family", "apartment_manager"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.room_labels", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["route", "lens", "rule", "pins"],
      examples=["How do people get out of each bedroom?", "How much hose do we need to reach the back bedroom?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    if not walls_ok(plan):
        ctx.step("No wall graph: routes cannot be measured")
        return _no_walls(plan, sid)
    mw = inputs.min_width_m
    a = analyse(plan, mw)
    rooms = rooms_by_id(plan)
    ctx.step(f"Found {len(a['exits'])} doorways to outside or unscanned space and {len(a['graph']['links'])} "
             "connections between rooms")
    if a["exit_floor"] is None:
        return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(
            status="unknown", text="No doorway in this scan leads outside or to unscanned space, so there is no "
                                   "exit to route to. The scan may stop at the unit's front door."))
    ok = {k: v for k, v in a["routes"].items() if v["available"]}
    ctx.step(f"Routed {len(ok)} of {len(a['routes'])} rooms to the nearest entrance")

    checks, findings, overlays, pins = [], [], [], []
    lens: dict[str, float] = {}
    corridor: dict[tuple, dict] = {}
    for rid, w in sorted(a["routes"].items(), key=lambda kv: -kv[1].get("length_m", 0)):
        room = rooms[rid]
        fid = f"egress_routes:{sid}:{rid}"
        if not w["available"]:
            checks.append(Check(id=f"route:{rid}", rule=f"Route out, {name(room)}", measured=None, threshold=None,
                                unit="m", status="unknown", findings=[fid]))
            findings.append(Finding(id=fid, title=f"No measured route out, {name(room)}", status="unknown",
                                    detail=w["reason"], anchor=RoomAnchor(sid=sid, room=rid), source=ROUTE))
            continue
        lens[rid] = round(w["length_m"], 1)
        nar = w["narrowest"]
        long = w["length_m"] > inputs.long_route_m
        src = STAIR if w["stairs"] else ROUTE
        checks.append(Check(id=f"length:{rid}", rule=f"Distance to an entrance, {name(room)}",
                            measured=round(w["length_m"], 1), threshold=inputs.long_route_m, unit="m",
                            status="warn" if long else "pass", standard="IBC 2021 Table 1006.2.1 (reference)",
                            findings=[fid]))
        findings.append(Finding(
            id=fid, title=f"Way out, {name(room)}", status="warn" if long else "pass",
            detail=(f"{w['length_m']:.1f} m to an entrance" + (" by the stairs" if w["stairs"] else "")
                    + (f", over {inputs.long_route_m:.1f} m" if long else "")
                    + (f"; narrowest point {nar['width']:.2f} m ({nar['kind']})" if nar else "") + "."),
            anchor=RoomAnchor(sid=sid, room=rid), source=src))
        for c in (c for leg in w["legs"] if not leg.get("stairs") for c in leg["chokes"] if c["kind"] == "corridor"):
            corridor.setdefault((round(c["point"][0], 1), round(c["point"][1], 1)), c)
        for leg in w["legs"]:
            if not leg.get("stairs"):
                o = leg["overlay"]
                overlays.append(RouteOverlay(floor=o["floor"], points=o["points"], chokes=o["chokes"],
                                             label=f"{name(room)} to the way out"))
    main = max(a["exits"], key=lambda e: clear_width(e) or 0)
    cw = clear_width(main)
    st = VERDICT_STATUS[judge(cw, mw)]
    fid = f"egress_routes:{sid}:exit"
    checks.append(Check(id="exit", rule="Widest doorway out, clear width", measured=round(cw, 2) if cw is not None else None,
                        threshold=mw, unit="m", status=st, standard="IRC 2021 R311.2 / IBC 2021 §1010.1.1, 32 in clear",
                        findings=[fid] if st != "pass" else []))
    if st != "pass":
        findings.append(Finding(id=fid, title="Widest doorway out", status=st,
                                detail=f"About {cw:.2f} m clear (opening less a 5 cm door allowance) against {mw:.2f} m.",
                                anchor=OpeningAnchor(sid=sid, opening=main["id"]), source=ROUTE))
    for k, c in sorted(corridor.items(), key=lambda kv: kv[1]["width"]):
        st = VERDICT_STATUS[judge(c["width"], HALL_M)]
        in_room = rooms.get(room_at(plan, c["point"][:2]) or "")
        # under 0.45 m is a route grazing a wall end, not a hallway; R311.6 is about hallways only
        if st == "pass" or c["width"] < GRAZE_M or not in_room or in_room.get("label") not in HALL_LABELS:
            continue
        fid = f"egress_routes:{sid}:pinch:{k[0]}_{k[1]}"
        checks.append(Check(id=f"pinch:{k[0]}_{k[1]}", rule="Hallway width on a way out", measured=round(c["width"], 2),
                            threshold=HALL_M, unit="m", status=st, standard="IRC 2021 R311.6, 36 in hallway",
                            findings=[fid]))
        findings.append(Finding(id=fid, title="Narrow hallway on a way out", status=st,
                                detail=f"{c['width']:.2f} m wall to wall against 0.91 m (36 in); furniture not counted.",
                                anchor=PointAnchor(sid=sid, point=tuple(c["point"])), source=ROUTE))
    # rooms with one way out and dead ends
    one_way = [r for r in live_rooms(plan) if a["degree"].get(r["id"], 0) == 1]
    dead = [r for r in one_way if r.get("label") in HALL_LABELS]
    for r in one_way:
        fid = f"egress_routes:{sid}:one_way:{r['id']}"
        dead_end = r in dead
        if r.get("label") == BEDROOM or dead_end:
            findings.append(Finding(
                id=fid, title=f"{'Dead end' if dead_end else 'One way out'}, {name(r)}", status="warn",
                detail=("A hallway reached through one doorway only: a dead end for search and escape." if dead_end
                        else "The only way out through the building is the one door; the window is the second way."),
                anchor=RoomAnchor(sid=sid, room=r["id"]), source=ROUTE))
    # bedroom windows as the second way out
    for rid, sills in a["windows"].items():
        room = rooms[rid]
        low = min((s for _, s in sills if s is not None), default=None)
        res = judge(low, EERO_SILL_M, at_least=False) if low is not None else "not available"
        st = VERDICT_STATUS[res]
        fid = f"egress_routes:{sid}:window:{rid}"
        checks.append(Check(id=f"window:{rid}", rule=f"Escape window sill height, {name(room)}",
                            measured=round(low, 2) if low is not None else None, threshold=EERO_SILL_M, unit="m",
                            status=st, standard="IRC 2021 R310.2.2, sill at most 44 in above the floor",
                            findings=[fid] if st != "pass" else []))
        if st != "pass":
            findings.append(Finding(
                id=fid, title=f"Escape window, {name(room)}", status=st,
                detail=("No window is recorded in this bedroom's walls; the scan may not mark windows. Check on site."
                        if not sills else
                        f"Lowest window sill {low:.2f} m above the floor against 1.12 m (44 in)." if low is not None
                        else "Window sill height is missing from the scan."),
                anchor=RoomAnchor(sid=sid, room=rid), source=WINDOW))
    # entrances
    n_exit = len(a["exits"])
    checks.append(Check(id="entrances", rule="Doorways to outside or unscanned space on the entry floor",
                        measured=n_exit, threshold=2, unit="", status="warn" if n_exit < 2 else "pass",
                        findings=[f"egress_routes:{sid}:single_entrance"] if n_exit < 2 else []))
    if n_exit < 2:
        findings.append(Finding(id=f"egress_routes:{sid}:single_entrance", title="One way in from outside",
                                status="warn", detail="Only one doorway leads out of the scanned space. In an apartment "
                                "this is usually the unit door to a corridor the scan does not cover.",
                                anchor=OpeningAnchor(sid=sid, opening=a["exits"][0]["id"]), source=ROUTE))
    for e in a["exits"]:
        pins.append(Pin(id=f"entrance:{e['id']}", anchor=OpeningAnchor(sid=sid, opening=e["id"]),
                        label=f"Entrance {e['width']:.2f} m" if e.get("width") else "Entrance", status="unknown"))
    for e in a["upper_openings"]:
        pins.append(Pin(id=f"opening:{e['id']}", anchor=OpeningAnchor(sid=sid, opening=e["id"]),
                        label="Opening to unscanned space", status="unknown"))
    # hose stretch
    longest_hose = max(a["hose"], key=lambda h: h["length_m"], default=None)
    for h in a["hose"]:
        e, room = h["entrance"], rooms[h["room"]]
        over = h["length_m"] > inputs.hose_m
        fid = f"egress_routes:{sid}:hose:{e['id']}"
        findings.append(Finding(
            id=fid, title=f"Hose stretch from an entrance to {name(room)}", status="warn" if over else "pass",
            detail=(f"{h['length_m']:.1f} m from this doorway to the far corner of {name(room)} "
                    f"({floor_label(plan, room['floor'])}), the farthest point reached from it"
                    + (", by the stairs" if h["walk"]["stairs"] else "") + f". Hose to compare: {inputs.hose_m:.0f} m."),
            anchor=OpeningAnchor(sid=sid, opening=e["id"]), source=STAIR if h["walk"]["stairs"] else ROUTE))
        for leg in h["walk"]["legs"]:
            if not leg.get("stairs"):
                o = leg["overlay"]
                overlays.append(RouteOverlay(floor=o["floor"], points=o["points"], chokes=[],
                                             label=f"Hose stretch to {name(room)}"))
    if longest_hose:
        over = longest_hose["length_m"] > inputs.hose_m
        checks.append(Check(id="hose", rule="Longest hose stretch from an entrance", measured=round(longest_hose["length_m"], 1),
                            threshold=inputs.hose_m, unit="m", status="warn" if over else "pass",
                            findings=[f"egress_routes:{sid}:hose:{longest_hose['entrance']['id']}"]))
    if lens:
        overlays.insert(0, LensOverlay(values=lens, ramp="sequential", legend=Legend(
            title="Walking distance to an entrance", unit="m", min=0, max=max(lens.values()))))
    if one_way:
        overlays.append(RuleOverlay(select=SelectRooms(rooms=[r["id"] for r in one_way]), style="warn"))
    if pins:
        overlays.append(PinsOverlay(pins=pins))

    lengths = [w["length_m"] for w in ok.values()]
    nars = [w["narrowest"] for w in ok.values() if w["narrowest"]]
    narrow = min(nars, key=lambda c: c["width"]) if nars else None
    fails = sum(c.status == "fail" for c in checks)
    warns = sum(c.status == "warn" for c in checks)
    status = "fail" if fails else "warn" if warns else "pass" if ok else "unknown"
    bedrooms_one_way = [r for r in one_way if r.get("label") == BEDROOM]
    text = (f"Routed {len(ok)} rooms; the longest walk out is {_m(max(lengths) if lengths else None)} and the "
            f"narrowest point {narrow['width']:.2f} m. " if narrow else f"Routed {len(ok)} rooms. ") + \
        (f"{len(bedrooms_one_way)} bedroom{'s have' if len(bedrooms_one_way) > 1 else ' has'} one door out. "
         if bedrooms_one_way else "") + \
        (f"Hose stretch to the farthest point: {longest_hose['length_m']:.0f} m." if longest_hose else "")
    return ToolResult(
        scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text.strip()),
        metrics=[Metric(id="longest_route", label="Longest walk out", value=round(max(lengths), 1) if lengths else None,
                        unit="m", source=ROUTE),
                 Metric(id="narrowest", label="Narrowest point", value=round(narrow["width"], 2) if narrow else None,
                        unit="m", source=ROUTE),
                 Metric(id="one_way_rooms", label="Rooms with one way out", value=len(one_way), unit="", source=ROUTE),
                 Metric(id="hose_stretch", label="Longest hose stretch",
                        value=round(longest_hose["length_m"], 1) if longest_hose else None, unit="m", source=ROUTE),
                 Metric(id="entrances", label="Entrances", value=n_exit, unit="", source=ROUTE)]
        + [Metric(id=f"route.{name(rooms[r])}", label=name(rooms[r]), value=v, unit="m", source=ROUTE)
           for r, v in sorted(lens.items(), key=lambda kv: -kv[1])[:12]],
        checks=checks, findings=findings, overlays=overlays,
        assumptions=[Assumption(id="access.door_width_m", label="Exit door clear width", value=mw, unit="m", editable=True),
                     Assumption(id="fire.long_route_m", label="Long route above", value=inputs.long_route_m, unit="m",
                                editable=True),
                     Assumption(id="fire.preconnect_m", label="Hose to compare", value=inputs.hose_m, unit="m",
                                editable=True),
                     Assumption(id="empty_rooms", label="Rooms are empty: furniture is not in the wall graph", value=True),
                     Assumption(id="entrance_unverified", label="A doorway with a room on one side is an entrance; it "
                                "may lead to an unscanned room", value=True)])
