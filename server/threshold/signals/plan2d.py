"""Walls as 2D segments with their openings cut out, crossing counts for many rays at once, and room grids."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import Polygon

from ..geometry._plan import floor_z, indoor_rooms, polygons, walls_by_id

GAP = ("doorway", "opening", "divider")  # an open doorway or wall-less opening blocks nothing


@dataclass
class Segs:
    """Solid pieces of the walls on one floor: a[i] to b[i], `kind` "wall" or "window", wall thickness."""
    a: np.ndarray
    b: np.ndarray
    kind: np.ndarray
    thickness: np.ndarray
    wall: list[str]

    def __len__(self) -> int:
        return len(self.wall)


def segments(plan: dict, floor: str) -> Segs:
    """Every wall on `floor` (not invisible walls) split at its openings: doorway spans removed, window spans kept
    as "window" pieces. An opening's span is its width centred on its centre projected onto the wall."""
    by_wall: dict[str, list[dict]] = {}
    for o in plan.get("openings") or []:
        by_wall.setdefault(o["wall"], []).append(o)
    a, b, kind, th, wid = [], [], [], [], []
    for w in walls_by_id(plan).values():
        if w["floor"] != floor or w.get("type") == "invisible":
            continue
        (ax, ay), (bx, by) = w["a"], w["b"]
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-6:
            continue
        ux, uy = (bx - ax) / L, (by - ay) / L
        cuts = []  # (t0, t1, kind) along the wall in metres
        for o in by_wall.get(w["id"], []):
            t = (o["center"][0] - ax) * ux + (o["center"][1] - ay) * uy
            h = (o.get("width") or 0) / 2
            cuts.append((max(0.0, t - h), min(L, t + h), "gap" if o["type"] in GAP else "window"))
        cuts.sort()
        pieces, t = [], 0.0
        for t0, t1, k in cuts:
            if t0 > t:
                pieces.append((t, t0, "wall"))
            if k == "window" and t1 > max(t, t0):
                pieces.append((max(t, t0), t1, "window"))
            t = max(t, t1)
        if t < L:
            pieces.append((t, L, "wall"))
        for t0, t1, k in pieces:
            if t1 - t0 < 0.02:
                continue
            a.append((ax + ux * t0, ay + uy * t0))
            b.append((ax + ux * t1, ay + uy * t1))
            kind.append(k)
            th.append(w.get("thickness") or 0.12)
            wid.append(w["id"])
    return Segs(np.array(a, float).reshape(-1, 2), np.array(b, float).reshape(-1, 2), np.array(kind, object),
                np.array(th, float), wid)


def cross_t(p, q: np.ndarray, segs: Segs) -> np.ndarray:
    """(M, N) position along the ray p -> q[m] (0 to 1) where it properly crosses wall piece n, NaN where it does
    not. Touching an end point counts as no crossing, so a ray that ends on a wall (a door centre) is not blocked."""
    q = np.asarray(q, float).reshape(-1, 2)
    if len(segs) == 0:
        return np.full((len(q), 0), np.nan)
    p = np.asarray(p, float)
    d = q - p                                   # (M,2)
    e = segs.b - segs.a                         # (N,2)
    f = segs.a - p                              # (N,2)
    den = d[:, None, 0] * e[None, :, 1] - d[:, None, 1] * e[None, :, 0]   # (M,N)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (f[None, :, 0] * e[None, :, 1] - f[None, :, 1] * e[None, :, 0]) / den   # along the ray
        u = (f[None, :, 0] * d[:, None, 1] - f[None, :, 1] * d[:, None, 0]) / den   # along the wall
    eps = 1e-6
    ok = (np.abs(den) > 1e-12) & (t > eps) & (t < 1 - eps) & (u >= 0) & (u <= 1)
    return np.where(ok, t, np.nan)


def crossings(p, q: np.ndarray, segs: Segs) -> np.ndarray:
    """(M, N) booleans: does the segment from p to q[m] cross wall piece n."""
    return ~np.isnan(cross_t(p, q, segs))


def ray_hits(p, dirs: np.ndarray, segs: Segs, max_range: float, solid: np.ndarray | None = None) -> np.ndarray:
    """Distance along each unit direction to the first solid piece, capped at max_range."""
    dirs = np.asarray(dirs, float).reshape(-1, 2)
    if len(segs) == 0:
        return np.full(len(dirs), max_range)
    sel = np.ones(len(segs), bool) if solid is None else solid
    a, e = segs.a[sel], segs.b[sel] - segs.a[sel]
    f = a - np.asarray(p, float)
    den = dirs[:, None, 0] * e[None, :, 1] - dirs[:, None, 1] * e[None, :, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (f[None, :, 0] * e[None, :, 1] - f[None, :, 1] * e[None, :, 0]) / den
        u = (f[None, :, 0] * dirs[:, None, 1] - f[None, :, 1] * dirs[:, None, 0]) / den
    ok = (np.abs(den) > 1e-12) & (t > 1e-6) & (u >= 0) & (u <= 1)
    t = np.where(ok, t, np.inf)
    return np.minimum(t.min(axis=1) if t.shape[1] else np.full(len(dirs), np.inf), max_range)


def floor_order(plan: dict) -> dict[str, int]:
    """Floor id -> storey index by scan z, lowest floor 0."""
    fz = floor_z(plan)
    return {f: i for i, f in enumerate(sorted(fz, key=fz.get))}


def room_polys(plan: dict) -> dict[str, Polygon]:
    """Indoor rooms (not Void, walled) that have an outline."""
    polys = polygons(plan)
    return {r["id"]: polys[r["id"]] for r in indoor_rooms(plan) if polys.get(r["id"]) is not None}


def grid(poly: Polygon, step: float) -> np.ndarray:
    """Points on a square grid inside the polygon, inset from its walls; at least its representative point."""
    inner = poly.buffer(-min(0.25, step / 3)) if poly.area > 1 else poly
    if inner.is_empty:
        inner = poly
    x0, y0, x1, y1 = inner.bounds
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    if len(xs) and len(ys):
        X, Y = np.meshgrid(xs, ys)
        pts = np.column_stack([X.ravel(), Y.ravel()])
        pts = pts[shapely.contains_xy(inner, pts[:, 0], pts[:, 1])]
        if len(pts):
            return pts
    rp = poly.representative_point()
    return np.array([[rp.x, rp.y]])


def room_names(plan: dict, ids) -> dict[str, str]:
    """Room id -> a name unique in the plan: "Bedroom", "Bedroom 2", ... in plan order."""
    seen: dict[str, int] = {}
    out = {}
    want = set(ids)
    for r in plan.get("rooms") or []:
        base = r.get("label") or "Unlabelled room"
        seen[base] = seen.get(base, 0) + 1
        if r["id"] in want:
            out[r["id"]] = base if seen[base] == 1 else f"{base} {seen[base]}"
    return out
