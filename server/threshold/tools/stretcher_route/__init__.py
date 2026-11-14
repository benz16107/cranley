"""Stretcher route: can paramedics carry a flat stretcher from the entrance to each bedroom? The furniture_fit
engine with the IBC 3002.4 stretcher, kept flat."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry._plan import VERDICT_STATUS
from .. import Assumption, Metric, ScanScope, ToolResult, Verdict, field, tool, Check
from .._access import GEO, STD, label, quality
from ..furniture_fit import carry_audit, pick_target


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    length_m: float = field(2.134, pref="stretcher.length_m", unit="m", gt=1, le=3, description="Stretcher length")
    width_m: float = field(0.61, pref="stretcher.width_m", unit="m", gt=0.3, le=1.2, description="Stretcher width")
    height_m: float = field(0.5, pref="stretcher.height_m", unit="m", gt=0.1, le=1.5,
                            description="Height with the patient on it, lowered")
    rooms: list[str] = field(["Bedroom"], description="Room types or ids to reach")


@tool(id="stretcher_route", title="Stretcher route", icon="ambulance",
      summary="Checks whether a flat ambulance stretcher can be carried from the entrance to each bedroom, and where "
              "it would have to be tilted.",
      model_description="Carry a flat ambulance stretcher (IBC 3002.4 size, 24 x 84 in, editable) from the main "
                        "entrance to each bedroom (or named rooms) in one scan: the route, each door and turn with "
                        "its margin, and a box at the tightest point per room.",
      personas=["fire_captain", "older_adult_family"], requires=[{"layer": "matterport.walls"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["route", "box"], examples=["Could paramedics get a stretcher to the bedroom?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    box = (inputs.length_m, inputs.width_m, inputs.height_m)
    assumptions = [Assumption(id="stretcher.length_m", label="Stretcher length", value=box[0], unit="m", editable=True),
                   Assumption(id="stretcher.width_m", label="Stretcher width", value=box[1], unit="m", editable=True),
                   Assumption(id="stretcher.height_m", label="Height, lowered with patient", value=box[2], unit="m",
                              editable=True),
                   Assumption(id="size_from", label=STD["stretcher"], value=True),
                   Assumption(id="flat", label="Kept flat the whole way", value=True)]
    scope = ScanScope(sid=sid)
    if not quality(plan).get("walls"):
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "This scan has no wall graph, so doors and turns cannot be measured.")))
    targets = [r for r in plan["rooms"] if r["id"] in inputs.rooms or r.get("label") in inputs.rooms]
    if not targets:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "None of the rooms asked for is in this scan.")))
    checks, findings, overlays, per = [], [], [], []
    for i, t in enumerate(targets):
        name = f"{label(t)} {i + 1}" if len(targets) > 1 else label(t)
        a = carry_audit(ctx, plan, "stretcher_route", box, True, t, None, "Stretcher", name)
        per.append((name, a))
        checks += a["checks"] or [Check(id=f"{t['id']}.route", rule=f"Stretcher to {name}: {a['reason']}",
                                        measured=None, threshold=0, unit="m", status=VERDICT_STATUS[a["result"]])]
        findings += a["findings"]
        overlays += a["overlays"]
    ctx.step(f"Carried a {box[0]:.2f} x {box[1]:.2f} m flat stretcher to {len(targets)} rooms")
    ok = [n for n, a in per if a["result"] == "likely pass"]
    bad = [n for n, a in per if a["result"] == "likely fail"]
    status = "pass" if len(ok) == len(per) else "fail" if bad else "warn"
    text = ("A flat stretcher reaches every room checked." if status == "pass" else
            f"A flat stretcher does not reach: {', '.join(bad).lower()}; it would have to be tilted or a chair used."
            if bad else "Some routes are too close to call or not in the scan; measure on site.")
    tight = [a["tight"]["slack"] for _, a in per if a["tight"] and a["tight"]["slack"] != float("-inf")]
    return ToolResult(scope=scope, verdict=Verdict(status=status, text=text), checks=checks, findings=findings,
                      overlays=overlays, assumptions=assumptions,
                      metrics=[Metric(id="reached", label="Rooms reached flat", value=len(ok), unit="", source=GEO),
                               Metric(id="rooms", label="Rooms checked", value=len(per), unit="", source=GEO),
                               Metric(id="tightest", label="Least room to spare", value=round(min(tight), 2)
                                      if tight else None, unit="m", source=GEO)])
