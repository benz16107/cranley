"""Field check: the on-site list. Other tools end in "measure on site", "too close to call" and "not seen"; this
turns those into things to do with a phone in the building, and when a capture comes back it reports what the
site says about the scan's result: confirmed, contradicted, or measured for the first time.

The tasks are worked out by `threshold.capture.tasks` from the workspace's own runs and handed in as `tasks`,
because a tool handler sees a scan, not the workspace. The capture routes run this after every capture that
answers a task, so its panel on the desktop is the live state of the visit."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .. import Check, Finding, Metric, Pin, PinsOverlay, ScanScope, ToolResult, Verdict, field, tool
from .._phone import anchor, media, source

SAID = {"confirmed": "confirms the scan", "contradicted": "contradicts the scan", "measured": "first measurement"}
METHOD_NOTE = {"manual": "Measured by the person on site and typed in", "vision": "Read from the person's photo by "
               "the vision reader", "sensor": "Read by the phone's sensors on site"}


class Outcome(BaseModel):
    verdict: Literal["confirmed", "contradicted", "measured"]
    status: Literal["pass", "warn", "fail", "unknown"]
    value: float | None = None
    err: float | None = None
    text: str = ""
    method: Literal["manual", "vision", "sensor"] = "manual"
    confidence: Literal["high", "medium", "low"] = "high"
    model_config = {"extra": "ignore"}


class Task(BaseModel):
    id: str
    kind: str
    title: str
    why: str = ""
    tools: list[str] = []
    findings: list[str] = []
    room: str | None = None
    opening: str | None = None
    scan_value: float | None = None
    threshold: float | None = None
    unit: str = "m"
    standard: str | None = None
    status: Literal["open", "done"] = "open"
    outcome: Outcome | None = None
    capture: str | None = None
    model_config = {"extra": "ignore"}


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    tasks: list[Task] | None = Field(None, description="The scan's phone tasks with their outcomes, from the capture "
                                                       "routes. Missing when run by hand: then it explains how to start.")
    offer_phone: bool = Field(False, description="Set by the server: no phone has sent anything to this workspace yet, "
                                                 "so the verdict says how to start one. Never set on the phone.")


def fmt(v: float | None, unit: str) -> str:
    return "" if v is None else f"{v:.1f} {unit}".strip() if unit in ("%", "h", "") else f"{v:.3f}".rstrip("0").rstrip(".") + f" {unit}"


def describe(t: Task) -> str:
    o = t.outcome
    said = [f"On site: {fmt(o.value, t.unit)}" + (f", give or take {fmt(o.err, t.unit)}" if o.err else "") if o.value is not None
            else "On site: checked by eye", o.text]
    if t.scan_value is not None and o.value is not None:
        said.append(f"The scan had {fmt(t.scan_value, t.unit)}.")
    if t.threshold is not None and t.kind in ("width", "step"):
        said.append(f"Limit {fmt(t.threshold, t.unit)}" + (f" ({t.standard})" if t.standard else "") + ".")
    return " ".join(s if s.endswith(".") else s + "." for s in said if s)


@tool(id="field_check", title="Field check", icon="clipboard-check",
      summary="Lists what the scan could not settle and a person on site can, and records what they found: confirmed, "
              "contradicted or measured.",
      model_description="The on-site checks a scan's results call for (clear door widths, steps, smoke alarms not seen, "
                        "the floor height for flood, window facing) and the outcome of each one a person has done with "
                        "the phone app: confirmed, contradicted or measured, with the capture as evidence. Run from the "
                        "phone link; by hand it only explains how to start.",
      personas=["wheelchair_user", "older_adult_family", "houston_homeowner_storm", "fire_captain", "apartment_manager"],
      requires=[{"layer": "phone.capture"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "StepLog"], overlays=["pins"],
      examples=["What should I check when I visit?", "What did the visit change?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sc = ScanScope(sid=inputs.scan)
    if inputs.tasks is None:
        return ToolResult(scope=sc, verdict=Verdict(status="unknown", text=(
            "Open this workspace on a phone (Continue on phone) to get the on-site checks for this building. They "
            "come from the other tools' results, so run those first.")))
    tasks = inputs.tasks
    if not tasks:
        return ToolResult(scope=sc, verdict=Verdict(status="pass", text="Nothing in this building's results needs "
                                                    "checking on site."))
    done = [t for t in tasks if t.status == "done" and t.outcome]
    tally: dict[str, int] = {"confirmed": 0, "contradicted": 0, "measured": 0}
    for t in done:
        tally[t.outcome.verdict] += 1
    ctx.step(f"{len(tasks)} on-site checks from {len({x for t in tasks for x in t.tools})} tools; {len(done)} done")
    src = source("manual", "high", "Counted from the on-site checks")
    checks, findings, pins = [], [], []
    for t in tasks:
        o = t.outcome if t.status == "done" else None
        fid = f"field_check:{inputs.scan}:{t.id}"
        a = anchor(inputs.scan, t.room, t.opening)
        checks.append(Check(id=t.id, rule=t.title + (f": {SAID[o.verdict]}" if o else ": to do on site"),
                            measured=o.value if o else None, threshold=t.threshold, unit=t.unit,
                            status=o.status if o else "unknown", standard=t.standard, findings=[fid] if o else []))
        if o:
            findings.append(Finding(id=fid, title=f"{t.title}: {SAID[o.verdict]}", status=o.status, detail=describe(t),
                                    anchor=a, media=media(t.capture),
                                    source=source(o.method, o.confidence, METHOD_NOTE[o.method])))
        if a is not None:
            pins.append(Pin(id=t.id, anchor=a, label=SAID[o.verdict] if o else "check on site", status=o.status if o else "unknown"))
    left = len(tasks) - len(done)
    worst = max((t.outcome.status for t in done), key=["unknown", "pass", "warn", "fail"].index, default="unknown")
    parts = [f"{n} {SAID[k]}" if k != "measured" else f"{n} measured for the first time" for k, n in tally.items() if n]
    text = (f"{len(done)} of {len(tasks)} on-site checks done" + (": " + ", ".join(parts) if parts else "") + "."
            + (f" {left} still to do." if left else "")
            + (" Open this workspace on a phone (Continue on phone) to do them." if left and inputs.offer_phone else ""))
    return ToolResult(
        # with checks still to do, "pass" would overstate the visit: only a problem found so far is reported early
        scope=sc, verdict=Verdict(status="unknown" if not done or (left and worst == "pass") else worst, text=text),
        metrics=[Metric(id="todo", label="To do on site", value=left, unit="", source=src),
                 Metric(id="confirmed", label="Confirm the scan", value=tally["confirmed"], unit="", source=src),
                 Metric(id="contradicted", label="Contradict the scan", value=tally["contradicted"], unit="", source=src),
                 Metric(id="measured", label="Measured first time", value=tally["measured"], unit="", source=src)],
        checks=checks, findings=findings, overlays=[PinsOverlay(pins=pins)] if pins else [])
