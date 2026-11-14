"""Kids fit: is this home right for young children? Stairs that need gates, every route a small child could take to
the pool (path_to_water, folded in), windows a child could fall from, whether the kitchen looks onto the back yard,
and the walk to the nearest playground, park and schools with the busy roads crossed on the way.

Standards: IRC 2018 R312.2.1, a window whose opening is more than 72 in (1.83 m) above the ground outside and whose
sill is less than 24 in (0.61 m) above the floor needs a fall-prevention device or a window opening control (ASTM
F2090). CPSC "Safety gates" guidance: gates at the top and bottom of stairs for children under 2 (we flag under 4).
"""
from __future__ import annotations

import math

from pydantic import BaseModel
from shapely.geometry import Point
from shapely.ops import unary_union

from ...geometry._plan import polygons
from ...sources import index
from .. import (
    Assumption,
    Check,
    Finding,
    Metric,
    NotApplicable,
    OpeningAnchor,
    Pin,
    PinsOverlay,
    ScanScope,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    run_tool,
    tool,
)
from .._access import SILL_NOISE_M, quality
from .._site import Site, Where, footprint, geo, locate, to_m
from .._site import align as al
from ..nearby import assumptions as near_assumptions
from ..nearby import report as near_report
from ..pet_fit import home, yard
from ..types import RuleOverlay, SelectOpenings

IRC = "IRC 2018 R312.2.1: sill under 24 in (0.61 m) with the opening over 72 in (1.83 m) above grade needs a window opening control device (ASTM F2090)"
GATES = "CPSC, Safety gates: gate the top and bottom of stairs for young children"
SILL_M = 0.61
DROP_M = 1.83
GEO = Source(layer="matterport", method="geometry", confidence="medium", note="Matterport wall graph and opening sills")
RANK = {"pass": 0, "unknown": 1, "warn": 2, "fail": 3}


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    youngest_age: int = field(ask="How old is your youngest child, in years?", pref="kids.youngest_age", unit="years", ge=0, le=17)
    lat: float | None = field(None, description="For a phone scan with no location")
    lon: float | None = None
    use_vision: bool = field(True, description="Inspect pool-side doors and the yard with the vision model (cached)")
    nearby: bool = field(True, description="Look up playgrounds, parks and schools in OpenStreetMap (cached)")


def outward(plan: dict, o: dict) -> tuple[float, float] | None:
    """A point 0.8 m outside a window or door on an outside wall, or None when both sides are scanned rooms."""
    w = next((w for w in plan["walls"] if w["id"] == o["wall"]), None)
    if not w:
        return None
    polys = [p for p in polygons(plan).values() if p is not None]
    inside = unary_union(polys).buffer(0.05) if polys else None
    (ax, ay), (bx, by) = w["a"], w["b"]
    L = math.hypot(bx - ax, by - ay) or 1
    nx, ny = -(by - ay) / L, (bx - ax) / L
    cx, cy = o["center"]
    outs = [(cx + 0.8 * sx, cy + 0.8 * sy) for sx, sy in ((nx, ny), (-nx, -ny))
            if inside is None or not inside.contains(Point(cx + 0.6 * sx, cy + 0.6 * sy))]
    return outs[0] if len(outs) == 1 else None


def window_falls(plan: dict) -> list[dict]:
    """Upper-floor windows with the IRC test applied: sill above the floor, and the opening's height above the
    ground (floor rise above the lowest floor plus the sill; ground taken as the lowest floor)."""
    out = []
    for w in home.fall_windows(plan)["windows"]:
        sill = w["sill_m"]
        if sill is None or w["drop_m"] <= DROP_M:
            irc = "unknown" if sill is None else "pass"
        else:  # sills scatter about 4 cm in the scan: within that of the line, measure on site
            irc = "fail" if sill < SILL_M - SILL_NOISE_M else "measure" if sill < SILL_M + SILL_NOISE_M else "pass"
        out.append({**w, "irc": irc})
    return out


def kitchen_view(plan: dict, s, back) -> dict:
    """Kitchen windows on an outside wall, and how many look onto the back yard (needs the plan placed on the map)."""
    rooms = {r["id"] for r in plan["rooms"] if r.get("label") in ("Kitchen", "Breakfast Nook", "Dining Room")}
    wins = [o for o in plan.get("openings") or [] if o["type"] == "window" and set(o.get("rooms") or []) & rooms]
    ext = [(o, outward(plan, o)) for o in wins]
    ext = [(o, p) for o, p in ext if p]
    yard_hits = None
    if s is not None and back is not None and ext:
        a = al.check(plan, footprint(s))
        if a["available"] and a["confidence"] != "low":
            fwd = to_m(s.lat)[0]
            yard_hits = [o["id"] for o, p in ext if back.buffer(2).contains(Point(fwd(*al.to_lonlat(plan, a, *p))))]
    return {"windows": [o["id"] for o, _ in ext], "onto_yard": yard_hits}


@tool(id="kids_fit", title="Kids fit", icon="baby",
      summary="Whether a home suits young children: stairs that need gates, the pool path with no barrier, windows a "
              "child could fall from, a back yard the kitchen looks onto, and the walk to playgrounds, parks and schools.",
      model_description="For one scanned home and the youngest child's age: staircases to gate (floors in the scan), every "
                        "route from a bedroom to the pool with the missing barrier (runs path_to_water), upper-floor windows "
                        "judged against IRC R312.2.1 (sill under 24 in with a drop over 72 in), kitchen windows that look onto "
                        "the back yard (plan placed on the Vexcel footprint), and the walk along the streets to the nearest "
                        "playground, park, elementary, middle and high school, library, public pool and childcare, with busy "
                        "roads crossed (OpenStreetMap).",
      personas=["parent_young_kids", "teen_soccer_family", "pool_safety_parent"],
      requires=[{"layer": "matterport.openings"}, {"layer": "vexcel.property", "need": "optional"},
                {"layer": "osm.places", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["route", "pins", "rule"], annotations={"cost": "slow"},
      examples=["Is this house safe for my toddler?", "Is there a playground within walking distance?",
                "Which windows need a window guard?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid, age = inputs.scan, inputs.youngest_age
    plan = ctx.plan(sid)
    if not quality(plan).get("walls"):
        raise NotApplicable("This scan has no wall graph, so stairs, windows and routes cannot be measured.")
    small = age < 6
    kind = (index.rows().get(sid) or {}).get("kind")
    try:
        s = locate(ctx, Where(scan=sid, lat=inputs.lat, lon=inputs.lon))
    except NotApplicable:  # a phone scan: no location unless the person gave one
        s = Site(inputs.lat, inputs.lon, sid, None, None, "point given") if inputs.lat is not None and inputs.lon is not None else None
    checks, findings, metrics, overlays = [], [], [], []
    reasons, unknown = [], []

    def add(cid, rule, measured, thr, unit, st, std, fid, why):
        checks.append(Check(id=cid, rule=rule, measured=measured, threshold=thr, unit=unit, status=st, standard=std,
                            findings=[fid] if fid else []))
        if why and st in ("warn", "fail"):
            reasons.append(why)
        elif why and st == "unknown":
            unknown.append(why)

    # stairs
    st = home.stairs(plan)
    stairs_n = max(st["floors"] - 1, 0)
    metrics.append(Metric(id="staircases", label="Staircases to gate (floors in the scan, less one)", value=stairs_n, unit="",
                          source=Source(layer="matterport", method="geometry", confidence="low", note="Stairs are not in the scan; one flight per floor change")))
    fid = f"kids_fit:{sid}:stairs"
    findings.append(Finding(id=fid, title="Stairs", status="warn" if stairs_n and age < 4 else "pass", anchor=None, source=GEO,
                            detail=f"{st['floors']} floors, about {st['steps_max']} steps from the entrance floor to the farthest one"
                                   + (f"; gate the top and bottom of {stairs_n} flight{'s' if stairs_n > 1 else ''}." if stairs_n else ".")))
    add("stairs", "Stairs gated top and bottom", stairs_n * 2, 0, "gates", "warn" if stairs_n and age < 4 else "pass", GATES, fid,
        f"{stairs_n * 2} stair gates to fit" if stairs_n and age < 4 else "")
    # windows
    falls = window_falls(plan)
    bad = [w for w in falls if w["irc"] == "fail"]
    close = [w for w in falls if w["irc"] == "measure"]
    fid = f"kids_fit:{sid}:windows"
    metrics.append(Metric(id="low_windows", label="Upper windows with a low sill", value=len(bad), unit="", source=GEO))
    if kind == "apartment_unit":
        add("windows", "Windows guarded against falls", len(bad) or None, 0, "windows", "warn" if small else "pass", IRC, fid,
            "the scan does not say which floor the unit is on; above the ground floor, fit window opening controls" if small else "")
        findings.append(Finding(id=fid, title="Window falls", status="warn" if small else "pass", anchor=None, source=GEO,
                                detail="An apartment unit: the plan does not say how far above the ground it is. From the second "
                                       "floor up, every window with a sill under 24 in needs an opening control (IRC R312.2.1)."))
    elif falls:
        stt = ("fail" if small else "warn") if bad else "warn" if close else "pass"
        add("windows", "Upper windows with a sill under 24 in guarded", len(bad), 0, "windows", stt, IRC, fid,
            f"{len(bad)} upper windows with a low sill need opening controls" if bad else
            f"{len(close)} upper window sills are within 4 cm of 24 in; measure them" if close else "")
        findings.append(Finding(id=fid, title="Windows a child could fall from" if bad else "Upper-floor windows", status=stt,
                                anchor=OpeningAnchor(sid=sid, opening=(bad or falls)[0]["id"]), source=GEO,
                                detail=f"{len(falls)} windows on upper floors; {len(bad)} have a sill under 0.57 m with the opening "
                                       f"more than 1.83 m above the ground (taken as the lowest floor); {len(close)} more are within "
                                       "the scan's 4 cm of the 0.61 m line. "
                                       + "; ".join(f"{w['room']}: sill {w['sill_m']:.2f} m, {w['drop_m']:.1f} m up" for w in (bad + close)[:5])))
        if bad:
            overlays.append(RuleOverlay(select=SelectOpenings(openings=[w["id"] for w in bad]), style="fail"))
            overlays.append(PinsOverlay(pins=[Pin(id=f"win_{w['id']}", anchor=OpeningAnchor(sid=sid, opening=w["id"]),
                                                  label="Window guard needed", status="fail") for w in bad[:10]]))
    # pool: path_to_water does the whole job
    if s is not None and kind != "apartment_unit":
        ctx.step("Tracing the routes from each bedroom to the pool (path_to_water)")
        try:
            pw = run_tool("path_to_water", {"scan": sid, "use_vision": inputs.use_vision}, ctx)
            fid = f"kids_fit:{sid}:pool"
            stt = pw.verdict.status if small else ("warn" if pw.verdict.status == "fail" else pw.verdict.status)
            add("pool", "Every route to the pool meets a barrier", next((m.value for m in pw.metrics if m.id == "unguarded"), None),
                0, "routes", stt, "CPSC Pub. 362 (2015)", fid, "" if stt == "pass" else pw.verdict.text.split(".")[0].lower())
            findings.append(Finding(id=fid, title="Path to the pool", status=pw.verdict.status, anchor=geo(s.lon, s.lat),
                                    source=Source(layer="matterport", method="geometry", confidence="medium", note="path_to_water"),
                                    detail=pw.verdict.text))
            overlays += [o for o in pw.overlays if o.kind == "route"]
            findings += [f for f in pw.findings if f.id.endswith(":fixes")]
        except ToolError as e:
            ctx.step(f"Pool routes not traced: {e}")
    # kitchen onto the yard
    if s is not None and kind != "apartment_unit":
        ys = yard.yard_shape(s)
        back = None
        if ys and ys[0] is not None:
            street = yard.street_side(s, ys[1]) if inputs.nearby else None
            back = yard.back_yard(ys[0], ys[1], street)
        kv = kitchen_view(plan, s, back)
        fid = f"kids_fit:{sid}:kitchen"
        if kv["onto_yard"] is None:
            stt = "unknown"
            detail = f"{len(kv['windows'])} kitchen or dining windows on an outside wall; the plan does not sit well enough on the map to tell which side they face."
        else:
            stt = "pass" if kv["onto_yard"] else "warn"
            detail = f"{len(kv['onto_yard'])} of {len(kv['windows'])} kitchen or dining windows look onto the back yard (plan placed on the Vexcel footprint)."
        add("kitchen_view", "The kitchen looks onto the back yard", len(kv["onto_yard"] or []) if kv["onto_yard"] is not None else None,
            1, "windows", stt, None, fid, "" if stt == "pass" else "no kitchen window onto the back yard" if stt == "warn" else
            "which way the kitchen windows face")
        findings.append(Finding(id=fid, title="Kitchen view of the yard", status=stt, source=GEO, detail=detail,
                                anchor=OpeningAnchor(sid=sid, opening=(kv["onto_yard"] or kv["windows"])[0]) if kv["windows"] else None))
        if kv["onto_yard"]:
            overlays.append(RuleOverlay(select=SelectOpenings(openings=kv["onto_yard"]), style="pass"))
    # nearby
    if s is not None and inputs.nearby:
        ctx.step("Looking up playgrounds, parks and schools in OpenStreetMap (one cached request per area)")
        level = "school_elementary" if age < 11 else "school_middle" if age < 14 else "school_high"
        cats = ["playground", "park", level, "library", "pool"] + (["childcare"] if age < 5 else [])
        near = near_report("kids_fit", sid, s.lat, s.lon, cats, prefix="near")
        metrics += near["metrics"]
        findings += near["findings"]
        overlays += near["overlays"]
        for cat, why_far in (("playground", "no playground within a 10-minute walk"), ("park", "no park within a 10-minute walk"),
                             (level, "the nearest school at this level is more than a 20-minute walk")):
            c = next((c for c in near["checks"] if c.id == f"near.{cat}"), None)
            h = (near["hits"].get(cat) or [None])[0]
            if c is None:
                continue
            lim = 20 if cat == level else 10
            stt = "unknown" if h is None and near["error"] else "pass" if h and h["minutes"] <= lim else "warn"
            add(f"near.{cat}", c.rule.replace("10-minute", f"{lim}-minute"), c.measured, lim, "min", stt, None,
                c.findings[0] if c.findings else None, "" if stt == "pass" else why_far)
            if h and h.get("busy_crossings") and cat in ("playground", level):
                add(f"cross.{cat}", f"Busy roads crossed on the walk to the {c.rule.split(' within')[0].lower()}", h["busy_crossings"], 0,
                    "roads", "warn", None, c.findings[0], f"{h['busy_crossings']} busy road crossing{'s' if h['busy_crossings'] > 1 else ''} on the walk to the {cat.replace('school_', '').replace('_', ' ')}")
        for c in near["checks"]:  # the rest inform; a missing library does not fail a home
            if c.id.split(".")[1] not in ("playground", "park", level):
                checks.append(c.model_copy(update={"status": "warn" if c.status == "fail" else c.status}))
    elif s is None:
        add("outdoor", "Pool, yard and places nearby", None, None, "", "unknown", None, None,
            "the scan has no location, so the pool, yard and places nearby were not checked")
    status = max((c.status for c in checks if c.status != "unknown"), key=RANK.get, default="unknown")
    word = {"pass": "Suits your children", "warn": "Suits your children with changes", "fail": "Needs changes before a child moves in",
            "unknown": "Cannot tell"}[status]
    text = f"{word} (youngest {age})" + (f": {'; '.join(reasons[:4])}." if reasons else ".") + (f" Not checked: {unknown[0]}." if unknown else "")
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays,
                      assumptions=[Assumption(id="kids.youngest_age", label="Youngest child", value=age, unit="years", editable=True),
                                   Assumption(id="kids.ground", label="Ground outside is level with the lowest floor", value=True),
                                   Assumption(id="kids.stairs", label="Stairs are not in the scan; one flight per floor change", value=True)]
                      + (near_assumptions("walk") if s is not None and inputs.nearby else []))

