"""Driveway fit: how long and wide the driveway is, how many cars park on it, and whether a long vehicle (trailer, RV,
boat) fits off the street. From above: Vexcel's detector boxes the driveway, the parcel line ends it at the street,
and the orthophoto's paved colour gives its width at stations along it. With a scan whose garage door was recorded,
the driveway starts at that door and runs out from it; otherwise it runs from the house toward the driveway box.
Aerial estimates: medium for length (parcel lines and the scan's placement are good to a couple of metres), low for
width (colour edges, shade and parked cars)."""
from __future__ import annotations

import math
import statistics
from typing import Literal

from shapely import wkt as shapely_wkt
from shapely.geometry import Point
from shapely.ops import unary_union

from ...aerial import detect as aerial_detect
from .. import Assumption, Check, Finding, Metric, Source, ToolResult, Verdict, field, tool
from ..garage_fit import geom as garage_geom
from ..garage_fit.vehicles import VEHICLES
from ..types import BoxOverlay
from .._site import Where, capture, fact, footprint, geo, geo_route, locate, metres, ortho_media, parcel, pin, pins, src, to_m

STALL = (5.2, 2.5)       # a car parked nose to tail on a driveway, and its 8 ft lane: length by width
MIN_LANE_M = 2.3         # narrower than this a car cannot park without blocking the walk
CAR_LANE_EXTRA = 0.3     # driveways are laid a little wider than whole stalls: 5.1 m holds two cars side by side
MAX_DRIVEWAY_M2 = 600.0  # Vexcel also boxes streets and whole cul-de-sacs as "driveway"
STATION_M = 1.5
LEN_SRC = Source(layer="vexcel", method="geometry", confidence="medium",
                 note="From the garage door or house to the parcel line along the driveway: Vexcel parcel and the scan's "
                      "placement on the aerial footprint, each good to about 2 m")
WIDTH_SRC = Source(layer="vexcel", method="geometry", confidence="low",
                   note="Paved width across the driveway on the orthophoto by colour, median of stations every 1.5 m; "
                        "shade, stains and parked cars move the edges")
DET_SRC = Source(layer="vexcel", method="vision", confidence="low",
                 note="Vexcel Custom Elements (SAM 3) 'driveway' boxes on the orthophoto; boxes are square to north")


class Inputs(Where):
    vehicle: Literal[tuple(VEHICLES)] = field("boat_20ft", ask="What long vehicle must fit off the street? " + "; ".join(
        f"{k}: {v.label}" for k, v in VEHICLES.items()), pref="driveway.vehicle",
        description="A vehicle that must park on the driveway, off the street (trailer, RV, boat, truck)")
    length_m: float | None = field(None, gt=1, le=20, unit="m", pref="driveway.length_m",
                                   description="Custom vehicle length, with tongue or hitch")
    width_m: float | None = field(None, gt=0.5, le=3.5, unit="m", pref="driveway.width_m", description="Custom width")


def _start_axis(ctx, s, fp_m, lat0, drives_m):
    """(start point, unit direction, how) in local metres. The scan's garage door when it has one, else the house edge
    facing the driveway box nearest the house."""
    if s.sid:
        try:
            plan = ctx.plan(s.sid)
            gs = garage_geom.find_garages(plan)
            sv = garage_geom.survey(plan, gs[0]["room"]) if gs else None
            if sv and sv["doors"] and (plan.get("geo") or {}).get("lat") is not None:
                from ...geometry import georef
                f = sv["frames"][0]
                d = max(sv["doors"], key=lambda x: x["width"])
                cx, cy = d["center"]
                out = (-f.v[0], -f.v[1])  # v points into the garage; the driveway runs the other way
                fwd = to_m(lat0)[0]
                p0 = fwd(*reversed(georef.to_latlon(plan, cx, cy)))
                p1 = fwd(*reversed(georef.to_latlon(plan, cx + out[0], cy + out[1])))
                n = math.dist(p0, p1) or 1.0
                return p0, ((p1[0] - p0[0]) / n, (p1[1] - p0[1]) / n), "garage door", plan, (cx, cy, out, d["width"])
        except Exception as e:  # noqa: BLE001  a scan that will not load still has an aerial answer
            ctx.step(f"Could not use the scan's garage door: {str(e)[:100]}")
    if fp_m is None or not drives_m:
        return None, None, None, None, None
    near = min(drives_m, key=lambda g: g.distance(fp_m))
    c = near.centroid
    p0 = fp_m.exterior.interpolate(fp_m.exterior.project(c))
    n = math.dist((p0.x, p0.y), (c.x, c.y)) or 1.0
    return (p0.x, p0.y), ((c.x - p0.x) / n, (c.y - p0.y) / n), "house edge", None, None


def _run_inside(geom_m, p0, u, cap: float = 60.0, step: float = 0.25) -> float:
    """How far from p0 along u the line stays inside geom_m (gaps under 1 m bridged)."""
    d, last, miss = 0.0, 0.0, 0.0
    while d < cap:
        d += step
        if geom_m.contains(Point(p0[0] + u[0] * d, p0[1] + u[1] * d)):
            last, miss = d, 0.0
        else:
            miss += step
            if miss > 1.0 and last > 0 or miss > 3.0:
                break
    return last


@tool(id="driveway_fit", title="Driveway fit", icon="car",
      summary="Estimates the driveway's length and width from the aerial photo, how many cars park on it, and whether "
              "a trailer, RV or boat fits off the street.",
      model_description="For any house in Houston or Los Angeles (a scan, or a point): driveway length from the garage "
                        "door or house to the parcel line, paved width on the orthophoto, how many cars park on it "
                        "(5.2 x 2.5 m each), and whether a long vehicle from the garage_fit table (trailer, boat, RV, "
                        "truck) fits on it without sticking into the sidewalk. Aerial estimates, labelled medium or low.",
      personas=["car_owner", "wheelchair_van_owner", "rv_boat_owner"], requires=[{"layer": "vexcel.ortho"}, {"layer": "vexcel.property"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "AssumptionChips", "StepLog"],
      overlays=["pins", "route", "box"], annotations={"cost": "slow"},
      examples=["How many cars fit on the driveway?", "Can I park my boat trailer off the street here?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    v = VEHICLES[inputs.vehicle]
    vl, vw = inputs.length_m or v.length, inputs.width_m or v.width
    name = v.label if not (inputs.length_m or inputs.width_m) else "Custom vehicle"
    s = locate(ctx, inputs)
    lat0 = s.lat
    pc, fp = parcel(s), footprint(s)
    base = [Assumption(id="driveway.length_m", label=f"{name.split(',')[0]} length", value=vl, unit="m", editable=True),
            Assumption(id="driveway.width_m", label="Width", value=vw, unit="m", editable=True),
            Assumption(id="stall", label="Room per parked car, length by width", value="5.2 m by 2.5 m"),
            Assumption(id="street", label="The sidewalk and the strip between the parcel line and the curb are the "
                       "city's: parking there is not counted", value=True)]
    if pc is None:
        return ToolResult(scope=s.scope, assumptions=base, verdict=Verdict(status="unknown", text=(
            "Vexcel has no parcel here, so the driveway cannot be ended at the property line.")))
    pc_m = metres(pc, lat0)
    fp_m = metres(fp, lat0) if fp is not None else None
    ctx.step("Looking for the driveway on the orthophoto (Vexcel detector, cached)")
    det = aerial_detect.detect(s.lat, s.lon, 60, ["driveway"], threshold=0.3, keep_large=True)
    drives = []
    for d in det["detections"]:
        if d["image"] not in ("spherical-ortho", "ortho"):
            continue
        g = metres(shapely_wkt.loads(d["polygon"]), lat0)
        if 10 < g.area <= MAX_DRIVEWAY_M2 and g.intersects(pc_m.buffer(2)) and (fp_m is None or g.distance(fp_m) < 8):
            drives.append(g)
    p0, u, how, plan, door = _start_axis(ctx, s, fp_m, lat0, drives)
    if p0 is None:
        return ToolResult(scope=s.scope, assumptions=base, verdict=Verdict(status="unknown", text=(
            "No driveway was found on the aerial photo next to the house, and the scan records no garage door to "
            "start from.")))
    to_lot = _run_inside(pc_m.buffer(0.3), p0, u)
    paved = unary_union(drives).buffer(0.5) if drives else None
    on_paved = _run_inside(paved, p0, u) if paved is not None else None
    length = min(to_lot, on_paved) if on_paved else to_lot
    ctx.step(f"Driveway from the {how}: {to_lot:.1f} m to the parcel line" +
             (f", {on_paved:.1f} m on the detected paving" if on_paved else ", no paving detected along it"))
    widths = []
    try:
        from ..truck_access import Photo, paved_run
        photo = Photo(s.lat, s.lon, max(60.0, 2 * length + 20))
        back = to_m(lat0)[1]
        dd = 1.0
        while dd < length - 0.5:
            w = paved_run(photo, lat0, back(p0[0] + u[0] * dd, p0[1] + u[1] * dd), u, cap_m=14)
            if w:
                widths.append(w)
            dd += STATION_M
        ctx.step(f"Paved width at {len(widths)} stations along it")
    except Exception as e:  # noqa: BLE001  no ortho: the width falls back to the door or the box
        ctx.step(f"Orthophoto width unavailable: {str(e)[:100]}")
    width = statistics.median(widths) if widths else None
    wsrc = WIDTH_SRC
    if width is None and door:
        width, wsrc = door[3], Source(layer="matterport", method="geometry", confidence="low",
                                      note="No paved width from the photo: the garage door's width stands in")
    lanes = max(1, int((width + CAR_LANE_EXTRA) // STALL[1])) if width and width >= MIN_LANE_M else 0
    rows = int(length // STALL[0])
    cars = lanes * rows
    lsrc = LEN_SRC if how == "garage door" else Source(**{**LEN_SRC.model_dump(), "confidence": "low",
                                                          "note": "From the house edge toward the detected driveway to the parcel line; the garage door is not known"})
    # the long vehicle
    need_l, need_w = vl + 0.3, vw + 0.3
    st_l = "pass" if length >= need_l else "warn" if length >= vl else "fail"
    st_w = "unknown" if width is None else "pass" if width >= need_w else "warn" if width >= vw else "fail"
    checks = [Check(id="long_length", rule=f"Driveway long enough for the {name.split(',')[0]} off the street",
                    measured=round(length, 2), threshold=round(need_l, 2), unit="m", status=st_l,
                    standard="Vehicle length plus 0.3 m; the sidewalk stays clear"),
              Check(id="long_width", rule=f"Driveway wide enough for the {name.split(',')[0]}",
                    measured=round(width, 2) if width else None, threshold=round(need_w, 2), unit="m", status=st_w,
                    standard="Vehicle width plus 0.3 m")]
    status = "fail" if "fail" in (st_l, st_w) else "warn" if "warn" in (st_l, st_w) or st_w == "unknown" else "pass"
    short = name.split(",")[0].split(" (")[0]  # garage_fit.short() takes its Dims; this is the same cut
    text = (f"The driveway is about {length:.0f} m long and {width:.1f} m wide: room for {cars} car{'s' if cars != 1 else ''}"
            if width else f"The driveway is about {length:.0f} m long (width not measured): room for {rows} car{'s' if rows != 1 else ''} in a line")
    text += {"pass": f", and the {short.lower() if short[0].islower() else short} fits off the street.",
             "warn": f"; the {short} is a tight fit, measure before buying.",
             "fail": f"; the {short} would stick out into the sidewalk or street."}[status]
    text += " Aerial estimate."
    back = to_m(lat0)[1]
    end = (p0[0] + u[0] * length, p0[1] + u[1] * length)
    a, b = back(*p0), back(*end)
    k = s.key
    findings = [Finding(id=f"driveway_fit:{k}:driveway", title="The driveway from above", status=status,
                        anchor=geo(*a), source=lsrc, media=[ortho_media(s, max(40.0, 2 * length + 15))],
                        detail=f"From the {how} to the parcel line along the driveway; {len(drives)} driveway box"
                               f"{'es' if len(drives) != 1 else ''} detected on the parcel.")]
    stall_pins = [pin(f"car_{i}_{j}", *back(p0[0] + u[0] * (STALL[0] * (i + 0.5)) + (-u[1]) * STALL[1] * (j - (lanes - 1) / 2),
                                         p0[1] + u[1] * (STALL[0] * (i + 0.5)) + u[0] * STALL[1] * (j - (lanes - 1) / 2)),
                      f"car {i * lanes + j + 1}", "pass") for i in range(rows) for j in range(lanes)]
    overlays = [geo_route([a, b], "Driveway"), *pins([pin("start", *a, how.capitalize(), "pass"),
                                                       pin("lot_line", *b, "Parcel line", status), *stall_pins])]
    if plan is not None and door:  # draw the long vehicle on the driveway in the scan's own frame, out from the door
        cx, cy, out, _ = door
        mid = 0.15 + vl / 2
        from ...geometry._plan import floor_z
        z = min(floor_z(plan).values(), default=0.0)
        overlays.append(BoxOverlay(center=(round(cx + out[0] * mid, 3), round(cy + out[1] * mid, 3), round(z + v.height / 2, 3)),
                                   size=(round(vl, 2), round(vw, 2), v.height), yaw_deg=round(math.degrees(math.atan2(out[1], out[0])), 1),
                                   label=short, status=status))
    metrics = [Metric(id="length", label="Driveway length", value=round(length, 1), unit="m", source=lsrc),
               Metric(id="width", label="Driveway width", value=round(width, 1) if width else None, unit="m", source=wsrc),
               Metric(id="cars", label="Cars that park on it", value=cars if width else None, unit="", source=lsrc),
               Metric(id="to_lot_line", label="House or garage door to the parcel line", value=round(to_lot, 1), unit="m", source=lsrc)]
    if widths:
        metrics.append(Metric(id="width_min", label="Narrowest paved width", value=round(min(widths), 1), unit="m", source=WIDTH_SRC))
    vf = fact(s, "vehicles")
    if vf is not None:
        metrics.append(Metric(id="vehicles_vexcel", label=f"Vehicles on the parcel on {capture(s)}", value=vf, unit="",
                              source=src(s, "vehicles")))
    return ToolResult(scope=s.scope, verdict=Verdict(status=status, text=text), metrics=metrics, checks=checks,
                      findings=findings, overlays=overlays, assumptions=base)
