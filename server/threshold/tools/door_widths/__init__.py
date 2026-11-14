"""Reference tool: every doorway's width against a threshold, as checks, pins and a pass/warn/fail rule overlay."""
from __future__ import annotations

from pydantic import BaseModel

from .. import (
    Action,
    Assumption,
    Check,
    Finding,
    Metric,
    OpeningAnchor,
    Pin,
    PinsOverlay,
    RuleOverlay,
    ScanScope,
    SelectOpenings,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)

WIDTH = Source(layer="matterport", method="geometry", confidence="medium",
               note="Opening width in the wall graph; a hinged door's leaf takes a few centimetres off it")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    min_width_m: float = field(ask="How wide a door do you need, in metres? For furniture, use its narrowest side; "
                                   "a wheelchair needs 0.813 m (32 in).",
                               pref="access.door_width_m", unit="m", gt=0.3, le=3.0)
    warn_margin_m: float = field(0.05, pref="access.door_warn_margin_m", unit="m", ge=0, le=0.5,
                                 description="Doorways this close above the threshold are a warning")
    standard: str | None = field(None, pref="access.door_standard", description="The rule the threshold comes from")


def _m(x: float) -> str:
    return f"{x:.3f}".rstrip("0").rstrip(".")


def _status(width: float | None, need: float, margin: float) -> str:
    if width is None:
        return "unknown"
    return "fail" if width < need else "warn" if width < need + margin else "pass"


def _where(o: dict, labels: dict[str, str]) -> str:
    names = [labels.get(r) or "unlabelled room" for r in o["rooms"]]
    return " to ".join(names) if len(names) > 1 else f"{names[0] if names else 'unknown room'} to outside"


@tool(id="door_widths", title="Door widths", icon="door-open",
      summary="Measures every doorway and flags the ones too narrow for you or what you are moving.",
      model_description="Check every doorway and open passage in one scan against a minimum width. Returns one check "
                        "per doorway, findings for the ones that fail or are close, pins and a coloured rule overlay.",
      personas=["wheelchair_user", "furniture_mover", "older_adult_family", "fire_captain", "apartment_manager"],
      requires=[{"layer": "matterport.openings"}, {"layer": "matterport.room_labels", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "Controls", "AssumptionChips", "StepLog",
              "ActionBar"],
      overlays=["pins", "rule"],
      examples=["Can my wheelchair get through every door?", "Will a 90 cm sofa fit through?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    labels = {r["id"]: r.get("label") for r in plan["rooms"]}
    doors = [o for o in plan["openings"] if o["type"] in ("doorway", "opening")]
    ctx.step(f"Found {len(doors)} doorways and passages in the wall graph")
    if not doors:
        return ToolResult(scope=ScanScope(sid=inputs.scan), verdict=Verdict(
            status="unknown", text="This scan's wall graph has no doorways, so widths cannot be checked."))

    need, margin = inputs.min_width_m, inputs.warn_margin_m
    checks, findings, pins = [], [], []
    by_status: dict[str, list[str]] = {"pass": [], "warn": [], "fail": [], "unknown": []}
    for o in sorted(doors, key=lambda o: o["width"] or 0):
        s = _status(o["width"], need, margin)
        by_status[s].append(o["id"])
        where = _where(o, labels)
        fid = f"door_widths:{inputs.scan}:{o['id']}"
        if s != "pass":
            word = {"fail": "narrower than", "warn": "only just above", "unknown": "not measured against"}[s]
            findings.append(Finding(
                id=fid, title=f"Doorway, {where}", status=s, anchor=OpeningAnchor(sid=inputs.scan, opening=o["id"]),
                detail=(f"{o['width']:.2f} m wide, {word} your {_m(need)} m." if o["width"] is not None
                        else "The scan has no width for this doorway."), source=WIDTH))
        checks.append(Check(id=o["id"], rule=f"Doorway width, {where}", measured=round(o["width"], 3) if o["width"] else None,
                            threshold=need, unit="m", status=s, standard=inputs.standard,
                            findings=[fid] if s != "pass" else []))
        pins.append(Pin(id=o["id"], anchor=OpeningAnchor(sid=inputs.scan, opening=o["id"]),
                        label=f"{o['width']:.2f} m" if o["width"] is not None else "?", status=s))
    ctx.step(f"Compared each with {_m(need)} m: {len(by_status['fail'])} fail, {len(by_status['warn'])} close")

    widths = [o["width"] for o in doors if o["width"] is not None]
    fails, warns = len(by_status["fail"]), len(by_status["warn"])
    status = "fail" if fails else "warn" if warns else "pass" if widths else "unknown"
    text = (f"{fails} of {len(doors)} doorways are narrower than {_m(need)} m." if fails else
            f"Every doorway is at least {_m(need)} m, {warns} with less than {margin * 100:.0f} cm to spare." if warns
            else f"All {len(doors)} doorways are at least {_m(need + margin)} m wide.")
    return ToolResult(
        scope=ScanScope(sid=inputs.scan), verdict=Verdict(status=status, text=text),
        metrics=[Metric(id="doorways", label="Doorways", value=len(doors), unit="", source=WIDTH),
                 Metric(id="narrowest", label="Narrowest", value=round(min(widths), 2) if widths else None, unit="m",
                        source=WIDTH),
                 Metric(id="too_narrow", label="Too narrow", value=fails, unit="", source=WIDTH)],
        checks=checks, findings=findings,
        overlays=[PinsOverlay(pins=pins)] + [RuleOverlay(select=SelectOpenings(openings=ids), style=s)
                                             for s, ids in by_status.items() if ids and s != "unknown"],
        assumptions=[Assumption(id="access.door_width_m", label="Width you need", value=need, unit="m", editable=True),
                     Assumption(id="access.door_warn_margin_m", label="Warn within", value=margin, unit="m",
                                editable=True),
                     Assumption(id="width_is_opening", label="Width is the wall opening, not clear width past the door",
                                value=True)],
        actions=[Action(id="wider", label="Check for a wider chair (0.90 m)", tool="door_widths",
                        inputs={"scan": inputs.scan, "min_width_m": 0.9})])
