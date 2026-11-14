"""Walls, room outlines and openings for scans whose Model API response has no wall graph. Pure functions.

What Matterport still serves for such a scan, per floor (checked on 2026-11-14):
  - a schematic DXF of LINE entities at the inner faces of the walls, already in the scan frame in metres (its
    extent matched the wall graph to 0.1 m on nine scans that have one). Two styles: closed outlines per room
    with no doors (older scans), or each wall face as its own segment with corners a few millimetres open and a
    gap at each door (newer). `closed` snaps the corners and bridges the door gaps.
  - a schematic PNG drawn from the same outlines at 100 px per metre, with no origin. It shows openings: a gap
    in a room's outline, usually filled with a dotted line.
So rooms come from the DXF faces, walls from pairs of facing outline edges (a shared wall's centre line is
midway between them, its thickness the gap), and openings from the runs along each edge that are not solid in
the PNG after it is registered to the DXF by a pixel offset.

Nothing here is measured: an opening's width is good to about the PNG's line work (a few centimetres at best),
its height and sill are unknown, and a door cannot be told from a window or an open passage on an outer wall.
"""
from __future__ import annotations

import math
import re

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

PX_PER_M = 100.0       # the schematic PNG's scale (measured on 7 scans: 100.0 to 100.6 from the line extents)
MIN_ROOM_WIDTH = 0.35  # m; faces thinner than this (2 * area / perimeter) are the space inside a wall
MIN_ROOM_AREA = 0.3    # m²
MAX_WALL_GAP = 0.45    # m; facing edges further apart than this are not one wall
MIN_SHARED = 0.15      # m; shorter overlaps between facing edges are corners, not walls
PARALLEL_DEG = 4.0
SNAP_M = 0.03          # m; endpoints this close are one corner
DOOR_GAP_M = 2.0       # m; a gap in one straight wall face up to this wide is a door
CLOSE_GAP_M = 3.0      # m; loose outline ends this close are joined
MIN_OPENING = 0.45     # m; shorter non-solid runs are breaks in the line work
EXTERIOR_THICKNESS = 0.2  # m; assumed for walls with a room on one side only (their centre line is unknown)


def dxf_lines(text: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """LINE entities (x, y pairs) from a DXF's text. Other entities are ignored."""
    tokens = [t.strip() for t in text.replace("\r", "").split("\n")]
    pairs = list(zip(tokens[0::2], tokens[1::2]))
    out, cur = [], None
    for code, value in pairs:
        if code == "0":
            if cur and {"10", "20", "11", "21"} <= cur.keys():
                out.append(((cur["10"], cur["20"]), (cur["11"], cur["21"])))
            cur = {} if value == "LINE" else None
        elif cur is not None and re.fullmatch(r"[12][01]", code):
            cur[code] = float(value)
    return [l for l in out if math.dist(*l) > 1e-6]


def _snap(lines, tol: float = SNAP_M):
    """Move endpoints within tol of an earlier endpoint onto it. Some schematics draw each wall face as its own
    segment and leave corners a few millimetres open."""
    pts: list[tuple[float, float]] = []

    def snap(p):
        for q in pts:
            if abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol:
                return q
        pts.append((p[0], p[1]))
        return pts[-1]

    return [(snap(a), snap(b)) for a, b in lines if math.dist(a, b) > tol]


def _loose(lines) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """(loose end, the segment's other end) for each endpoint used once."""
    n: dict[tuple[float, float], int] = {}
    for a, b in lines:
        n[a] = n.get(a, 0) + 1
        n[b] = n.get(b, 0) + 1
    return [(p, q) for a, b in lines for p, q in ((a, b), (b, a)) if n[p] == 1]


def bridges(lines, max_gap: float = DOOR_GAP_M) -> list:
    """Segments across door gaps: joins two loose ends whose segments lie on one line, facing each other, up to
    max_gap apart. Schematics of the newer style leave a wall face open where a door is."""
    ends = _loose(lines)
    cands = []
    for i, (p, pq) in enumerate(ends):
        u = np.subtract(p, pq) / max(math.dist(p, pq), 1e-9)  # pointing out of the loose end
        for j, (r, rq) in enumerate(ends[i + 1:], i + 1):
            v = np.subtract(r, rq) / max(math.dist(r, rq), 1e-9)
            d = np.subtract(r, p)
            gap = float(np.dot(d, u))
            if 0.05 < gap <= max_gap and float(np.dot(u, v)) < -0.995 and abs(u[0] * d[1] - u[1] * d[0]) < 0.03:
                cands.append((gap, i, j))
    out, used = [], set()
    for gap, i, j in sorted(cands):
        if i not in used and j not in used:
            out.append((ends[i][0], ends[j][0]))
            used |= {i, j}
    return out


def close_gaps(lines, max_gap: float = CLOSE_GAP_M):
    """One segment joining each loose end to the nearest other loose end within max_gap: an outline left open
    where a room meets the outside (a patio, an entry) still closes into a room."""
    loose = list(dict.fromkeys(p for p, _ in _loose(lines)))
    extra, used = [], set()
    pairs = sorted((math.dist(p, q), i, j) for i, p in enumerate(loose) for j, q in enumerate(loose) if i < j)
    for d, i, j in pairs:
        if d <= max_gap and i not in used and j not in used:
            extra.append((loose[i], loose[j]))
            used |= {i, j}
    return extra


def closed(lines):
    """The lines with corners snapped, door gaps bridged and remaining loose ends joined."""
    lines = _snap(lines)
    lines = lines + bridges(lines)
    return lines + close_gaps(lines)


def faces(lines) -> list[Polygon]:
    """Closed outlines formed by the lines, without the slivers inside walls. Endpoints are also snapped to 1 mm
    by shapely: the DXF's outlines miss closing by fractions of a millimetre."""
    shapes = polygonize(shapely.set_precision(unary_union([LineString(l) for l in closed(lines)]), 0.001))
    keep = [orient(p.simplify(0.01), 1.0) for p in shapes
            if p.area >= MIN_ROOM_AREA and 2 * p.area / p.length >= MIN_ROOM_WIDTH]
    return sorted(keep, key=lambda p: -p.area)


def match_rooms(polys: list[Polygon], rooms: list[dict], panos: list[dict]) -> dict[str, int]:
    """room id -> index into polys. A panorama stands inside its room, so its room takes the face it is in;
    rooms without panoramas take a leftover face whose area is within 35% of theirs."""
    votes: dict[str, dict[int, int]] = {}
    for p in panos:
        if not p.get("room"):
            continue
        pt = Point(p["position"][:2])
        for i, f in enumerate(polys):
            if f.contains(pt):
                votes.setdefault(p["room"], {}).setdefault(i, 0)
                votes[p["room"]][i] += 1
    out: dict[str, int] = {}
    for rid, v in sorted(votes.items(), key=lambda kv: -max(kv[1].values())):
        for i in sorted(v, key=lambda k: -v[k]):
            if i not in out.values():
                out[rid] = i
                break
    left = [i for i in range(len(polys)) if i not in out.values()]
    for r in sorted((r for r in rooms if r["id"] not in out and r.get("area")), key=lambda r: -r["area"]):
        best = min(left, key=lambda i: abs(polys[i].area - r["area"]), default=None)
        if best is not None and 0.65 <= polys[best].area / r["area"] <= 1.35:
            out[r["id"]] = best
            left.remove(best)
    return out


def _edges(poly: Polygon):
    c = list(poly.exterior.coords)
    return [(np.array(c[i]), np.array(c[i + 1])) for i in range(len(c) - 1) if math.dist(c[i], c[i + 1]) > 1e-3]


def _overlap(a0, a1, b0, b1):
    """Facing edges: the part of a's span both cover, as (t0, t1) along a, and the gap between them. None when
    the edges do not face each other."""
    da = a1 - a0
    la = float(np.linalg.norm(da))
    u = da / la
    db = b1 - b0
    v = db / np.linalg.norm(db)
    if abs(u[0] * v[1] - u[1] * v[0]) > math.sin(math.radians(PARALLEL_DEG)) or float(np.dot(u, db)) > 0:
        return None  # not parallel, or running the same way (two edges of CCW rooms that share a wall run opposite)
    n = np.array([u[1], -u[0]])  # outward normal of a CCW room's edge
    gap = float(np.dot(b0 - a0, n))
    if not -0.02 <= gap <= MAX_WALL_GAP:
        return None
    t = sorted([float(np.dot(b0 - a0, u)), float(np.dot(b1 - a0, u))])
    t0, t1 = max(0.0, t[0]), min(la, t[1])
    return (t0, t1, max(gap, 0.0)) if t1 - t0 >= MIN_SHARED else None


def build_walls(polys: dict[str, Polygon]) -> list[dict]:
    """Wall centre lines from room outlines (inner faces). Each wall: a, b, thickness, rooms, plus the face
    edges it came from (`faces`: [(room, a, b)]) so openings can be read along them."""
    walls = []
    edges = {rid: _edges(p) for rid, p in polys.items()}
    used: dict[tuple[str, int], list[tuple[float, float]]] = {}
    ids = sorted(polys)
    for ai, ra in enumerate(ids):
        for ia, (a0, a1) in enumerate(edges[ra]):
            la = float(np.linalg.norm(a1 - a0))
            u = (a1 - a0) / la
            n = np.array([u[1], -u[0]])
            for rb in ids[ai + 1:]:
                for ib, (b0, b1) in enumerate(edges[rb]):
                    ov = _overlap(a0, a1, b0, b1)
                    if not ov:
                        continue
                    t0, t1, gap = ov
                    p0, p1 = a0 + u * t0 + n * gap / 2, a0 + u * t1 + n * gap / 2
                    used.setdefault((ra, ia), []).append((t0, t1))
                    lb = float(np.linalg.norm(b1 - b0))
                    ub = (b1 - b0) / lb
                    s = sorted([float(np.dot(a0 + u * t0 + n * gap - b0, ub)), float(np.dot(a0 + u * t1 + n * gap - b0, ub))])
                    used.setdefault((rb, ib), []).append((max(0.0, s[0]), min(lb, s[1])))
                    walls.append({"a": p0.tolist(), "b": p1.tolist(), "thickness": round(gap, 3), "rooms": [ra, rb],
                                  "faces": [(ra, (a0 + u * t0).tolist(), (a0 + u * t1).tolist()),
                                            (rb, (b0 + ub * max(0.0, s[0])).tolist(), (b0 + ub * min(lb, s[1])).tolist())]})
    for rid in ids:  # what is left of each edge faces outside or unscanned space
        for ie, (e0, e1) in enumerate(edges[rid]):
            le = float(np.linalg.norm(e1 - e0))
            u = (e1 - e0) / le
            n = np.array([u[1], -u[0]])
            for t0, t1 in _free(le, used.get((rid, ie), [])):
                f0, f1 = e0 + u * t0, e0 + u * t1
                off = n * EXTERIOR_THICKNESS / 2
                walls.append({"a": (f0 + off).tolist(), "b": (f1 + off).tolist(), "thickness": None, "rooms": [rid],
                              "faces": [(rid, f0.tolist(), f1.tolist())]})
    return walls


def _free(length: float, taken: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out, cur = [], 0.0
    for t0, t1 in sorted(taken):
        if t0 - cur >= MIN_SHARED:
            out.append((cur, t0))
        cur = max(cur, t1)
    if length - cur >= MIN_SHARED:
        out.append((cur, length))
    return out


# ---- the schematic PNG ----

def _samples(lines, step_px: float = 3.0) -> np.ndarray:
    out = []
    for a, b in lines:
        n = max(2, int(math.dist(a, b) * PX_PER_M / step_px))
        t = np.linspace(0, 1, n)[:, None]
        out.append(np.array(a) + (np.array(b) - np.array(a)) * t)
    return np.concatenate(out)


def _score(dark: np.ndarray, s: np.ndarray, ox: float, oy: float) -> float:
    h, w = dark.shape
    px = np.round(ox + s[:, 0] * PX_PER_M).astype(int)
    py = np.round(oy - s[:, 1] * PX_PER_M).astype(int)
    ok = (px >= 0) & (px < w) & (py >= 0) & (py < h)
    return float(dark[py[ok], px[ok]].sum()) / len(s)


def register(dark: np.ndarray, lines, coarse: int = 4, search: int = 6) -> tuple[float, float, float]:
    """Pixel offset (ox, oy) so that x_px = ox + x * 100 and y_px = oy - y * 100, and the share of the DXF line
    samples that then land on ink. A cross-correlation of the drawn lines with the ink at 1/`coarse` scale finds
    the offset (the PNG can carry dotted lines outside the outlines, so its ink extent is not the DXF's), then
    every shift within `search` px refines it."""
    s = _samples(lines)
    h, w = dark.shape
    hc, wc = -(-h // coarse), -(-w // coarse)
    ink = np.zeros((hc * coarse, wc * coarse), bool)
    ink[:h, :w] = dark
    ink = ink.reshape(hc, coarse, wc, coarse).any(axis=(1, 3)).astype(np.float32)
    xmin, ymax = s[:, 0].min(), s[:, 1].max()
    tx = ((s[:, 0] - xmin) * PX_PER_M / coarse).astype(int)
    ty = ((ymax - s[:, 1]) * PX_PER_M / coarse).astype(int)
    tmpl = np.zeros((ty.max() + 1, tx.max() + 1), np.float32)
    tmpl[ty, tx] = 1.0
    shape = (hc + tmpl.shape[0], wc + tmpl.shape[1])
    corr = np.fft.irfft2(np.fft.rfft2(ink, shape) * np.conj(np.fft.rfft2(tmpl, shape)), shape)
    dy, dx = np.unravel_index(int(np.argmax(corr)), corr.shape)
    dy, dx = (dy - shape[0] if dy > hc else dy), (dx - shape[1] if dx > wc else dx)
    ox0, oy0 = dx * coarse - xmin * PX_PER_M, dy * coarse + ymax * PX_PER_M
    grid = [(_score(dark, s, ox0 + ddx, oy0 + ddy), ddx, ddy)
            for ddx in range(-search, search + 1) for ddy in range(-search, search + 1)]
    top = max(g[0] for g in grid)
    near = [g for g in grid if g[0] >= top - 0.005]  # lines are ~6 px wide: centre the shifts that tie
    return ox0 + float(np.mean([g[1] for g in near])), oy0 + float(np.mean([g[2] for g in near])), top


def solid_profile(dark: np.ndarray, a, b, ox: float, oy: float, band: int = 1, window: int = 9) -> np.ndarray:
    """For each centimetre along the face edge a->b: True where the PNG line is solid ink. A dotted line or a gap
    reads as not solid: its dots are 3 to 5 px long every 8 px, so `window` (px along the line that must all be
    ink) is longer than that. `band`: px either side of the line centre that count."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    length = float(np.linalg.norm(b - a))
    n = max(1, int(length * PX_PER_M))
    u = (b - a) / length
    nrm = np.array([-u[1], u[0]])
    t = (np.arange(n) + 0.5) / PX_PER_M
    h, w = dark.shape
    ink = np.zeros(n, bool)
    for k in range(-band, band + 1):  # the line is ~6 px wide: any offset in the band that is ink counts
        p = a + np.outer(t, u) + np.outer(np.full(n, k / PX_PER_M), nrm)
        px = np.clip(np.round(ox + p[:, 0] * PX_PER_M).astype(int), 0, w - 1)
        py = np.clip(np.round(oy - p[:, 1] * PX_PER_M).astype(int), 0, h - 1)
        ink |= dark[py, px]
    if window > 1:  # solid = every pixel in a small run along the line is ink; dots have gaps
        c = np.convolve(ink.astype(int), np.ones(window, int), "same")
        ink = c >= window
    return ink


def runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """[start, end) of each run of True at least min_len long."""
    out, start = [], None
    for i, v in enumerate(np.append(mask, False)):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    return out


def find_openings(walls: list[dict], dark: np.ndarray, ox: float, oy: float) -> list[dict]:
    """Openings along each wall: where every face edge of the wall is not solid for at least MIN_OPENING."""
    out = []
    for wi, w in enumerate(walls):
        a, b = np.array(w["a"]), np.array(w["b"])
        length = float(np.linalg.norm(b - a))
        if length < MIN_OPENING or w.get("type") == "invisible":
            continue
        u = (b - a) / length
        n = int(length * PX_PER_M)
        open_all = np.ones(n, bool)
        for _, f0, f1 in w["faces"]:
            prof = ~solid_profile(dark, f0, f1, ox, oy)
            # map the face's profile onto the wall's centimetres (faces run the wall's way or the opposite way)
            f0, f1 = np.array(f0), np.array(f1)
            t = np.clip(np.round((np.dot(np.linspace(0, 1, n)[:, None] * (b - a) + a - f0, (f1 - f0) / max(np.linalg.norm(f1 - f0), 1e-9))) * PX_PER_M).astype(int), 0, len(prof) - 1)
            open_all &= prof[t]
        edge = 3  # a corner where two outlines meet is never an opening
        open_all[:edge] = open_all[-edge:] = False
        for s, e in runs(open_all, int(MIN_OPENING * PX_PER_M)):
            c = a + u * ((s + e) / 2 / PX_PER_M)
            out.append({"wall": wi, "width": round((e - s) / PX_PER_M, 2), "center": c.tolist(),
                        "rooms": list(w["rooms"]),
                        "type": "doorway" if len(w["rooms"]) == 2 else "opening"})
    return out


def recover_floor(dxf_text: str, png_gray: np.ndarray | None, rooms: list[dict], panos: list[dict]) -> dict:
    """Everything recoverable for one floor. `rooms` and `panos` are that floor's ScanPlan rooms and panos.
    Returns polygons {room id: Polygon}, walls, openings, registration score, and unmatched face count."""
    lines = dxf_lines(dxf_text)
    polys = faces(lines)
    match = match_rooms(polys, rooms, panos)
    by_room = {rid: polys[i] for rid, i in match.items()}
    walls = build_walls(by_room)
    snapped = _snap(lines)
    drawn = unary_union([LineString(l) for l in snapped + bridges(snapped)]).buffer(0.03) if lines else None
    for w in walls:  # a face edge that only exists because two loose ends were joined is an open boundary
        segs = [LineString([f0, f1]) for _, f0, f1 in w["faces"]]
        cover = max(sg.intersection(drawn).length / sg.length for sg in segs) if drawn is not None else 0.0
        w["type"] = "wall" if cover >= 0.5 else "invisible"
    openings, score = [], None
    if png_gray is not None and lines:
        dark = png_gray < 128
        ox, oy, score = register(dark, lines)
        openings = find_openings(walls, dark, ox, oy)
    return {"polygons": by_room, "walls": walls, "openings": openings, "registration": score,
            "faces": len(polys), "faces_unmatched": len(polys) - len(match), "lines": len(lines)}


def plan_parts(floor: str, tag: str, rec: dict) -> dict:
    """recover_floor's result as ScanPlan pieces (plain lists, ids prefixed with `tag`), every one marked
    source "dxf"."""
    walls, openings = [], []
    for i, w in enumerate(rec["walls"]):
        walls.append({"id": f"{tag}w{i}", "floor": floor, "a": [round(v, 4) for v in w["a"]],
                      "b": [round(v, 4) for v in w["b"]], "type": w.get("type", "wall"), "thickness": w["thickness"],
                      "length": round(math.dist(w["a"], w["b"]), 4), "rooms": list(w["rooms"]), "openings": [],
                      "source": "dxf"})
    for i, o in enumerate(rec["openings"]):
        wid = walls[o["wall"]]["id"]
        walls[o["wall"]]["openings"].append(f"{tag}o{i}")
        openings.append({"id": f"{tag}o{i}", "wall": wid, "floor": floor, "type": o["type"], "width": o["width"],
                         "height": None, "sill": None, "center": [round(v, 4) for v in o["center"]],
                         "rooms": list(o["rooms"]), "source": "schematic_png"})
    rooms = {rid: {"polygon": [[round(x, 4), round(y, 4)] for x, y in p.exterior.coords[:-1]],
                   "hole_polygons": [[[round(x, 4), round(y, 4)] for x, y in h.coords[:-1]] for h in p.interiors],
                   "center": list(p.representative_point().coords[0]), "outline_area": p.area,
                   "walls": [w["id"] for w in walls if rid in w["rooms"]]}
             for rid, p in rec["polygons"].items()}
    return {"floor": floor, "walls": walls, "openings": openings, "rooms": rooms,
            "registration": rec["registration"], "faces_unmatched": rec["faces_unmatched"]}
