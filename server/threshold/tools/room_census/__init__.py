"""Reference tool: rooms by type with their areas, and a lens that tints each room by area."""
from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from ...geometry._plan import indoor_rooms
from .. import (
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    RoomAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

AREA = Source(layer="matterport", method="geometry", confidence="high", note="Matterport room floor area")
LABEL = Source(layer="matterport", method="lookup", confidence="medium", note="Matterport room classification")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")


@tool(id="room_census", title="Room census", icon="layout-grid",
      summary="Which rooms this space has, how big each kind is, and which rooms have no type.",
      model_description="Count rooms by type with floor areas for one scan, from the wall graph. Cheap; run it first "
                        "on any building to learn its layout. Returns one metric per room type and an area lens.",
      personas=["renter_listing", "apartment_manager", "office_tenant", "costar_researcher", "wheelchair_user"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.room_labels", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "FloorPlanMini", "StepLog"], overlays=["lens"],
      examples=["What rooms does this unit have?", "How big are the bedrooms?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    rooms = indoor_rooms(plan)  # no Void ("not floor"), no wall-less yard or unscanned capture
    open_air = sum(r.get("label") != "Void" for r in plan["rooms"]) - len(rooms)
    ctx.step(f"Read {len(rooms)} rooms from the wall graph" + (f"; left out {open_air} areas with no walls (outdoor or unscanned)" if open_air else ""))
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in rooms:
        by_type[r.get("label") or "Unlabelled"].append(r)
    total = sum(r.get("area") or 0 for r in rooms)
    labelled = sum(len(v) for k, v in by_type.items() if k != "Unlabelled")
    share = labelled / len(rooms) if rooms else 0.0
    ctx.step(f"Grouped them into {len(by_type)} types")

    metrics = [Metric(id="rooms", label="Rooms", value=len(rooms), unit="", source=AREA),
               Metric(id="area_total", label="Floor area", value=round(total, 1), unit="m²", source=AREA),
               Metric(id="labelled_share", label="Rooms with a type", value=round(share * 100), unit="%", source=LABEL)]
    for kind, rs in sorted(by_type.items(), key=lambda kv: -sum(r.get("area") or 0 for r in kv[1])):
        metrics.append(Metric(id=f"area.{kind}", label=f"{kind} ({len(rs)})",
                              value=round(sum(r.get("area") or 0 for r in rs), 1), unit="m²", source=AREA))

    status = "pass" if share >= 0.5 else "warn"
    check = Check(id="labelled", rule="At least half the rooms have a type", measured=round(share * 100),
                  threshold=50, unit="%", status=status, findings=["room_census:unlabelled"] if status == "warn" else [])
    findings = [Finding(id="room_census:unlabelled", title="Most rooms have no type", status="warn",
                        detail=f"{len(rooms) - labelled} of {len(rooms)} rooms are unlabelled, so tools that look "
                               "for a kind of room (kitchen, bathroom) will miss them. Correct a label to teach me.",
                        anchor=RoomAnchor(sid=inputs.scan, room=by_type["Unlabelled"][0]["id"]), source=LABEL)
                ] if status == "warn" and by_type.get("Unlabelled") else []
    areas = {r["id"]: round(r["area"], 2) for r in rooms if r.get("area")}
    lens = LensOverlay(values=areas, ramp="sequential",
                       legend=Legend(title="Room area", unit="m²", min=min(areas.values(), default=0),
                                     max=max(areas.values(), default=0)))
    kinds = ", ".join(k for k in by_type if k != "Unlabelled") or "no labelled rooms"
    return ToolResult(scope=ScanScope(sid=inputs.scan), metrics=metrics, checks=[check], findings=findings,
                      overlays=[lens], verdict=Verdict(status=status,
                                                       text=f"{len(rooms)} rooms, {total:.0f} m²: {kinds}."
                                                       + (f" {open_air} area{'s' if open_air > 1 else ''} with no walls (outdoor or unscanned) {'are' if open_air > 1 else 'is'} left out." if open_air else "")))
