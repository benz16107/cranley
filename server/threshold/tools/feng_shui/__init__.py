"""Feng shui: how a practitioner of this Chinese layout tradition would read the plan.

Feng shui is a cultural practice, not a measurement of anything a scan can test; this tool makes no claim that a
layout changes health, money or luck. It reports what a practitioner would note, found from the geometry: the
front door's facing direction, the Bagua (Lo Shu) grid on each floor with its life areas and elements, which rooms
fall where, the command position for beds and desks, the usual notes (door lines, stairs facing the door, missing
corners, a bathroom at the centre) and, given a birth year and gender, the person's Kua number and directions.
Compass bearings use `geometry.georef.azimuth_of` (the sun workstream's helpers had not reached main).
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel
from shapely.geometry import LineString

from ...geometry._plan import floor_z, polygons, room_floor_z, rooms_by_id, walls_by_id
from ...geometry.georef import azimuth_of
from .. import (
    Action,
    Assumption,
    Check,
    Finding,
    Legend,
    LensOverlay,
    Metric,
    OpeningAnchor,
    Pin,
    PinsOverlay,
    PointAnchor,
    RoomAnchor,
    ScanScope,
    Source,
    ToolResult,
    Verdict,
    field,
    tool,
)
from .._access import entrances, floor_name, graph
from ..types import BoxOverlay, RouteOverlay
from . import kua as K
from .bagua import (
    BTB_PLACE,
    MISSING_SHARE,
    SECTORS,
    clear_line,
    door_line,
    grid,
    inward,
    share_in,
)
from .command import BEDS, DESK, place

GEO = Source(layer="matterport", method="geometry", confidence="high", note="Wall graph and room outlines")
COMPASS = Source(layer="matterport", method="geometry", confidence="medium",
                 note="Bearings from the scan's geocoordinates (checked on 40 houses, typical error 3 degrees)")
RULE = Source(layer="model", method="lookup", confidence="high", note="Standard Kua formula and Eight Mansions table")
TRADITION = ("Feng shui is a traditional Chinese layout practice. These are the things a practitioner would note; "
             "they are not measured effects, and how much weight to give them is yours to decide.")
BATH = ("Bathroom", "Toilet", "Powder Room", "Half Bath")
DESK_ROOMS = ("Office", "Study", "Den")
CORNERS = ("NE", "SE", "SW", "NW")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    convention: Literal["compass", "western"] = field(
        "compass", pref="feng_shui.convention",
        description="compass: Compass School, the eight sectors named by true north. western: Western (BTB) Bagua, "
                    "the grid turned so the front door wall is the Career row.")
    birth_year: int | None = field(None, pref="feng_shui.birth_year", ge=1900, le=2100,
                                   description="Birth year for the Kua number; use the year before for a birth "
                                               "before about 4 February")
    gender: Literal["female", "male"] | None = field(None, pref="feng_shui.gender",
                                                     description="The Kua formula differs for men and women")
    bed: Literal["twin", "full", "queen", "king"] = field("queen", pref="feng_shui.bed", description="Bed size to place")
    front_door: str | None = field(None, description="Opening id of the front door, when the first guess is wrong")


def _names(plan: dict) -> dict[str, str]:
    rooms = plan.get("rooms") or []
    out = {}
    for r in rooms:
        lab = r.get("label") or "Unlabelled room"
        same = [x["id"] for x in rooms if (x.get("label") or "Unlabelled room") == lab]
        out[r["id"]] = f"{lab} {same.index(r['id']) + 1}" if len(same) > 1 else lab
    return out


def _sector_name(d: str, convention: str) -> str:
    _num, area, element = SECTORS[d]
    if convention == "western":
        return f"{area} ({BTB_PLACE[d]}), {element}"
    return f"{'Centre' if d == 'C' else d}, {area}, {element}"


def _sector_prose(d: str, convention: str) -> str:
    _, area, element = SECTORS[d]
    if convention == "western" or d == "C":
        return f"{area} square ({BTB_PLACE[d]}, {element})"
    return f"{K.WORD[d]} square ({area}, {element})"


@tool(id="feng_shui", title="Feng shui reading",
      summary="How a feng shui practitioner would read this home: the front door's direction, the Bagua grid on each "
              "floor, the command position for beds and desks, and the usual layout notes. A cultural tradition, "
              "not a measured effect.",
      model_description="Traditional Chinese feng shui reading of one scanned home from its floor plan and true north: "
                        "front door facing direction, Bagua (Lo Shu) sectors per floor with life area and element, which "
                        "rooms fall in each sector, command position for the bed in each bedroom and the desk in each "
                        "office (with boxes), notes such as front and back doors in line, stairs facing the door, missing "
                        "corners and a bathroom at the centre, and with a birth year and gender the person's Kua number "
                        "and favourable directions. Compass School by default; Western (BTB) door-aligned on request. "
                        "Describe it as a cultural layout tradition, never as a proven effect.",
      personas=["feng_shui_curious"], requires=[{"layer": "matterport.walls"}, {"layer": "matterport.rooms"},
                                                {"layer": "matterport.geo", "need": "optional",
                                                 "fallback": "Western (door-aligned) convention, no compass"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "FloorPlanMini", "AssumptionChips", "Note", "StepLog"],
      overlays=["lens", "pins", "route", "box"],
      examples=["Where should the bed go for good feng shui?", "Is the front door in line with the back door?",
                "I was born in 1988 and I'm a woman: which rooms suit my directions?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    sid = inputs.scan
    plan = ctx.plan(sid)
    scope = ScanScope(sid=sid)
    g = graph(plan)
    if not g["available"]:
        return ToolResult(scope=scope, verdict=Verdict(status="unknown", text="This scan has no wall graph, so its doors "
                                                                              "and room shapes are unknown; a feng shui reading needs both."))
    names, rooms, walls = _names(plan), rooms_by_id(plan), walls_by_id(plan)
    has_geo = azimuth_of(plan, 0.0, 1.0) is not None
    convention = inputs.convention
    notes: list[str] = []
    if convention == "compass" and not has_geo:
        convention = "western"
        notes.append("This scan has no geocoordinates, so true north is unknown; the reading uses the Western "
                     "door-aligned convention instead.")
    ctx.step(f"Reading the plan by the {'Compass School' if convention == 'compass' else 'Western (BTB)'} convention")

    # front door
    ents = entrances(plan)
    front = next((e for e in ents if e["opening"] == inputs.front_door), None) if inputs.front_door else None
    front = front or (ents[0] if ents else None)
    metrics, checks, findings, overlays, pins = [], [], [], [], []
    door_out, door_dir = None, None
    if front is None:
        if convention == "western":
            return ToolResult(scope=scope, verdict=Verdict(status="unknown", text="No doorway leads outside in this scan, "
                                                                                  "and the Western convention aligns the grid to the front door."))
        notes.append("No doorway in this scan leads outside, so the front door is unknown.")
    else:
        m = inward(plan, front, front["room"], walls)
        door_out = (-m[0], -m[1])
        az = azimuth_of(plan, *door_out) if has_geo else None
        door_dir = K.compass8(az) if az is not None else None
        if az is not None:
            metrics.append(Metric(id="door_bearing", label="Front door faces", value=round(az), unit="°", source=COMPASS))
        findings.append(Finding(
            id=f"feng_shui:{sid}:front_door", title="Front door", status="pass",
            detail=(f"Facing {K.WORD[door_dir]} ({az:.0f}° from true north), so the house sits {K.WORD[K.compass8(az + 180)]}. "
                    if az is not None else "Facing direction unknown without geocoordinates. ")
                   + f"Taken as the main entrance: the doorway from outside into the {names[front['room']]}"
                   + (" (the widest one-sided doorway on the lowest floor; the plan cannot confirm it leads outside)."
                      if not inputs.front_door else " (chosen by you)."),
            anchor=OpeningAnchor(sid=sid, opening=front["opening"]), source=COMPASS if az is not None else GEO))

    # the Bagua on each floor
    fz, rz = floor_z(plan), room_floor_z(plan)
    main_floor = front["floor"] if front else (plan.get("floors") or [{}])[0].get("id")
    sector_of: dict[str, str] = {}
    grids = {}
    ctx.step("Laying the Bagua grid over each floor's outline")
    for fl in plan.get("floors") or []:
        gr = grid(plan, fl["id"], convention, door_out)
        if not gr["available"]:
            continue
        grids[fl["id"]] = gr
        sector_of.update(gr["room_sector"])
        fname = floor_name(plan, fl["id"])
        main = fl["id"] == main_floor
        for d, cell in gr["cells"].items():
            listed = ", ".join(names[r] for r in cell["rooms"]) or "no room"
            checks.append(Check(id=f"sector:{fl['id']}:{d}", rule=f"{fname.capitalize()}: {_sector_name(d, convention)}. Rooms: {listed}",
                                measured=round(100 * cell["share"]), threshold=round(100 * MISSING_SHARE) if main else None,
                                unit="% inside", status="warn" if main and cell["share"] < MISSING_SHARE else "pass",
                                standard=None if main else "Upper floor: read for which rooms sit where; missing areas "
                                                           "are judged on the entrance floor's outline"))
            if fl["id"] == main_floor:
                z = fz.get(fl["id"], 0.0)
                overlays.append(BoxOverlay(center=(*cell["center"], z + 0.01), size=(*cell["size"], 0.02),
                                           yaw_deg=math.degrees(gr["theta"]),
                                           label=f"{SECTORS[d][0]} {d if convention == 'compass' else SECTORS[d][1].split()[0]}",
                                           status="warn" if cell["share"] < MISSING_SHARE else "unknown"))
                pins.append(Pin(id=f"bagua:{d}", anchor=PointAnchor(sid=sid, point=(*cell["center"], z)),
                                label=_sector_name(d, convention), status="warn" if cell["share"] < MISSING_SHARE else "unknown"))
            if main and d != "C" and cell["share"] < MISSING_SHARE:
                corner = d in CORNERS
                findings.append(Finding(
                    id=f"feng_shui:{sid}:missing:{fl['id']}:{d}", title="Missing corner" if corner else "Missing area",
                    status="warn", anchor=PointAnchor(sid=sid, point=(*cell["center"], fz.get(fl["id"], 0.0))), source=GEO,
                    detail=f"On {fname}, the {_sector_prose(d, convention)} "
                           f"is {100 * cell['share']:.0f}% inside the outline, as in an L-shaped plan. Practitioners call "
                           f"this a missing {'corner' if corner else 'area'} and often 'complete' it with a light, plant "
                           f"or mirror on that side."))
        if gr["offset_deg"] is not None and fl["id"] == main_floor:
            metrics.append(Metric(id="turned", label="Walls turned from north", value=round(gr["offset_deg"]), unit="°",
                                  source=COMPASS))
        cen = gr["cells"]["C"]["polygon"]
        for rid in gr["room_sector"]:
            if rooms[rid].get("label") in BATH and share_in(plan, rid, cen) >= 0.5:
                findings.append(Finding(
                    id=f"feng_shui:{sid}:bath_centre:{rid}", title="Bathroom at the centre", status="warn",
                    anchor=RoomAnchor(sid=sid, room=rid), source=GEO,
                    detail=f"Most of the {names[rid]} ({100 * share_in(plan, rid, cen):.0f}% of its floor) is in the centre "
                           f"square on {fname}. The centre is the home's heart in this tradition, and practitioners note "
                           f"water draining from it; the usual advice is to keep the door shut and the room bright."))
    if grids:
        overlays.insert(0, LensOverlay(values={r: float(SECTORS[d][0]) for r, d in sector_of.items()}, ramp="sequential",
                                       legend=Legend(title="Lo Shu number of the room's square", unit="", min=1, max=9)))
    if front is not None and front["room"] in sector_of:
        findings[0].detail += f" It opens into the {_sector_prose(sector_of[front['room']], convention)}."

    # lines from the front door
    if front is not None:
        exits = {e["opening"] for e in ents}
        line = door_line(plan, front, door_out, walls, exits)
        z = fz.get(front["floor"], 0.0)
        back = [d for d in line if d["exit"]]
        if line:
            far = line[-1]
            overlays.append(RouteOverlay(floor=front["floor"], points=[(*front["center"], z + 0.05), (*far["center"], z + 0.05)],
                                         label="Straight line from the front door"))
        if back:
            findings.append(Finding(
                id=f"feng_shui:{sid}:back_door_line", title="Back door in line with the front door", status="warn",
                anchor=OpeningAnchor(sid=sid, opening=back[0]["opening"]), source=GEO,
                detail=f"A doorway to the outside is straight in from the front door, {back[0]['along']:.1f} m away, with "
                       f"nothing solid between. Practitioners say energy rushes straight through; a screen, plant or rug "
                       f"that breaks the line is the usual remedy."))
        if line and not back:  # a back door on the line is the stronger note; one finding per line
            findings.append(Finding(
                id=f"feng_shui:{sid}:door_line", title="Doors lined up through the house", status="warn",
                anchor=OpeningAnchor(sid=sid, opening=line[-1]["opening"]), source=GEO,
                detail=f"{len(line)} doorway{'s' if len(line) > 1 else ''} line up straight in from the front door, "
                       f"the farthest {line[-1]['along']:.1f} m in. Practitioners prefer the way in to turn or be screened."))
        checks.append(Check(id="door_line", rule="Doorways straight in from the front door", measured=len(line),
                            threshold=0, unit="doors", status="warn" if line else "pass"))
        stairs = [r for r in plan.get("rooms") or [] if "stair" in (r.get("label") or "").lower() and r["floor"] == front["floor"]]
        hit = None
        if stairs:
            c0, n = front["center"], (-door_out[0], -door_out[1])
            ray = LineString([c0, (c0[0] + 12 * n[0], c0[1] + 12 * n[1])])
            for r in stairs:
                p = polygons(plan).get(r["id"])
                seg = ray.intersection(p) if p is not None else None
                if seg is not None and not seg.is_empty:
                    first = seg.interpolate(0) if seg.geom_type == "LineString" else seg.geoms[0].interpolate(0)
                    if clear_line(plan, front["floor"], (c0[0] + 0.15 * n[0], c0[1] + 0.15 * n[1]), (first.x, first.y)):
                        hit = (r, math.dist(c0, (first.x, first.y)))
                        break
        if hit:
            findings.append(Finding(
                id=f"feng_shui:{sid}:stairs_door", title="Staircase facing the front door", status="warn",
                anchor=RoomAnchor(sid=sid, room=hit[0]["id"]), source=GEO,
                detail=f"The {names[hit[0]['id']]} starts {hit[1]:.1f} m straight in from the front door. Practitioners say "
                       f"energy runs up or down the stairs and out; a rug, plant or turn in the path is the usual remedy."))
        checks.append(Check(id="stairs_door", rule="Staircase straight in from the front door",
                            measured=round(hit[1], 2) if hit else None, threshold=None, unit="m",
                            status="warn" if hit else ("pass" if stairs or len(plan.get("floors") or []) == 1 else "unknown"),
                            standard=None if stairs or len(plan.get("floors") or []) == 1 else
                            "Stairs are not in the scan data and no room is labelled a staircase; look on site."))

    # Kua number
    good = None
    if inputs.birth_year and inputs.gender:
        k = K.kua(inputs.birth_year, inputs.gender)
        dirs = K.directions(k)
        good = {d for d, (ok, _, _) in dirs.items() if ok}
        metrics.append(Metric(id="kua", label="Kua number", value=k, unit="", source=RULE))
        fav = "; ".join(f"{K.WORD[d]} ({m}, {c})" for d, (ok, m, c) in dirs.items() if ok)
        txt = f"Kua {k}, {K.group(k)} group. Favourable: {fav}. {K.FORMULA}"
        if has_geo:
            liked = [names[r] for r, d in sector_of.items() if d in good and rooms[r].get("label") in ("Bedroom", "Office", "Kitchen")]
            if liked:
                txt += f" Rooms in your favourable sectors: {', '.join(liked)}."
            if door_dir:
                _ok, m, c = dirs[door_dir]
                txt += f" The front door faces {K.WORD[door_dir]}, your {m} ({c}) direction."
        else:
            txt += " Without geocoordinates the directions cannot be matched to this home."
        findings.append(Finding(id=f"feng_shui:{sid}:kua", title="Your Kua number and directions", status="pass",
                                detail=txt, anchor=None, source=RULE))

    # command positions
    ctx.step("Looking for the command position in each bedroom and office")
    links = g["links"] + [e | {"rooms": [e["room"]]} for e in g["entrances"]]
    placed = 0
    for r in plan.get("rooms") or []:
        lab = r.get("label")
        piece = "bed" if lab == "Bedroom" else "desk" if lab in DESK_ROOMS else None
        if piece is None:
            continue
        size = BEDS[inputs.bed] if piece == "bed" else DESK
        p = place(plan, r["id"], piece, size, links, walls, good if has_geo else None)
        rule = f"{names[r['id']]}: {piece} in the command position"
        if not p["available"]:
            checks.append(Check(id=f"command:{r['id']}", rule=rule, measured=None, threshold=None, unit="m", status="unknown",
                                standard=p["reason"]))
            continue
        placed += 1
        broken = [t for t, ok in (("the door is not in view", p["rules"]["view"]),
                                  ("it sits in line with a door", p["rules"]["not_in_line"]),
                                  (f"the wall behind is shared with the {(p['back_room'] or '').lower()}", p["rules"]["no_soft_wall"])) if not ok]
        status = "pass" if not broken else "warn"
        checks.append(Check(id=f"command:{r['id']}", rule=rule + " (distance to the door)", measured=round(p["door_distance_m"], 2),
                            threshold=None, unit="m", status=status, findings=[f"feng_shui:{sid}:place:{r['id']}"]))
        h = 0.55 if piece == "bed" else 0.75
        overlays.append(BoxOverlay(center=(*p["center"], rz.get(r["id"], 0.0) + h / 2), size=(p["size"][0], p["size"][1], h),
                                   yaw_deg=p["yaw_deg"], label=f"Suggested {piece}, {names[r['id']]}", status=status))
        how = ("bed with its head against the wall" if piece == "bed"
               else "desk out from the wall, so you sit between it and the wall facing into the room")
        dtxt = ""
        if p["head_az"] is not None:
            d = K.compass8(p["head_az"] if piece == "bed" else p["face_az"])
            dtxt = (f" The {'head points' if piece == 'bed' else 'sitter faces'} {K.WORD[d]}"
                    + (f", {'one of' if p['kua_ok'] else 'not one of'} your favourable directions." if good else "."))
        findings.append(Finding(
            id=f"feng_shui:{sid}:place:{r['id']}", title=f"Suggested {piece} spot", status=status,
            anchor=RoomAnchor(sid=sid, room=r["id"]), source=GEO,
            detail=(f"Place the {how}: the door is {p['door_distance_m']:.1f} m away, "
                    f"{p['door_angle_deg']:.0f}° off straight ahead"
                    + (", in view, not in line with it, and a wall with no door or window behind." if not broken
                       else f". This is the best spot the room allows, but {' and '.join(broken)}.") + dtxt)))
    if pins:
        overlays.append(PinsOverlay(pins=pins))

    warned = [f for f in findings if f.status == "warn" and f.id.split(":")[2] != "place"]
    metrics.append(Metric(id="notes", label="Layout notes", value=len(warned), unit="", source=GEO))
    lead = (f"Front door faces {K.WORD[door_dir]}. " if door_dir else "")
    verdict = Verdict(status="warn" if warned else "pass",
                      text=f"{lead}{'Compass School' if convention == 'compass' else 'Western (BTB)'} reading: "
                           f"{len(warned)} layout note{'s' if len(warned) != 1 else ''} a practitioner would raise, and "
                           f"{placed} suggested bed or desk spot{'s' if placed != 1 else ''}. A cultural tradition, not a measured effect.")
    assumptions = [
        Assumption(id="feng_shui.convention", label="Convention", value=convention, editable=True),
        Assumption(id="grid", label="Grid", value="3 x 3 over the outline's bounding rectangle, aligned to the walls; "
                   + ("outer squares named by their compass bearing from the centre" if convention == "compass"
                      else "the front door wall is the Knowledge, Career and Helpful people row"), editable=False),
        Assumption(id="feng_shui.bed", label="Bed size", value=inputs.bed, editable=True),
        Assumption(id="outline", label="Outline", value="all walled indoor rooms, including an attached garage; patios left out"),
        Assumption(id="tradition", label="About this reading", value=TRADITION),
        *[Assumption(id=f"note{i}", label="Note", value=t) for i, t in enumerate(notes)],
    ]
    if inputs.birth_year:
        assumptions.append(Assumption(id="feng_shui.birth_year", label="Birth year (solar year from about 4 February)",
                                      value=inputs.birth_year, editable=True))
    other = "western" if convention == "compass" else "compass"
    actions = [Action(id="convention", label="Use the Western (door-aligned) Bagua" if other == "western"
                      else "Use the Compass School Bagua", tool="feng_shui", inputs={"scan": sid, "convention": other})] \
        if other == "western" or has_geo else []
    return ToolResult(scope=scope, verdict=verdict, metrics=metrics, checks=checks, findings=findings, overlays=overlays,
                      assumptions=assumptions, actions=actions)
