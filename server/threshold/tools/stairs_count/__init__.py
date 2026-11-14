"""Stairs: floors, how far each is above the entrance, an estimate of the steps between, where the bedrooms and
bathrooms are, and steps at doorways, level by level. The scan does not contain the stairs themselves: floors are
not linked in the plan, so a step count is the height difference over an assumed riser, labelled as an estimate."""
from __future__ import annotations

from pydantic import BaseModel

from .. import (Assumption, Check, Finding, Metric, OpeningAnchor, Pin, PinsOverlay, RoomAnchor, ScanScope, Source,
                ToolResult, Verdict, field, tool)
from ..types import Media, PanoAnchor, PointAnchor
from .._access import (GEO, GEO_LOW, STD, elevations, floor_name, fmt, links_of, pick_entrance, quality, sill_step,
                       step_kind)
from .._access import look


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    riser_m: float = field(0.178, pref="access.riser_m", unit="m", gt=0.1, le=0.25,
                           description="Riser height used to estimate a step count")
    read_panoramas: bool = field(True, description="Look for stairs in the staircase and entrance panoramas")


def levels(plan: dict, riser: float) -> dict:
    """Per floor: elevation, rise from the entrance floor, estimated steps, rooms by type, doorway steps."""
    el = elevations(plan)
    ent = pick_entrance(plan)
    floors = sorted(plan.get("floors") or [], key=lambda f: (el.get(f["id"]) or 0.0, f.get("sequence") or 0))
    entry = ent["floor"] if ent else (floors[0]["id"] if floors else None)
    steps = {}
    for oid, link in links_of(plan).items():
        s = sill_step(plan, link)
        if step_kind(s) != "none":
            steps.setdefault(link["floor"], []).append((oid, s, step_kind(s)))
    out = []
    for f in floors:
        rs = [r for r in plan["rooms"] if r["floor"] == f["id"] and r.get("label") != "Void"]
        count = lambda lab: sum(1 for r in rs if r.get("label") == lab)
        rise = (el.get(f["id"]) or 0.0) - (el.get(entry) or 0.0) if entry else None
        out.append({"floor": f["id"], "name": floor_name(plan, f["id"]), "elevation": el.get(f["id"]), "rise": rise,
                    "steps": round(abs(rise) / riser) if rise is not None else None, "entry": f["id"] == entry,
                    "bedrooms": count("Bedroom"), "bathrooms": count("Bathroom"), "rooms": len(rs),
                    "staircases": [r["id"] for r in rs if r.get("label") == "Staircase"],
                    "door_steps": steps.get(f["id"], [])})
    return {"entrance": ent, "entry_floor": entry, "levels": out}


@tool(id="stairs_count", title="Stairs", icon="stairs",
      summary="Counts the floors, estimates the steps between the entrance and the bedrooms, and finds steps at "
              "doorways, floor by floor.",
      model_description="Stairs and level changes in one scan, level by level: each floor's height above the "
                        "entrance floor, an estimated step count (height over an editable riser), bedrooms and "
                        "bathrooms per floor, staircase rooms, doorway sill steps, and stairs seen in panoramas.",
      personas=["older_adult_family", "wheelchair_user"], requires=[{"layer": "matterport.rooms"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "MiniChart", "AssumptionChips", "StepLog"],
      overlays=["pins"], examples=["How many stairs are there to the bedrooms?", "Is everything on one floor?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    lv = levels(plan, inputs.riser_m)
    L = lv["levels"]
    ctx.step(f"{len(L)} floors; entrance on {floor_name(plan, lv['entry_floor']) if lv['entry_floor'] else 'none'}")
    est = Source(layer="matterport", method="geometry", confidence="low",
                 note="Floor heights from the panorama heights; step count is the rise over the assumed riser")
    checks, findings = [], []
    for f in L:
        fids = []
        if not f["entry"] and f["rise"] is not None:
            fid = f"stairs_count:{sid}:{f['floor']}"
            fids.append(fid)
            findings.append(Finding(
                id=fid, title=f"Stairs to {f['name']}", status="warn", source=est,
                anchor=RoomAnchor(sid=sid, room=f["staircases"][0]) if f["staircases"] else None,
                detail=f"{fmt(abs(f['rise']))} {'up' if f['rise'] > 0 else 'down'} from the entrance floor, about "
                       f"{f['steps']} steps at {inputs.riser_m * 100:.1f} cm each. {f['bedrooms']} bedrooms and "
                       f"{f['bathrooms']} bathrooms there. Check handrails on both sides and a light switch at the "
                       f"top and bottom on site ({STD['steadi']})."))
        for oid, s, kind in f["door_steps"]:
            fid = f"stairs_count:{sid}:step:{oid}"
            fids.append(fid)
            findings.append(Finding(id=fid, title="Step at a doorway" if kind == "step" else "Stairs at a doorway",
                                    status="fail" if kind == "step" else "warn", source=GEO_LOW,
                                    anchor=OpeningAnchor(sid=sid, opening=oid),
                                    detail=f"Sill {s * 100:.0f} cm off this floor's level. {STD['level']}."))
        st = "pass" if f["entry"] and not f["door_steps"] else "fail" if any(k == "step" for _, _, k in f["door_steps"]) \
            else "warn"
        checks.append(Check(id=f"level.{f['floor']}", rule=(
            f"{f['name'].capitalize()}: " + ("entrance floor" if f["entry"] else
                                             f"about {f['steps']} steps from the entrance floor")
            + f", {f['bedrooms']} bedrooms, {f['bathrooms']} bathrooms, {len(f['door_steps'])} doorway steps"),
            measured=f["steps"], threshold=0, unit="steps", status=st, standard=STD["level"], findings=fids))
    if inputs.read_panoramas:
        rooms = [r for r in plan["rooms"] if r.get("label") in ("Staircase", "Entrance")]
        panos = [p["id"] for r in rooms for p in [look.central_pano(plan, r)] if p][:4]
        if panos:
            ctx.step(f"Reading {len(panos)} staircase and entrance panoramas")
        found, _err = look.objects(plan, panos)
        for o in found:
            if o["label"] not in ("stairs", "step or threshold", "ramp"):
                continue
            fd = o["finding"]
            a = fd["anchor"]
            findings.append(Finding(id=f"stairs_count:{sid}:seen:{fd['id']}", title=f"Panorama shows {o['label']}",
                                    status="warn", detail=f"{fd['detail']}. Seen, not measured.",
                                    anchor=PointAnchor(**a) if "point" in a else PanoAnchor(**a),
                                    media=[Media(**m) for m in fd["media"]], source=Source(**fd["source"])))
    entry = next((f for f in L if f["entry"]), None)
    bed_up = entry is not None and entry["bedrooms"] == 0 and any(f["bedrooms"] for f in L)
    bath_up = entry is not None and entry["bathrooms"] == 0 and any(f["bathrooms"] for f in L)
    door_steps = sum(len(f["door_steps"]) for f in L)
    if len(L) <= 1 and not door_steps:
        status, text = "pass", "One floor in the scan and no step found at a doorway."
    elif bed_up or bath_up:
        status, text = "fail", ("Stairs stand between the entrance and every " +
                                " and every ".join(x for x, b in (("bedroom", bed_up), ("bathroom", bath_up)) if b) + ".")
    else:
        status, text = "warn", (f"{len(L)} floors" if len(L) > 1 else "One floor") + \
            (", but a bedroom and a bathroom are on the entrance floor." if len(L) > 1 else "") + \
            (f" {door_steps} doorway steps." if door_steps else "")
    if not quality(plan).get("walls"):
        text += " No wall graph, so doorway steps could not be read and the entrance floor is the lowest."
    worst_steps = max((f["steps"] or 0 for f in L), default=0)
    return ToolResult(
        scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), checks=checks, findings=findings,
        overlays=[PinsOverlay(pins=[Pin(id=f.id, anchor=f.anchor, label=f.title, status=f.status)
                                    for f in findings if f.anchor])] if any(f.anchor for f in findings) else [],
        assumptions=[Assumption(id="access.riser_m", label="Riser height for the step estimate", value=inputs.riser_m,
                                unit="m", editable=True),
                     Assumption(id="no_stairs_in_plan", label="The plan has no stairs; floors are not linked",
                                value=True)],
        metrics=[Metric(id="floors", label="Floors", value=len(L), unit="", source=GEO),
                 Metric(id="steps_max", label="Most steps from the entrance floor (estimate)", value=worst_steps,
                        unit="steps", source=est),
                 Metric(id="door_steps", label="Steps at doorways", value=door_steps, unit="", source=GEO_LOW),
                 Metric(id="entry_bedrooms", label="Bedrooms on the entrance floor",
                        value=entry["bedrooms"] if entry else None, unit="", source=GEO)]
        + [Metric(id=f"rise.{f['floor']}", label=f["name"], value=round(f["rise"], 2) if f["rise"] is not None else None,
                  unit="m", source=est) for f in L])
