"""Edits that would fix the failing checks of a goal, found from the plan's own geometry. Each candidate is one edit
with the problem it targets; the renovate tool tries each one and ranks them by what they fix and what they cost."""
from __future__ import annotations

from ..geometry import turning_space
from ..geometry._plan import SCAN_TOLERANCE_M, clear_width, implausible
from ..tools._access import graph, links_of, pick_entrance, sill_step, start_point, step_kind
from ..tools.step_free_route import targets
from .edits import DoorSwing, Edit, EditError, AddRamp, GrabBars, MoveWall, RemoveWall, WidenDoor, apply

DOOR_CLEAR_M = 0.815      # ADA 404.2.3
TURN_M = 1.525            # ADA 304.3.1
DOOR_SIZES_M = (0.915, 0.89)  # a 36 in door (about 865 mm clear), then the narrowest opening that clears the tolerance
HINGE_GAIN_M = 0.045      # offset hinges give back the hung leaf, about 1 3/4 in
SHIFTS_M = [round(0.05 * k, 2) for k in range(1, 17)]  # up to 80 cm
ABSORB = {"Closet", "Pantry", "Laundry", "Utility Room", "Storage", "Void", None}  # rooms a bathroom may take over
SKIP_DOORS = {"Closet", "Void", "Pantry"}


def _name(rooms: dict, rid: str | None) -> str:
    return (rooms.get(rid) or {}).get("label") or "room"


def door_fixes(plan: dict, openings: list[str], why: str) -> list[dict]:
    """For each too-narrow doorway: offset hinges when the leaf is all that is missing, and a wider door."""
    links = links_of(plan)
    out = []
    for oid in dict.fromkeys(openings):
        d = links.get(oid)
        if d is None or d["kind"] not in ("doorway", "opening") or implausible(d):
            continue
        cw = clear_width(d)
        if cw is None or cw >= DOOR_CLEAR_M + SCAN_TOLERANCE_M:
            continue
        if d["kind"] == "doorway" and cw + HINGE_GAIN_M >= DOOR_CLEAR_M + SCAN_TOLERANCE_M:
            out.append({"edit": DoorSwing(opening=oid, swing="offset_hinges"), "target": oid, "why": why})
        for w in DOOR_SIZES_M:
            e = WidenDoor(opening=oid, width_m=w)
            if _ok(plan, e):
                out.append({"edit": e, "target": oid, "why": why})
                break
    return out


def route_problems(plan: dict, destinations: list[str]) -> tuple[list[str], list[str]]:
    """Narrow doorways and stepped sills on the routes from the entrance to these rooms."""
    from ..geometry import route
    ent = pick_entrance(plan)
    if ent is None:
        return [], []
    links = links_of(plan)
    narrow, steps = [], []
    for r in targets(plan, destinations):
        if r["floor"] != ent["floor"]:
            continue
        rt = route(plan, start_point(plan, ent), r["id"], floor=r["floor"])
        if not rt["available"]:
            continue
        crossed = [ent["opening"]] + [d["opening"] for d in rt["doors"] if d["opening"] != ent["opening"]]
        for oid in crossed:
            d = links.get(oid)
            if d is None:
                continue
            narrow.append(oid)
            if step_kind(sill_step(plan, d)) in ("step", "possible"):
                steps.append(oid)
    return narrow, steps


def _ok(plan: dict, e: Edit) -> bool:
    try:
        apply(plan, [e])
        return True
    except EditError:
        return False


def turn_fixes(plan: dict, room_ids: list[str]) -> list[dict]:
    """For each room too tight to turn in: the smallest move of one of its inner walls that makes the circle fit
    without making a neighbour fail its own circle, and taking out the wall to a closet next door."""
    rooms = {r["id"]: r for r in plan["rooms"]}
    out = []
    for rid in room_ids:
        t = turning_space(plan, rid, TURN_M)
        if not t["available"] or t["diameter"] >= TURN_M + SCAN_TOLERANCE_M:
            continue
        for w in (w for w in plan["walls"] if rid in w["rooms"] and w["type"] == "wall" and len(w["rooms"]) == 2):
            other = next(r for r in w["rooms"] if r != rid)
            if _name(rooms, other) == "Bathroom":
                continue
            other_before = turning_space(plan, other, TURN_M)
            for s in SHIFTS_M:
                e = MoveWall(wall=w["id"], offset_m=s, grow=rid)
                try:
                    after, _ = apply(plan, [e])
                except EditError:
                    break  # a larger move fails the same way
                if turning_space(after, rid, TURN_M)["diameter"] < TURN_M + SCAN_TOLERANCE_M:
                    continue
                o = turning_space(after, other, TURN_M)
                if other_before["available"] and other_before["diameter"] >= TURN_M + SCAN_TOLERANCE_M \
                        and o["diameter"] < TURN_M + SCAN_TOLERANCE_M and rooms[other].get("label") not in ABSORB:
                    break  # the neighbour would lose its own turning circle
                out.append({"edit": e, "target": rid,
                            "why": f"turning circle in the {_name(rooms, rid)}, taking {s * 100:.0f} cm from the "
                                   f"{_name(rooms, other)}"})
                break
            if rooms[other].get("label") in ABSORB:
                e = RemoveWall(wall=w["id"])
                try:
                    after, _ = apply(plan, [e])
                except EditError:
                    continue
                keep = next(r["id"] for r in after["rooms"] if r["id"] in w["rooms"])
                if turning_space(after, keep, TURN_M)["diameter"] >= TURN_M + SCAN_TOLERANCE_M:
                    out.append({"edit": e, "target": rid,
                                "why": f"turning circle in the {_name(rooms, rid)}, taking in the {_name(rooms, other)}"})
    return out


def propose(plan: dict, goal: str) -> list[dict]:
    """Candidate edits for a goal: [{edit, target, why}], one or more per problem."""
    rooms = {r["id"]: r for r in plan["rooms"]}
    baths = [r["id"] for r in plan["rooms"] if r.get("label") == "Bathroom"]
    out: list[dict] = []
    if goal in ("bathroom_route", "wheelchair_ready"):
        dest = ["Bathroom"] if goal == "bathroom_route" else ["Bathroom", "Bedroom", "Kitchen"]
        narrow, steps = route_problems(plan, dest)
        g = graph(plan)
        bath_doors = [d["opening"] for d in g.get("links", []) + g.get("entrances", [])
                      if d.get("opening") and set(d.get("rooms") or [d.get("room")]) & set(baths)]
        out += door_fixes(plan, narrow + bath_doors, "door on the route from the entrance")
        out += [{"edit": AddRamp(opening=o), "target": o, "why": "step at a door on the route"}
                for o in dict.fromkeys(steps) if _ok(plan, AddRamp(opening=o))]
    if goal in ("bathroom_turn", "wheelchair_ready"):
        out += turn_fixes(plan, baths)
    if goal == "wheelchair_ready":
        living = [r["id"] for r in plan["rooms"] if r.get("label") in ("Kitchen", "Bedroom", "Living Room")]
        out += turn_fixes(plan, living)
        out += [{"edit": GrabBars(room=b), "target": b, "why": "grab bars at the toilet and bathing (FHA Requirement 6)"}
                for b in baths if _ok(plan, GrabBars(room=b))]
    if goal == "door_widths":
        g = graph(plan)
        doors = [d["opening"] for d in g.get("links", []) + g.get("entrances", []) if d.get("opening")
                 and not {_name(rooms, r) for r in d.get("rooms") or [d.get("room")]} <= SKIP_DOORS]
        out += door_fixes(plan, doors, "doorway narrower than 32 in clear")
    seen, uniq = set(), []
    for c in out:
        k = c["edit"].model_dump_json()
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq
