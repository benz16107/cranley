"""Slope check: the phone as a level. Laid on a ramp it reads the running slope and the cross slope from its tilt
sensor, judged against the ADA ramp limits; on a threshold's bevel, against the ADA bevel limit; held against a
door frame, how far the frame is out of plumb.

One reading carries the sensor's own offset and, with the phone on its back, the tilt its camera bump adds. Turning
the phone end for end and reading again cancels both: the slope reverses sign and the offset does not, so the slope
is half the difference. Without the second reading the result says so and carries a wider error."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel

from .. import Assumption, Check, Finding, Metric, ToolResult, Verdict, field, tool
from .._phone import anchor, key, media, scope, source

RAMP_MAX = 1 / 12      # ADA 2010 405.2: running slope of a ramp, 1:12 maximum
CROSS_MAX = 1 / 48     # ADA 2010 405.3: cross slope of a ramp, 1:48 maximum
WALK_MAX = 1 / 20      # ADA 2010 403.3: steeper than 1:20 a walking surface is a ramp and must meet 405
BEVEL_MAX = 1 / 2      # ADA 2010 303.3: a level change of 1/4 to 1/2 in is beveled no steeper than 1:2
STD = {"ramp": "ADA 2010 405.2: ramp running slope 1:12 (8.33%) maximum",
       "cross": "ADA 2010 405.3: ramp cross slope 1:48 (2.08%) maximum",
       "walk": "ADA 2010 403.3: a walking surface steeper than 1:20 (5%) is a ramp",
       "bevel": "ADA 2010 303.3: changes in level of 1/4 to 1/2 in beveled no steeper than 1:2 (50%)"}
ERR_FLIPPED_DEG = 0.3  # two readings end for end: what is left is sensor noise and how still the phone lay
ERR_SINGLE_DEG = 1.0   # one reading: sensor offset plus the camera bump, neither known


class Inputs(BaseModel):
    mode: Literal["ramp", "threshold", "plumb"] = field("ramp", description="ramp: laid on the surface, long edge up "
                                                        "the slope. threshold: laid on the bevel. plumb: long edge "
                                                        "held against a door frame")
    reading_deg: float = field(description="Tilt along the phone's long axis, degrees, averaged while it lay still",
                               ge=-90, le=90)
    flipped_deg: float | None = field(None, ge=-90, le=90, description="The same after turning the phone end for end")
    cross_deg: float | None = field(None, ge=-90, le=90, description="Tilt across the phone's short axis")
    cross_flipped_deg: float | None = field(None, ge=-90, le=90)
    spread_deg: float = field(0.0, ge=0, le=45, description="Standard deviation of the samples: how still it lay")
    scan: str | None = None
    room: str | None = None
    opening: str | None = None
    capture: str | None = field(None, description="Capture id of the sensor reading")


def settle(first: float, flipped: float | None, spread: float) -> tuple[float, float, bool]:
    """(angle in degrees, error in degrees, whether the offset was cancelled)."""
    if flipped is None:
        return abs(first), math.hypot(ERR_SINGLE_DEG, spread), False
    return abs(first - flipped) / 2, math.hypot(ERR_FLIPPED_DEG, spread), True


def grade(deg: float) -> float:
    return math.tan(math.radians(deg))


def judge(deg: float, err: float, limit: float) -> str:
    lo, hi = grade(max(0.0, deg - err)), grade(deg + err)
    return "pass" if hi <= limit else "fail" if lo > limit else "warn"


def ratio(g: float) -> str:
    return f"1:{1 / g:.0f}" if g > 1e-4 else "level"


@tool(id="slope_check", title="Slope check", icon="triangle-right",
      summary="Uses the phone as a level: a ramp's slope and cross slope against the ADA limits, a threshold's "
              "bevel, or how far a door frame is out of plumb.",
      model_description="Phone only: a person runs this from the phone app, an agent cannot. Judge a slope read by a phone's tilt sensor. mode ramp: running slope against ADA 405.2 "
                        "(1:12) and cross slope against 405.3 (1:48). mode threshold: a bevel against ADA 303.3 "
                        "(1:2). mode plumb: a door frame's lean. Needs readings from the phone app; it cannot run "
                        "from a scan alone.", requires=[{"layer": "phone.tilt"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "AssumptionChips", "StepLog"],
      examples=["Is this ramp too steep for a wheelchair?", "Is the door frame straight?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    deg, err, cancelled = settle(inputs.reading_deg, inputs.flipped_deg, inputs.spread_deg)
    ctx.step(f"Tilt {deg:.2f} degrees, give or take {err:.2f}" + (", offset cancelled by the second reading" if cancelled
             else ", from one reading: the sensor's offset and the camera bump are in it"))
    src = source("sensor", "medium" if cancelled else "low",
                 "Phone tilt sensor, two readings end for end" if cancelled else
                 "Phone tilt sensor, one reading; turn the phone end for end and read again to cancel its offset")
    g = grade(deg)
    k = key(inputs.scan, inputs.opening or inputs.room, inputs.mode)
    a = anchor(inputs.scan, inputs.room, inputs.opening)
    metrics = [Metric(id="slope_pct", label="Out of plumb" if inputs.mode == "plumb" else "Slope", value=round(100 * g, 2),
                      unit="%", source=src),
               Metric(id="angle_deg", label="Angle", value=round(deg, 2), unit="deg", source=src),
               Metric(id="error_deg", label="Give or take", value=round(err, 2), unit="deg", source=src)]
    checks: list[Check] = []
    if inputs.mode == "plumb":
        status = "pass" if deg <= err else "warn"
        text = ("The frame is plumb within what the phone can tell." if status == "pass" else
                f"The frame leans {1000 * g:.0f} mm in each metre of height.")
        detail = f"{deg:.2f} degrees from vertical, give or take {err:.2f}. No accessibility standard sets a limit; " \
                 "a leaning frame is why a door binds or swings by itself."
    else:
        limit, std = (RAMP_MAX, STD["ramp"]) if inputs.mode == "ramp" else (BEVEL_MAX, STD["bevel"])
        status = judge(deg, err, limit)
        checks.append(Check(id="running", rule="Running slope" if inputs.mode == "ramp" else "Bevel slope",
                            measured=round(100 * g, 2), threshold=round(100 * limit, 2), unit="%", status=status,
                            standard=std, findings=[f"slope_check:{k}"]))
        if inputs.mode == "ramp":
            checks.append(Check(id="is_ramp", rule="Steep enough to count as a ramp", measured=round(100 * g, 2),
                                threshold=round(100 * WALK_MAX, 2), unit="%", standard=STD["walk"],
                                status="pass" if grade(deg + err) <= WALK_MAX else "warn"))
        if inputs.cross_deg is not None and inputs.mode == "ramp":
            cdeg, cerr, _ = settle(inputs.cross_deg, inputs.cross_flipped_deg, inputs.spread_deg)
            cs = judge(cdeg, cerr, CROSS_MAX)
            metrics.append(Metric(id="cross_pct", label="Cross slope", value=round(100 * grade(cdeg), 2), unit="%", source=src))
            checks.append(Check(id="cross", rule="Cross slope", measured=round(100 * grade(cdeg), 2),
                                threshold=round(100 * CROSS_MAX, 2), unit="%", status=cs, standard=STD["cross"],
                                findings=[f"slope_check:{k}"]))
            status = max(status, cs, key=["pass", "warn", "fail"].index)
        what = "ramp" if inputs.mode == "ramp" else "bevel"
        text = {"pass": f"This {what} is within the limit, with the phone's error allowed for.",
                "warn": f"This {what} is within the phone's error of the limit: check it with a level.",
                "fail": f"This {what} is steeper than the limit, with the phone's error allowed for."}[status]
        detail = f"{100 * g:.1f}% ({ratio(g)}), {deg:.2f} degrees give or take {err:.2f}. {std}."
    return ToolResult(
        scope=scope(inputs.scan), verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
        findings=[Finding(id=f"slope_check:{k}", title={"ramp": "Ramp slope, read on site", "threshold": "Threshold bevel, "
                          "read on site", "plumb": "Door frame, read on site"}[inputs.mode], status=status, detail=detail,
                          anchor=a, source=src, media=media(inputs.capture))],
        assumptions=[Assumption(id="offset_cancelled", label="Sensor offset and camera bump cancelled by a second "
                                "reading end for end", value=cancelled),
                     Assumption(id="phone_not_a_level", label="A phone is not a calibrated level", value=True)])
