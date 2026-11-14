"""Window check: stand at a window, point the phone straight out, and its compass says which way the window faces.
That confirms or corrects the daylight tool's facing and sun hours for the room, which otherwise rest on the scan's
compass rotation."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from ... import geometry
from ...geometry import georef
from .. import Assumption, Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from .._phone import anchor, key, media, scope, source

# Magnetic declination, degrees east of true north, for the cities the scans are in and the event's own.
# shortcut: three rounded values (World Magnetic Model 2025, to about half a degree); use the model itself for anywhere else.
DECLINATION = [((29.76, -95.37), 1.6, "Houston"), ((34.05, -118.24), 11.2, "Los Angeles"), ((40.35, -74.66), -12.6, "Princeton")]
INDOOR_ERR_DEG = 15.0   # a phone compass indoors, near steel, wiring and appliances
SCAN_ERR_DEG = {True: 3.0, False: 10.0}  # the scan's own facing: checked against the footprint, or not
CONTRADICT_DEG = 45.0   # beyond this the two cannot both be right


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    room: str = field(description="Room id the window is in")
    heading_deg: float = field(ge=0, lt=360, description="Compass heading of the phone's top edge, pointing out of the window")
    magnetic: bool = field(True, description="The heading is from magnetic north (what phone browsers give)")
    heading_accuracy_deg: float | None = field(None, ge=0, le=180, description="The phone's own figure, when it gives one")
    lat: float | None = field(None, description="From the phone's fix, used when the scan has no location")
    lon: float | None = None
    date: str | None = field(None, pref="daylight.date", pattern=r"^\d{4}-\d{2}-\d{2}$")
    capture: str | None = None
    by_hand: bool = field(False, description="The direction was picked by hand (one of eight), not read from the compass")


def declination(lat: float | None, lon: float | None) -> tuple[float, str | None]:
    if lat is None or lon is None:
        return 0.0, None
    (_, d, city), dist = min(((x, abs(x[0][0] - lat) + abs(x[0][1] - lon)) for x in DECLINATION), key=lambda p: p[1])
    return (d, city) if dist < 3 else (0.0, None)


def apart(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def sun_hours(azimuth: float, lat: float, lon: float, day: dt.date, step_min: int = 10) -> float:
    """Hours the sun is up and in front of a window facing `azimuth`: the daylight tool's own rule."""
    zone = ZoneInfo(georef.guess_timezone(lon))
    start = dt.datetime.combine(day, dt.time(0, 0), zone)
    n = 0
    for m in range(0, 24 * 60, step_min):
        az, el = georef.sun_position(start + dt.timedelta(minutes=m), lat, lon)
        n += el > 0 and apart(az, azimuth) < 90
    return n * step_min / 60


def _picked(capture: str | None) -> bool:
    """The phone app marks a direction picked by hand with values.magnetic = false (no compass on that phone)."""
    from ...capture import store
    try:
        return capture is not None and (store.get(capture).get("values") or {}).get("magnetic") is False
    except LookupError:
        return False


@tool(id="window_check", title="Window check", icon="compass",
      summary="Point the phone out of a window: its compass confirms or corrects which way the room faces and its "
              "hours of sun.",
      model_description="Phone only: a person runs this from the phone app, an agent cannot. Compare a phone compass heading taken at a window with the scan's facing for that room's "
                        "windows (the daylight tool's source), and recompute direct sun hours for the heading. Needs "
                        "a heading from the phone app.",
      requires=[{"layer": "phone.compass"}, {"layer": "matterport.geo", "need": "optional",
                                             "fallback": "the phone's facing only, nothing to compare with"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "AssumptionChips", "StepLog"],
      examples=["Does the bedroom really face east?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    if not inputs.by_hand and _picked(inputs.capture):
        inputs = inputs.model_copy(update={"by_hand": True, "magnetic": False})  # a picked N or E is true north
    plan = ctx.plan(inputs.scan)
    room = next((r for r in plan.get("rooms") or [] if r["id"] == inputs.room), None)
    name = (room or {}).get("label") or "Unlabelled room"
    g = plan.get("geo") or {}
    lat, lon = (g.get("lat"), g.get("lon")) if g.get("lat") is not None else (inputs.lat, inputs.lon)
    dec, city = declination(lat, lon) if inputs.magnetic else (0.0, None)
    heading = (inputs.heading_deg + dec) % 360
    err = max(INDOOR_ERR_DEG, inputs.heading_accuracy_deg or 0)
    ctx.step(f"Heading {inputs.heading_deg:.0f} degrees" + (f", {dec:+.1f} for magnetic declination at {city}" if city
             else ", no declination applied" if inputs.magnetic else " from true north"))
    src = source("manual", "low", f"Direction picked by hand at the window, give or take {err:.0f} degrees") if inputs.by_hand \
        else source("sensor", "low" if err > 20 or (inputs.magnetic and city is None) else "medium",
                    f"Phone compass at the window, give or take {err:.0f} degrees indoors")
    day = dt.date.fromisoformat(inputs.date) if inputs.date else dt.date.today()
    hours = round(sun_hours(heading, lat, lon, day), 1) if lat is not None and lon is not None else None
    facing = geometry.facing(plan)
    wins = [o for o in facing["openings"] if o["type"] == "window" and o["room"] == inputs.room] if facing["available"] else []
    fid = f"window_check:{key(inputs.scan, inputs.room)}"
    metrics = [Metric(id="heading_deg", label="Window faces (phone)", value=round(heading), unit="deg", source=src),
               Metric(id="sun_phone_h", label="Direct sun by the phone's facing", value=hours, unit="h", source=src)]
    assumptions = [Assumption(id="daylight.date", label="Day traced", value=day.isoformat(), editable=True),
                   Assumption(id="declination", label="Magnetic declination applied", value=round(dec, 1), unit="deg"),
                   Assumption(id="no_shading", label="Trees, neighbours, eaves and blinds are not counted", value=True)]
    said = f"By the phone the window in the {name.lower()} faces {georef.compass(heading)}"
    if not wins:
        why = "the scan has no compass rotation" if not facing["available"] else "the scan marks no window in this room"
        return ToolResult(
            scope=scope(inputs.scan), metrics=metrics, assumptions=assumptions,
            verdict=Verdict(status="unknown", text=f"{said}; {why}, so there is nothing to compare it with."),
            findings=[Finding(id=fid, title=f"Window facing in the {name.lower()}, read on site", status="unknown", source=src,
                              anchor=anchor(inputs.scan, inputs.room), media=media(inputs.capture),
                              detail=f"{heading:.0f} degrees ({georef.compass(heading)}), give or take {err:.0f}."
                                     + (f" {hours:.1f} h of direct sun on {day.isoformat()}." if hours is not None else ""))])
    w = min(wins, key=lambda o: apart(o["azimuth_deg"], heading))
    diff = apart(w["azimuth_deg"], heading)
    verified = bool(facing.get("verified") and (plan.get("quality") or {}).get("georef"))
    tol = err + SCAN_ERR_DEG[verified]
    status = "pass" if diff <= tol else "fail" if diff > max(CONTRADICT_DEG, tol) else "warn"
    scan_hours = round(sun_hours(w["azimuth_deg"], lat, lon, day), 1)
    ctx.step(f"The scan's nearest window in this room faces {w['azimuth_deg']:.0f} degrees: {diff:.0f} apart")
    metrics += [Metric(id="scan_deg", label="Window faces (scan)", value=round(w["azimuth_deg"]), unit="deg",
                       source=Source(layer="matterport", method="geometry", confidence="medium" if verified else "low",
                                     note="Wall normal turned by the scan's compass rotation")),
                Metric(id="difference_deg", label="Apart", value=round(diff), unit="deg", source=src),
                Metric(id="sun_scan_h", label="Direct sun by the scan's facing", value=scan_hours, unit="h", source=src)]
    text = {"pass": f"{said}, which agrees with the scan ({w['compass']}).",
            "warn": f"{said}; the scan says {w['compass']}. Too far apart to agree, too close to call wrong: "
                    + ("a direction picked from eight cannot settle it." if inputs.by_hand else "read it again away from metal."),
            "fail": f"{said}; the scan says {w['compass']}. They cannot both be right, and the sun hours change with it."}[status]
    return ToolResult(
        scope=scope(inputs.scan), verdict=Verdict(status=status, text=text), metrics=metrics, assumptions=assumptions,
        checks=[Check(id="facing", rule=f"Window facing, {name}: phone against scan", measured=round(diff), threshold=round(tol),
                      unit="deg", status=status, findings=[fid]),
                Check(id="sun", rule=f"Direct sun, {name}: by the phone's facing", measured=hours, threshold=scan_hours,
                      unit="h", status=status, kind="claim", findings=[fid])],
        findings=[Finding(id=fid, title=f"Window facing in the {name.lower()}, read on site", status=status, source=src,
                          anchor=anchor(inputs.scan, inputs.room, w["opening"]), media=media(inputs.capture),
                          detail=f"Phone: {heading:.0f} degrees ({georef.compass(heading)}), give or take {err:.0f}. "
                                 f"Scan: {w['azimuth_deg']:.0f} degrees ({w['compass']}), "
                                 f"{'checked against the building footprint' if verified else 'not checked against an aerial photo'}. "
                                 f"Direct sun on {day.isoformat()}: {hours:.1f} h by the phone, {scan_hours:.1f} h by the scan.")])
