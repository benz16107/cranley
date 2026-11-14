"""Typed plan edits, checked against the plan's geometry and applied to a copy.

`apply(plan, edits)` returns the edited copy (a new sid, `w_<12 hex>`, from the base sid and the edits, so the same
renovation always gets the same id) and a diff: what each edit changed, in plan ids and metres. The base plan is never
touched. An edit that does not fit the geometry raises EditError with a sentence a person can act on.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from shapely.geometry import Polygon

from ..geometry._plan import floor_z
from ..geometry.fit import free_wall_runs
from ..scanplan import _room_shape

END_MARGIN_M = 0.05     # a doorway keeps this much wall at each end of its wall (the frame needs a stud)
GAP_M = 0.10            # and this much wall between it and the next opening
MAX_DOOR_M = 1.83       # 72 in: wider is a cased opening, not a door
MAX_SHIFT_M = 1.5       # a wall moves at most this far; further is a new layout, not an edit
MIN_ROOM_M2 = 0.8       # no edit may shrink a room below this
RAMP_SLOPE = 1 / 12     # ADA 405.2: running slope at most 1:12
BAR_RUN_M = 0.915       # 36 in: the shortest free wall that takes a grab bar (ADA 609.4 side bar is 42 in long)
SNAP = 1e-6


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WidenDoor(Edit):
    op: Literal["widen_door"] = "widen_door"
    opening: str
    width_m: float = Field(gt=0.4, le=MAX_DOOR_M, description="New opening width in the wall (clear width is about 5 cm less)")


class MoveWall(Edit):
    op: Literal["move_wall"] = "move_wall"
    wall: str
    offset_m: float = Field(ge=-MAX_SHIFT_M, le=MAX_SHIFT_M, description="Along the wall's normal; positive grows `into`'s neighbour")
    grow: str | None = Field(None, description="Room that gets bigger; the sign of offset_m is then ignored")


class RemoveWall(Edit):
    op: Literal["remove_wall"] = "remove_wall"
    wall: str


class AddRamp(Edit):
    op: Literal["add_ramp"] = "add_ramp"
    opening: str


class GrabBars(Edit):
    op: Literal["grab_bars"] = "grab_bars"
    room: str
    bars: int = Field(2, ge=1, le=6)


class DoorSwing(Edit):
    op: Literal["door_swing"] = "door_swing"
    opening: str
    swing: Literal["offset_hinges", "pocket", "swing_out"]


AnyEdit = Annotated[Union[WidenDoor, MoveWall, RemoveWall, AddRamp, GrabBars, DoorSwing], Field(discriminator="op")]
EDITS = TypeAdapter(list[AnyEdit])
HUNG_LEAF_M = 0.05  # geometry._plan.HUNG_DOOR_ALLOWANCE_M: what a hinged leaf takes out of the opening


class EditError(ValueError):
    """An edit that does not fit this plan. The message is safe to show a person."""


def parse(edits: list) -> list[Edit]:
    return EDITS.validate_python([e.model_dump() if isinstance(e, BaseModel) else e for e in edits])


def derived_sid(base: str, edits: list[Edit]) -> str:
    key = json.dumps([base, [e.model_dump() for e in edits]], sort_keys=True, separators=(",", ":"))
    return "w_" + hashlib.sha256(key.encode()).hexdigest()[:12]


def apply(plan: dict, edits: list) -> tuple[dict, list[dict]]:
    """The edited copy and one diff entry per edit. Edits apply in order; each sees the ones before it."""
    edits = parse(edits)
    if not edits:
        raise EditError("No edits to apply.")
    base = (plan.get("whatif") or {}).get("base") or plan["sid"]
    prior = (plan.get("whatif") or {}).get("edits") or []
    out = copy.deepcopy(plan)
    if not out["quality"].get("walls"):
        raise EditError("This scan has no wall graph, so there is no geometry to edit.")
    diff = []
    for i, e in enumerate(edits):
        try:
            diff.append({"edit": i, "op": e.op, **APPLY[e.op](out, e)})
        except EditError as err:
            raise EditError(f"Edit {i + 1} ({e.op.replace('_', ' ')}): {err}") from None
    all_edits = parse(prior) + edits
    out["sid"] = derived_sid(base, all_edits)
    out["whatif"] = {"base": base, "edits": [x.model_dump() for x in all_edits]}
    out["name"] = f"{plan.get('name') or base} (what if)"
    out["floorplans"] = []  # the floor photos show the rooms as they are; a moved wall would not match them
    return out, diff


# ---- lookups ----

def _cm(x: float) -> str:
    return f"{x * 100:.1f}".rstrip("0").rstrip(".") + " cm"


def _pair(plan: dict, rooms: list[str]) -> str:
    return " to ".join(_room_name(plan, r) for r in rooms) if len(rooms) > 1 else f"{_room_name(plan, rooms[0])} to outside"


def _by(plan: dict, key: str, id_: str, what: str) -> dict:
    hit = next((x for x in plan[key] if x["id"] == id_), None)
    if hit is None:
        raise EditError(f"there is no {what} {id_} in this plan")
    return hit


def _room_name(plan: dict, rid: str) -> str:
    r = next((r for r in plan["rooms"] if r["id"] == rid), None)
    return (r or {}).get("label") or "room"


def _door(plan: dict, oid: str) -> dict:
    o = _by(plan, "openings", oid, "opening")
    if o["type"] == "window":
        raise EditError("that opening is a window, not a door")
    return o


def _t(wall: dict, pt) -> float:
    (ax, ay), (bx, by) = wall["a"], wall["b"]
    L2 = (bx - ax) ** 2 + (by - ay) ** 2 or 1e-12
    return ((pt[0] - ax) * (bx - ax) + (pt[1] - ay) * (by - ay)) / L2


def _at(wall: dict, t: float) -> list[float]:
    (ax, ay), (bx, by) = wall["a"], wall["b"]
    return [ax + (bx - ax) * t, ay + (by - ay) * t]


def _normal(wall: dict) -> tuple[float, float]:
    (ax, ay), (bx, by) = wall["a"], wall["b"]
    L = math.hypot(bx - ax, by - ay) or 1.0
    return (-(by - ay) / L, (bx - ax) / L)


def _reshape(plan: dict, rids: set[str]) -> dict[str, tuple[float | None, float | None]]:
    """Rebuild the outline of these rooms from their walls (the normalizer's own polygonize). Returns old and new
    area per room. Matterport's area is kept as a base and moved by the change in outline area."""
    walls = {w["id"]: w for w in plan["walls"]}
    out = {}
    for r in plan["rooms"]:
        if r["id"] not in rids:
            continue
        old_poly = Polygon(r["polygon"]).area if len(r.get("polygon") or []) >= 3 else None
        shape = _room_shape(r["walls"], r.get("holes") or [], walls)
        if not shape["polygon"]:
            raise EditError(f"the {_room_name(plan, r['id'])} would no longer close into a room")
        old = r.get("area")
        new = (old - old_poly + shape["area"]) if old and old_poly else shape["area"]
        if new < MIN_ROOM_M2:
            raise EditError(f"the {_room_name(plan, r['id'])} would shrink to {new:.1f} m²")
        r.update(polygon=shape["polygon"], hole_polygons=shape["hole_polygons"], extra_polygons=shape["extra_polygons"],
                 center=shape["center"], area=new, area_source="polygon", polygon_source="whatif",
                 width=None, depth=None)
        out[r["id"]] = (old, new)
    return out


def _fits(wall: dict, center_t: float, width: float, others: list[dict]) -> str | None:
    L = wall["length"]
    lo, hi = center_t * L - width / 2, center_t * L + width / 2
    if lo < END_MARGIN_M or hi > L - END_MARGIN_M:
        return f"a {width:.2f} m opening does not fit in its {L:.2f} m wall at this position"
    for o in others:
        c = _t(wall, o["center"]) * L
        if abs(c - center_t * L) < (width + (o["width"] or 0)) / 2 + GAP_M:
            return f"a {width:.2f} m opening would run into the {o['type']} beside it"
    return None


def _place(wall: dict, t0: float, width: float, others: list[dict]) -> float:
    """Where along the wall (0..1) an opening this wide fits: its own place if it can, else the nearest place that
    does, in 1 cm steps (the frame is rebuilt anyway)."""
    L = wall["length"] or 1e-9
    tries = sorted((t0 + k * 0.01 / L for k in range(-int(L * 100) - 1, int(L * 100) + 2)), key=lambda t: abs(t - t0))
    t = next((t for t in tries if 0 <= t <= 1 and _fits(wall, t, width, others) is None), None)
    if t is None:
        raise EditError(_fits(wall, min(max(t0, 0.0), 1.0), width, others))
    return t


# ---- edits ----

def _widen_door(plan: dict, e: WidenDoor) -> dict:
    o = _door(plan, e.opening)
    old = o["width"] or 0.0
    if e.width_m <= old + 0.005:
        raise EditError(f"the opening is already {old:.2f} m wide")
    wall = _by(plan, "walls", o["wall"], "wall")
    others = [x for x in plan["openings"] if x["wall"] == wall["id"] and x["id"] != o["id"]]
    t0, L = _t(wall, o["center"]), wall["length"]
    t = _place(wall, t0, e.width_m, others)
    o["center"], o["width"] = _at(wall, t), e.width_m
    return {"opening": o["id"], "wall": wall["id"], "rooms": o["rooms"], "width": [old, e.width_m],
            "short": f"Widen door, {_pair(plan, o['rooms'])}",
            "shift_m": round(abs(t - t0) * L, 3), "wall_length": wall["length"],
            "text": f"Widen the door between {' and '.join(_room_name(plan, r) for r in o['rooms']) or 'rooms'} "
                    f"from {_cm(old)} to {_cm(e.width_m)}"}


def _connected(plan: dict, wall: dict) -> list[tuple[dict, str, str | None]]:
    """Walls with an end on this one: (other wall, its end 'a'|'b', our end 'a'|'b', or None for a T that meets
    the middle of this wall)."""
    from shapely.geometry import LineString, Point
    seg = LineString([wall["a"], wall["b"]])
    out = []
    for w in plan["walls"]:
        if w["id"] == wall["id"] or w["floor"] != wall["floor"]:
            continue
        for theirs in ("a", "b"):
            mine = next((m for m in ("a", "b") if math.dist(w[theirs], wall[m]) < SNAP), None)
            if mine or seg.distance(Point(w[theirs])) < 1e-4:
                out.append((w, theirs, mine))
    return out


def _move_wall(plan: dict, e: MoveWall) -> dict:
    wall = _by(plan, "walls", e.wall, "wall")
    if wall["type"] != "wall":
        raise EditError("that is an invisible boundary, not a wall")
    rooms = wall["rooms"]
    if len(rooms) != 2:
        raise EditError("only a wall between two scanned rooms can move (an outer wall moves the building)")
    nx, ny = _normal(wall)
    off = e.offset_m
    if e.grow:
        if e.grow not in rooms:
            raise EditError(f"the wall is not on the {e.grow} room")
        r = next(r for r in plan["rooms"] if r["id"] == e.grow)
        c = r.get("center") or Polygon(r["polygon"]).representative_point().coords[0]
        mid = _at(wall, 0.5)
        side = (c[0] - mid[0]) * nx + (c[1] - mid[1]) * ny  # >0: the grown room is on the +normal side
        off = -abs(off) if side > 0 else abs(off)
    if abs(off) < 0.01:
        raise EditError("move it at least 1 cm")
    links = _connected(plan, wall)
    for w, _, _ in links:  # a neighbour must be roughly at right angles, so stretching it keeps its line
        cos = abs(_normal(w)[0] * nx + _normal(w)[1] * ny)
        if cos > 0.26:
            raise EditError("a wall meeting this one is not at right angles to it, so the move would bend it")
    old_a, old_b = list(wall["a"]), list(wall["b"])
    slid: list[str] = []
    for k in ("a", "b"):
        wall[k] = [wall[k][0] + nx * off, wall[k][1] + ny * off]
    for w, theirs, mine in links:
        w[theirs] = list(wall[mine]) if mine else [w[theirs][0] + nx * off, w[theirs][1] + ny * off]
        w["length"] = math.dist(w["a"], w["b"])
        for o in (x for x in plan["openings"] if x["wall"] == w["id"]):
            try:
                t = _place(w, _t(w, o["center"]), o["width"] or 0,
                           [x for x in plan["openings"] if x["wall"] == w["id"] and x is not o])
            except EditError:
                raise EditError(f"the {o['type']} in a wall that meets this one would no longer fit") from None
            if math.dist(_at(w, t), o["center"]) > 0.005:
                slid.append(o["id"])
            o["center"] = _at(w, t)
    for o in (x for x in plan["openings"] if x["wall"] == wall["id"]):
        o["center"] = [o["center"][0] + nx * off, o["center"][1] + ny * off]
    touched = set(rooms) | {r for w, _, _ in links for r in w["rooms"]}
    areas = _reshape(plan, touched)
    return {"wall": wall["id"], "rooms": rooms, "offset_m": round(abs(off), 3),
            "short": f"Move wall {abs(off) * 100:.0f} cm, {_pair(plan, rooms)}", "a": [old_a, wall["a"]],
            "b": [old_b, wall["b"]], "length": wall["length"], "stretched": [w["id"] for w, _, _ in links], "slid_openings": slid,
            "areas": {k: [round(a, 2) if a else a, round(b, 2)] for k, (a, b) in areas.items()},
            "swept_m2": round(abs(off) * wall["length"], 2),
            "text": f"Move the wall between the {_room_name(plan, rooms[0])} and the {_room_name(plan, rooms[1])} "
                    f"by {abs(off) * 100:.0f} cm" + (f" into the {_room_name(plan, next(r for r in rooms if r != e.grow))}"
                                                    if e.grow else "")}


def _remove_wall(plan: dict, e: RemoveWall) -> dict:
    wall = _by(plan, "walls", e.wall, "wall")
    if wall["type"] != "wall" or len(wall["rooms"]) != 2:
        raise EditError("only a wall between two scanned rooms can come out")
    keep_id, gone_id = sorted(wall["rooms"], key=lambda rid: -(next(r for r in plan["rooms"] if r["id"] == rid).get("area") or 0))
    keep = next(r for r in plan["rooms"] if r["id"] == keep_id)
    gone = next(r for r in plan["rooms"] if r["id"] == gone_id)
    if keep["floor"] != gone["floor"]:
        raise EditError("the rooms either side are on different floors")
    shared = {w["id"] for w in plan["walls"] if set(w["rooms"]) == {keep_id, gone_id}}
    walls_before = list(plan["walls"])
    dropped = [o["id"] for o in plan["openings"] if o["wall"] in shared]
    plan["openings"] = [o for o in plan["openings"] if o["wall"] not in shared]
    plan["walls"] = [w for w in plan["walls"] if w["id"] not in shared]
    for w in plan["walls"]:
        w["rooms"] = list(dict.fromkeys(keep_id if r == gone_id else r for r in w["rooms"]))
    for o in plan["openings"]:
        o["rooms"] = list(dict.fromkeys(keep_id if r == gone_id else r for r in o["rooms"]))
    for p in plan.get("panos") or []:
        if p.get("room") == gone_id:
            p["room"] = keep_id
    keep["walls"] = [w for w in dict.fromkeys(keep["walls"] + gone["walls"]) if w not in shared]
    keep["holes"] = (keep.get("holes") or []) + (gone.get("holes") or [])
    old_keep, old_gone = keep.get("area") or 0, gone.get("area") or 0
    plan["rooms"] = [r for r in plan["rooms"] if r["id"] != gone_id]
    _reshape(plan, {keep_id})
    if old_keep and old_gone:  # Matterport's areas, summed: the wall's own footprint is too small to matter
        keep["area"] = old_keep + old_gone
    length = sum(w["length"] for w in walls_before if w["id"] in shared)
    return {"wall": wall["id"], "walls": sorted(shared), "rooms": [keep_id, gone_id], "merged_into": keep_id,
            "short": f"Take out wall, {keep.get('label') or 'room'} and {gone.get('label') or 'room'}",
            "removed_openings": dropped, "length": length,
            "areas": {keep_id: [round(old_keep, 2), round(keep["area"], 2)], gone_id: [round(old_gone, 2), 0.0]},
            "text": f"Take out the wall between the {keep.get('label') or 'room'} and the {gone.get('label') or 'room'}"}


def _add_ramp(plan: dict, e: AddRamp) -> dict:
    o = _door(plan, e.opening)
    if o.get("sill") is None:
        raise EditError("the scan has no sill height for this doorway, so the step is unknown")
    z = floor_z(plan).get(o["floor"], 0.0)
    rise = abs(o["sill"] - z)
    if rise <= 0.013:
        raise EditError(f"the sill is {rise * 100:.1f} cm off the floor: no ramp needed")
    if rise > 0.76:
        raise EditError(f"a {rise:.2f} m rise needs a lift, not a ramp (ADA 405.6: 30 in per run)")
    o["sill"] = z
    run = rise / RAMP_SLOPE
    return {"opening": o["id"], "rooms": o["rooms"], "rise_m": round(rise, 3), "run_m": round(run, 2),
            "short": f"Ramp, {_pair(plan, o['rooms'])}",
            "text": f"Ramp the {rise * 100:.0f} cm step at the door to the {_room_name(plan, o['rooms'][0])} "
                    f"({run:.1f} m at 1:12)"}


def _grab_bars(plan: dict, e: GrabBars) -> dict:
    r = _by(plan, "rooms", e.room, "room")
    runs = [x for x in free_wall_runs(plan, r["id"]).get("runs") or [] if x["length"] >= BAR_RUN_M]
    if not runs:
        raise EditError(f"the {r.get('label') or 'room'} has no stretch of free wall {BAR_RUN_M:.2f} m long for a bar")
    plan.setdefault("fixtures", []).append({"kind": "grab_bars", "room": r["id"], "count": e.bars, "source": "whatif"})
    return {"room": r["id"], "bars": e.bars, "longest_free_wall": round(runs[0]["length"], 2),
            "short": f"Grab bars, {r.get('label') or 'room'}",
            "text": f"Fit {e.bars} grab bars in the {r.get('label') or 'room'} (with blocking in the wall)"}


def _door_swing(plan: dict, e: DoorSwing) -> dict:
    o = _door(plan, e.opening)
    if o["type"] != "doorway":
        raise EditError("that is an open passage with no door to rehang")
    old = o["width"] or 0.0
    if e.swing in ("offset_hinges", "pocket"):
        # shortcut: tools take a doorway's clear width as the opening less a hung leaf; a leaf that swings clear of
        # the opening (offset hinges) or slides into the wall (pocket) gives the whole opening, so the edit adds
        # the leaf back to the width. Replace with a `swing` field read by geometry.clear_width if the lead adds one
        o["width"] = old + HUNG_LEAF_M
    o["swing"] = e.swing
    return {"opening": o["id"], "rooms": o["rooms"], "swing": e.swing, "width": [old, o["width"]],
            "short": {"offset_hinges": "Offset hinges", "pocket": "Pocket door", "swing_out": "Door swings out"}[e.swing]
                     + f", {_pair(plan, o['rooms'])}",
            "modelled": e.swing != "swing_out",
            "text": {"offset_hinges": "Rehang the door on offset hinges", "pocket": "Replace the door with a pocket door",
                     "swing_out": "Rehang the door to swing out"}[e.swing]
                    + f" between {' and '.join(_room_name(plan, r) for r in o['rooms'])}"}


APPLY = {"widen_door": _widen_door, "move_wall": _move_wall, "remove_wall": _remove_wall, "add_ramp": _add_ramp,
         "grab_bars": _grab_bars, "door_swing": _door_swing}
