"""Flood rehearsal: water at a level in scan z, per-room depth and wetted areas, and the order rooms flood.

Water enters through exterior openings (a doorway with one room, or a window with one room) once the level is
above the sill, and spreads through doorways over their sills. Stairs are not in the scan, so an upper floor
also floods once the level passes its floor height. Floor heights come from the doorway sills on each floor; a room
whose panoramas and a doorway sill both show a step (a sunken garage) gets its own level."""
from __future__ import annotations

import heapq
import math
from itertools import pairwise

from ._plan import (
    cached,
    default_ceiling,
    floor_z,
    geo_source,
    openings_by_id,
    polygons,
    room_floor_z,
    room_label,
    walls_by_id,
)
from .graph import room_graph


def flood_levels(plan: dict, entry: str | None = None) -> dict:
    """The water level (scan z) at which each room first takes water, and the opening it comes through.
    `entry` limits where water gets in to one exterior opening id."""
    fz = floor_z(plan)
    rooms = plan.get("rooms") or []
    z0 = cached(plan, "room_floor_z", lambda: room_floor_z(plan))
    adj: dict[str, list[tuple[str, float, str | None]]] = {}

    def link(a, b, cost, via):
        adj.setdefault(a, []).append((b, cost, via))
        adj.setdefault(b, []).append((a, cost, via))

    g = cached(plan, "graph", lambda: room_graph(plan))
    note = None
    if g["available"]:
        for e in g["entrances"]:
            if entry in (None, e["opening"]):
                link("outside", e["room"], e["sill"] if e["sill"] is not None else z0[e["room"]], e["opening"])
        for o in plan.get("openings") or []:
            if o["type"] == "window" and len(o.get("rooms") or []) == 1 and entry in (None, o["id"]):
                link("outside", o["rooms"][0], o["sill"] if o["sill"] is not None else z0[o["rooms"][0]], o["id"])
        for l in g["links"]:
            a, b = l["rooms"]
            link(a, b, l["sill"] if l["sill"] is not None else max(z0[a], z0[b]), l["opening"] or l["id"])
        seeped = _seep_links(plan, g["components"])
        for a, b in seeped:
            link(a, b, max(z0[a], z0[b]), None)
        if seeped:
            note = (f"{len(seeped)} pairs of rooms share a wall but no doorway in the scan (an open passage the scan "
                    "missed, or a wall); water is taken to pass between them at the higher floor, as house walls are "
                    "not watertight.")
    if "outside" not in adj:
        note = "No exterior opening in the scan; water is taken to rise from the floor in every room."
        for r in rooms:
            link("outside", r["id"], z0[r["id"]], None)
    floors = sorted(plan.get("floors") or [], key=lambda f: f.get("sequence") or 0)
    for lower, upper in pairwise(floors):
        stair = f"stair:{upper['id']}"
        for r in rooms:
            if r["floor"] in (lower["id"], upper["id"]):
                link(stair, r["id"], fz.get(upper["id"], 0.0), None)
    best = {"outside": -math.inf}
    via: dict[str, str | None] = {}
    heap = [(-math.inf, "outside")]
    while heap:
        d, u = heapq.heappop(heap)
        if d > best.get(u, math.inf):
            continue
        for v, cost, through in adj.get(u, ()):
            nd = max(d, cost, z0.get(v, -math.inf))
            if nd < best.get(v, math.inf):
                best[v], via[v] = nd, through
                heapq.heappush(heap, (nd, v))
    return {"levels": {r["id"]: best.get(r["id"]) for r in rooms}, "via": via, "floor_z": fz, "room_z": z0,
            "note": note}


SHARED_WALL_M = 0.6   # rooms whose outlines run side by side this far share a wall


def _seep_links(plan: dict, components: list[list[str]]) -> list[tuple[str, str]]:
    """Room pairs on one floor, in different connected parts of the room graph, that share a wall."""
    comp = {r: i for i, c in enumerate(components) for r in c}
    polys = polygons(plan)
    rooms = [r for r in plan.get("rooms") or [] if polys.get(r["id"]) is not None and r.get("label") != "Void"]
    out = []
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            if a["floor"] != b["floor"] or comp.get(a["id"]) == comp.get(b["id"]):
                continue
            pa, pb = polys[a["id"]], polys[b["id"]]
            if pa.distance(pb) > 0.3:
                continue
            if pa.buffer(0.2).intersection(pb.buffer(0.2)).area / 0.4 >= SHARED_WALL_M:
                out.append((a["id"], b["id"]))
    return out


def water(plan: dict, level: float, entry: str | None = None) -> dict:
    """Water at `level` (scan z, metres). Per room: depth, wetted floor area, wetted wall area net of openings,
    openings overtopped; the order rooms flood; a Contract 4 water overlay and a depth lens."""
    rooms = plan.get("rooms") or []
    if not rooms:
        return {"available": False, "reason": "This scan has no rooms."}
    fl = flood_levels(plan, entry)
    walls, opens, polys = walls_by_id(plan), openings_by_id(plan), polygons(plan)
    ceiling = default_ceiling(plan) or 2.4
    per_room, values = [], {}
    for r in rooms:
        z0 = fl["room_z"][r["id"]]
        at = fl["levels"][r["id"]]
        reached = at is not None and at < level
        depth = max(0.0, level - z0) if reached else 0.0
        h = r.get("height") or ceiling
        wet_h = min(depth, h)
        rw = [walls[w] for w in r.get("walls") or [] if w in walls and walls[w].get("type") != "invisible"]
        wall_area = sum(w["length"] for w in rw) * wet_h
        over = []
        for w in rw:
            for oid in w.get("openings") or []:
                o = opens.get(oid)
                if o is None or o.get("sill") is None:
                    continue
                wall_area -= max(0.0, min(z0 + wet_h, o["sill"] + (o["height"] or 0)) - max(z0, o["sill"])) * (o["width"] or 0)
                if o["sill"] < level:
                    over.append(oid)
        area = r.get("area") or (polys[r["id"]].area if polys[r["id"]] is not None else None)
        per_room.append({"room": r["id"], "label": room_label(r), "floor": r["floor"], "floor_z": z0,
                         "step_m": round(z0 - fl["floor_z"].get(r["floor"], 0.0), 3),
                         "floods_at": at if at is not None and at > -math.inf else None, "reached": reached,
                         "via": fl["via"].get(r["id"]), "depth": depth,
                         "wetted_floor_area": (area or 0.0) if depth > 0 else 0.0,
                         "wetted_wall_area": max(0.0, wall_area) if depth > 0 else 0.0,
                         "openings_overtopped": over if depth > 0 else []})
        values[r["id"]] = round(depth, 3)
    order = sorted((x for x in per_room if x["floods_at"] is not None), key=lambda x: x["floods_at"])
    overtopped = sorted({o["id"] for o in plan.get("openings") or [] if o.get("sill") is not None and o["sill"] < level})
    ground = min(fl["floor_z"].values(), default=0.0)
    return {"available": True, "level": level, "datum": "scan_z", "level_above_lowest_floor": level - ground,
            "rooms": per_room, "order": [{"room": x["room"], "label": x["label"], "floods_at": x["floods_at"],
                                          "via": x["via"]} for x in order],
            "openings_overtopped": overtopped, "note": fl["note"],
            "overlay": {"kind": "water", "level_m": level, "datum": "scan_z"},
            "lens": {"kind": "lens", "values": values, "ramp": "sequential",
                     "legend": {"title": "Water depth", "unit": "m", "min": 0, "max": max(values.values(), default=0)}},
            "source": geo_source("Still-water fill through openings by sill height; floor levels from doorway "
                                 "sills. No flow rates, pressure or drainage.", "medium")}
