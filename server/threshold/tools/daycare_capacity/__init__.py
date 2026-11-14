"""Daycare capacity: could this space be licensed as a child-care centre, and for how many children? Indoor activity
area from the scan, outdoor play area from the aerial photo, toilets and sinks from the panoramas, each against the
state rule. The capacity is the smallest of the four, and the limiting one is named.

Rules (read 2026-11-13):
- Texas, 26 TAC ch. 746 (child-care centres). §746.4201: 30 ft2 of indoor activity space per licensed child.
  §746.4301(a): 80 ft2 of outdoor activity space per child using it at one time; (b) the outdoor space must hold at
  least 25% of the licensed capacity. §746.4407(a) and §746.4401(a): one flush toilet and one sink for every 17
  children 18 months and older (centres licensed for 13 or more).
  https://regulations.justia.com/states/texas/title-26/part-1/chapter-746/subchapter-t ,
  https://www.law.cornell.edu/regulations/texas/26-Tex-Admin-Code-SS-746-4407
- California, 22 CCR (Title 22, Div. 12, Ch. 1). §101238.3: 35 ft2 of indoor activity space per child, and
  §101238.2: 75 ft2 of outdoor activity space per child, both on total licensed capacity. §101238(h): one toilet and
  one hand-washing fixture for every 15 children; (i) one more of each for ill children, staff and emergencies.
  https://www.cdss.ca.gov/ord/entres/getinfo/pdf/ccc6.pdf
Indoor activity space leaves out bathrooms, kitchens, halls, offices and storage (both states' guidance); pools do
not count as outdoor space (California).
"""
from __future__ import annotations

import math

from shapely import wkt as shapely_wkt

from ...aerial import detect as aerial_detect
from .. import (
    Check,
    Finding,
    Metric,
    RoomAnchor,
    RuleOverlay,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from .._site import (
    FT2_PER_M2,
    Where,
    capture,
    fact,
    footprint,
    geo,
    geo_route,
    locate,
    lonlat,
    metres,
    ortho_media,
    parcel,
    pin,
    pins,
)
from ..types import SelectRooms

RULES = {
    "TX": {"indoor": 30, "outdoor": 80, "outdoor_share": 0.25, "per_toilet": 17, "per_sink": 17, "spare": 0,
           "cite": {"indoor": "26 TAC §746.4201", "outdoor": "26 TAC §746.4301(a), (b)", "toilets": "26 TAC §746.4407(a)",
                    "sinks": "26 TAC §746.4401(a)"}},
    "CA": {"indoor": 35, "outdoor": 75, "outdoor_share": 1.0, "per_toilet": 15, "per_sink": 15, "spare": 1,
           "cite": {"indoor": "22 CCR §101238.3", "outdoor": "22 CCR §101238.2", "toilets": "22 CCR §101238(h), (i)",
                    "sinks": "22 CCR §101238(h), (i)"}},
}
EXCLUDED = {"bathroom", "kitchen", "hallway", "closet", "pantry", "laundry", "utility room", "garage", "staircase",
            "entrance", "void", "office", "balcony", "patio", "restroom", "corridor", "storage", "mail room",
            "server or electrical room", "stairwell", "elevator lobby", "kitchen or break room", "leasing office"}
WET = {"bathroom", "restroom", "laundry", "utility room"}
MIN_ROOM_M2 = 2.0
AREA = Source(layer="matterport", method="geometry", confidence="high", note="Room areas from the scan's room outlines")


class Inputs(Where):
    state: str | None = field(None, pattern="^(TX|CA)$", description="TX or CA; from the location when left out")
    use_vision: bool = field(True, description="Count toilets and sinks in the panoramas with the vision model (cached)")


def indoor(plan: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(counted, excluded, unlabelled) rooms. Unlabelled rooms are left out and listed, never guessed."""
    counted, excluded, unknown = [], [], []
    for r in plan["rooms"]:
        a = r.get("area") or 0
        if a < MIN_ROOM_M2:
            continue
        lab = (r.get("label") or "").strip().lower()
        if not lab or lab == "other":
            unknown.append(r)
        elif lab in EXCLUDED:
            excluded.append(r)
        else:
            counted.append(r)
    return counted, excluded, unknown


def capacities(rule: dict, indoor_ft2: float | None, outdoor_ft2: float | None, toilets: int | None,
               sinks: int | None) -> dict[str, int | None]:
    """Children each input allows under one state's rule (None when unknown)."""
    f = lambda v, per: None if v is None else max(0, math.floor(v / per))
    out_cap = None if outdoor_ft2 is None else math.floor(outdoor_ft2 / (rule["outdoor"] * rule["outdoor_share"]))
    return {"indoor": f(indoor_ft2, rule["indoor"]), "outdoor": out_cap,
            "toilets": None if toilets is None else max(0, toilets - rule["spare"]) * rule["per_toilet"],
            "sinks": None if sinks is None else max(0, sinks - rule["spare"]) * rule["per_sink"]}


def outdoor_area(s) -> dict | None:
    """Parcel less the building, the pool and the estimated paving. Paving is Vexcel's share of the parcel, so it is an
    area, not a shape: the play-area outline drawn is the unbuilt land before paving comes off."""
    pc, fp = parcel(s), footprint(s)
    if pc is None or fp is None:
        return None
    pm = metres(pc, s.lat)
    free = pm.difference(metres(fp, s.lat).buffer(0.5))
    pool_m2 = 0.0
    if fact(s, "pool"):
        det = aerial_detect.detect(s.lat, s.lon, 80, ["swimming pool"], threshold=0.3)
        for d in det["detections"]:
            g = metres(shapely_wkt.loads(d["polygon"]), s.lat)
            if d["image"] == "spherical-ortho" and g.intersection(pm).area > 0.5 * g.area:
                pool_m2 += g.buffer(1.5).intersection(free).area
                free = free.difference(g.buffer(1.5))
    paved = (fact(s, "paved_percent") or 0) / 100 * pm.area
    play = max(0.0, free.area - paved)
    return {"parcel_m2": pm.area, "unbuilt_m2": free.area, "paved_m2": paved, "pool_m2": pool_m2, "play_m2": play,
            "outline": lonlat(free, s.lat)}


def fixtures(ctx, plan: dict) -> dict | None:
    """Toilets and sinks in the bathrooms, read from the central panorama of each wet room."""
    from ...vision.reader import find_objects, room_panos
    wet = [r for r in plan["rooms"] if (r.get("label") or "").lower() in WET]
    panos = []
    for r in wet:
        inside = room_panos(plan, r)
        if inside:
            panos.append(inside[0]["id"])
            continue
        # small bathrooms are often shot from the doorway: the nearest panorama within 4 m of the room's centre
        pts = r.get("polygon") or []
        c = r.get("center") or ([sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)] if pts else None)
        near = [(math.dist(c, q["position"][:2]), q["id"]) for q in plan["panos"]
                if c and q.get("rotation") and q.get("floor") == r["floor"]]
        near = [x for x in near if x[0] <= 4]
        if near:
            panos.append(min(near)[1])
    panos = list(dict.fromkeys(panos))
    if not panos:
        return None
    found = find_objects(plan, labels=["toilet", "sink"], panos=panos, max_panos=8)
    return {"found": found, "toilets": sum(f["label"] == "toilet" for f in found),
            "sinks": sum(f["label"] == "sink" for f in found), "rooms": len(panos)}


@tool(id="daycare_capacity", title="Daycare capacity", icon="baby",
      summary="How many children this space could be licensed for: indoor room area, outdoor play area, toilets and sinks "
              "against the Texas or California rule, with the limiting factor named.",
      model_description="For a scanned building in Houston (Texas, 26 TAC 746) or Los Angeles (California, 22 CCR 101238): "
                        "indoor activity area from the scan's labelled rooms (bathrooms, kitchens, halls, offices and "
                        "storage left out), outdoor play area from the aerial parcel less building, pool and paving, "
                        "toilets and sinks counted in the panoramas, each turned into a child count by the state rule. "
                        "Returns the capacity, the limiting factor, room highlights and the play-area outline on the map.",
      personas=["daycare_operator"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.room_labels"}, {"layer": "vexcel.property"},
                {"layer": "matterport.panos", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "EvidenceStrip", "AssumptionChips", "StepLog"],
      overlays=["rule", "route", "pins"], annotations={"cost": "slow"},
      examples=["How many kids could I license here?", "Is there enough outdoor play space for a daycare?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    s = locate(ctx, inputs)
    st = inputs.state or s.state
    rule = RULES[st]
    k = s.key
    checks, findings, metrics, overlays, ps = [], [], [], [], []
    in_ft2 = None
    counted = excluded = unknown = []
    if s.sid:
        plan = ctx.plan(s.sid)
        counted, excluded, unknown = indoor(plan)
        guessed = []
        if unknown and inputs.use_vision and len(unknown) <= 6:  # name unlabelled rooms from their panoramas
            try:
                from ...vision.reader import label_rooms
                got = {x["room"]: x for x in label_rooms(plan, [r["id"] for r in unknown])}
            except Exception as e:  # noqa: BLE001  they stay unlabelled and left out
                got = {}
                ctx.step(f"Unlabelled rooms not read: {str(e)[:100]}")
            for r in list(unknown):
                g = got.get(r["id"])
                if g and g["label"].lower() not in ("other",):
                    unknown.remove(r)
                    r = {**r, "label": g["label"]}
                    guessed.append(r)
                    (excluded if g["label"].lower() in EXCLUDED else counted).append(r)
            if guessed:
                ctx.step("Vision model named " + ", ".join(f"{r['label']} ({r['area']:.0f} m2)" for r in guessed))
        in_m2 = sum(r["area"] for r in counted)
        in_ft2 = in_m2 * FT2_PER_M2 if counted else None
        ctx.step(f"{len(counted)} rooms count as activity space ({in_m2:.0f} m2), {len(excluded)} left out, "
                 f"{len(unknown)} unlabelled")
        overlays += [RuleOverlay(select=SelectRooms(rooms=[r["id"] for r in counted]), style="pass")] if counted else []
        overlays += [RuleOverlay(select=SelectRooms(rooms=[r["id"] for r in excluded + unknown]), style="dim")] \
            if excluded or unknown else []
        for r in counted:
            metrics.append(Metric(id=f"rooms.{r['id']}", label=r.get("label") or "room", value=round(r["area"] * FT2_PER_M2),
                                  unit="ft2", source=AREA))
        if guessed:
            findings.append(Finding(id=f"daycare_capacity:{k}:guessed", title="Room types read from the panoramas", status="unknown",
                                    anchor=RoomAnchor(sid=s.sid, room=guessed[0]["id"]),
                                    source=Source(layer="model", method="vision", confidence="medium",
                                                  note="label_rooms on the panorama nearest each room's centre"),
                                    detail="The scan had no type for " + ", ".join(f"a {r['label'].lower()} of {r['area'] * FT2_PER_M2:.0f} ft2"
                                                                                   for r in guessed) + "; check them."))
        if unknown:
            findings.append(Finding(id=f"daycare_capacity:{k}:unlabelled", title="Rooms with no label left out", status="unknown",
                                    anchor=RoomAnchor(sid=s.sid, room=unknown[0]["id"]), source=AREA,
                                    detail=f"{len(unknown)} rooms, {sum(r['area'] for r in unknown) * FT2_PER_M2:.0f} ft2, have no "
                                           "room type, so they are not counted. Label them to add any that are play rooms."))
    else:
        plan = None
        ctx.step("No scan: indoor area and fixtures are unknown")
    out = outdoor_area(s)
    out_ft2 = out["play_m2"] * FT2_PER_M2 if out else None
    if out:
        ctx.step(f"Parcel {out['parcel_m2']:.0f} m2; unbuilt {out['unbuilt_m2']:.0f} m2, less {out['paved_m2']:.0f} m2 paved "
                 f"and {out['pool_m2']:.0f} m2 of pool: {out['play_m2']:.0f} m2 to play")
        ring = max(getattr(out["outline"], "geoms", [out["outline"]]), key=lambda g: g.area)
        if not ring.is_empty:
            overlays.append(geo_route(list(ring.exterior.coords), "Outdoor play area (before paving is taken off)"))
            c = ring.representative_point()
            ps.append(pin("play", c.x, c.y, "outdoor play", "pass"))
    fx = None
    if plan and inputs.use_vision:
        try:
            fx = fixtures(ctx, plan)
        except Exception as e:  # noqa: BLE001  fixtures stay unknown
            ctx.step(f"Toilets and sinks not counted: {str(e)[:120]}")
    caps = capacities(rule, in_ft2, out_ft2, fx["toilets"] if fx else None, fx["sinks"] if fx else None)
    vis = Source(layer="model", method="vision", confidence="medium",
                 note=f"Vision model on the central panorama of {fx['rooms']} wet rooms" if fx else "Vision model")
    out_src = Source(layer="vexcel", method="geometry", confidence="low",
                     note="Vexcel parcel less its footprint, pools (SAM 3) with a 1.5 m apron, and Vexcel's paved share; "
                          "fence line and shade not checked")
    labels = {"indoor": ("Indoor activity space", in_ft2, "ft2", AREA), "outdoor": ("Outdoor play space", out_ft2, "ft2", out_src),
              "toilets": ("Toilets", fx["toilets"] if fx else None, "", vis), "sinks": ("Sinks", fx["sinks"] if fx else None, "", vis)}
    per = {"indoor": f"{rule['indoor']} ft2 per child", "outdoor": f"{rule['outdoor']} ft2 per child"
           + (", sized for 25% of capacity" if rule["outdoor_share"] < 1 else ""),
           "toilets": f"1 per {rule['per_toilet']} children" + (" plus 1 spare" if rule["spare"] else ""),
           "sinks": f"1 per {rule['per_sink']} children" + (" plus 1 spare" if rule["spare"] else "")}
    for key, (label, val, unit, srcx) in labels.items():
        metrics.insert(0 if key == "indoor" else len(metrics), Metric(id=key, label=label, value=round(val) if val is not None else None,
                                                                       unit=unit, source=srcx))
        metrics.append(Metric(id=f"cap.{key}", label=f"Children, by {key}", value=caps[key], unit="children", source=srcx))
    if out_ft2 is not None and rule["outdoor_share"] < 1:
        metrics.append(Metric(id="outdoor_at_once", label="Children outside at one time", value=math.floor(out_ft2 / rule["outdoor"]),
                              unit="children", source=out_src))
    known = {k_: v for k_, v in caps.items() if v is not None}
    cap = min(known.values()) if known else None
    limit = min(known, key=known.get) if known else None
    for key, v in caps.items():
        fid = f"daycare_capacity:{k}:{key}"
        status = "unknown" if v is None else "warn" if key == limit else "pass"
        checks.append(Check(id=key, rule=f"{labels[key][0]}: {per[key]}", measured=v, threshold=cap, unit="children",
                            status=status, standard=f"{rule['cite'][key]} ({st})", findings=[fid]))
        if key == "outdoor" and out:
            findings.append(Finding(id=fid, title="Outdoor play area", status=status, anchor=geo(*ps[0].anchor.geo) if ps else geo(s.lon, s.lat),
                                    source=out_src, media=[ortho_media(s, 80, out["outline"])],
                                    detail=f"{out['play_m2'] * FT2_PER_M2:.0f} ft2 left after the building, "
                                           f"{out['paved_m2'] * FT2_PER_M2:.0f} ft2 of paving and {out['pool_m2'] * FT2_PER_M2:.0f} ft2 of "
                                           f"pool and apron. A licensed play yard needs a fence ({'4 ft or more, ' if st == 'CA' else ''}"
                                           "not checked) and shade."))
        if key in ("toilets", "sinks") and fx:
            hits = [f for f in fx["found"] if f["label"] == key[:-1]]
            findings.append(Finding(id=fid, title=f"{key.capitalize()} found in the bathrooms", status=status,
                                    anchor=hits[0]["finding"]["anchor"] if hits else None, source=vis,
                                    media=[m for f in hits for m in f["finding"]["media"]][:6],
                                    detail=f"{len(hits)} {key} seen in {fx['rooms']} wet rooms; child-height fixtures not told apart."))
    if cap is None:
        status, text = "unknown", "Neither the scan nor the aerial photo gives enough to size a daycare here."
    elif in_ft2 is None:  # outdoor space alone is no capacity: indoor space and toilets usually decide it
        status = "unknown"
        text = (f"Without a scan only the outdoor space is known: it would allow about {caps['outdoor']} children under {st} "
                "rules. Indoor space, toilets and sinks decide the licence and need a scan.")
    else:
        status = "pass" if cap >= 13 else "warn"
        names = {"indoor": "indoor space", "outdoor": "outdoor play space", "toilets": "toilets", "sinks": "sinks"}
        others = ", ".join(f"{names[a]} allows {b}" for a, b in known.items() if a != limit)
        text = (f"About {cap} children under {st} rules, limited by {names[limit]}" + (f" ({others})." if others else ".")
                + (" Indoor space is unknown without a scan." if in_ft2 is None else ""))
    if out:
        text += f" Imagery {capture(s)}."
    return ToolResult(scope=s.scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays + pins(ps),
                      assumptions=[{"id": "state", "label": "State rules", "value": st},
                                   {"id": "excluded", "label": "Not activity space", "value": ", ".join(sorted(EXCLUDED)[:10]) + ", ..."},
                                   {"id": "fence", "label": "Play-yard fence and shade not checked", "value": True},
                                   {"id": "licence", "label": "Zoning, fire marshal and staffing ratios not checked", "value": True}])
