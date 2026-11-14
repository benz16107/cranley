# Tools

A tool is a folder `threshold/tools/<id>/` whose `__init__.py` defines an `Inputs` model and one handler
decorated with `@tool(...)`. The registry finds it by itself; the agent, `GET /api/tools` and the web tool
dock all read the same manifest. Run it with `run_tool("<id>", {...})` or `POST /api/tools/<id>/run`.

## A whole tool

```python
"""Ceiling height: flags rooms lower than the person needs."""
from __future__ import annotations

from pydantic import BaseModel

from .. import Check, Finding, Metric, RoomAnchor, ScanScope, Source, ToolResult, Verdict, field, tool

SRC = Source(layer="matterport", method="geometry", confidence="high")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan")                       # filled from the selected building
    min_height_m: float = field(ask="How much headroom do you need, in metres?",  # asked if nothing fills it
                                pref="space.min_height_m", unit="m", gt=1.5)       # saved preference


@tool(id="ceiling_height", title="Ceiling height", summary="Rooms lower than you need.",
      model_description="Check every room's ceiling height in one scan against a minimum.",
      requires=[{"layer": "matterport.rooms"}], blocks=["VerdictHeader", "CheckList", "StepLog"])
def run(ctx, inputs: Inputs) -> ToolResult:
    rooms = [r for r in ctx.plan(inputs.scan)["rooms"] if r.get("height")]
    ctx.step(f"Read {len(rooms)} room heights")
    low = [r for r in rooms if r["height"] < inputs.min_height_m]
    return ToolResult(
        scope=ScanScope(sid=inputs.scan),
        verdict=Verdict(status="fail" if low else "pass", text=f"{len(low)} of {len(rooms)} rooms are too low."),
        metrics=[Metric(id="low", label="Too low", value=len(low), unit="", source=SRC)],
        checks=[Check(id=r["id"], rule=f"Height, {r['label'] or 'room'}", measured=r["height"], unit="m",
                      threshold=inputs.min_height_m, status="fail" if r in low else "pass") for r in rooms],
        findings=[Finding(id=f"ceiling_height:{inputs.scan}:{r['id']}", title=f"Low ceiling, {r['label'] or 'room'}",
                          status="fail", detail=f"{r['height']:.2f} m", source=SRC,
                          anchor=RoomAnchor(sid=inputs.scan, room=r["id"])) for r in low])
```

## Rules

- **Inputs.** `field(ask=...)` makes a required input an intake question; `pref=` names the preference key that
  fills it (a persona preset's `thresholds`, the person's answer, or an edit they made). Fill order: given input,
  preference, answer, preset, then the default. `source="selection.scan"` comes from the selected building.
- **Numbers come from code.** Every measured value goes into `metrics`, `checks`, `findings` or overlays. The
  model sees only the verdict text, finding ids, statuses and titles, so keep measurements out of titles.
- **Finding ids are stable**: `<tool>:<scan>:<thing>`. A re-run replaces them, and a finding the person rejected
  stays hidden.
- **Metric ids with a dot** (`area.Bedroom`) are one series: the panel puts them in a `MiniChart`. Ids without
  a dot go in the `MetricRow` (first four).
- **Editable assumptions** use the preference key as `id`, so editing the chip sets that preference and marks
  the run stale.
- **Overlays** are Contract 4 (`LensOverlay`, `RuleOverlay`, `PinsOverlay`, ...). The panel is built from `blocks`.
- **Report progress** with `ctx.step("...")`; it shows in the run's `StepLog`.
- **Fail softly.** Missing data is `status="unknown"` with a sentence saying why, not an exception. Raise
  `ToolError` only for something the person can fix. `ctx.plan(sid)` raises it for an unknown scan.
- **Test it** in `tests/<workstream>/` with a small hand-made plan (`tests/agent/conftest.py` has one) and
  `ToolContext(plans=...)`; never with sponsor data in the repo.
- A tool a persona names before it exists goes in `agent/personas/planned_tools.json`; once the folder exists
  the real one replaces the stub.

Reference tools: `room_census/` (a lens) and `door_widths/` (checks, pins, a rule overlay, controls).
