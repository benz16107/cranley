"""Step-free route: from the entrance to each room that matters, every doorway with its width, the narrowest point,
level changes, and a verdict per destination. Doorways whose recorded width is a data error are checked against
the panorama before anything is failed."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry import reach, route
from ...geometry._plan import VERDICT_STATUS, clear_width, judge
from .. import (Action, Assumption, Check, Finding, Metric, OpeningAnchor, Pin, PinsOverlay, RoomAnchor, RuleOverlay,
                ScanScope, Source, ToolResult, Verdict, field, tool)
from ..types import Media, PanoAnchor, PointAnchor, RouteOverlay, SelectRooms
from .._access import (GEO, GEO_LOW, RISER_M, SILL_NOISE_M, STD, STEP_M, Chair, cannot, chair_list, elevations,
                       floor_name, fmt, implausible, label, links_of, pick_entrance, quality, rooms, sill_step,
                       start_point, step_kind)
from .._access import look

WORST = ["likely fail", "measure on site", "not available", "likely pass"]
VISION_STEP = ("step or threshold", "stairs", "ramp")
LIFT_WORDS = ("elevator", "lift")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    destinations: list[str] = field(["Bathroom", "Bedroom", "Kitchen"], pref="access.destinations",
                                    description="Room types (Bathroom, Bedroom, Kitchen, Living Room...) or room ids")
    min_width_m: float = field(0.815, pref="access.door_width_m", unit="m", gt=0.3, le=2.0,
                               description="Clear width you need through doors")
    entrance: str | None = field(None, description="Opening id of the entrance to start from; default the main one")
    read_panoramas: bool = field(True, description="Ask the panoramas about steps and about doorways whose width "
                                                   "is a data error")
    chairs: list[Chair] = field([], pref="access.chairs",
                                description="Each chair the person uses (everyday, travel...); the route is checked "
                                            "for each. A chair without a width uses min_width_m")


def lifts(plan: dict) -> list[dict]:
    """Rooms the scan labels as an elevator or lift."""
    return [r for r in plan.get("rooms") or [] if any(w in (r.get("label") or "").lower() for w in LIFT_WORDS)]


def worst(results: list[str]) -> str:
    return min(results, key=WORST.index) if results else "not available"


SAME = {"restroom": "Bathroom", "kitchen or break room": "Kitchen"}  # commercial labels (offices) for home types


def targets(plan: dict, wanted: list[str]) -> list[dict]:
    rs = [r for r in plan["rooms"] if r.get("label") != "Void"]
    kind = lambda r: SAME.get(r.get("label"), r.get("label"))
    out = [r for r in rs if r["id"] in wanted or kind(r) in wanted]
    return sorted(out, key=lambda r: (wanted.index(r["id"]) if r["id"] in wanted else wanted.index(kind(r))))


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
            where = f"On {floor_name(plan, r['floor'])}"
            if lifts(plan):
                item.update(result="measure on site", rise=rise, elevator=True, reason=(
                    f"{where}, {fmt(rise)} from the entrance floor. The scan shows an elevator, so the only step-free "
                    "way is the elevator; the scan does not link floors, so check it reaches this floor and is in "
                    "service."))
            else:
                item.update(result="likely fail", rise=rise, elevator=False, reason=(
                    f"{where}, {fmt(rise)} from the entrance floor: stairs, about {round(rise / RISER_M)} steps at a "
                    "7 in riser. The scan shows no elevator or lift and does not link floors."
                    if rise > 0.3 else f"{where}, not linked to the entrance floor in the scan."))
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
        results += ["measure on site" if d["step_kind"] == "possible" else "likely fail"
                    for d in item["doors"] if d["step_kind"] != "none"]
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
    apply_seen(out, links)
    return out


def apply_seen(out: dict, links: dict) -> None:
    """A step the panorama shows in a room a route passes through counts against that route, not only as a pin."""
    for it in out["routes"]:
        on = {rid for d in it["doors"] for rid in (links[d["opening"]].get("rooms") or [links[d["opening"]].get("room")])}
        it["seen_steps"] = [f for f in out["vision"] if f.get("room") in on]
        if it["seen_steps"] and it["result"] == "likely pass":
            it["result"] = "measure on site"


def steps_of(it: dict) -> dict:
    """The step answer for one route: kind ('stairs', 'elevator', 'step', 'possible', 'none', 'unknown'), the
    highest sill step measured (m) and a few words."""
    if "elevator" in it:
        return {"kind": "elevator" if it["elevator"] else "stairs", "height": it.get("rise"),
                "words": "elevator only (another floor)" if it["elevator"] else "stairs (another floor)"}
    if it["route"] is None:
        return {"kind": "unknown", "height": None, "words": "not known (no route in the scan)"}
    sure = [d["step"] for d in it["doors"] if d["step_kind"] in ("step", "stair")]
    maybe = [d["step"] for d in it["doors"] if d["step_kind"] == "possible"]
    seen = it.get("seen_steps") or []
    measured = [d["step"] for d in it["doors"] if d["step"] is not None]
    top = max(measured, default=None)
    at_door = bool(it["doors"]) and it["doors"][0]["step_kind"] in ("step", "stair")  # doors[0] is the entrance
    if sure:
        n = len(sure)
        where = "the entrance door" if at_door and n == 1 else "doorways, one the entrance door" if at_door else \
            "a doorway" if n == 1 else "doorways"
        return {"kind": "step", "height": top, "words": f"{'a' if n == 1 else n} {max(sure) * 100:.0f} cm "
                                                        f"step{'s' if n > 1 else ''} at {where}"}
    if maybe or seen:
        bits = ([f"a possible {max(maybe) * 100:.0f} cm sill step"] if maybe else []) + \
               ([f"{', '.join(sorted({f['label'] for f in seen}))} seen in a panorama"] if seen else [])
        return {"kind": "possible", "height": top, "words": " and ".join(bits) + ", measure it"}
    if not measured:
        return {"kind": "unknown", "height": None, "words": "not known (no sill heights in the scan)"}
    return {"kind": "none", "height": top, "words": f"none found at {len(measured)} doorway"
                                                    f"{'s' if len(measured) > 1 else ''}"}


STEP_STATUS = {"stairs": "fail", "step": "fail", "elevator": "warn", "possible": "warn", "none": "pass",
               "unknown": "unknown"}
STEP_RANK = ["none", "elevator", "possible", "unknown", "step", "stairs"]
BEST = ["likely pass", "measure on site", "not available", "likely fail"]


def best_by_type(routes: list[dict]) -> dict[str, dict]:
    """Per destination type, the best room of it (one reachable bathroom is enough)."""
    out: dict[str, dict] = {}
    for it in routes:
        t = label(it["room"])
        if t not in out or BEST.index(it["result"]) < BEST.index(out[t]["result"]):
            out[t] = it
    return out


def step_free_rooms(plan: dict, ent: dict, width: float) -> dict:
    """Every room on the entrance floor reachable from the entrance with no doorway step, and the rooms on other
    floors, with whether an elevator is in the scan."""
    rs = rooms(plan)
    links = links_of(plan)
    ent_step = step_kind(sill_step(plan, links[ent["opening"]])) if ent["opening"] in links else "none"
    rc = reach(plan, width, start=ent["room"], max_step=STEP_M + SILL_NOISE_M)
    real = [r for r in rc.get("rooms", []) if not r["void"] and rs.get(r["room"], {}).get("label") not in ("Void",)]
    here = [r for r in real if r["floor"] == ent["floor"]]
    ok = [r for r in here if r["connected"] and ent_step in ("none", "possible")]
    return {"ok": ok, "blocked": [r for r in here if r not in ok], "other": [r for r in real if r["floor"] != ent["floor"]],
            "lift": bool(lifts(plan)), "entrance_step": ent_step}


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
      personas=["wheelchair_user", "older_adult_family", "wheelchair_home_search", "aging_in_place_planner"],
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
    chairs = chair_list(inputs.chairs, inputs.min_width_m)
    inputs = inputs.model_copy(update={"min_width_m": chairs[0]["door"]})  # the widest chair sets the main routes
    assumptions = [Assumption(id="access.door_width_m", label="Clear width you need", value=inputs.min_width_m,
                              unit="m", editable=not inputs.chairs),
                   Assumption(id="hung_door", label="Door widths are wall openings less 5 cm for a hung door",
                              value=True),
                   Assumption(id="furniture", label="Rooms are empty: furniture is not in the scan", value=True)]
    assumptions += [Assumption(id=f"chair.{i}", label=f"{c['name']}: clear door width it needs", value=c["door"],
                               unit="m") for i, c in enumerate(chairs) if c["name"]]
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
                    id=fid, title={"possible": "Possible step at a doorway", "step": "Step at a doorway"}.get(
                        d["step_kind"], "Stairs or a split level"),
                    status="warn" if d["step_kind"] == "possible" else "fail", anchor=a, source=GEO_LOW,
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

    # steps first: the question a wheelchair user asks is "any steps?", before any width
    step_checks = []
    for it in res["routes"]:
        a = steps_of(it)
        step_checks.append(Check(
            id=f"steps.{it['room']['id']}", rule=f"Any steps or level changes between the entrance and "
            f"{label(it['room']).lower()}: {a['words']}", measured=round(a["height"], 3) if a["height"] is not None
            else None, threshold=STEP_M, unit="m", status=STEP_STATUS[a["kind"]], standard=STD["level"],
            findings=[f for f in next(c.findings for c in checks if c.id == f"route.{it['room']['id']}")
                      if ":step:" in f or ":floor:" in f or ":seen:" in f]))
    checks = step_checks + checks
    sf = step_free_rooms(plan, ent, inputs.min_width_m)
    def names(xs):
        from collections import Counter
        n = Counter(label(rooms(plan).get(x["room"])).lower() for x in xs)
        return ", ".join(f"{k} ({v})" if v > 1 else k for k, v in sorted(n.items())) or "none"
    other = sf["other"]
    checks.append(Check(
        id="stepfree.rooms", rule=f"Rooms on the entrance floor reached with no step at any doorway: {names(sf['ok'])}"
        + (f"; not without a step: {names(sf['blocked'])}" if sf["blocked"] else "")
        + (f"; on other floors ({names(other)}): " + ("only by the elevator" if sf["lift"] else
                                                       "stairs only, no elevator in the scan") if other else "")
        + ("; the entrance doorway itself has a step" if sf["entrance_step"] in ("step", "stair") else
           "; the entrance doorway may have a step, measure it" if sf["entrance_step"] == "possible" else ""),
        measured=len(sf["ok"]), threshold=None, unit="rooms",
        status="pass" if not sf["blocked"] and not other else "warn", standard=STD["level"]))
    # chairs after the first: same routes, narrower or wider needs (steps do not depend on the chair)
    per_chair = [(chairs[0], res)]
    for c in chairs[1:]:
        rc = run_routes(ctx, plan, inputs.model_copy(update={"min_width_m": c["door"], "read_panoramas": False}))
        rc["vision"] = res["vision"]
        apply_seen(rc, links_of(plan))
        per_chair.append((c, rc))
    if len(chairs) > 1:
        for i, (c, rc) in enumerate(per_chair):
            for t, it in best_by_type(rc["routes"]).items():
                ws = [d["clear_width"] for d in it["doors"] if not d["implausible"] and d["clear_width"]] + \
                     [x["width"] for x in it["chokes"]]
                checks.append(Check(id=f"chair{i}.{it['room']['id']}",
                                    rule=f"{c['name']} (needs {fmt(c['door'])} clear), entrance to {t.lower()}",
                                    measured=round(min(ws), 3) if ws else None, threshold=c["door"], unit="m",
                                    status=VERDICT_STATUS[it["result"]], standard=STD["door"]))

    # verdict per destination type: one reachable room of a type is enough (your bedroom, one bathroom)
    bt = best_by_type(res["routes"])
    best = {t: it["result"] for t, it in bt.items()}
    lead = "Steps from the entrance: " + "; ".join(f"{t.lower()}, {steps_of(it)['words']}" for t, it in bt.items()) + "."
    failed = [t for t, b in best.items() if b == "likely fail"]
    unsure = [t for t, b in best.items() if b in ("measure on site", "not available")]
    if failed:
        stepped = [t for t in failed if steps_of(bt[t])["kind"] in ("step", "stairs")]
        narrow = [t for t in failed if t not in stepped]
        status, text = "fail", " ".join(
            ([f"Not step-free: {', '.join(stepped).lower()}."] if stepped else []) +
            ([f"Too narrow for you: {', '.join(narrow).lower()}."] if narrow else []))
    elif unsure:
        status, text = "warn", f"Routes exist; {', '.join(unsure).lower()} need a tape measure or a look on site."
    else:
        status, text = "pass", "Every destination has a step-free route wide enough for you, on the scan geometry."
    text = lead + " " + text
    if len(chairs) > 1:
        def reached(rc):
            return ", ".join(t.lower() for t, it in best_by_type(rc["routes"]).items()
                             if it["result"] == "likely pass") or "none of them"
        text += " By chair: " + "; ".join(f"{c['name']} reaches {reached(rc)}" for c, rc in per_chair) + "."
    text += " The entrance is a doorway with a room on one side only; the scan cannot tell outside from unscanned."
    checks += [cannot("outside", "steps outside the entrance or in a building lobby before the elevators, unless that "
                                 "part was scanned; check the way in with Curb to door"),
               cannot("obstructions", "boxes, carts, bales or cleaning supplies left in a hallway, aisle or elevator "
                                      "on the day"),
               cannot("ada", "whether the building is 'accessible' as claimed: the ADA has no certification or "
                             "inspection, so the claim is the owner's word")]
    if other or sf["lift"]:
        checks.append(cannot("elevator", "whether the elevator is in service and reaches every floor"))
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
