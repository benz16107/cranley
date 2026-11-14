"""Walkable routes on one floor, their clear widths, and which rooms a body of a given width can reach.

Rooms joined by invisible walls form one open space. Inside a space the route is a shortest path over a
visibility graph whose nodes are door centres and points set back WALK_OFFSET_M from each inside corner.
Rooms with no polygon are crossed door to door in a straight line (low confidence).
Furniture is not in the wall graph: every width here is the empty room."""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np
import shapely
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from ._plan import (
    VERDICT_STATUS,
    cached,
    clear_width,
    floor_z,
    geo_source,
    implausible,
    judge,
    polygons,
    room_label,
    rooms_by_id,
    unavailable,
)
from .graph import neighbours, room_graph

WALK_OFFSET_M = 0.3        # half a person's width: routes keep this far from inside corners
EPS_M = 0.02               # slack so a segment along a wall or ending on a door still counts as inside
SAMPLE_STEP_M = 0.2        # spacing of corridor width samples along the route
DOOR_SKIP_M = 0.35         # near a door the door width governs, so corridor samples skip this span
MAX_SIDE_M = 3.0           # a wall farther than this on either side means open floor, not a corridor
CORRIDOR_REPORT_M = 1.5    # corridor narrowings under this width are reported as chokes
DEFAULT_THICKNESS_M = 0.12
ADA_DOOR_CLEAR_M = 0.8128  # 32 in


@dataclass
class _Space:
    rooms: list[str]
    region: Polygon | None
    blockers: object = None  # walls inside the space that are on none of its rooms' boundaries
    nodes: list[str] = field(default_factory=list)


@dataclass
class _Nav:
    floor: str
    z: float
    pos: dict[str, tuple[float, float]]
    adj: dict[str, list[tuple[str, float]]]
    spaces: list[_Space]
    room_space: dict[str, int]
    doors: dict[str, dict]
    segs: tuple[np.ndarray, np.ndarray, np.ndarray]


def _graph(plan: dict) -> dict:
    return cached(plan, "graph", lambda: room_graph(plan))


def _nav(plan: dict, floor: str) -> _Nav:
    return cached(plan, f"nav:{floor}", lambda: _build_nav(plan, floor))


def _build_nav(plan: dict, floor: str) -> _Nav:
    g = _graph(plan)
    rooms = [r for r in plan["rooms"] if r["floor"] == floor]
    # rooms joined by invisible walls are one space
    parent = {r["id"]: r["id"] for r in rooms}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    for link in g["links"]:
        if link["kind"] == "invisible" and link["floor"] == floor and all(r in parent for r in link["rooms"]):
            parent[find(link["rooms"][0])] = find(link["rooms"][1])
    groups: dict[str, list[str]] = {}
    for r in rooms:
        groups.setdefault(find(r["id"]), []).append(r["id"])
    room_polys = polygons(plan)
    pieces = _wall_pieces(plan, floor)
    wall_rooms = {w["id"]: set(w.get("rooms") or []) for w in plan["walls"]}
    spaces: list[_Space] = []
    room_space: dict[str, int] = {}
    pos: dict[str, tuple[float, float]] = {}
    adj: dict[str, list[tuple[str, float]]] = {}
    doors: dict[str, dict] = {}
    for d in g["links"] + g["entrances"]:
        if d["floor"] == floor and d["kind"] != "invisible":
            doors[f"d:{d['id']}"] = d
            pos[f"d:{d['id']}"] = tuple(d["center"])
    for members in groups.values():
        polys = [p for p in (room_polys[m] for m in members) if p is not None]
        region = unary_union([p.buffer(EPS_M) for p in polys]) if polys else None
        sp = _Space(members, region)
        if region is not None:
            inside = [shapely.linestrings([a, b]) for wid, a, b, _ in pieces if not wall_rooms[wid] & set(members)]
            hits = [ln for ln in inside if region.intersects(ln)]
            sp.blockers = shapely.multilinestrings(hits) if hits else None
        idx = len(spaces)
        spaces.append(sp)
        for m in members:
            room_space[m] = idx
        sp.nodes = [nid for nid, d in doors.items()
                    if set(d["rooms"] if "rooms" in d else [d["room"]]) & set(members)]
        for i, p in enumerate(polys):
            for j, w in enumerate(_corner_waypoints(p)):
                nid = f"w:{idx}:{i}:{j}"
                pos[nid] = w
                sp.nodes.append(nid)
        _connect(sp, sp.nodes, pos, adj)
    segs = (np.array([p[1] for p in pieces]).reshape(-1, 2), np.array([p[2] for p in pieces]).reshape(-1, 2),
            np.array([p[3] for p in pieces]))
    return _Nav(floor, floor_z(plan).get(floor, 0.0), pos, adj, spaces, room_space, doors, segs)


def _corner_waypoints(poly: Polygon) -> list[tuple[float, float]]:
    """Points WALK_OFFSET_M inside each reflex (inside) corner: the only places a shortest path bends."""
    inner = poly.buffer(-WALK_OFFSET_M, join_style="mitre")
    if inner.is_empty:
        return []
    ring = shapely.geometry.polygon.orient(poly, 1.0).exterior.coords[:-1]
    n = len(ring)
    out = []
    for i in range(n):
        (ax, ay), (bx, by), (cx, cy) = ring[i - 1], ring[i], ring[(i + 1) % n]
        if (bx - ax) * (cy - by) - (by - ay) * (cx - bx) < -1e-9:  # right turn on a CCW ring = reflex
            q = shapely.ops.nearest_points(inner.boundary, Point(bx, by))[0]
            out.append((q.x, q.y))
    return out


def _connect(sp: _Space, nodes: list[str], pos, adj, only_from: str | None = None) -> None:
    pairs = [(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]] if only_from is None else \
        [(only_from, b) for b in nodes if b != only_from]
    if not pairs:
        return
    if sp.region is None:
        ok = np.ones(len(pairs), dtype=bool)  # no polygon: walk straight between this room's doors
    else:
        lines = shapely.linestrings([[pos[a], pos[b]] for a, b in pairs])
        shapely.prepare(sp.region)
        ok = shapely.covers(sp.region, lines)
        if sp.blockers is not None:
            shapely.prepare(sp.blockers)
            ok &= ~shapely.intersects(sp.blockers, lines)
    for (a, b), good in zip(pairs, ok):
        if good:
            d = math.dist(pos[a], pos[b])
            adj.setdefault(a, []).append((b, d))
            adj.setdefault(b, []).append((a, d))


def _wall_pieces(plan: dict, floor: str) -> list[tuple[str, tuple, tuple, float]]:
    """Solid wall pieces on a floor with door spans cut out: (wall id, a, b, half thickness)."""
    opens = {o["id"]: o for o in plan.get("openings") or []}
    out = []
    for w in plan.get("walls") or []:
        if w["floor"] != floor or w.get("type") == "invisible" or w["length"] <= 0:
            continue
        (ax, ay), (bx, by) = w["a"], w["b"]
        L = w["length"]
        cuts = sorted((math.dist(w["a"], opens[o]["center"]) - (opens[o]["width"] or 0) / 2,
                        math.dist(w["a"], opens[o]["center"]) + (opens[o]["width"] or 0) / 2)
                       for o in w.get("openings") or [] if o in opens and opens[o]["type"] != "window")
        t = 0.0
        for lo, hi in cuts + [(L, L)]:
            if lo > t + 1e-3:
                out.append((w["id"], (ax + (bx - ax) * t / L, ay + (by - ay) * t / L),
                            (ax + (bx - ax) * min(lo, L) / L, ay + (by - ay) * min(lo, L) / L),
                            (w.get("thickness") or DEFAULT_THICKNESS_M) / 2))
            t = max(t, hi)
    return out


def cross_section(segs, points: np.ndarray, dirs: np.ndarray) -> np.ndarray:
    """Clear width at each point, measured wall face to wall face perpendicular to the travel direction.
    Capped at 2 * MAX_SIDE_M when no wall is near."""
    A, B, H = segs
    if len(points) == 0:
        return np.zeros(0)
    if len(A) == 0:
        return np.full(len(points), 2 * MAX_SIDE_M)
    n = np.stack([-dirs[:, 1], dirs[:, 0]], axis=1)
    E = B - A
    total = np.zeros(len(points))
    for s in (1.0, -1.0):
        r = n * s
        ap = A[None, :, :] - points[:, None, :]
        den = r[:, None, 0] * E[None, :, 1] - r[:, None, 1] * E[None, :, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (ap[..., 0] * E[None, :, 1] - ap[..., 1] * E[None, :, 0]) / den
            u = (ap[..., 0] * r[:, None, 1] - ap[..., 1] * r[:, None, 0]) / den
        hit = (np.abs(den) > 1e-12) & (t > 1e-6) & (u >= 0) & (u <= 1)
        dist = np.where(hit, t - H[None, :], np.inf)
        total += np.minimum(np.clip(dist.min(axis=1), 0, None), MAX_SIDE_M)
    return total


def _locate(plan: dict, nav: _Nav, xy) -> int | None:
    p = Point(xy)
    best, best_d = None, 0.5
    for i, sp in enumerate(nav.spaces):
        if sp.region is not None:
            d = sp.region.distance(p)
            if d < best_d:
                best, best_d = i, d
    return best


def _room_point(plan: dict, room_id: str):
    poly = polygons(plan)[room_id]
    if poly is None:
        return None
    c = shapely.maximum_inscribed_circle(poly).coords[0]
    return (c[0], c[1])


def route(plan: dict, start, end, *, min_width: float = ADA_DOOR_CLEAR_M, floor: str | None = None) -> dict:
    """Shortest walkable route between two rooms or points on one floor.

    `start` and `end` are a room id, an [x, y] point (give `floor` when the plan has several), or the string
    "entrance" for the nearest entrance on that floor. Returns length, doors crossed with widths, chokes
    (doors and corridor narrowings) judged against `min_width`, the narrowest point, and a Contract 4 overlay."""
    if not plan.get("walls"):
        return unavailable("This scan has no wall graph, so there are no doors to route through.")
    rooms = rooms_by_id(plan)
    floors = {_floor_of(plan, rooms, s, floor) for s in (start, end)} - {None}
    if len(floors) != 1:
        return unavailable("Both ends must be on one floor. Stairs are not in the scan data."
                           if len(floors) > 1 else "Could not tell which floor the route is on; pass `floor`.")
    fl = floors.pop()
    nav = _nav(plan, fl)
    pos, adj = dict(nav.pos), {k: list(v) for k, v in nav.adj.items()}
    ends: list[str] = []
    q_space: dict[str, int] = {}
    for tag, s in (("S", start), ("E", end)):
        nid = f"q:{tag}"
        if s == "entrance":
            ents = [n for n, d in nav.doors.items() if "room" in d]
            if not ents:
                return unavailable("This floor has no entrance (a doorway with a room on one side only).")
            for e in ents:
                adj.setdefault(nid, []).append((e, 0.0))
                adj.setdefault(e, []).append((nid, 0.0))
            ends.append(nid)
            continue
        if isinstance(s, str):
            if s not in rooms:
                return unavailable(f"No room {s} in this scan.")
            xy, sp_i = _room_point(plan, s), nav.room_space.get(s)
        else:
            xy = (float(s[0]), float(s[1]))
            sp_i = _locate(plan, nav, xy)
            if sp_i is None:
                return unavailable(f"Point {list(xy)} is not inside any scanned room on this floor.")
        sp = nav.spaces[sp_i]
        if xy is None:  # room without polygon: start at any of its doors
            for d in sp.nodes:
                if d.startswith("d:"):
                    adj.setdefault(nid, []).append((d, 0.0))
                    adj.setdefault(d, []).append((nid, 0.0))
        else:
            pos[nid] = xy
            same = [e for e in ends if q_space.get(e) == sp_i]
            _connect(sp, sp.nodes + same + [nid], pos, adj, only_from=nid)
            q_space[nid] = sp_i
        ends.append(nid)
    path = _dijkstra(adj, pos, "q:S", "q:E")
    if path is None:
        return unavailable("No walkable connection between these two places in the wall graph.", floor=fl)
    return _describe(plan, nav, pos, path, min_width, start, end)


def _floor_of(plan, rooms, s, floor):
    if s == "entrance" or not isinstance(s, str):
        return floor or (plan["floors"][0]["id"] if len(plan.get("floors") or []) == 1 else None)
    return rooms[s]["floor"] if s in rooms else None


def _dijkstra(adj, pos, src, dst):
    dist, prev, heap = {src: 0.0}, {}, [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == dst:
            out = [u]
            while u in prev:
                u = prev[u]
                out.append(u)
            return out[::-1]
        if d > dist.get(u, math.inf):
            continue
        for v, w in adj.get(u, ()):
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v], prev[v] = nd, u
                heapq.heappush(heap, (nd, v))
    return None


def _describe(plan, nav: _Nav, pos, path, min_width, start, end) -> dict:
    pnodes = [n for n in path if n in pos]
    pts = [pos[n] for n in pnodes]
    door_nodes = [n for n in path if n.startswith("d:")]
    doors = []
    for n in door_nodes:
        d = nav.doors[n]
        cw, bad = clear_width(d), implausible(d)
        doors.append({"opening": d["opening"], "kind": d["kind"], "width": d["width"], "clear_width": cw,
                      "height": d["height"], "center": d["center"], "inferred": d.get("inferred", False),
                      "implausible": bad, "result": "measure on site" if bad else judge(cw, min_width)})
    # corridor widths sampled along each straight leg, away from doors and bends
    door_xy = np.array([nav.doors[n]["center"] for n in door_nodes]).reshape(-1, 2)
    samples, dirs, along, leg = [], [], [], []
    s0 = 0.0
    for k, ((ax, ay), (bx, by)) in enumerate(pairwise(pts)):
        L = math.hypot(bx - ax, by - ay)
        if L > 1e-6:
            ux, uy = (bx - ax) / L, (by - ay) / L
            for t in np.arange(SAMPLE_STEP_M / 2, L, SAMPLE_STEP_M):
                if t < 0.15 or t > L - 0.15:
                    continue
                p = (ax + ux * t, ay + uy * t)
                if len(door_xy) and np.min(np.hypot(door_xy[:, 0] - p[0], door_xy[:, 1] - p[1])) < DOOR_SKIP_M:
                    continue
                samples.append(p)
                dirs.append((ux, uy))
                along.append(s0 + t)
                leg.append(k)
        s0 += L
    widths = cross_section(nav.segs, np.array(samples).reshape(-1, 2), np.array(dirs).reshape(-1, 2))
    z = nav.z
    legs = [{"a": list(pts[k]), "b": list(pts[k + 1]), "length": math.dist(pts[k], pts[k + 1]),
             "min_width": min((float(w) for w, j in zip(widths, leg) if j == k), default=None)
             or _mid_width(nav, pts[k], pts[k + 1]),
             "door_at_end": nav.doors[pnodes[k + 1]]["opening"] if pnodes[k + 1].startswith("d:") else None}
            for k in range(len(pts) - 1)]
    chokes = [{"point": [*d["center"], z], "width": d["clear_width"], "kind": d["kind"], "opening": d["opening"],
               "status": VERDICT_STATUS[d["result"]], "result": d["result"], "implausible": d["implausible"]}
              for d in doors]
    run: list[int] = []
    for i in range(len(widths) + 1):
        if i < len(widths) and widths[i] < CORRIDOR_REPORT_M and (not run or along[i] - along[run[-1]] < 2 * SAMPLE_STEP_M):
            run.append(i)
            continue
        if run:
            k = min(run, key=lambda j: widths[j])
            res = judge(float(widths[k]), min_width)
            chokes.append({"point": [*samples[k], z], "width": float(widths[k]), "kind": "corridor", "opening": None,
                           "status": VERDICT_STATUS[res], "result": res, "implausible": False})
            run = []
        if i < len(widths) and widths[i] < CORRIDOR_REPORT_M:
            run = [i]
    valid = [c for c in chokes if c["width"] is not None and not c["implausible"]]  # data errors are not the narrowest
    narrow = min(valid, key=lambda c: c["width"]) if valid else None
    rooms = rooms_by_id(plan)
    name = lambda s: "the entrance" if s == "entrance" else room_label(rooms[s]) if isinstance(s, str) else "point"
    label = f"{name(start)} to {name(end)}"
    low = any(sp.region is None for sp in nav.spaces if set(sp.nodes) & set(path))
    return {"available": True, "floor": nav.floor, "length_m": s0, "points": [[x, y, z] for x, y in pts],
            "doors": doors, "chokes": chokes, "legs": legs, "narrowest": narrow, "min_width": min_width,
            "profile": [[round(a, 2), round(float(w), 3)] for a, w in zip(along, widths)],
            "overlay": {"kind": "route", "floor": nav.floor, "points": [[x, y, z] for x, y in pts],
                        "chokes": [{"point": c["point"], "width": c["width"], "status": c["status"]} for c in chokes],
                        "label": label},
            "source": geo_source("Empty-room route over the wall graph; furniture is not counted. Door widths "
                                 "less a 5 cm hung-door allowance.", "low" if low else "medium")}


def _mid_width(nav: _Nav, a, b) -> float | None:
    L = math.dist(a, b)
    if L < 1e-6:
        return None
    mid = np.array([[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]])
    return float(cross_section(nav.segs, mid, np.array([[(b[0] - a[0]) / L, (b[1] - a[1]) / L]]))[0])


def reach(plan: dict, min_width: float, start: str | None = None, max_step: float | None = None) -> dict:
    """Which rooms a body `min_width` wide can reach from the entrances (or from room `start`).

    Each room gets the widest bottleneck over all paths from a start: the narrowest door on the best path.
    Judged with the scan tolerance: 'likely pass' (reachable), 'measure on site', 'likely fail'. A doorway with
    an implausible width (a data error) does not limit the path; rooms reached through one are 'measure on site'
    and name it in `data_error`. With `max_step`, a doorway whose sill is more than that above or below its
    storey's floor level cannot be crossed (a robot's climbable step). Corridor
    pinches inside rooms are not part of this; use `route` for one path's full clearance profile."""
    g = _graph(plan)
    if not g["available"]:
        return g
    fz = floor_z(plan) if max_step is not None else {}

    def stepped(link) -> bool:
        return max_step is not None and link.get("sill") is not None and \
            abs(link["sill"] - fz.get(link["floor"], 0.0)) > max_step

    starts = [start] if start else sorted({e["room"] for e in g["entrances"] if not stepped(e)})
    note = None
    if not starts and not g["entrances"]:  # (entrances that all have too high a step leave nothing reachable)
        biggest = max((n for n in g["nodes"] if not n["void"]), key=lambda n: n["area"] or 0, default=None)
        if biggest is None:
            return unavailable("No entrance and no rooms to start from.")
        starts, note = [biggest["room"]], "No entrance in the scan; started from the largest room."
    best: dict[str, float] = {}
    via: dict[str, str | None] = {}
    suspect: dict[str, str | None] = {}  # the implausible link on the best path, if any
    heap = []
    for s in starts:
        ent = [clear_width(e) for e in g["entrances"] if e["room"] == s and not stepped(e)] if not start else [math.inf]
        w0 = max([w for w in ent if w is not None], default=math.inf)
        if w0 > best.get(s, -1):
            best[s], via[s], suspect[s] = w0, None, None
            heapq.heappush(heap, (-w0, s))
    adj = neighbours(g)
    while heap:
        nw, u = heapq.heappop(heap)
        if -nw < best[u]:
            continue
        for v, link in adj.get(u, ()):
            if stepped(link):
                continue
            cw, bad = clear_width(link), implausible(link)
            w = -nw if bad else min(-nw, cw if cw is not None else 0.0)  # a data error does not limit the width
            if w > best.get(v, -1):
                best[v], via[v], suspect[v] = w, link["id"], link["id"] if bad else suspect[u]
                heapq.heappush(heap, (-w, v))
    rooms = []
    for n in g["nodes"]:
        bw = best.get(n["room"])
        res = "likely fail" if bw is None else ("likely pass" if bw == math.inf else judge(bw, min_width))
        if res == "likely pass" and suspect.get(n["room"]):
            res = "measure on site"
        rooms.append({"room": n["room"], "label": n["label"], "floor": n["floor"], "void": n["void"],
                      "bottleneck_width": None if bw in (None, math.inf) else bw, "connected": bw is not None,
                      "result": res, "status": VERDICT_STATUS[res], "via": via.get(n["room"]),
                      "data_error": suspect.get(n["room"])})
    vals = {r["room"]: {"pass": 1, "warn": 0.5, "fail": 0}[r["status"]] for r in rooms if r["status"] != "unknown"}
    return {"available": True, "min_width": min_width, "starts": starts, "rooms": rooms, "note": note,
            "lens": {"kind": "lens", "values": vals, "ramp": "status",
                     "legend": {"title": f"Reachable at {min_width:.2f} m wide", "unit": None, "min": 0, "max": 1}},
            "source": geo_source("Door widths from the wall graph less a 5 cm hung-door allowance; stairs and "
                                 "furniture not counted.", "medium")}
