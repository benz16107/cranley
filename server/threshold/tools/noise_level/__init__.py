"""Noise level: an A-weighted sound level per room from the phone's microphone, as a lens.

The phone app computes the A-weighted equivalent level (LAeq) over a fixed interval from raw microphone samples
with the browser's voice processing switched off. A phone microphone is not a sound level meter: its sensitivity
is not known, so the absolute level carries a wide stated error. Differences between rooms measured with the same
phone in the same visit are much better than the absolute numbers, and that comparison is what this is for."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .. import Assumption, Check, Finding, Legend, LensOverlay, Metric, ToolResult, Verdict, field, tool
from .._phone import anchor, key, media, scope, source

ABS_ERR_DB = 10.0   # absolute level from an uncalibrated phone microphone
REL_ERR_DB = 3.0    # difference between two rooms, same phone, same visit
MIN_SECONDS = 10
# WHO, Guidelines for Community Noise (1999), table 4.1: 35 dB LAeq inside dwellings by day, 30 dB LAeq in bedrooms at night
WHO = "WHO Guidelines for Community Noise (1999), table 4.1"
LIMIT = {"Bedroom": 30.0}
LIMIT_DWELLING = 35.0
SRC = source("sensor", "low", f"Phone microphone, uncalibrated: the level is good to about {ABS_ERR_DB:.0f} dB, "
             f"differences between rooms to about {REL_ERR_DB:.0f} dB")


class Reading(BaseModel):
    room: str | None = Field(None, description="Room id in the scan")
    label: str | None = Field(None, description="What the person called the place when there is no scan")
    leq_dba: float = Field(ge=0, le=140)
    lmax_dba: float | None = Field(None, ge=0, le=150)
    seconds: float = Field(gt=0, le=600)
    capture: str | None = None


class Inputs(BaseModel):
    readings: list[Reading] = field(description="One A-weighted level per room, from the phone app", min_length=1)
    scan: str | None = None


def judge(leq: float, limit: float) -> str:
    """Only what survives the microphone's error is called; never a fail from an uncalibrated microphone."""
    return "pass" if leq + ABS_ERR_DB <= limit else "warn" if leq - ABS_ERR_DB > limit else "unknown"


@tool(id="noise_level", title="Noise level", icon="audio-lines",
      summary="How loud each room is, from the phone's microphone: an uncalibrated A-weighted level per room, best "
              "read as which rooms are quieter.",
      model_description="A-weighted sound level (LAeq) per room from a phone microphone, as a per-room lens, against "
                        "the WHO indoor guideline levels. Uncalibrated: absolute levels are good to about 10 dB, "
                        "differences between rooms to about 3 dB. Needs readings from the phone app.",
      personas=["renter_listing", "renter_checking_claims"], requires=[{"layer": "phone.microphone"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "FloorPlanMini", "AssumptionChips", "StepLog"],
      overlays=["lens"], examples=["Which bedroom is quietest?", "How loud is the street side?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan) if inputs.scan else {"rooms": []}
    labels = {r["id"]: r.get("label") or "Unlabelled room" for r in plan.get("rooms") or []}
    latest: dict[str, Reading] = {}
    for r in inputs.readings:  # a room measured twice keeps the later reading
        latest[r.room or r.label or f"place {len(latest) + 1}"] = r
    ctx.step(f"{len(latest)} places measured, {min(r.seconds for r in latest.values()):.0f} s or more each")
    short = [k for k, r in latest.items() if r.seconds < MIN_SECONDS]
    name = lambda k, r: labels.get(r.room or "", r.label or k)  # noqa: E731
    checks, findings, metrics = [], [], []
    for k, r in sorted(latest.items(), key=lambda kv: -kv[1].leq_dba):
        n = name(k, r)
        limit = LIMIT.get(labels.get(r.room or "", r.label or ""), LIMIT_DWELLING)
        st = judge(r.leq_dba, limit)
        fid = f"noise_level:{key(inputs.scan, r.room or k)}"
        checks.append(Check(id=k, rule=f"Sound level, {n}", measured=round(r.leq_dba, 1), threshold=limit, unit="dBA",
                            status=st, standard=WHO, findings=[fid]))
        findings.append(Finding(
            id=fid, title=f"Sound level in {n[0].lower() + n[1:]}", status=st, source=SRC, media=media(r.capture),
            anchor=anchor(inputs.scan, r.room),
            detail=f"{r.leq_dba:.0f} dBA over {r.seconds:.0f} s" + (f", peaks to {r.lmax_dba:.0f}" if r.lmax_dba else "")
                   + f"; give or take {ABS_ERR_DB:.0f} dB. Guideline {limit:.0f} dBA ({WHO})."
                   + (" Too short an interval to trust." if r.seconds < MIN_SECONDS else "")))
        metrics.append(Metric(id=f"level.{n}", label=n, value=round(r.leq_dba, 1), unit="dBA", source=SRC))
    by = sorted(latest.items(), key=lambda kv: kv[1].leq_dba)
    quiet, loud = by[0], by[-1]
    gap = loud[1].leq_dba - quiet[1].leq_dba
    metrics = [Metric(id="quietest", label=f"Quietest: {name(*quiet)}", value=round(quiet[1].leq_dba, 1), unit="dBA", source=SRC),
               Metric(id="loudest", label=f"Loudest: {name(*loud)}", value=round(loud[1].leq_dba, 1), unit="dBA", source=SRC),
               Metric(id="gap", label="Difference", value=round(gap, 1), unit="dB", source=SRC), *metrics]
    if len(by) > 1 and gap > REL_ERR_DB:
        text = f"The {name(*quiet).lower()} is the quietest and the {name(*loud).lower()} the loudest of {len(by)} places measured."
    elif len(by) > 1:
        text = f"The {len(by)} places measured are within {REL_ERR_DB:.0f} dB of each other: no real difference."
    else:
        text = f"One place measured, the {name(*quiet).lower()}. Measure another room to compare."
    text += " Levels come from an uncalibrated phone microphone."
    if short:
        text += f" {len(short)} reading{'s were' if len(short) > 1 else ' was'} shorter than {MIN_SECONDS} s."
    values = {r.room: round(r.leq_dba, 1) for r in latest.values() if r.room in labels}
    return ToolResult(
        scope=scope(inputs.scan), metrics=metrics, checks=checks, findings=findings,
        verdict=Verdict(status="warn" if any(c.status == "warn" for c in checks) else "unknown" if len(by) == 1 else "pass",
                        text=text),
        overlays=[LensOverlay(values=values, ramp="sequential", legend=Legend(
            title="Sound level (phone, uncalibrated)", unit="dBA", min=min(values.values()), max=max(values.values())))]
        if values else [],
        assumptions=[Assumption(id="uncalibrated", label="Microphone not calibrated: absolute level give or take",
                                value=ABS_ERR_DB, unit="dB"),
                     Assumption(id="relative", label="Room to room difference give or take", value=REL_ERR_DB, unit="dB"),
                     Assumption(id="moment", label="One moment on one day; traffic and neighbours vary", value=True)])
