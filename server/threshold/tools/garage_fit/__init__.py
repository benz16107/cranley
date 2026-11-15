"""Garage fit: does a vehicle fit in this garage? The garage is found from room labels or a ground-floor room with a
car-wide door; its door, inside width, depth and ceiling come from the wall graph; the vehicle comes from a table of
common models or custom sizes. Answers fits / tight / does not fit, how many fit side by side, the room on each side
to open doors and walk round, headroom under the door for a lift or a roof box, and room left for a bench, a charger,
a motorcycle or a rack. The vehicles are drawn parked as Contract 4 boxes, coloured by their clearance.
With `search_city` it searches every scanned house in a city instead (search.py)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .. import (Action, ToolError, Assumption, Check, Finding, Metric, OpeningAnchor, PointAnchor, RoomAnchor, RuleOverlay,
                ScanScope, Source, ToolResult, Verdict, field, tool)
from ..types import BoxOverlay
from .._access import cannot, fmt, has_objects
from . import geom
from .park import Dims, analyse, pair, things
from .vehicles import THING_MODEL, THINGS, VEHICLES, model_of

IN = 0.0254
GEO = Source(layer="matterport", method="geometry", confidence="medium",
             note="Wall graph of the empty garage; walls at their inner face; door widths are the opening in the wall")
GEO_LOW = Source(layer="matterport", method="geometry", confidence="low",
                 note="Part of this rests on an assumption named in the result (a door the scan did not measure)")
SPEC = Source(layer="model", method="lookup", confidence="medium",
              note="Maker's published size for a recent model year, base trim; edit it for yours")
WORD = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}
Use = Literal[tuple(THINGS)]


class Inputs(BaseModel):
    scan: str | None = field(None, source="selection.scan", description="Scan id (leave empty with search_city)")
    vehicle: Literal[tuple(VEHICLES)] = field("ford_f150", ask="Which vehicle? " + "; ".join(
        f"{k}: {v.label}" for k, v in VEHICLES.items()), pref="garage.vehicle",
        description="A vehicle from the built-in table; its sizes are editable assumptions")
    second_vehicle: Literal[tuple(VEHICLES)] | None = field(
        None, pref="garage.second_vehicle", description="A second, different vehicle to park beside the first (an "
                                                       "F-150 and a Highlander); checks both, each with its own doors")
    count: int | None = field(None, ge=0, le=5, pref="garage.count",
                              description="How many of the vehicle must fit side by side; empty for as many as fit, "
                                          "0 for none (an empty garage for a gym or workshop)")
    length_m: float | None = field(None, gt=1, le=15, unit="m", pref="garage.length_m", description="Custom length")
    storage_length_m: float | None = field(None, gt=1, le=15, unit="m", pref="garage.storage_length_m",
                                           description="Boats and trailers: the maker's storage length (motor trimmed "
                                                       "up, tongue swung or off), used instead of the overall length")
    width_m: float | None = field(None, gt=0.5, le=3.5, unit="m", pref="garage.width_m",
                                  description="Custom body width, mirrors folded")
    mirror_width_m: float | None = field(None, gt=0.5, le=3.5, unit="m", pref="garage.mirror_width_m",
                                         description="Custom width with mirrors out")
    height_m: float | None = field(None, gt=0.5, le=5, unit="m", pref="garage.height_m", description="Custom height")
    lift_in: float = field(0, ge=0, le=12, unit="in", pref="garage.lift_in",
                           description="Suspension lift plus bigger tyres, inches added to the height")
    roof_load_m: float = field(0, ge=0, le=1.5, unit="m", pref="garage.roof_load_m",
                               description="Roof box, rack or bikes: metres above the roof (a cargo box is about 0.45)")
    uses: list[Use] = field(["workbench", "ev_charger"], pref="garage.uses",
                            description="Also find room for: workbench, ev_charger, motorcycle, bikes, squat_rack "
                                        "(home gym: an 8 x 8 ft platform and overhead-press headroom)")
    lifter_height_m: float = field(1.78, gt=1.2, le=2.2, unit="m", pref="garage.lifter_height_m",
                                   description="Height of the person pressing overhead, for the home gym check")
    room: str | None = field(None, description="Room id of the garage, if not the one found")
    which_fit: bool = field(False, description="Turn it round: try every vehicle in the table in this garage and "
                                               "list the ones that fit, with the room to spare")
    search_city: Literal["Houston", "Los Angeles", "any"] | None = field(
        None, description="Search every scanned house in this city for a garage that fits `count` of the vehicle "
                          "(default two) instead of checking one scan")
    limit: int = field(20, ge=1, le=100, description="Search: homes to return")


def dims(inputs: Inputs) -> Dims:
    v = VEHICLES[inputs.vehicle]
    custom = any(x is not None for x in (inputs.length_m, inputs.width_m, inputs.mirror_width_m, inputs.height_m))
    w = inputs.width_m or v.width
    stored = inputs.storage_length_m if inputs.length_m is None else None
    return Dims(label=("Custom vehicle" if custom else v.label) + (", storage length" if stored else ""),
                length=inputs.length_m or stored or v.length, width=w,
                mirrors=inputs.mirror_width_m or max(v.mirrors, w), towed=v.towed, ramp=v.ramp, door=v.door,
                height=round((inputs.height_m or v.height) + inputs.lift_in * IN + inputs.roof_load_m, 3))


def catalog_dims(vid: str) -> Dims:
    v = VEHICLES[vid]
    return Dims(label=v.label, length=v.length, width=v.width, mirrors=v.mirrors, height=v.height, door=v.door,
                ramp=v.ramp, towed=v.towed)


def pair_part(sid: str, a: dict, d: Dims, d2: Dims, z0: float, src) -> dict:
    """Checks, findings, boxes and a sentence for two different vehicles side by side."""
    pr = a["pair"] = pair(a, d, d2)  # kept on the analysis so extras and storage go round both vehicles
    f = a["frame"]
    out = {"status": pr["status"], "checks": [], "findings": [], "boxes": []}
    names = f"{short(d)} and {short(d2)}"
    out["checks"].append(Check(id="pair", rule=f"{names} side by side", measured=None, threshold=None, unit="",
                               status=pr["status"], standard="Each vehicle keeps its own door room beside it and "
                                                             f"{geom.FRONT_FITS_M:.2f} m ahead to walk round; tight "
                                                             f"down to {geom.SQUEEZE_M:.2f} m to squeeze out"))
    for k, (car, (u, v), c) in enumerate(zip(pr["order"], pr["cars"], pr["clear"])):
        tag = short(car)
        need = car.door if not car.towed else 0.6
        for side in ("left", "right"):
            if c.get(side) is None:
                continue
            st = "pass" if c[side] >= need - 0.01 else "warn" if c[side] >= geom.SQUEEZE_M - 0.01 else "fail"
            out["checks"].append(Check(id=f"pair{k}.{side}", rule=f"{tag}, {side} side: room to open the doors",
                                       measured=round(c[side], 3), threshold=round(need, 3), unit="m", status=st))
        if c.get("front") is not None:
            st = "pass" if c["front"] >= geom.FRONT_FITS_M - 0.01 else "warn" if c["front"] >= geom.FRONT_TIGHT_M - 0.01 \
                else "fail"
            out["checks"].append(Check(id=f"pair{k}.front", rule=f"{tag}: room ahead of the bumper to walk round",
                                       measured=round(c["front"], 3), threshold=geom.FRONT_FITS_M, unit="m", status=st))
        out["boxes"].append(_box(f, u, v, car.width, car.length, car.height, z0, tag, pr["status"]))
    if pr["status"] == "fail":
        out["findings"].append(Finding(id=f"garage_fit:{sid}:pair", title=f"{names} do not fit side by side",
                                       status="fail", source=src, anchor=None,
                                       detail=f"Not even squeezed: {fmt(d.width)} and {fmt(d2.width)} wide with "
                                              f"{geom.SQUEEZE_M:.2f} m beside each, in {fmt(a['width'])} inside."))
    out["text"] = {"pass": f" The {names} fit side by side with room to open the doors.",
                   "warn": f" The {names} fit side by side only tight: you squeeze out of the doors.",
                   "fail": f" The {names} do not fit side by side."}[pr["status"]]
    return out


def which_fit(ctx, sid: str, plan: dict, g: dict, base: list) -> ToolResult:
    """Every vehicle in the table parked alone in this garage, best fits first, with depth and side room to spare."""
    rows = []
    for vid in VEHICLES:
        d = catalog_dims(vid)
        a = analyse(plan, g, d, 1)
        if a is None:
            return ToolResult(scope=ScanScope(sid=sid), assumptions=base, verdict=Verdict(status="unknown", text=(
                "The scan has a garage but no outline for it, so it cannot be measured.")))
        dh, measured = a["door_height"], a["door_height_measured"]
        h = judge_h(round(dh - d.height, 3)) if measured else "warn" if d.height + geom.HEIGHT_TIGHT_M > dh else "pass"
        st = max((a["status"], h), key=["pass", "warn", "fail"].index)
        c = (a["clear"] or [{}])[0]
        sides = [x for x in (c.get("left"), c.get("right")) if x is not None]
        depth = round(a["depth"] - d.length - geom.REAR_M - geom.FRONT_FITS_M, 2) if a["depth"] else None
        rows.append((st, vid, d, depth, round(min(sides) - (d.door if not d.towed else 0.6), 2) if sides else None))
    rows.sort(key=lambda r: (["pass", "warn", "fail"].index(r[0]), -r[2].length))
    word = {"pass": "fits with doors open", "warn": "fits tight", "fail": "does not fit"}
    checks = [Check(id=f"fits.{vid}", rule=f"{d.label}: {word[st]}; " + (f"{fmt(dep)} " + ("to spare in depth" if dep >= 0
                    else "short in depth") if dep is not None else "depth not measured") +
                    (f", {fmt(side)} {'to spare' if side >= 0 else 'short'} beside it to open a door" if side is not None
                     else ""), measured=dep, threshold=0, unit="m", status=st) for st, vid, d, dep, side in rows]
    ok = [r for r in rows if r[0] == "pass"]
    tight = [r for r in rows if r[0] == "warn"]
    ctx.step(f"Parked each of {len(rows)} vehicles alone in the garage: {len(ok)} fit, {len(tight)} tight")
    longest = max(ok or tight, key=lambda r: r[2].length, default=None)
    text = (f"{len(ok)} of {len(rows)} vehicles in the table fit with doors open and {len(tight)} more fit tight."
            + (f" The longest that fits{'' if ok else ' tight'} is the {longest[2].label} ({fmt(longest[2].length)})."
               if longest else " None fits."))
    a0 = analyse(plan, g, catalog_dims(rows[0][1]), 1)
    src = GEO_LOW if g["how"] == "wide door" else GEO
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status="pass" if ok else "warn" if tight else "fail",
                                                                 text=text), checks=checks, assumptions=base[6:],
                      metrics=[Metric(id="fit_count", label="Vehicles that fit with doors open", value=len(ok), unit="",
                                      source=src),
                               Metric(id="tight_count", label="Vehicles that fit tight", value=len(tight), unit="",
                                      source=src),
                               Metric(id="garage.depth", label="Inside depth", value=a0["depth"], unit="m", source=src),
                               Metric(id="garage.width", label="Inside width", value=a0["width"], unit="m", source=src)])


def short(d: Dims) -> str:
    return d.label.split(",")[0].split(" (")[0]


def judge_h(margin: float | None) -> str:
    return "unknown" if margin is None else "pass" if margin >= geom.HEIGHT_FITS_M else \
        "warn" if margin >= geom.HEIGHT_TIGHT_M else "fail"


def side_status(gap: float | None, need: float) -> str:
    return "unknown" if gap is None else "pass" if gap >= need - 0.01 else "warn" if gap >= geom.SQUEEZE_M - 0.01 \
        else "fail"


def assumptions(inputs: Inputs, d: Dims) -> list[Assumption]:
    v = VEHICLES[inputs.vehicle]
    stored = inputs.storage_length_m is not None and inputs.length_m is None
    return [Assumption(id="garage.storage_length_m" if stored else "garage.length_m",
                       label=f"{short(d)} {'storage length (motor up, tongue swung)' if stored else 'length'}",
                       value=d.length, unit="m", editable=True),
            Assumption(id="garage.width_m", label="Body width, mirrors folded", value=d.width, unit="m", editable=True),
            Assumption(id="garage.mirror_width_m", label="Widest point: fenders and side lights" if d.towed else
                       "Width, mirrors out", value=d.mirrors, unit="m", editable=True),
            Assumption(id="garage.height_m", label="Height", value=inputs.height_m or v.height, unit="m", editable=True),
            Assumption(id="garage.lift_in", label="Lift and tyres", value=inputs.lift_in, unit="in", editable=True),
            Assumption(id="garage.roof_load_m", label="On the roof", value=inputs.roof_load_m, unit="m", editable=True),
            Assumption(id="door_clearance", label="Beside the body to open a door and get out", value=d.door, unit="m"),
            Assumption(id="squeeze", label="Beside the body to squeeze out (tight)", value=geom.SQUEEZE_M, unit="m"),
            Assumption(id="front", label="Ahead of the bumper to walk round", value=geom.FRONT_FITS_M, unit="m"),
            Assumption(id="mirrors", label="Each side between mirrors and door frame driving in",
                       value=geom.MIRROR_MARGIN_M, unit="m"),
            Assumption(id="drift", label="Sideways shift between the door and the parked spot (steering in)",
                       value=geom.DRIFT_M, unit="m"),
            Assumption(id="empty", label="Measured as an empty room: shelves, bins and freezers a Matterport scan does "
                       "not record take room too", value=True)]


def no_garage(ctx, sid: str, scope, base: list) -> ToolResult:
    """Say plainly there is no garage in the scan, and what the aerial photos show, if the scan has a location."""
    text = ("This scan has no garage: no room is labelled Garage or Carport, and no ground-floor room has a door wide "
            "enough for a car.")
    metrics = []
    try:
        from ...aerial import detect as aerial_detect
        from .._site import Where, locate
        s = locate(ctx, Where(scan=sid))
        ctx.step("Looking for a garage door and a driveway on Vexcel's aerial and oblique photos (cached)")
        det = aerial_detect.detect(s.lat, s.lon, 40, ["garage door", "driveway"], obliques=True, threshold=0.35)
        gd, dw = det["counts"].get("garage door", 0), det["counts"].get("driveway", 0)
        asrc = Source(layer="vexcel", method="vision", confidence="low",
                      note="Vexcel Custom Elements (SAM 3) on the orthophoto and the four obliques, 40 m around the "
                           "scan's point; a garage door seen may be a neighbour's")
        metrics = [Metric(id="aerial_garage_doors", label="Garage doors seen from the air", value=gd, unit="",
                          source=asrc),
                   Metric(id="aerial_driveways", label="Driveways seen from the air", value=dw, unit="", source=asrc)]
        if gd:
            text += " The oblique aerial photos do show a garage door here, so the garage was likely not scanned."
        elif dw:
            text += " The aerial photos show a driveway but no garage door; it may be a carport or open parking."
        else:
            text += " The aerial photos show no garage door or driveway either."
    except Exception as e:  # noqa: BLE001  no location (a phone scan) or Vexcel down: the scan answer stands alone
        text += " The aerial photos could not be checked: " + (str(e).split(".")[0][:120] or type(e).__name__) + "."
    return ToolResult(scope=scope, verdict=Verdict(status="unknown", text=text), metrics=metrics,
                      assumptions=base, actions=[Action(id="driveway", label="Check the driveway instead",
                                                        tool="driveway_fit", inputs={"scan": sid})])


@tool(id="garage_fit", title="Garage fit", icon="car",
      summary="Checks whether your car, truck, van or trailer fits in a scanned garage: how many side by side, the "
              "room to open doors, headroom for a lift or roof box, and room for a bench or charger.",
      model_description="Park a vehicle (about 60 common models from a built-in table, or custom sizes) in the garage "
                        "of one scan: finds the garage (room label, or a ground-floor room with a car-wide door), "
                        "measures its door width and height, inside width, depth and ceiling, and answers fits / tight "
                        "/ does not fit, how many fit side by side, clearance on each side and in front, headroom for "
                        "a lifted truck or roof box, and room for a workbench, EV charger, motorcycle, bikes or a "
                        "squat rack. Draws the vehicles parked as boxes. With search_city, searches every scanned "
                        "house in Houston or Los Angeles for a garage that fits `count` of the vehicle.",
      personas=["car_owner", "wheelchair_van_owner", "rv_boat_owner", "home_gym_builder"], requires=[{"layer": "matterport.walls"}, {"layer": "matterport.rooms"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "RankedTable", "AssumptionChips", "StepLog",
              "ActionBar"],
      overlays=["box", "rule"],
      examples=["Will my F-150 fit in this garage?", "Can I park two cars and still have a workbench?",
                "Houses in Houston whose garage fits two F-150s", "Is there headroom for my lifted Jeep with a roof box?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    d = dims(inputs)
    base = assumptions(inputs, d)
    if inputs.search_city or not inputs.scan:
        from .search import search
        return search(ctx, inputs, d, base)
    sid = inputs.scan
    plan = ctx.plan(sid)
    scope = ScanScope(sid=sid)
    gs = geom.find_garages(plan)
    if inputs.room:
        r = next((r for r in plan.get("rooms") or [] if r["id"] == inputs.room), None)
        if r is None:
            raise ToolError(f"No room {inputs.room!r} in this scan; leave `room` empty to use the garage found.")
        gs = [{"room": r, "how": "chosen"}]
    if not gs:
        return no_garage(ctx, sid, scope, base)
    g = gs[0]
    room = g["room"]
    ctx.step(f"Garage: {room.get('label') or 'unlabelled room'} of {room.get('area') or 0:.0f} m2 "
             f"({ {'label': 'its label', 'chosen': 'the room you chose'}.get(g['how'], 'a ground-floor room with a car-wide door')})")
    if inputs.which_fit:
        return which_fit(ctx, sid, plan, g, base)
    a = analyse(plan, g, d, 1 if inputs.second_vehicle else inputs.count)
    if a is None:
        return ToolResult(scope=scope, assumptions=base, verdict=Verdict(status="unknown", text=(
            "The scan has a garage but no outline for it, so it cannot be measured.")))
    ctx.step(f"Parked a {d.length:.2f} x {d.width:.2f} m {short(d)}: {a['fits']} fit with doors open, {a['tight']} tight")
    return result(sid, plan, g, a, d, inputs, base)


def _box(f, u: float, v: float, w: float, l: float, h: float, z0: float, label: str, status: str,
         model: str | None = None) -> BoxOverlay:
    c = f.back(u + w / 2, v + l / 2)
    return BoxOverlay(center=(round(c[0], 3), round(c[1], 3), round(z0 + h / 2, 3)), size=(round(l, 3), round(w, 3),
                      round(h, 3)), yaw_deg=round(f.yaw_deg, 1), label=label, status=status, model=model)


def result(sid: str, plan: dict, g: dict, a: dict, d: Dims, inputs: Inputs, base: list) -> ToolResult:
    room, f, z0 = g["room"], a["frame"], a["survey"]["z"]
    rid = room["id"]
    src = GEO_LOW if g["how"] == "wide door" else GEO
    checks, findings, overlays = [], [], [RuleOverlay(select={"rooms": [rid]}, style="highlight")]
    name = short(d)
    n = a["n"]
    # the doors
    doors = a["doors"]
    if doors:
        dw = a["door_width"]
        need_fit = d.mirrors + 2 * geom.MIRROR_MARGIN_M
        need_tight = d.width + 2 * geom.BODY_MARGIN_M
        st = "pass" if dw >= need_fit else "warn" if dw >= need_tight else "fail"
        widest = max(doors, key=lambda x: x["width"])
        fid = f"garage_fit:{sid}:door_width"
        checks.append(Check(id="door_width", rule=f"Garage door opening wide enough for one {name}, " +
                            ("at its widest point (fenders and side lights)" if d.towed else "mirrors out"),
                            measured=round(dw, 3), threshold=round(need_fit, 3), unit="m", status=st,
                            standard="Mirrors-out width plus 15 cm each side; tight down to the body plus 5 cm (mirrors folded)",
                            findings=[fid] if st != "pass" else []))
        if st != "pass":
            findings.append(Finding(id=fid, title="Garage door: " + ("fold the mirrors" if st == "warn" else "too narrow"),
                                    status=st, anchor=OpeningAnchor(sid=sid, opening=widest["opening"]), source=src,
                                    detail=f"{fmt(dw)} opening; the {name} is {fmt(d.mirrors)} " +
                                           ("at its fenders and side lights" if d.towed else
                                            f"with mirrors out and {fmt(d.width)} folded") + "."))
    else:
        findings.append(Finding(id=f"garage_fit:{sid}:no_door", title="Garage door not in the scan", status="unknown",
                                anchor=RoomAnchor(sid=sid, room=rid), source=GEO_LOW,
                                detail="The scan recorded no car-wide opening in the garage walls (the door was likely "
                                       "closed and scanned as wall), so the door width is not checked and the "
                                       "vehicle is parked square to the walls whichever way fits more."))
    # headroom
    dh, measured = a["door_height"], a["door_height_measured"]
    hst = judge_h(round(dh - d.height, 3))
    if not measured and hst == "pass" and dh - d.height < 0.25 or \
            not measured and hst == "fail" and d.height + geom.HEIGHT_TIGHT_M <= geom.TALLEST_DOOR_H:
        hst = "warn"  # an assumed door: a firm answer only when far from it (taller than an 8 ft door fails)
    fid = f"garage_fit:{sid}:door_height"
    checks.append(Check(id="door_height", rule=f"Headroom under the garage door for the {name}"
                        + (" (lift and roof load included)" if inputs.lift_in or inputs.roof_load_m else ""),
                        measured=round(dh, 3), threshold=round(d.height + geom.HEIGHT_FITS_M, 3), unit="m",
                        status=hst, findings=[fid] if hst != "pass" else [],
                        standard=("Door height from the scan" if measured else
                                  "Not measured by the scan: the usual 7 ft (2.13 m) door is assumed") +
                                 "; vehicle height plus 10 cm, tight to 3 cm"))
    if hst != "pass":
        findings.append(Finding(id=fid, title="Headroom under the door: " + ("measure it" if not measured else
                                                                             "tight" if hst == "warn" else "too low"),
                                status=hst, source=src if measured else GEO_LOW,
                                anchor=OpeningAnchor(sid=sid, opening=doors[0]["opening"]) if doors else RoomAnchor(sid=sid, room=rid),
                                detail=f"The {name} stands {fmt(d.height)} tall; the door is "
                                       + (f"{fmt(dh)} high." if measured else
                                          "not measured in the scan, and a standard 7 ft door is 2.13 m.")))
    ceil = a["ceiling"]
    if ceil:
        cst = judge_h(round(ceil - d.height, 3))
        if not a["ceiling_measured"] and cst == "fail":
            cst = "warn"  # the home's typical ceiling stands in; garages are often taller
        checks.append(Check(id="ceiling", rule="Ceiling over the parked vehicle", measured=round(ceil, 3),
                            threshold=round(d.height + geom.HEIGHT_FITS_M, 3), unit="m", status=cst,
                            standard=None if a["ceiling_measured"] else "The garage has no height in the scan: the "
                            "home's typical ceiling is used"))
    # depth on its own: from the door line to the back wall, less anything the scan measured standing in the way
    if a["depth"]:
        fit_d = round(d.length + geom.REAR_M + geom.FRONT_FITS_M, 3)
        tight_d = d.length + geom.REAR_TIGHT_M + geom.FRONT_TIGHT_M
        dst = "pass" if a["depth"] >= fit_d - 0.01 else "warn" if a["depth"] >= tight_d - 0.01 else "fail"
        objs = a["survey"]["obstacles"]
        checks.append(Check(id="depth", rule=f"Depth from the door to the back wall for the {name}" +
                            (f", clear of {len(objs)} object{'s' if len(objs) > 1 else ''} the scan measured" if objs
                             else ""), measured=a["depth"], threshold=fit_d, unit="m", status=dst,
                            standard=f"Length plus {geom.REAR_M:.2f} m behind for the door and "
                                     f"{geom.FRONT_FITS_M:.2f} m ahead to walk round; tight down to "
                                     f"{geom.REAR_TIGHT_M + geom.FRONT_TIGHT_M:.2f} m in all"))
    if n == 0:  # nothing parked: the door and headroom checks were for the vehicle
        checks, findings = [], [f for f in findings if f.id.endswith("no_door")]
    # parking
    lv_need = d.door if not d.towed else 0.6
    if n:
        for i, ((u, v), c) in enumerate(zip(a["cars"], a["clear"] or [{}] * n)):
            k = f"car{i + 1}"
            sides = [x for x in (c.get("left"), c.get("right")) if x is not None]
            worst = min(sides) if sides else None
            st_side = side_status(worst, lv_need)
            st_front = "unknown" if c.get("front") is None else "pass" if c["front"] >= geom.FRONT_FITS_M - 0.01 else \
                "warn" if c["front"] >= geom.FRONT_TIGHT_M - 0.01 else "fail"
            st = "fail" if a["status"] == "fail" else max((st_side, st_front), key=["pass", "unknown", "warn", "fail"].index)
            tag = f"{name} {i + 1}" if n > 1 else name
            fid = f"garage_fit:{sid}:{k}"
            for side in ("left", "right"):
                if c.get(side) is not None:
                    need = d.ramp if (d.ramp and side == "right") else lv_need
                    s2 = "fail" if a["status"] == "fail" and c[side] < geom.SQUEEZE_M else (
                        "pass" if c[side] >= need - 0.01 else "warn" if c[side] >= geom.SQUEEZE_M - 0.01 else "fail")
                    what = "ramp side, room for the ramp and chair" if need == d.ramp and d.ramp else (
                        "to open the doors" if not d.towed else "to walk past")
                    checks.append(Check(id=f"{k}.{side}", rule=f"{tag}, {side} side: room {what}",
                                        measured=round(c[side], 3), threshold=round(need, 3), unit="m", status=s2,
                                        findings=[fid] if s2 != "pass" else []))
            if c.get("front") is not None:
                checks.append(Check(id=f"{k}.front", rule=f"{tag}: room ahead of the bumper to walk round",
                                    measured=round(c["front"], 3), threshold=geom.FRONT_FITS_M, unit="m", status=st_front,
                                    findings=[fid] if st_front != "pass" else []))
            centre = f.back(u + d.width / 2, v + d.length / 2)
            if st != "pass":
                findings.append(Finding(id=fid, title=f"{tag}: {'too big for the space' if a['status'] == 'fail' else 'tight'}",
                                        status=st, source=src, anchor=PointAnchor(sid=sid, point=(centre[0], centre[1], z0 + 1.0)),
                                        detail=", ".join(f"{s} {fmt(c[s])}" for s in ("left", "right", "front") if c.get(s) is not None)
                                        + f" clear; doors need {fmt(lv_need)} beside the body."))
            overlays.append(_box(f, u, v, d.width, d.length, d.height, z0, tag, st, model_of(inputs.vehicle)))
    pp = None
    if inputs.second_vehicle and n:
        pp = pair_part(sid, a, d, catalog_dims(inputs.second_vehicle), z0, src)
        overlays = [o for o in overlays if not isinstance(o, BoxOverlay)] + pp["boxes"]
        checks += pp["checks"]
        findings += pp["findings"]
    # extras
    for t in things(a, d, list(inputs.uses)):
        k, spot = t["id"], t["spot"]
        lab = {"workbench": "Workbench", "ev_charger": "EV charger", "motorcycle": "Motorcycle", "bikes": "Bikes",
               "squat_rack": "Home gym platform"}[k]
        st = "pass" if spot else "fail"
        extra_ok = True
        if k == "squat_rack":
            need_h = round(1.30 * inputs.lifter_height_m + 0.15, 2)
            hs = judge_h(round((ceil or 0) - need_h + geom.HEIGHT_FITS_M, 3)) if ceil else "unknown"
            checks.append(Check(id="gym.ceiling", rule="Ceiling for an overhead press", measured=round(ceil, 3) if ceil else None,
                                threshold=need_h, unit="m", status=hs,
                                standard="Standing reach about 1.3 times height, plus bar and plates; keep the rack "
                                         "clear of the open door's track"))
            extra_ok = hs == "pass"
        checks.append(Check(id=f"room.{k}", rule=f"Room for: {t['note']}" + (" (after parking)" if n else ""),
                            measured=None, threshold=None, unit="", status=st))
        if spot:
            (cu, cv), yaw, (sl, sw) = geom.corners_center(spot)
            if k in THING_MODEL and sl < sw:  # a model's length runs along the box's first side
                sl, sw, yaw = sw, sl, yaw + 90
            c = f.back(cu, cv)
            hgt = t["height"] if k != "ev_charger" else 0.45
            zc = z0 + (1.2 if k == "ev_charger" else hgt / 2)
            size = (0.35, 0.2, 0.45) if k == "ev_charger" else (round(sl, 2), round(sw, 2), hgt)
            overlays.append(BoxOverlay(center=(round(c[0], 3), round(c[1], 3), round(zc, 3)), size=size,
                                       yaw_deg=round(f.scan_yaw(yaw), 1), label=lab,
                                       status="pass" if extra_ok else "warn", model=THING_MODEL.get(k)))
    for o in a["survey"]["obstacles"]:
        findings.append(Finding(id=f"garage_fit:{sid}:object:{o['id']}", title=f"In the garage: {o['label'].lower()}",
                                status="unknown", source=Source(layer="matterport", method="geometry",
                                                                confidence="medium", note="Object the phone scan found"),
                                anchor=PointAnchor(sid=sid, point=tuple(o["center"])),
                                detail=f"{fmt(o['size'][0])} x {fmt(o['size'][1])}; its floor is left out of the parking space."))
    # verdict
    fits, tight = a["fits"], a["tight"]
    statuses = [c.status for c in checks if c.id in ("door_width", "door_height", "ceiling")] + [a["status"]] \
        if n else [c.status for c in checks if c.id.startswith(("room.", "gym."))]
    if pp:
        statuses.append(pp["status"])
    status = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    many = lambda k: f"{WORD.get(k, k)} {name}{'s' if k > 1 else ''}"
    if n == 0:
        text = "The garage is empty in this check: " + ("everything asked for has room." if all(
            c.status == "pass" for c in checks if c.id.startswith(("room.", "gym."))) else "not everything asked for fits.")
    elif a["status"] == "fail":
        text = (f"{many(n)} {'does' if n == 1 else 'do'} not fit side by side" +
                (f"; {WORD.get(tight, tight).lower()} fit{'s' if tight == 1 else ''}, tight." if tight else "."))
    else:
        text = f"{many(n)} {'fits' if n == 1 else 'fit'}" + (
            (" with room to walk round" if d.towed else " with room to open the doors") if a["which"] == "fits" else
            (", tight: little room to walk round" if d.towed else ", tight: you squeeze out of the doors"))
        text += "." if inputs.count is not None or inputs.second_vehicle or fits == tight else f" ({fits} with doors fully open, {tight} tight)."
    why = {"door_width": " The garage door is narrow for it: fold the mirrors.",
           "door_height": " Headroom under the garage door is tight." if measured else
           (" It is taller than even an 8 ft garage door; the scan did not measure this one."
            if d.height + geom.HEIGHT_TIGHT_M > geom.TALLEST_DOOR_H else
            " It would not clear a standard 7 ft garage door, and the scan did not measure this one: measure it."
            if dh < d.height + geom.HEIGHT_TIGHT_M else
            " The scan did not measure the garage door's height: check it against the vehicle."),
           "ceiling": " The ceiling is low for it." if a["ceiling_measured"] else
           " The garage has no ceiling height in the scan, and the home's typical ceiling is low for it: measure it."}
    for c in checks:
        if c.id in why and c.status in ("warn", "fail") and n:
            text += why[c.id] if c.status == "warn" or c.id == "door_height" and not measured or \
                c.id == "ceiling" and not a["ceiling_measured"] else \
                {"door_width": " The garage door is too narrow for it.", "door_height": " It does not clear the garage door.",
                 "ceiling": " It does not clear the ceiling."}[c.id]
    if pp:
        text += pp["text"]
    if g["how"] == "wide door":
        text += " The room is unlabelled; it was taken for the garage because of its car-wide door."
    if n and not has_objects(plan):
        checks.append(cannot("garage_depth", "a water heater, furnace, HVAC fittings, steps up into the house or "
                                             "shelves at the back wall; this scan measures depth to the wall face, so "
                                             "measure from the door to whatever stands out furthest"))
    side_vals = [x for c in a["clear"] for x in (c.get("left"), c.get("right")) if x is not None]
    metrics = [Metric(id="fit_count", label=f"{name}s with doors open", value=fits, unit="", source=src),
               Metric(id="tight_count", label=f"{name}s, tight", value=tight, unit="", source=src),
               Metric(id="side_clearance", label="Least room beside a vehicle", value=round(min(side_vals), 2) if side_vals else None,
                      unit="m", source=src),
               Metric(id="headroom", label="Headroom under the door", value=round(dh - d.height, 2), unit="m",
                      source=src if measured else GEO_LOW),
               Metric(id="garage.width", label="Inside width", value=a["width"], unit="m", source=src),
               Metric(id="garage.depth", label="Inside depth", value=a["depth"], unit="m", source=src),
               Metric(id="garage.door_width", label="Garage door width", value=a["door_width"], unit="m", source=src),
               Metric(id="garage.door_height", label="Garage door height", value=dh if measured else None, unit="m", source=src),
               Metric(id="garage.ceiling", label="Ceiling", value=ceil, unit="m", source=src),
               Metric(id="garage.area", label="Floor area", value=round(a["survey"]["poly"].area, 1), unit="m2", source=src)]
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status=status, text=text), metrics=metrics,
                      checks=checks, findings=findings, overlays=overlays, assumptions=base,
                      actions=[Action(id="driveway", label="Check the driveway", tool="driveway_fit", inputs={"scan": sid})])
