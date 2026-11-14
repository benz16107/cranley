"""The Bagua (Lo Shu nine-square) grid over a floor outline, and the lines a practitioner looks for. Pure geometry.

The grid is aligned to the house: its axes follow the dominant wall direction and it covers the outline's
bounding rectangle in thirds. Its eight outer squares are then named either by compass (Compass School: the
bearing from the centre square to each square, from the scan's geocoordinates) or by the front door (Western /
BTB: the door wall is the Knowledge, Career and Helpful people row).
"""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from ...geometry._plan import indoor_rooms, polygons, wall_normal
from ...geometry.georef import azimuth_of
from .kua import DIRS

# Lo Shu number, life area, element; the Later Heaven arrangement used by both conventions
SECTORS = {
    "N": (1, "Career and life path", "Water"),
    "NE": (8, "Knowledge and self-cultivation", "Earth"),
    "E": (3, "Family and health", "Wood"),
    "SE": (4, "Wealth", "Wood"),
    "S": (9, "Fame and reputation", "Fire"),
    "SW": (2, "Love and partnership", "Earth"),
    "W": (7, "Children and creativity", "Metal"),
    "NW": (6, "Helpful people and travel", "Metal"),
    "C": (5, "Health and balance", "Earth"),
}
# Western / BTB names the squares by where they sit seen from the front door, looking in
BTB_PLACE = {"N": "entrance side, middle", "NE": "entrance side, left", "NW": "entrance side, right",
             "E": "middle, left", "W": "middle, right", "SE": "far side, left", "S": "far side, middle",
             "SW": "far side, right", "C": "centre"}
OUTDOOR = {"Patio", "Balcony", "Deck", "Porch", "Yard", "Terrace", "Exterior"}
SPAN_SHARE = 0.25    # a room this much inside a square is listed there too
MISSING_SHARE = 0.5   # a square less than half covered by the outline is a missing area (the usual rule of thumb)


def house_angle(plan: dict, floor: str) -> float:
    """Dominant wall direction on a floor in radians, in (-pi/4, pi/4]: a length-weighted mean of angles mod 90."""
    c = s = 0.0
    for w in plan.get("walls") or []:
        if w["floor"] != floor or w.get("type") == "invisible":
            continue
        dx, dy = w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]
        a, length = math.atan2(dy, dx), math.hypot(dx, dy)
        c, s = c + length * math.cos(4 * a), s + length * math.sin(4 * a)
    return math.atan2(s, c) / 4 if (c or s) else 0.0


def outline(plan: dict, floor: str) -> Polygon | None:
    """The floor's indoor outline: every walled room except outdoor ones, small gaps at the walls closed."""
    polys = polygons(plan)
    parts = [polys[r["id"]] for r in indoor_rooms(plan)
             if r["floor"] == floor and r.get("label") not in OUTDOOR and polys.get(r["id"]) is not None]
    if not parts:
        return None
    u = unary_union([p.buffer(0.2, join_style=2) for p in parts]).buffer(-0.2, join_style=2)
    if u.geom_type == "MultiPolygon":
        u = max(u.geoms, key=lambda g: g.area)
    return u if not u.is_empty else None


def _cw(ref: tuple[float, float], d: tuple[float, float]) -> float:
    """Clockwise angle in degrees from ref to d in the scan frame (z up)."""
    return -math.degrees(math.atan2(ref[0] * d[1] - ref[1] * d[0], ref[0] * d[0] + ref[1] * d[1])) % 360


def _assign(bearings: list[float]) -> list[str]:
    """Name eight squares by their bearings, keeping their clockwise order (each name used once)."""
    order = sorted(range(8), key=lambda i: bearings[i])
    best = min(range(8), key=lambda k: sum(abs((bearings[i] - 45 * ((k + j) % 8) + 180) % 360 - 180)
                                         for j, i in enumerate(order)))
    names = [""] * 8
    for j, i in enumerate(order):
        names[i] = DIRS[(best + j) % 8]
    return names


def grid(plan: dict, floor: str, convention: str, door_out: tuple[float, float] | None) -> dict:
    """{available, theta, cells: {dir: {polygon, center, size, share, rooms}}, offset_deg, outline}."""
    poly = outline(plan, floor)
    if poly is None:
        return {"available": False, "reason": "This floor has no room outlines to lay a grid over."}
    th = house_angle(plan, floor)
    u, v = (math.cos(th), math.sin(th)), (-math.sin(th), math.cos(th))
    pts = list(poly.exterior.coords)
    ss, ts = [p[0] * u[0] + p[1] * u[1] for p in pts], [p[0] * v[0] + p[1] * v[1] for p in pts]
    s0, s1, t0, t1 = min(ss), max(ss), min(ts), max(ts)
    ws, wt = (s1 - s0) / 3, (t1 - t0) / 3

    def at(s, t):
        return (s * u[0] + t * v[0], s * u[1] + t * v[1])

    raw = {}
    for i in range(3):
        for j in range(3):
            a, b = s0 + i * ws, t0 + j * wt
            cell = Polygon([at(a, b), at(a + ws, b), at(a + ws, b + wt), at(a, b + wt)])
            raw[(i, j)] = {"polygon": cell, "center": at(a + ws / 2, b + wt / 2), "size": (ws, wt),
                           "share": poly.intersection(cell).area / cell.area if cell.area else 0.0}
    cx, cy = raw[(1, 1)]["center"]
    outer = [k for k in raw if k != (1, 1)]
    vec = [(raw[k]["center"][0] - cx, raw[k]["center"][1] - cy) for k in outer]
    if convention == "compass":
        bearings = [azimuth_of(plan, dx, dy) for dx, dy in vec]
        ref_az = azimuth_of(plan, *v)
        offset = (ref_az + 45) % 90 - 45  # how far the house's walls are turned from the compass axes
    else:
        bearings = [_cw(door_out, d) for d in vec]
        offset = None
    names = _assign(bearings)
    cells = {"C": raw[(1, 1)] | {"bearing": None}}
    for k, name, brg in zip(outer, names, bearings):
        cells[name] = raw[k] | {"bearing": brg}
    rooms_in = room_sectors(plan, floor, cells)
    for d, c in cells.items():  # a room is listed in every square holding a quarter of it, or most of it
        c["rooms"] = [rid for rid, sec in rooms_in.items() if sec == d or share_in(plan, rid, c["polygon"]) >= SPAN_SHARE]
    return {"available": True, "theta": th, "cells": cells, "offset_deg": offset, "outline": poly,
            "room_sector": rooms_in}


def room_sectors(plan: dict, floor: str, cells: dict) -> dict[str, str]:
    """Room id -> the square that holds most of its floor."""
    polys, out = polygons(plan), {}
    for r in plan.get("rooms") or []:
        p = polys.get(r["id"])
        if r["floor"] != floor or p is None or r.get("label") == "Void":
            continue
        out[r["id"]] = max(cells, key=lambda d: p.intersection(cells[d]["polygon"]).area)
    return out


def share_in(plan: dict, room_id: str, cell: Polygon) -> float:
    p = polygons(plan).get(room_id)
    return p.intersection(cell).area / p.area if p is not None and p.area else 0.0


# ---- lines of sight between doors ----

def inward(plan: dict, opening: dict, room_id: str | None, walls: dict) -> tuple[float, float]:
    """Unit normal of an opening's wall pointing into its room (or into the outline when the room is unknown)."""
    w = walls.get(opening["wall"])
    nx, ny = wall_normal(w) if w else (0.0, 1.0)
    poly = polygons(plan).get(room_id) if room_id else None
    probe = Point(opening["center"][0] + 0.3 * nx, opening["center"][1] + 0.3 * ny)
    if poly is None:
        poly = unary_union([p for p in polygons(plan).values() if p is not None])
    return (nx, ny) if poly.contains(probe) else (-nx, -ny)


def clear_line(plan: dict, floor: str, a, b, skip: float = 0.2) -> bool:
    """True when the straight line from a to b crosses walls only where they have a doorway or opening."""
    seg = LineString([a, b])
    ops = [o for o in plan.get("openings") or [] if o["floor"] == floor and o["type"] != "window"]
    for w in plan.get("walls") or []:
        if w["floor"] != floor or w.get("type") == "invisible":
            continue
        hit = seg.intersection(LineString([w["a"], w["b"]]))
        if hit.is_empty or hit.geom_type != "Point":
            continue
        if hit.distance(Point(a)) < skip or hit.distance(Point(b)) < skip:
            continue
        dx, dy = w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]
        length = math.hypot(dx, dy) or 1.0
        if not any(o["wall"] == w["id"] and abs(((hit.x - o["center"][0]) * dx + (hit.y - o["center"][1]) * dy) / length)
                   <= (o.get("width") or 0) / 2 for o in ops):
            return False
    return True


LINE_LATERAL_M = 0.4   # door centres this close to the front door's axis count as "in line"


def door_line(plan: dict, front: dict, out: tuple[float, float], walls: dict, exits: set[str]) -> list[dict]:
    """Doorways on the front door's floor straight in from it with nothing solid between, nearest first."""
    c0, n = front["center"], (-out[0], -out[1])
    found = []
    for o in plan.get("openings") or []:
        if o["id"] == front["opening"] or o["floor"] != front["floor"] or o["type"] == "window":
            continue
        dx, dy = o["center"][0] - c0[0], o["center"][1] - c0[1]
        along, lateral = dx * n[0] + dy * n[1], abs(-dx * n[1] + dy * n[0])
        w = walls.get(o["wall"])
        if along < 0.8 or lateral > LINE_LATERAL_M or w is None:
            continue
        wx, wy = w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]
        if abs(wx * n[0] + wy * n[1]) / (math.hypot(wx, wy) or 1) > 0.5:  # the door must face the front door
            continue
        start = (c0[0] + 0.15 * n[0], c0[1] + 0.15 * n[1])
        if clear_line(plan, front["floor"], start, o["center"]):
            found.append({"opening": o["id"], "along": along, "lateral": lateral, "center": o["center"],
                          "exit": o["id"] in exits})
    return sorted(found, key=lambda f: f["along"])
