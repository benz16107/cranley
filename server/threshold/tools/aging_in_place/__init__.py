"""Aging in place: the CDC STEADI 'Check for Safety' items the scan can answer, level by level, from the
aging_in_place rule pack (geometry), the stairs summary, and the bathroom panoramas. Items about belongings
(rugs, cords, shelves) or things the scan cannot see (handrails, lights, slippery floors) are listed as such."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry import evaluate_pack
from .. import (Action, Assumption, Check, Finding, Metric, Pin, PinsOverlay, RoomAnchor, ScanScope, Source, ToolResult,
                Verdict, field, tool)
from ..types import Media
from .._access import GEO, STD, floor_name, quality, rooms
from .._access import look
from ..stairs_count import levels

# STEADI 2017 questions the scan cannot answer, and why
NOT_FROM_SCAN = [
    ("rugs", "Floors: 'Do you have throw rugs on the floor?'", "belongings change after the scan"),
    ("cords", "Floors: 'Do you have to walk over or around wires or cords?'", "belongings change after the scan"),
    ("stair_light", "Stairs: 'Is there a light and light switch at the top and bottom of the stairs?'",
     "switches are not in the scan; look on site"),
    ("handrails", "Stairs: handrails on both sides, as long as the stairs", "handrails are not in the scan"),
    ("shelves", "Kitchen: 'Are the things you use often on high shelves?'", "belongings"),
    ("tub_floor", "Bathrooms: 'Is the tub or shower floor slippery?'", "surface grip cannot be seen"),
    ("bed_light", "Bedrooms: 'Is the light near the bed hard to reach?'", "lamps and switches are not in the scan"),
]


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    read_panoramas: bool = field(True, description="Look at the bathroom panoramas for grab bars and the tub or shower")


def _floor_of_anchor(plan, a: dict) -> str | None:
    rs = rooms(plan)
    if a.get("room") in rs:
        return rs[a["room"]]["floor"]
    if a.get("opening"):
        return next((o["floor"] for o in plan.get("openings") or [] if o["id"] == a["opening"]), None)
    return None


@tool(id="aging_in_place", title="Aging in place", icon="home-heart",
      summary="Goes through the CDC home fall-prevention checklist for the parts the scan can answer, floor by floor: "
              "clear paths, steps, stairs, the night path from bed to bathroom, and grab bars.",
      model_description="CDC STEADI 'Check for Safety' items answerable from one scan, level by level: clear path "
                        "widths from the entrance, the bedroom-to-bathroom route, doorway steps, stairs between "
                        "floors, bed and bath on the entrance floor (AARP HomeFit), and grab bars and tub or shower "
                        "type seen in bathroom panoramas. Lists the checklist items the scan cannot answer.",
      personas=["older_adult_family"], requires=[{"layer": "matterport.walls"}, {"layer": "matterport.room_labels"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "StepLog", "ActionBar"],
      overlays=["pins"], annotations={"cost": "slow"},
      examples=["Is this home safe for my mother to age in?", "Where could someone trip in this house?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    pack = evaluate_pack(plan, "aging_in_place")
    ctx.step(f"Evaluated the {pack['title']} rule pack: {len(pack['checks'])} checks")
    lv = levels(plan, 0.178)
    names = {f["floor"]: f["name"] for f in lv["levels"]}
    checks, findings = [], []
    labelled = quality(plan).get("labels")
    for c in pack["checks"]:
        fids = []
        if not labelled and c["id"].endswith("entry_floor_living"):
            checks.append(Check(id="steadi.entry_floor_living", rule=c["rule"] + " Not answerable: the scan has no "
                                "room labels.", measured=None, threshold=c["threshold"], unit=c["unit"],
                                status="unknown", standard=c["standard"]))
            continue
        for f in (x for x in pack["findings"] if x["id"] in c["findings"]):
            fl = _floor_of_anchor(plan, f["anchor"])
            fid = f"aging_in_place:{sid}:{f['id']}"
            fids.append(fid)
            anchor = f["anchor"] if len(f["anchor"]) > 1 else None  # whole-home items have no place
            findings.append(Finding(id=fid, title=(f"{names[fl].capitalize()}: " if fl in names else "") +
                                    f["title"].split(":")[0], status=f["status"], detail=f["detail"],
                                    anchor=anchor, source=Source(**f["source"])))
        checks.append(Check(id=f"steadi.{c['id'].split('.')[-1]}", rule=c["rule"], measured=c["measured"],
                            threshold=c["threshold"], unit=c["unit"], status=c["status"], standard=c["standard"],
                            findings=fids))
    for f in lv["levels"]:
        if not f["entry"]:
            checks.append(Check(id=f"level.{f['floor']}", rule=(
                f"{f['name'].capitalize()}: reached by stairs, about {f['steps']} steps; {f['bedrooms']} bedrooms, "
                f"{f['bathrooms']} bathrooms. Handrails and stair lights need a look on site."),
                measured=f["steps"], threshold=0, unit="steps", status="warn", standard=STD["steadi"] + ", Stairs"))
    if inputs.read_panoramas and quality(plan).get("labels"):
        baths = [r for r in plan["rooms"] if r.get("label") == "Bathroom"]
        for i, b in enumerate(baths):
            fx = look.bath_fixtures(plan, b)
            if "error" in fx:
                continue
            fl = names.get(b["floor"], "floor ?") + (f" bathroom {i + 1}" if len(baths) > 1 else " bathroom")
            fid = f"aging_in_place:{sid}:support:{b['id']}"
            ok = fx["grab_bars"] == "at both"
            findings.append(Finding(id=fid, title=f"{fl.capitalize()}: grab bars {fx['grab_bars']}",
                                    status="pass" if ok else "warn", anchor=RoomAnchor(sid=sid, room=b["id"]),
                                    detail=f"{fx['reason']} Bathing: {fx['bathing']}. STEADI: grab bars next to and "
                                           "inside the tub, and next to the toilet.",
                                    media=[Media(**m) for m in fx["media"]],
                                    source=Source(layer="model", method="vision", confidence=fx["confidence"],
                                                  note=f"Vision model on panorama {fx['pano']}")))
            checks.append(Check(id=f"support.{b['id']}", rule=f"{fl.capitalize()}: support getting in and out "
                                f"of the tub and up from the toilet (grab bars seen: {fx['grab_bars']})",
                                measured=None, threshold=None, unit="", status="pass" if ok else "warn",
                                standard=STD["steadi"] + ", Bathrooms", findings=[fid]))
    for cid, q, why in NOT_FROM_SCAN:
        checks.append(Check(id=f"not_scan.{cid}", rule=f"{q} Not answerable: {why}.", measured=None, threshold=None,
                            unit="", status="unknown", standard=STD["steadi"]))
    hazards = [f for f in findings if f.status in ("fail", "warn")]
    st = [c.status for c in checks if not c.id.startswith("not_scan")]
    status = "fail" if "fail" in st else "warn" if "warn" in st else "unknown" if all(s == "unknown" for s in st) \
        else "pass"
    text = {"fail": f"{len(hazards)} places to fix or check, at least one clear hazard.",
            "warn": f"{len(hazards)} places to check on site; nothing clearly fails.",
            "pass": "Every checklist item the scan can answer looks fine.",
            "unknown": "This scan cannot answer the checklist (no wall graph or room labels)."}[status]
    ctx.step(text)
    return ToolResult(
        scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), checks=checks, findings=findings,
        overlays=[PinsOverlay(pins=[Pin(id=f.id, anchor=f.anchor, label=f.title, status=f.status)
                                    for f in hazards if f.anchor])] if any(f.anchor for f in hazards) else [],
        assumptions=[Assumption(id="empty", label="Rooms are empty: furniture and rugs are not in the scan", value=True)],
        metrics=[Metric(id="hazards", label="Places to fix or check", value=len(hazards), unit="", source=GEO),
                 Metric(id="floors", label="Floors", value=len(lv["levels"]), unit="", source=GEO),
                 Metric(id="answerable", label="Checklist items the scan answers",
                        value=sum(1 for c in checks if c.status != "unknown"), unit="", source=GEO)],
        actions=[Action(id="stairs", label="Count the stairs", tool="stairs_count", inputs={"scan": sid}),
                 Action(id="bath", label="Check the bathrooms in detail", tool="bathroom_clearance", inputs={"scan": sid})])

