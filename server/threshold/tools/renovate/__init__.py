"""Renovate: what it would take to make a home meet a goal (step-free route to the bathroom, a turning circle in the
bathroom, door widths, or all of it). Proposes edits from the failing checks, or takes yours, tries each alone, saves
the best package as a what-if scan (`w_...`, which every tool runs on), re-runs the goal's tools on it, and prices
each edit from takeoff quantities with unit costs that are labelled assumptions."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ...whatif import AnyEdit, EditError, renovate as engine
from .. import (Action, Assumption, Check, Finding, Metric, OpeningAnchor, RoomAnchor, RuleOverlay, ScanScope,
                SelectOpenings, Source, ToolError, ToolResult, Verdict, field, tool)
from ..types import SelectWalls, WallAnchor

GEO = Source(layer="matterport", method="geometry", confidence="medium",
             note="The goal's tools re-run on the edited wall graph; panoramas are not read (they show the home as it is)")
PRICE = Source(layer="model", method="simulation", confidence="low",
               note="Takeoff quantities times national-average unit costs from cost guides; not a quote")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id (a what-if scan adds to its edits)")
    goal: Literal["wheelchair_ready", "bathroom_route", "bathroom_turn", "door_widths"] = field(
        "wheelchair_ready", ask="What should the home be ready for: a step-free route to the bathroom, a turning "
                                "circle in the bathroom, wide doors, or all of it (wheelchair-ready)?",
        pref="renovate.goal")
    edits: list[AnyEdit] | None = field(None, description="Your own edits instead of the proposed ones: widen_door "
                                        "{opening, width_m}, move_wall {wall, offset_m, grow}, remove_wall {wall}, "
                                        "add_ramp {opening}, grab_bars {room, bars}, door_swing {opening, swing}")
    city: bool = field(False, description="Also ask the facts database, on a throwaway fork, how many homes in the "
                                          "city would pass with one door widened (30 to 90 s)")


def _anchor(sid: str, change: dict):
    if change.get("opening"):
        return OpeningAnchor(sid=sid, opening=change["opening"])
    if change.get("wall"):
        return WallAnchor(sid=sid, wall=change["wall"])
    return RoomAnchor(sid=sid, room=change.get("room") or change["rooms"][0])


TITLE = {"widen_door": "Widen a door", "move_wall": "Move a wall", "remove_wall": "Take out a wall",
         "add_ramp": "Ramp a step", "grab_bars": "Fit grab bars", "door_swing": "Rehang a door"}


@tool(id="renovate", title="What if: renovate", icon="hammer",
      summary="What it would take to make this home wheelchair-ready: the edits, what each one fixes and what it "
              "costs, with the renovated plan to compare side by side.",
      model_description="Renovation what-if for one scan with a wall graph. With only a goal (wheelchair_ready, "
                        "bathroom_route, bathroom_turn, door_widths) it proposes edits from the failing checks "
                        "(widen doors, move or remove a wall, ramp a step, grab bars); or pass `edits`. Re-runs "
                        "door_widths, step_free_route, turning_space and bathroom_clearance on the edited copy, "
                        "saves it as a what-if scan id (in the first metric's source note and the actions) that any "
                        "tool accepts, and returns the checks that flipped, a ranked table of edits by fixes and "
                        "cost, and the unit costs as assumptions. `city` adds a city-wide count on a database fork.",
      personas=["wheelchair_user", "older_adult_family", "apartment_manager", "wheelchair_home_search"],
      requires=[{"layer": "matterport.walls"}, {"layer": "matterport.openings"}],
      blocks=["VerdictHeader", "MetricRow", "RankedTable", "CheckList", "AssumptionChips", "StepLog", "ActionBar"],
      overlays=["rule"],
      table=[{"metric": "fixed", "label": "Checks fixed"}, {"metric": "cost", "label": "Cost"},
             {"metric": "per_1k", "label": "Per $1k"}],
      examples=["What would it take to make this apartment wheelchair-ready?",
                "Widen the bathroom door to 36 inches: what changes?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    try:
        r = engine.run(ctx, inputs.scan, inputs.goal, inputs.edits, city=inputs.city)
    except EditError as e:
        raise ToolError(str(e)) from None
    scope = ScanScope(sid=inputs.scan)
    if not r["available"]:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=r["reason"]))
    b, a = r["before"], r["after"]
    if not r["package"]:
        return ToolResult(scope=scope, verdict=Verdict(
            status="pass" if b["failing"] == 0 else "unknown",
            text="Nothing fails for this goal, so there is nothing to renovate." if b["failing"] == 0 else
                 "No edit found that fixes a failing check; the problems may need a tape measure or are not walls."))
    fixed = [f for f in r["flips"] if f["change"] == "fixed"]
    broke = [f for f in r["flips"] if f["change"] in ("broke", "worse")]
    gone = [f for f in r["flips"] if f["change"] == "gone" and (f["before"] or {}).get("status") == "fail"]
    status = "pass" if a["failing"] == 0 else "warn" if len(fixed) else "fail"
    still = [c.split(":", 1)[0] for c in r["still_failing"]]
    n = len(r["package"])
    text = (f"{n} edit{'s' if n != 1 else ''} fix{'es' if n == 1 else ''} {len(fixed)} of {b['failing']} failing checks"
            + (f"; still failing: {', '.join(still[:3])}" + (f" and {len(still) - 3} more" if len(still) > 3 else "")
               if still else "; nothing the tools check still fails")
            + (f", and {len(broke)} get worse" if broke else "")
            + (f"; {len(gone)} checks no longer apply (a room was merged into another)" if gone else "") + ".")
    sid = r["sid"]
    src_sid = Source(**{**PRICE.model_dump(), "note": f"{PRICE.note}. Renovated plan: {sid}"})
    metrics = [Metric(id="total_cost", label="Estimated cost", value=r["total_cost"], unit="$", source=src_sid),
               Metric(id="fixed", label="Checks fixed", value=len(fixed), unit="", source=GEO),
               Metric(id="failing_before", label="Failing now", value=b["failing"], unit="", source=GEO),
               Metric(id="failing_after", label="Failing after", value=a["failing"], unit="", source=GEO)]
    for i, t in enumerate(c for c in r["candidates"] if not c["error"]):
        name = t["short"] + ("" if t["in_package"] else " (left out)")
        metrics += [Metric(id=f"e{i}/fixed", label=name, value=t["fixed"], unit="", source=GEO),
                    Metric(id=f"e{i}/cost", label=name, value=t["cost"]["total"], unit="$", source=PRICE),
                    Metric(id=f"e{i}/per_1k", label=name, value=t["per_1k"], unit="", source=PRICE)]
    def was(f):
        b, a = f["before"] or {}, f["after"] or {}
        if b.get("measured") is None or a.get("measured") is None:
            return f"{b.get('status', 'none')} to {a.get('status', 'none')}"
        return f"{b['measured']:g} to {a['measured']:g} {f['unit']}".strip()
    checks = [Check(id=f"{f['tool']}:{f['check']}", rule=f"{f['rule']} ({f['change']}: {was(f)})",
                    measured=(f["after"] or {}).get("measured"), threshold=f["threshold"], unit=f["unit"],
                    status=(f["after"] or {}).get("status") or "unknown") for f in r["flips"]]
    findings = [Finding(id=f"renovate:{inputs.scan}:{ln['edit']['op']}:{n}", title=TITLE[ln["edit"]["op"]],
                        status="pass", detail=f"{ln['text']}. About ${ln['cost']['total']:,} ("
                        + "; ".join(f"{i['quantity']:g} {i['unit']} at ${i['rate']:g}" for i in ln["cost"]["items"])
                        + ")." + (f" {ln['cost']['note']}" if ln["cost"]["note"] else ""),
                        anchor=_anchor(inputs.scan, ln["change"]), source=PRICE) for n, ln in enumerate(r["package"])]
    findings += [Finding(id=f"renovate:{inputs.scan}:skipped:{n}", title="Edit left out", status="warn",
                         detail=s["reason"], anchor=None, source=GEO) for n, s in enumerate(r["skipped"])]
    opens = [ln["change"]["opening"] for ln in r["package"] if ln["change"].get("opening")]
    walls = [ln["change"]["wall"] for ln in r["package"] if ln["change"].get("wall")]
    overlays = [RuleOverlay(select=SelectOpenings(openings=opens), style="highlight")] if opens else []
    overlays += [RuleOverlay(select=SelectWalls(walls=walls), style="highlight")] if walls else []
    assumptions = [Assumption(id=x["id"], label=f"{x['label']} ({x['source']})", value=x["value"], unit=x["unit"],
                              editable=False) for x in r["assumptions"]]
    fk = r["fork"]
    if fk and fk.get("available"):
        csrc = Source(layer="model", method="lookup", confidence="medium", note=fk["note"])
        metrics += [Metric(id="city_ready_now", label=f"Ready now, {fk['kind'] or 'homes'} in {fk['city'] or 'this city'}",
                           value=fk["ready_now"], unit="", source=csrc),
                    Metric(id="city_ready_widened", label=fk["label"], value=fk["after"], unit="", source=csrc)]
        findings.append(Finding(id=f"renovate:{inputs.scan}:city", title="City-wide, on a database fork", status="pass",
                                detail=f"{fk['ready_now']} of {fk['homes']} {fk['kind'] or 'homes'} in {fk['city'] or 'this city'} have a "
                                       f"wheelchair-ready bathroom now; {fk['after']} would with the doors on the way "
                                       f"widened to 36 in. " + {True: "The renovated home is one of them. ",
                                       False: "The renovated home still misses one of the three checks. ",
                                       None: "This home is not in the facts database, so it is not counted. "}[fk["renovated_ready"]] +
                                       f"Ran on {'a zero-copy fork ' + fk['service'] if fk['mode'] == 'fork' else 'a scenario schema'}"
                                       f" ({fk['ms'] / 1000:.0f} s), deleted after.", anchor=None, source=csrc))
        text += f" City-wide: {fk['ready_now']} of {fk['homes']} ready now, {fk['after']} with doors widened."
    elif fk:
        findings.append(Finding(id=f"renovate:{inputs.scan}:city", title="City-wide scenario did not run",
                                status="unknown", detail=fk["reason"], anchor=None, source=GEO))
    actions = [Action(id=f"after_{t}", label=f"Run {t.replace('_', ' ')} on the renovated plan", tool=t,
                      inputs={"scan": sid}) for t in r["tools"]]
    return ToolResult(scope=scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays, assumptions=assumptions, actions=actions)
