"""Floor height: the flood tool's weak number, measured by a person at the front door.

Three things come back from the phone and each becomes an estimate of the floor's height above the ground outside
the door, in the same form the flood tool's own methods use, so its `combine` weighs them together:

  steps       the steps counted up to the door, times a riser (the person's measured one, or a typical one with a
              wider error). The most useful of the three.
  barometer   the native app's pressure change from the street to the door, less the ground's own rise.
  GPS         the browser's altitude at the door less at the street, less the ground's own rise (Vexcel ground
              elevation at each fix). GPS altitude is good to metres, so this rarely narrows anything; it is
              reported so the person can see that.

Then the flood is run with the floor range before and after, and the result says how much the range of water
inside and of rooms taking water shrank."""
from __future__ import annotations

import math

from pydantic import BaseModel, Field

from .. import Action, Assumption, Check, Finding, Metric, ToolResult, Verdict, field, tool
from .._phone import anchor, media, scope, source
from ..flood_rehearsal import floor_height as fh
from ..flood_rehearsal import scenario

IN = 0.0254
RISER_M = 7 * IN            # a typical riser at a house door; IRC R311.7.5.1 allows up to 7 3/4 in
RISER_ERR_M = 0.03          # per step, when the riser is assumed and not measured
RISER_MEASURED_ERR_M = 0.01 # per step, when the person measured one
SILL_M, SILL_ERR_M = 0.03, 0.02  # the threshold strip and the last lip up to the finished floor
GRADE_ERR_M = 0.15          # Vexcel ground elevation, one point against another a street's width away
BARO_ERR_M = 0.3            # a phone barometer over a minute's walk
NAME = {"phone_steps": "steps counted at the door", "phone_baro": "the phone's barometer, street to door",
        "phone_gps": "GPS altitude, street to door"}


class Spot(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = None
    altitude_m: float | None = None
    altitude_accuracy_m: float | None = None
    model_config = {"extra": "ignore"}


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    steps: int | None = field(None, ge=0, le=12, description="Steps up from the ground to the door, counted on site")
    riser_m: float | None = field(None, gt=0.05, le=0.3, unit="m", description="One step's height, if measured")
    door: Spot | None = field(None, description="The phone's fix standing at the front door")
    street: Spot | None = field(None, description="The phone's fix standing at the street or the edge of the yard")
    baro_rise_m: float | None = field(None, ge=-20, le=20, unit="m", description="Barometer: how much higher the door "
                                      "is than the street (native app)")
    depth_m: float = field(0.5, pref="flood.depth_m", unit="m", ge=0, le=3, description="Water above the ground outside, "
                           "for the before and after")
    use_drone: bool = field(True, description="As in the flood rehearsal: use the drone photos when there are any")
    capture: str | None = field(None, description="Capture id of the photo of the threshold")


def _ground(pts: list[tuple[float, float]]) -> list[float]:
    return scenario._heights("dtm", pts)


def estimates(inputs: Inputs, ground=None) -> tuple[list[dict], dict]:
    """The phone's estimates of the floor height above the ground at the door, and what went into them."""
    out, info = [], {"grade_m": None}
    if inputs.steps is not None:
        riser, per = (inputs.riser_m, RISER_MEASURED_ERR_M) if inputs.riser_m else (RISER_M, RISER_ERR_M)
        out.append(fh._est("phone_steps", inputs.steps * riser + SILL_M, math.hypot(inputs.steps * per, SILL_ERR_M),
                           "high" if inputs.riser_m or inputs.steps == 0 else "medium",
                           f"{inputs.steps} step{'s' if inputs.steps != 1 else ''} counted at the door, "
                           + (f"each measured at {riser:.3f} m" if inputs.riser_m else f"at a typical {riser:.2f} m riser")
                           + ", plus the threshold.", steps=inputs.steps))
    if inputs.door and inputs.street:
        try:
            g_door, g_street = (ground or _ground)([(inputs.door.lon, inputs.door.lat), (inputs.street.lon, inputs.street.lat)])
            info["grade_m"] = g_door - g_street
        except Exception as e:  # noqa: BLE001 - the aerial ground model is one input of several
            info["grade_error"] = str(e)[:120]
    grade = info["grade_m"]
    if inputs.baro_rise_m is not None and grade is not None:
        out.append(fh._est("phone_baro", inputs.baro_rise_m - grade, math.hypot(BARO_ERR_M, GRADE_ERR_M), "medium",
                           "The phone's barometer from the street to the door, less the ground's own rise between them."))
    d, s = inputs.door, inputs.street
    if d and s and d.altitude_m is not None and s.altitude_m is not None and grade is not None:
        err = math.hypot(d.altitude_accuracy_m or 10.0, s.altitude_accuracy_m or 10.0, GRADE_ERR_M)
        info["gps_rise_m"], info["gps_err_m"] = d.altitude_m - s.altitude_m, err
        out.append(fh._est("phone_gps", d.altitude_m - s.altitude_m - grade, err, "low",
                           "GPS altitude at the door less at the street, less the ground's own rise. GPS altitude is "
                           "good to metres, so this is shown, not relied on."))
    return out, info


def _wet(flood: dict, k: str) -> int:
    return len(scenario.wet_rooms(flood, k))


def _entry(flood: dict, k: str) -> float:
    return max(0.0, flood["levels"][k] - flood["ref_z"])


@tool(id="floor_height", title="Floor height", icon="move-vertical",
      summary="Narrows the floor's height above the ground, the flood result's widest uncertainty, from steps counted "
              "and fixes taken at your own front door.",
      model_description="Phone only: a person runs this from the phone app, an agent cannot. Combine on-site phone inputs (steps counted at the door and a measured riser, GPS fixes at "
                        "the door and the street with Vexcel ground elevation, a barometer rise) with the flood "
                        "rehearsal's own floor-height methods, and report how much the range of water inside and of "
                        "rooms taking water shrank. Needs inputs from the phone app.",
      requires=[{"layer": "phone.gps", "need": "optional"}, {"layer": "matterport.rooms"},
                {"layer": "vexcel.elevation", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog", "ActionBar"],
      annotations={"cost": "slow"}, examples=["How high is my floor above the yard?", "Narrow the flood range"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    scenario.check_plan(plan)
    base = scenario.FloodInputs(scan=sid, depth_m=inputs.depth_m, use_drone=inputs.use_drone)
    before = scenario.run(plan, base, ctx.step)
    f0 = before["floor"]
    mine, info = estimates(inputs)
    sc = scope(sid)
    if not mine:
        return ToolResult(scope=sc, verdict=Verdict(status="unknown", text=(
            "Nothing from the phone could be turned into a floor height. Count the steps up to the door: that alone "
            "is enough.")))
    for e in mine:
        ctx.step(f"{NAME[e['method']].capitalize()}: {e['value_m']:.2f} m, give or take {e['err_m']:.2f}")
    prior = [e for e in f0["estimates"] if e["method"] != "assumed"]
    f1 = fh.combine(prior + mine, f0.get("bound"))
    # the flood with the floor at each end of the new range (a floor height given to the scenario is used as it is)
    lo = scenario.run(plan, base.model_copy(update={"floor_height_m": f1["hi_m"]}), lambda s: None)   # high floor: least water
    hi = scenario.run(plan, base.model_copy(update={"floor_height_m": f1["lo_m"]}), lambda s: None)   # low floor: most water
    w0, w1 = f0["hi_m"] - f0["lo_m"], f1["hi_m"] - f1["lo_m"]
    d0 = (_entry(before, "lo"), _entry(before, "hi"))
    d1 = (_entry(lo, "mid"), _entry(hi, "mid"))
    r0 = (_wet(before, "lo"), _wet(before, "hi"))
    r1 = (_wet(lo, "mid"), _wet(hi, "mid"))
    best = next(e for e in mine if e["method"] == f1["method"]) if f1["method"] in NAME else None
    src = source("sensor" if f1["method"] in ("phone_gps", "phone_baro") else "manual", f1["confidence"],
                 f"Floor height from {NAME[f1['method']]}; range "
                 f"{f1['lo_m']:.2f} to {f1['hi_m']:.2f} m") if best else source(
                     "manual", f1["confidence"], "The phone's inputs did not beat the methods already in the flood result")
    narrowed = w1 < w0 - 0.005
    shrink = round(100 * (1 - w1 / w0)) if w0 > 0 else 0
    status = "pass" if narrowed else "warn"
    text = (f"The floor height range is now {f1['lo_m']:.2f} to {f1['hi_m']:.2f} m, {shrink}% narrower than before "
            f"({f0['lo_m']:.2f} to {f0['hi_m']:.2f} m)." if narrowed else
            f"The phone's inputs did not narrow the floor height: it stays {f1['lo_m']:.2f} to {f1['hi_m']:.2f} m.")
    text += (f" With {inputs.depth_m:.2f} m of water outside, rooms taking water: {r1[0]} to {r1[1]} (was {r0[0]} to {r0[1]})."
             if r1 != r0 else f" With {inputs.depth_m:.2f} m of water outside, {r1[0]} to {r1[1]} rooms take water, as before.")
    if f1.get("widened_by"):
        text += " The methods disagree, so the range was widened to take them all in."
    fid = f"floor_height:{sid}:door"
    lines = [f"{NAME.get(e['method'], e['method'])}: {e['value_m']:.2f} m, give or take {e['err_m']:.2f} ({e['confidence']}). {e['note']}"
             for e in mine]
    if info.get("grade_m") is not None:
        lines.append(f"The ground at the door is {info['grade_m']:+.2f} m against the ground at the street (Vexcel ground "
                     f"elevation, give or take {GRADE_ERR_M:.2f}).")
    door = before.get("entry_door")
    return ToolResult(
        scope=sc, verdict=Verdict(status=status, text=text),
        metrics=[Metric(id="floor_height", label="Floor above the ground", value=f1["value_m"], unit="m", source=src),
                 Metric(id="range_after", label="Range now", value=round(w1, 3), unit="m", source=src),
                 Metric(id="range_before", label="Range before", value=round(w0, 3), unit="m", source=src),
                 Metric(id="shrink_pct", label="Narrower by", value=shrink, unit="%", source=src),
                 Metric(id="floor_low", label="Floor height, low end", value=f1["lo_m"], unit="m", source=src),
                 Metric(id="floor_high", label="Floor height, high end", value=f1["hi_m"], unit="m", source=src),
                 Metric(id="grade", label="Ground at the door above the street", unit="m", source=src,
                        value=round(info["grade_m"], 2) if info.get("grade_m") is not None else None)],
        checks=[Check(id="floor_range", rule="Floor height range: now against before", measured=round(w1, 3),
                      threshold=round(w0, 3), unit="m", status=status, kind="claim", findings=[fid]),
                Check(id="depth_range", rule="Range of water on the entry floor: now against before",
                      measured=round(d1[1] - d1[0], 3), threshold=round(d0[1] - d0[0], 3), unit="m", status=status,
                      kind="claim", findings=[fid]),
                Check(id="rooms_range", rule="Range of rooms taking water: now against before", measured=r1[1] - r1[0],
                      threshold=r0[1] - r0[0], unit="rooms", status=status, kind="claim", findings=[fid])],
        findings=[Finding(id=fid, title="Floor height, measured at the door", status=status, source=src,
                          anchor=anchor(sid, opening=door["id"] if door else None), media=media(inputs.capture),
                          detail=f"{f1['value_m']:.2f} m (between {f1['lo_m']:.2f} and {f1['hi_m']:.2f} m). " + " ".join(lines)
                                 + f" Water on the entry floor: {d1[0]:.2f} to {d1[1]:.2f} m (was {d0[0]:.2f} to {d0[1]:.2f} m).")],
        assumptions=[Assumption(id="flood.depth_m", label="Water above the ground outside", value=inputs.depth_m, unit="m",
                                editable=True),
                     Assumption(id="riser", label="Riser " + ("measured" if inputs.riser_m else "assumed, typical"),
                                value=round(inputs.riser_m or RISER_M, 3), unit="m"),
                     Assumption(id="same_door", label="The door you stood at is the scan's entry door", value=True)],
        actions=[Action(id="rerun_flood", label="Run the flood rehearsal with this floor height", tool="flood_rehearsal",
                        inputs={"scan": sid, "floor_height_m": f1["value_m"], "depth_m": inputs.depth_m})])
