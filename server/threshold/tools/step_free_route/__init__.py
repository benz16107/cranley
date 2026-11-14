"""Step-free route: from the entrance to each room that matters, every doorway with its width, the narrowest point,
level changes, and a verdict per destination. Doorways whose recorded width is a data error are checked against
the panorama before anything is failed."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry import route
from ...geometry._plan import VERDICT_STATUS, clear_width, judge
from .. import (Action, Assumption, Check, Finding, Metric, OpeningAnchor, Pin, PinsOverlay, RoomAnchor, RuleOverlay,
                ScanScope, Source, ToolResult, Verdict, field, tool)
from ..types import Media, PanoAnchor, PointAnchor, RouteOverlay, SelectRooms
from .._access import (GEO, GEO_LOW, RISER_M, STD, elevations, floor_name, fmt, implausible, label, links_of,
                       pick_entrance, quality, rooms, sill_step, start_point, step_kind)
from .._access import look

WORST = ["likely fail", "measure on site", "not available", "likely pass"]
VISION_STEP = ("step or threshold", "stairs", "ramp")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    destinations: list[str] = field(["Bathroom", "Bedroom", "Kitchen"], pref="access.destinations",
                                    description="Room types (Bathroom, Bedroom, Kitchen, Living Room...) or room ids")
    min_width_m: float = field(0.815, pref="access.door_width_m", unit="m", gt=0.3, le=2.0,
                               description="Clear width you need through doors")
    entrance: str | None = field(None, description="Opening id of the entrance to start from; default the main one")
    read_panoramas: bool = field(True, description="Ask the panoramas about steps and about doorways whose width "
                                                   "is a data error")


def worst(results: list[str]) -> str:
    return min(results, key=WORST.index) if results else "not available"


def targets(plan: dict, wanted: list[str]) -> list[dict]:
    rs = [r for r in plan["rooms"] if r.get("label") != "Void"]
    out = [r for r in rs if r["id"] in wanted or r.get("label") in wanted]
    return sorted(out, key=lambda r: (wanted.index(r["id"]) if r["id"] in wanted else wanted.index(r["label"])))


def door_entry(plan, link, min_w, read, seen, ctx) -> dict:
    """One doorway on a route: width, clear width, result, sill step, and the panorama's view of a data error."""
    bad = implausible(link)
    cw = clear_width(link)
    step = sill_step(plan, link)
    e = {"opening": link["opening"], "width": link.get("width"), "clear_width": cw, "implausible": bad,
         "result": "measure on site" if bad else judge(cw, min_w), "step": step, "step_kind": step_kind(step),
         "center": link["center"], "look": None}
    if bad and read:
        if link["opening"] not in seen:
            op = next(o for o in plan["openings"] if o["id"] == link["opening"])
            ctx.step(f"Width {fmt(link.get('width'))} is a data error; asking the panorama what is at that doorway")
            seen[link["opening"]] = look.doorway(plan, op)
        e["look"] = seen[link["opening"]]
    return e


def run_routes(ctx, plan: dict, inputs) -> dict:
    """The shared engine of step_free_route: routes from the entrance to each target with level changes."""
    rs, links, el = rooms(plan), links_of(plan), elevations(plan)
    ent = pick_entrance(plan, inputs.entrance)
    out = {"entrance": ent, "routes": [], "vision": [], "vision_error": None}
    if ent is None:
        return out
    seen: dict[str, dict] = {}
    for r in targets(plan, inputs.destinations):
        item = {"room": r, "result": "not available", "doors": [], "chokes": [], "route": None, "reason": None}
        out["routes"].append(item)
        if r["floor"] != ent["floor"]:
            rise = abs((el.get(r["floor"]) or 0) - (el.get(ent["floor"]) or 0))
            item.update(result="likely fail", rise=rise, reason=(
                f"On {floor_name(plan, r['floor'])}, {fmt(rise)} from the entrance floor: stairs, about "
                f"{round(rise / RISER_M)} steps at a 7 in riser. The scan does not link floors or show a lift."
                if rise > 0.3 else f"On {floor_name(plan, r['floor'])}, not linked to the entrance floor in the scan."))
            continue
        rt = route(plan, start_point(plan, ent), r["id"], min_width=inputs.min_width_m, floor=r["floor"])
        if not rt["available"]:
            item["reason"] = rt["reason"]
            continue
        crossed = [d["opening"] for d in rt["doors"]]
        if ent["opening"] not in crossed:
            crossed.insert(0, ent["opening"])
        item["doors"] = [door_entry(plan, links[o], inputs.min_width_m, inputs.read_panoramas, seen, ctx)
                         for o in crossed if o in links]
        item["chokes"] = [c for c in rt["chokes"] if c["kind"] == "corridor"]
        item["route"] = rt
        results = [d["result"] for d in item["doors"]] + [c["result"] for c in item["chokes"]]
        results += ["likely fail" for d in item["doors"] if d["step_kind"] != "none"]
        item["result"] = worst(results) if results else "likely pass"
    # panoramas on the routes: steps, thresholds, stairs and ramps the wall graph cannot show
    if inputs.read_panoramas:
        on_route = {rid for it in out["routes"] for d in it["doors"] for rid in (links[d["opening"]].get("rooms")
                                                                                   or [links[d["opening"]].get("room")])}
        panos = [p["id"] for rid in sorted(on_route) if rid in rs for p in [look.central_pano(plan, rs[rid])] if p][:6]
        if panos:
            ctx.step(f"Reading {len(panos)} panoramas along the routes for steps, thresholds and ramps")
        found, err = look.objects(plan, panos)
        out["vision"] = [f for f in found if f["label"] in VISION_STEP]
        out["vision_error"] = err
    return out


def _route_source(rt) -> Source:
    s = rt["source"]
    return Source(layer="matterport", method="geometry", confidence=s["confidence"], note=s["note"])


@tool(id="step_free_route", title="Step-free route", icon="route",
      summary="Draws the route from the entrance to each room you need, with every door's width, the narrowest "
              "point and any step, and says whether you can get there.",
      model_description="Route audit for a wheelchair or walker user in one scan: from the entrance to each "
                        "destination room (Bathroom, Bedroom, Kitchen or named rooms), every doorway with width, the "
                        "narrowest point, level changes, and a verdict per destination. Implausible door widths are "
                        "flagged as data errors and checked against the panorama.",
      personas=["wheelchair_user", "older_adult_family"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.rooms"},
                {"layer": "matterport.panos", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "Controls",
              "AssumptionChips", "StepLog", "ActionBar"],
      overlays=["route", "pins", "rule"], annotations={"cost": "slow"},
      examples=["Can I get from the front door to the bathroom in my wheelchair?",
                "Is there a step-free way to the bedroom?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    q = quality(plan)
    scope = ScanScope(sid=sid)
    assumptions = [Assumption(id="access.door_width_m", label="Clear width you need", value=inputs.min_width_m,
                              unit="m", editable=True),
                   Assumption(id="hung_door", label="Door widths are wall openings less 5 cm for a hung door",
                              value=True),
                   Assumption(id="furniture", label="Rooms are empty: furniture is not in the scan", value=True)]
    if not q.get("walls"):
        ctx.step("No wall graph in this scan")
        tg = targets(plan, inputs.destinations)
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=(
            "This scan has rooms and panoramas but no wall graph, so doors, widths and routes cannot be measured.")),
            checks=[Check(id=r["id"], rule=f"Step-free route to {label(r)}", measured=None,
                          threshold=inputs.min_width_m, unit="m", status="unknown", standard=STD["door"]) for r in tg],
            assumptions=assumptions)
    res = run_routes(ctx, plan, inputs)
    ent = res["entrance"]
    if ent is None:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "No doorway in this scan has a room on one side only, so the entrance is not in the scan.")))
    ctx.step(f"Started at the entrance into the {label(rooms(plan).get(ent['room'])).lower()}; "
             f"routed to {len(res['routes'])} rooms")
    if not res["routes"]:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "None of the rooms you asked for are in this scan: " + ", ".join(inputs.destinations) + ".")))

    findings: dict[str, Finding] = {}
    checks, overlays, pins = [], [], []
    n_of: dict[str, int] = {}
    for it in res["routes"]:
        r = it["room"]
        n_of[label(r)] = n_of.get(label(r), 0) + 1
        name = f"{label(r)} {n_of[label(r)]}" if sum(1 for x in res["routes"] if label(x["room"]) == label(r)) > 1 \
            else label(r)
        fids = []
        for d in it["doors"]:
            a = OpeningAnchor(sid=sid, opening=d["opening"])
            if d["implausible"]:
                fid = f"step_free_route:{sid}:data:{d['opening']}"
                lk = d["look"] or {}
                seen = lk.get("seen")
                detail = (f"The scan records this doorway as {d['width'] * 100:.0f} cm wide, narrower than any door: "
                          f"a wall-graph error, not a narrow door. ")
                detail += (f"The panorama shows: {seen} ({lk.get('door')}, {lk.get('confidence')} confidence). "
                           if seen else f"Panorama not read: {lk.get('error', 'reading switched off')}. ")
                detail += "Measure this doorway on site."
                findings[fid] = Finding(id=fid, title="Door width is a data error", status="warn", detail=detail,
                                        anchor=a, media=[Media(**m) for m in lk.get("media", [])],
                                        source=Source(layer="model" if seen else "matterport",
                                                      method="vision" if seen else "geometry", confidence="low",
                                                      note="Width from the wall graph is implausible; door type from "
                                                           "the vision model" if seen else "Implausible wall-graph width"))
                fids.append(fid)
            elif d["result"] != "likely pass":
                fid = f"step_free_route:{sid}:door:{d['opening']}"
                findings[fid] = Finding(
                    id=fid, title="Doorway narrower than you need" if d["result"] == "likely fail"
                    else "Doorway too close to call", status=VERDICT_STATUS[d["result"]], anchor=a, source=GEO,
                    detail=f"Opening {fmt(d['width'])} in the wall, about {fmt(d['clear_width'])} clear with a door "
                           f"hung, against your {fmt(inputs.min_width_m)}. {STD['door']}.")
                fids.append(fid)
            if d["step_kind"] != "none":
                fid = f"step_free_route:{sid}:step:{d['opening']}"
                findings[fid] = Finding(
                    id=fid, title="Step at a doorway" if d["step_kind"] == "step" else "Stairs or a split level",
                    status="fail", anchor=a, source=GEO_LOW,
                    detail=f"The doorway sill is {d['step'] * 100:.0f} cm off this storey's floor level. "
                           f"Sill heights scatter about 4 cm on flat floors, so smaller steps do not show. {STD['level']}.")
                fids.append(fid)
        for c in it["chokes"]:
            if c["status"] == "pass":
                continue
            fid = f"step_free_route:{sid}:pinch:{c['point'][0]:.1f},{c['point'][1]:.1f}"
            findings[fid] = Finding(id=fid, title="Narrow passage between walls", status=c["status"],
                                    anchor=PointAnchor(sid=sid, point=tuple(c["point"])), source=GEO,
                                    detail=f"{fmt(c['width'])} between wall faces. {STD['route']}.")
            fids.append(fid)
        rt = it["route"]
        plausible = [d["clear_width"] for d in it["doors"] if not d["implausible"] and d["clear_width"] is not None]
        plausible += [c["width"] for c in it["chokes"]]
        narrow = min(plausible, default=None)
        detail = it["reason"] or (f"{rt['length_m']:.1f} m from the entrance through {len(it['doors'])} doorways; "
                                  f"narrowest {fmt(narrow)}.")
        checks.append(Check(id=f"route.{r['id']}", rule=f"Step-free route, entrance to {name}: {detail}",
                            measured=round(narrow, 3) if narrow is not None else None, threshold=inputs.min_width_m,
                            unit="m", status=VERDICT_STATUS[it["result"]], standard=f"{STD['door']}; {STD['level']}",
                            findings=fids))
        if it["reason"] and it["result"] == "likely fail":
            fid = f"step_free_route:{sid}:floor:{r['id']}"
            findings[fid] = Finding(id=fid, title=f"{name} is up or down stairs", status="fail", detail=it["reason"],
                                    anchor=RoomAnchor(sid=sid, room=r["id"]), source=GEO_LOW)
            checks[-1].findings.append(fid)
        if rt:
            ov = rt["overlay"]
            ov["label"] = f"Entrance to {name}"
            overlays.append(RouteOverlay(**ov))
    for f in res["vision"]:
        fd = f["finding"]
        fid = f"step_free_route:{sid}:seen:{fd['id']}"
        anchor = fd["anchor"]
        findings[fid] = Finding(id=fid, title=f"Panorama shows {f['label']}", status="warn",
                                detail=f"{fd['detail']}. Seen by the vision model in the panorama, not measured; "
                                       "check its height on site.",
                                anchor=PointAnchor(**anchor) if "point" in anchor else PanoAnchor(**anchor),
                                media=[Media(**m) for m in fd["media"]], source=Source(**fd["source"]))
    for f in findings.values():
        if f.anchor is not None:
            pins.append(Pin(id=f.id, anchor=f.anchor, label=f.title, status=f.status))
    if pins:
        overlays.append(PinsOverlay(pins=pins))
    by = {"pass": [], "warn": [], "fail": []}
    for it in res["routes"]:
        s = VERDICT_STATUS[it["result"]]
        if s in by:
            by[s].append(it["room"]["id"])
    overlays += [RuleOverlay(select=SelectRooms(rooms=v), style=k) for k, v in by.items() if v]

    # verdict per destination type: one reachable room of a type is enough (your bedroom, one bathroom)
    types: dict[str, list[str]] = {}
    for it in res["routes"]:
        types.setdefault(label(it["room"]), []).append(it["result"])
    best = {t: min(v, key=["likely pass", "measure on site", "not available", "likely fail"].index)
            for t, v in types.items()}
    failed = [t for t, b in best.items() if b == "likely fail"]
    unsure = [t for t, b in best.items() if b in ("measure on site", "not available")]
    if failed:
        status, text = "fail", f"No step-free route wide enough to: {', '.join(failed).lower()}."
    elif unsure:
        status, text = "warn", f"Routes exist; {', '.join(unsure).lower()} need a tape measure or a look on site."
    else:
        status, text = "pass", "Every destination has a step-free route wide enough for you, on the scan geometry."
    text += " The entrance is a doorway with a room on one side only; the scan cannot tell outside from unscanned."
    routes_ok = [it for it in res["routes"] if it["route"]]
    narrowest = min((c for it in routes_ok for c in ([d["clear_width"] for d in it["doors"] if not d["implausible"]
                                                     and d["clear_width"]] + [c["width"] for c in it["chokes"]])),
                    default=None)
    bath = [it["route"]["length_m"] for it in routes_ok if it["room"].get("label") == "Bathroom"]
    ctx.step(f"{len(findings)} findings; verdict {status}")
    src = GEO if all(it["route"] is None or it["route"]["source"]["confidence"] != "low" for it in res["routes"]) \
        else GEO_LOW
    return ToolResult(
        scope=scope, verdict=Verdict(status=status, text=text),
        metrics=[Metric(id="reachable", label="Destinations reachable", unit="",
                        value=sum(1 for it in res["routes"] if it["result"] == "likely pass"), source=src),
                 Metric(id="narrowest", label="Narrowest point on the routes", unit="m",
                        value=round(narrowest, 2) if narrowest is not None else None, source=src),
                 Metric(id="level_changes", label="Steps at doorways", unit="", source=GEO_LOW,
                        value=len({d["opening"] for it in res["routes"] for d in it["doors"] if d["step_kind"] != "none"})),
                 Metric(id="data_errors", label="Door widths that are data errors", unit="", source=GEO,
                        value=len({d["opening"] for it in res["routes"] for d in it["doors"] if d["implausible"]})),
                 Metric(id="bath_route_m", label="Entrance to nearest bathroom", unit="m", source=src,
                        value=round(min(bath), 1) if bath else None)],
        checks=checks, findings=list(findings.values()), overlays=overlays, assumptions=assumptions,
        actions=[Action(id="turning", label="Check turning space in these rooms", tool="turning_space",
                        inputs={"scan": sid}),
                 Action(id="bathroom", label="Check the bathroom for a wheelchair", tool="bathroom_clearance",
                        inputs={"scan": sid}),
                 Action(id="outside", label="Check the way in from parking", tool="curb_to_door", inputs={"scan": sid})]
        + ([Action(id="vision_off", label="Re-run without reading panoramas", tool="step_free_route",
                   inputs={"scan": sid, "read_panoramas": False})] if res["vision_error"] else []))
