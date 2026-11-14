"""Robot fit: which rooms a wheeled body (width, turning circle, climbable step) can reach and turn in, for one scan
or many, and which single change to the body gains the most rooms. Reach and turning circles come from geometry."""
from __future__ import annotations

from pydantic import BaseModel

from ...geometry import reach, turning_spaces
from ...geometry._plan import judge
from .. import (Assumption, Check, Finding, Legend, LensOverlay, Metric, RoomAnchor, ScanScope, Source, ToolResult,
                Verdict, field, tool)
from ..types import ScansScope
from .._access import GEO, SILL_NOISE_M, quality
from ..measure_search import table

SKIP = {"Void"}
STEP_TOL = SILL_NOISE_M   # sills scatter this much on flat floors, so a step is blocking only above step + this


class Inputs(BaseModel):
    scan: str | None = field(None, source="selection.scan", description="One scan; leave out for many")
    scans: list[str] | None = field(None, description="Scan ids to test; default every scan in the measures table "
                                                      "that has a wall graph")
    body_width_m: float = field(0.5, pref="robot.body_width_m", unit="m", gt=0.1, le=1.5, description="Robot width")
    turning_diameter_m: float = field(0.7, pref="robot.turning_diameter_m", unit="m", gt=0.1, le=3,
                                      description="Turning circle the robot needs")
    step_height_m: float = field(0.02, pref="robot.step_height_m", unit="m", ge=0, le=0.3,
                                 description="Highest step the robot can climb")


def fit_scan(plan: dict, w: float, d: float, s: float, turns: dict | None = None) -> dict | None:
    """Rooms reached and turnable for one body. None when the scan has no wall graph."""
    if not quality(plan).get("walls"):
        return None
    rc = reach(plan, w, max_step=s + STEP_TOL)
    if not rc["available"]:
        return None
    if turns is None:
        ts = turning_spaces(plan, d)
        turns = {t["room"]: t["diameter"] for t in ts.get("rooms", [])}
    rows = []
    for r in rc["rooms"]:
        if r["void"]:
            continue
        reached = r["result"] in ("likely pass", "measure on site")
        dia = turns.get(r["room"])
        turn_ok = dia is not None and judge(dia, d) != "likely fail"
        rows.append({"room": r["room"], "label": r["label"], "reached": reached, "turn": dia, "turn_ok": turn_ok,
                     "usable": reached and turn_ok, "unsure": r["result"] == "measure on site"})
    return {"rooms": rows, "turns": turns, "all": bool(rows) and all(x["usable"] for x in rows)}


def variants(w: float, d: float, s: float) -> list[tuple[str, str, float, float, float]]:
    return [("as_given", "As given", w, d, s),
            ("narrower_5cm", "5 cm narrower", max(0.05, w - 0.05), d, s),
            ("step_plus_1cm", "Climbs 1 cm higher", w, d, s + 0.01),
            ("step_plus_2cm", "Climbs 2 cm higher", w, d, s + 0.02),
            ("turn_minus_10cm", "Turning circle 10 cm smaller", w, max(0.1, d - 0.1), s)]


@tool(id="robot_fit", title="Robot fit", icon="robot",
      summary="Shows which rooms a robot of a given width, turning circle and step height can reach and turn in, "
              "across one home or many, and which single change to the robot gains the most.",
      model_description="For a wheeled body (width, turning diameter, climbable step), the share of rooms and of "
                        "homes it can reach from the entrance and turn in, over one scan, a list, or every measured "
                        "scan; and the gain from each single change (5 cm narrower, 1 or 2 cm more step, 10 cm "
                        "tighter turn), best first.",
      personas=[], requires=[{"layer": "matterport.walls"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "Controls", "AssumptionChips", "StepLog"],
      overlays=["lens"], annotations={"cost": "slow"},
      examples=["What share of homes can a 50 cm robot reach every room of?",
                "Would a narrower robot or a better step climber help more?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    w, d, s = inputs.body_width_m, inputs.turning_diameter_m, inputs.step_height_m
    sids = [inputs.scan] if inputs.scan and not inputs.scans else inputs.scans or table.scan_ids(walls=True)
    assumptions = [Assumption(id="robot.body_width_m", label="Robot width", value=w, unit="m", editable=True),
                   Assumption(id="robot.turning_diameter_m", label="Turning circle", value=d, unit="m", editable=True),
                   Assumption(id="robot.step_height_m", label="Highest step it climbs", value=s, unit="m",
                              editable=True),
                   Assumption(id="sill_noise", label="Doorway sills scatter about 4 cm on flat floors, so a step "
                                                     "blocks only above the climb height plus 4 cm", value=STEP_TOL,
                              unit="m"),
                   Assumption(id="empty", label="Empty rooms; rugs, cables and furniture not counted", value=True)]
    vs = variants(w, d, s)
    tally = {v[0]: {"rooms": 0, "usable": 0, "homes": 0, "homes_all": 0} for v in vs}
    single = None
    skipped = 0
    for sid in sids:
        try:
            plan = ctx.plan(sid)
        except Exception:
            skipped += 1
            continue
        base = fit_scan(plan, w, d, s)
        if base is None:
            skipped += 1
            continue
        for key, _, vw, vd, vstep in vs:
            r = base if key == "as_given" else fit_scan(plan, vw, vd, vstep,
                                                        base["turns"] if vd == d else None)
            t = tally[key]
            t["rooms"] += len(r["rooms"])
            t["usable"] += sum(x["usable"] for x in r["rooms"])
            t["homes"] += 1
            t["homes_all"] += r["all"]
        if len(sids) == 1:
            single = (sid, plan, base)
    measured = tally["as_given"]["homes"]
    ctx.step(f"Tested {measured} scans with a wall graph ({skipped} could not be measured)")
    share = lambda k, f: (tally[k][f[0]] / tally[k][f[1]]) if tally[k][f[1]] else None
    room_share = {k: share(k, ("usable", "rooms")) for k in tally}
    home_share = {k: share(k, ("homes_all", "homes")) for k in tally}
    scope = ScanScope(sid=sids[0]) if len(sids) == 1 else ScansScope(sids=sids)
    if not measured:
        return ToolResult(scope=scope, assumptions=assumptions, verdict=Verdict(status="unknown", text=(
            "None of these scans has a wall graph, so reach cannot be measured.")))
    gains = sorted(((room_share[k] - room_share["as_given"], k, lab) for k, lab, *_ in vs[1:]), reverse=True)
    best = gains[0]
    checks = [Check(id=f"variant.{k}", rule=f"{lab}: share of rooms reached and turnable", unit="%",
                    measured=round(100 * room_share[k], 1), threshold=None,
                    status="pass" if room_share[k] >= 0.9 else "warn" if room_share[k] >= 0.5 else "fail")
              for k, lab, *_ in vs]
    src = Source(layer="matterport", method="geometry", confidence="medium",
                 note=f"Reach from the entrance over the wall graph and the largest circle per room, {measured} scans")
    metrics = [Metric(id="rooms_share", label="Rooms reached and turnable", value=round(100 * room_share["as_given"], 1),
                      unit="%", source=src),
               Metric(id="homes_share", label="Homes with every room usable", value=round(100 * home_share["as_given"], 1),
                      unit="%", source=src),
               Metric(id="best_gain", label=f"Best single change: {best[2].lower()}", value=round(100 * best[0], 1),
                      unit="points", source=src),
               Metric(id="scans", label="Scans measured", value=measured, unit="", source=src)]
    metrics += [Metric(id=f"gain.{k}", label=lab, value=round(100 * g, 1), unit="points", source=src)
                for g, k, lab in gains]
    findings, overlays = [], []
    if single:
        sid, plan, base = single
        for x in base["rooms"]:
            if not x["usable"]:
                why = "cannot get in (door too narrow or a step too high)" if not x["reached"] else \
                    "can get in but not turn round"
                findings.append(Finding(id=f"robot_fit:{sid}:{x['room']}", title=f"{x['label']}: {why}", status="fail",
                                        anchor=RoomAnchor(sid=sid, room=x["room"]), source=GEO,
                                        detail=f"Largest circle {x['turn']:.2f} m against {d:.2f} m."
                                        if x["turn"] is not None else "No floor outline for this room."))
        overlays.append(LensOverlay(values={x["room"]: 1.0 if x["usable"] else 0.5 if x["reached"] else 0.0
                                            for x in base["rooms"]}, ramp="status",
                                    legend=Legend(title="Robot can reach and turn", unit="", min=0, max=1)))
    rs = room_share["as_given"]
    status = "pass" if rs >= 0.9 else "warn" if rs >= 0.5 else "fail"
    text = (f"The robot reaches and turns in {100 * rs:.0f}% of rooms"
            + (f"; {100 * home_share['as_given']:.0f}% of the {measured} homes are fully usable" if measured > 1 else "")
            + (f". {best[2]} gains the most rooms." if best[0] > 0 else ". No single change gains rooms."))
    return ToolResult(scope=scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays, assumptions=assumptions)
