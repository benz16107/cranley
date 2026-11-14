"""Storage space: closet, pantry and storage-room area of a unit or suite, its share of the floor, and bedrooms with
no closet room beside them."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry._plan import indoor_rooms
from .. import (
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    RoomAnchor,
    RuleOverlay,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..room_labeller import ensure_labels, facts
from ..types import SelectRooms

FT2 = facts.M2_TO_FT2
AREA = Source(layer="matterport", method="geometry", confidence="high", note="Room floor areas from the scan")
LABEL = Source(layer="matterport", method="lookup", confidence="medium", note="Room types: Matterport's, the labeller's or yours")
STORAGE = {"Closet", "Pantry", "storage"}
BEDROOM = {"Bedroom"}


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    label_with_vision: bool = field(True, description="Label unlabelled rooms from the panoramas first (slow once)")


def storage(plan: dict) -> dict:
    """Storage rooms, their area, the floor they share, and bedrooms with no closet room through a door."""
    rooms = facts.live_rooms(plan)
    store = [r for r in rooms if r.get("label") in STORAGE and r.get("area")]
    total = sum(r["area"] for r in indoor_rooms(plan) if r.get("area"))
    s = sum(r["area"] for r in store)
    ids = {r["id"] for r in store}
    linked: dict[str, set[str]] = {}
    for o in plan.get("openings") or []:
        rs = o.get("rooms") or []
        if o["type"] != "window" and len(rs) == 2:
            linked.setdefault(rs[0], set()).add(rs[1])
            linked.setdefault(rs[1], set()).add(rs[0])
    beds = [r for r in rooms if r.get("label") in BEDROOM]
    baths = {r["id"] for r in rooms if r.get("label") == "Bathroom"}

    def reach(rid: str) -> set[str]:  # next door, or through an en-suite bathroom (walk-in closets often open off it)
        near = linked.get(rid, set())
        return near | {x for b in near & baths for x in linked.get(b, set())}

    bare = [r for r in beds if not (reach(r["id"]) & ids)] if plan.get("openings") else []
    return {"rooms": store, "area": s, "floor": total, "share": s / total if total else None, "bedrooms": beds,
            "bedrooms_without": bare, "unlabelled": [r for r in rooms if not r.get("label")]}


@tool(id="storage_space", title="Storage space", icon="archive",
      summary="Totals closet and storage area and its share of the unit, and finds bedrooms without a closet room.",
      model_description="Closet, pantry and storage-room area of one scan, its share of the floor area, each storage room "
                        "on the plan, and bedrooms with no closet room through a door. Reach-in closets that the scan "
                        "does not cut out as rooms are not counted.",
      personas=["renter_listing", "apartment_manager", "office_tenant"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.room_labels", "need": "optional", "fallback": "room labeller"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "MiniChart", "FloorPlanMini", "StepLog"], overlays=["lens", "rule"],
      examples=["How much closet space does this unit have?", "Which bedrooms have no closet?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ensure_labels(ctx, sid, inputs.label_with_vision)
    st = storage(plan)
    q = facts.quality(plan)
    ctx.step(f"Found {len(st['rooms'])} storage rooms among {len(facts.live_rooms(plan))}")
    if not st["floor"]:
        return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status="unknown", text="This scan has no room areas."))
    metrics = [Metric(id="storage_area", label="Storage area", value=round(st["area"] * FT2), unit="ft²", source=AREA),
               Metric(id="storage_share", label="Share of the floor", value=round(100 * st["share"], 1), unit="%", source=AREA),
               Metric(id="storage_rooms", label="Closets and storage rooms", value=len(st["rooms"]), unit="", source=LABEL),
               Metric(id="floor_area", label="Floor area", value=round(st["floor"] * FT2), unit="ft²", source=AREA)]
    metrics += [Metric(id=f"area.{r['id']}", label=f"{r['label']} {i + 1}", value=round(r["area"] * FT2), unit="ft²", source=AREA)
                for i, r in enumerate(sorted(st["rooms"], key=lambda r: -r["area"]))]
    checks, findings = [], []
    if st["bedrooms"] and plan.get("openings"):
        bad = st["bedrooms_without"]
        checks.append(Check(id="bedroom_closets", rule="Bedrooms with a mapped door to a closet room (directly or through an en-suite bathroom)",
                            measured=len(st["bedrooms"]) - len(bad), threshold=len(st["bedrooms"]), unit="bedrooms",
                            status="pass" if not bad else "warn", findings=[f"storage_space:{sid}:{r['id']}" for r in bad]))
        findings += [Finding(id=f"storage_space:{sid}:{r['id']}", title="Bedroom without a closet room", status="warn",
                             detail=f"No closet room opens off this {r['area'] * FT2:,.0f} ft² bedroom or its bathroom. It may have a reach-in "
                                    "closet the scan did not cut out as a room; check the panorama.",
                             anchor=RoomAnchor(sid=sid, room=r["id"]), source=LABEL) for r in bad]
    overlays = []
    if st["rooms"]:
        vals = {r["id"]: round(r["area"] * FT2) for r in st["rooms"]}
        overlays += [LensOverlay(values=vals, ramp="sequential", legend=Legend(title="Storage room area", unit="ft²", min=0,
                                                                             max=max(vals.values()))),
                     RuleOverlay(select=SelectRooms(rooms=list(vals)), style="highlight")]
    n = len(st["rooms"])
    text = (f"{st['area'] * FT2:,.0f} ft² of closets and storage in {n} room{'' if n == 1 else 's'}, "
            f"{100 * st['share']:.1f}% of {st['floor'] * FT2:,.0f} ft².")
    if st["bedrooms_without"]:
        text += (f" {len(st['bedrooms_without'])} of {len(st['bedrooms'])} bedrooms have no mapped door to a closet room "
                 "(the wall graph can miss a door, so check the panorama).")
    text += " Reach-in closets that the scan does not cut out as rooms are not counted."
    if st["unlabelled"]:
        text += f" {len(st['unlabelled'])} room{'s have' if len(st['unlabelled']) > 1 else ' has'} no label."
    if not q["walls"]:
        text += " No wall graph: closets are found by label only, and which bedroom a closet serves is unknown."
    status = "warn" if st["bedrooms_without"] or st["unlabelled"] else "pass"
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays)
