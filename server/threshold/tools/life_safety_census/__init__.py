"""Life-safety census: every sleeping room checked for a smoke alarm seen in its panorama, with the photo as evidence.
Results are leads to check on site: "not seen" is never "absent"."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry import room_graph
from ...geometry.graph import neighbours
from .. import (
    Assumption,
    Check,
    Finding,
    Metric,
    Pin,
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
from ..fire_preplan.common import (
    BEDROOM,
    HALL_LABELS,
    VisionBudget,
    central_pano,
    ceiling_quality,
    floor_label,
    labels_ok,
    live_rooms,
    name,
    objects,
    scope_sids,
    walls_ok,
)
from ..types import Media, ScansScope, SelectRooms

SEEN = Source(layer="model", method="vision", confidence="medium",
              note="Vision model on the room's central panorama, all six faces (face 0 is the ceiling)")
NOT_SEEN = Source(layer="model", method="vision", confidence="low",
                  note="Nothing found in one panorama: an alarm on a wall, behind a fan or outside the photo is missed")
LAW = {
    "TX": [("Tex. Prop. Code §92.255(a)", "a smoke alarm in each separate bedroom; in a corridor serving several "
            "bedrooms, near them; and on each level of a multi-level unit (landlord's duty)")],
    "CA": [("Cal. Health & Safety Code §13113.7", "an approved smoke alarm in every dwelling unit, installed to "
            "current building standards in rentals"),
           ("California Residential Code R314.3 (2022)", "in each sleeping room, outside each sleeping area near the "
            "bedrooms, and on each story; the 2025 code may renumber this section")],
}
STATUS = {"seen": "pass", "not seen": "warn", "could not see": "unknown"}


class Inputs(BaseModel):
    scan: str | None = field(None, source="selection.scan", description="Scan id")
    whole_property: bool = field(False, description="Check every scan of the selected scan's CoStar property")
    property_id: int | None = field(None, description="CoStar property id; checks all its scans")
    read_panoramas: bool = field(True, description="Send unread panoramas to the vision model")
    max_scans_read: int = field(3, ge=0, le=12, description="At most this many unread scans go to the vision model "
                                                              "in one run; scans read before are free")


def state_of(plan: dict) -> str | None:
    text = f"{plan.get('address') or ''} {plan.get('city') or ''}"
    if ", TX" in text or "Houston" in text or "Texas" in text:
        return "TX"
    if ", CA" in text or "Los Angeles" in text or "California" in text:
        return "CA"
    return None


def look(plan: dict, room: dict, found: list[dict] | None) -> dict:
    """seen / not seen / could not see for one room, with the evidence."""
    sid = plan["sid"]
    pano = central_pano(plan, room)
    if pano is None:
        return {"result": "could not see", "why": "no panorama stands in this room", "media": [], "alarms": []}
    ceiling = [Media(kind="pano", ref=f"{sid}/{pano['id']}/0")]
    if found is None:
        return {"result": "could not see", "why": "its panorama was not read in this run (vision budget)",
                "media": ceiling, "alarms": []}
    here = [d for d in found if d["label"] == "smoke alarm" and d.get("in_room") == room["id"]]
    # only high confidence counts as seen: by eye, 18 of 18 high calls were alarms and 8 of 15 medium (2026-11-14)
    alarms = [d for d in here if d["finding"]["source"]["confidence"] == "high"]
    if here and not alarms:
        return {"result": "could not see", "why": "possible alarm, not clear enough to call: " +
                "; ".join(d["finding"]["detail"] for d in here), "alarms": [],
                "media": [Media(**m) for d in here for m in d["finding"]["media"]]}
    if alarms:
        media = [Media(**m) for d in alarms for m in d["finding"]["media"]]
        return {"result": "seen", "why": f"{len(alarms)} seen: " + "; ".join(d["finding"]["detail"] for d in alarms),
                "media": media, "alarms": alarms}
    ok, why = ceiling_quality(sid, pano["id"])
    if not ok:
        return {"result": "could not see", "why": why, "media": ceiling, "alarms": []}
    return {"result": "not seen", "why": "the ceiling photo is readable and no alarm was found in the room's "
                                         "panorama", "media": ceiling, "alarms": []}


def census(plan: dict, found: list[dict] | None) -> dict:
    """Bedrooms, the hallways that serve two or more of them, and each level, each with a look()."""
    rooms = {r["id"]: r for r in live_rooms(plan)}
    beds = [r for r in rooms.values() if r.get("label") == BEDROOM]
    out = {"bedrooms": [(r, look(plan, r, found)) for r in beds], "halls": [], "levels": []}
    if walls_ok(plan) and len(beds) >= 2:
        adj = neighbours(room_graph(plan))
        for r in rooms.values():
            if r.get("label") in HALL_LABELS and sum(n in {b["id"] for b in beds} for n, _ in adj.get(r["id"], [])) >= 2:
                out["halls"].append((r, look(plan, r, found)))
    floors = sorted({r["floor"] for r in rooms.values()})
    for f in floors:
        on = [r for r in rooms.values() if r["floor"] == f]
        seen = [d for d in found or [] if d["label"] == "smoke alarm" and rooms.get(d.get("in_room") or "", {}).get("floor") == f]
        res = "seen" if seen else "could not see" if found is None else "not seen"
        out["levels"].append((f, on, res, seen))
    return out


@tool(id="life_safety_census", title="Smoke alarm census", icon="bell",
      summary="Checks every bedroom's ceiling photo for a smoke alarm and lists where none was seen, as leads to check.",
      model_description="For one scan or every scan of a property: each bedroom (and each hallway serving two or more "
                        "bedrooms, and each level) read for a smoke alarm in its panorama. Each is 'seen' with the "
                        "photo crop, 'not seen' (a lead, not a violation) or 'could not see'. Cites Texas Property "
                        "Code 92.255 or California law by the scan's city.",
      personas=["fire_captain", "apartment_manager", "renter_listing"],
      requires=[{"layer": "matterport.panoramas"}, {"layer": "matterport.room_labels"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "StepLog", "Note"],
      overlays=["rule", "pins"], annotations={"cost": "slow"},
      examples=["Do the bedrooms in this complex have smoke alarms?", "Which units should the install crew visit?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sids, pid = scope_sids(inputs.scan, inputs.whole_property, inputs.property_id)
    budget = VisionBudget(inputs.max_scans_read if inputs.read_panoramas else 0)
    multi = len(sids) > 1
    checks, findings, overlays = [], [], []
    tally = {"seen": 0, "not seen": 0, "could not see": 0}
    states, no_labels, plans = set(), [], []
    for sid in sids:
        try:
            plan = ctx.plan(sid)
        except Exception as e:  # noqa: BLE001  one bad scan in a property should not sink the census
            ctx.step(f"Skipped {sid}: {e}")
            continue
        plans.append(plan)
        states.add(state_of(plan))
        beds = [r for r in live_rooms(plan) if r.get("label") == BEDROOM]
        if not labels_ok(plan):
            no_labels.append(plan)
            continue
        if not beds:
            continue
        found = objects(plan, budget)
        c = census(plan, found)
        where = f"{(plan.get('name') or sid)[:40]}: " if multi else ""
        ctx.step(f"{where}{len(beds)} bedrooms, panoramas {'read' if found is not None else 'not read'}")
        pins, by_res = [], {"seen": [], "not seen": [], "could not see": []}
        for kind, items in (("Bedroom", c["bedrooms"]), ("Hallway serving bedrooms", c["halls"])):
            for r, lk in items:
                tally[lk["result"]] += kind == "Bedroom"
                by_res[lk["result"]].append(r["id"])
                st = STATUS[lk["result"]]
                fid = f"life_safety_census:{sid}:{r['id']}"
                title = f"{kind}, smoke alarm {lk['result']}"
                anchor = RoomAnchor(sid=sid, room=r["id"])
                findings.append(Finding(
                    id=fid, title=title, status=st, anchor=anchor, media=lk["media"],
                    source=SEEN if lk["result"] == "seen" else NOT_SEEN,
                    detail=f"{where}{name(r)} on {floor_label(plan, r['floor'])}: {lk['why']}."
                           + (" A lead to check on site, not a finding of absence." if lk["result"] == "not seen" else "")))
                checks.append(Check(id=f"{sid}:{r['id']}", rule=f"{where}Smoke alarm seen, {kind.lower()}",
                                    measured=len(lk["alarms"]) if lk["result"] != "could not see" else None,
                                    threshold=1, unit="seen", status=st, findings=[fid],
                                    standard="; ".join(c for c, _ in LAW.get(state_of(plan), []))))
                for d in lk["alarms"]:
                    pins.append(Pin(id=f"{sid}:{d['finding']['id']}", anchor=d["finding"]["anchor"],
                                    label="Smoke alarm", status="pass"))
        if len(c["levels"]) > 1:
            for f, on, res, seen in c["levels"]:
                st = STATUS[res]
                fid = f"life_safety_census:{sid}:level:{f}"
                checks.append(Check(id=f"{sid}:level:{f}", rule=f"{where}Smoke alarm seen on {floor_label(plan, f)}",
                                    measured=len(seen) if res != "could not see" else None, threshold=1, unit="seen",
                                    status=st, findings=[fid] if st != "pass" else []))
                if st != "pass":
                    findings.append(Finding(id=fid, title=f"Level, smoke alarm {res}", status=st, anchor=None,
                                            source=NOT_SEEN, detail=f"{where}No alarm was seen anywhere on "
                                            f"{floor_label(plan, f)} ({len(on)} rooms)." if res == "not seen" else
                                            f"{where}{floor_label(plan, f).capitalize()} was not read."))
        if not multi:
            overlays += [RuleOverlay(select=SelectRooms(rooms=ids), style={"seen": "pass", "not seen": "warn",
                                                                           "could not see": "dim"}[res])
                         for res, ids in by_res.items() if ids]
            if pins:
                overlays.append(PinsOverlay(pins=pins))
    for plan in no_labels:
        findings.append(Finding(
            id=f"life_safety_census:{plan['sid']}:no_labels", title="Rooms have no types", status="unknown",
            anchor=None, source=NOT_SEEN,
            detail=f"{(plan.get('name') or plan['sid'])[:40]}: Matterport did not type its rooms, so the bedrooms "
                   "cannot be picked out. Read its panoramas with the fire pre-plan for alarms anywhere in it."))
    ctx.step(f"Sent {len(budget.read)} new scans to the vision model")
    n = sum(tally.values())
    law = [c for st in sorted(s for s in states if s) for c in LAW[st]]
    if n == 0:
        verdict = Verdict(status="unknown", text="No bedrooms with a room type in " +
                          ("these scans." if multi else "this scan.") +
                          (" Rooms are untyped, so sleeping rooms cannot be picked out." if no_labels else ""))
    else:
        status = "warn" if tally["not seen"] else "unknown" if tally["could not see"] == n else "pass" \
            if not tally["could not see"] else "warn"
        verdict = Verdict(status=status, text=(
            f"{n} bedroom{'s' if n != 1 else ''}: a smoke alarm was seen in {tally['seen']}, not seen in {tally['not seen']}, and "
            f"{tally['could not see']} could not be checked. These are leads to check on site, not violations."))
    src = SEEN
    scope = ScansScope(sids=[p["sid"] for p in plans]) if multi else ScanScope(sid=sids[0])
    return ToolResult(
        scope=scope, verdict=verdict,
        metrics=[Metric(id="bedrooms", label="Bedrooms", value=n, unit="", source=src),
                 Metric(id="seen", label="Alarm seen", value=tally["seen"], unit="", source=SEEN),
                 Metric(id="not_seen", label="Not seen", value=tally["not seen"], unit="", source=NOT_SEEN),
                 Metric(id="could_not_see", label="Could not see", value=tally["could not see"], unit="", source=NOT_SEEN)]
        + ([Metric(id="scans", label="Scans", value=len(plans), unit="", source=src)] if multi else []),
        checks=checks, findings=findings, overlays=overlays,
        assumptions=[Assumption(id="law", label="Rule: " + " | ".join(f"{c}: {t}" for c, t in law) if law else
                                "Rule: no state rule matched this address", value=", ".join(c for c, _ in law) or None),
                     Assumption(id="one_pano", label="One panorama per room is read (the one nearest its centre)",
                                value=True),
                     Assumption(id="not_seen_is_lead", label="Not seen means not found in the photo, not absent",
                                value=True)]
        + ([Assumption(id="property_id", label="CoStar property", value=pid)] if pid else []))
