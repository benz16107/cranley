"""Starting points for training: surface samples, each coloured by the sweep that sees it best.

Geometry comes from Matterport's 50,000 triangle mesh (`assets.meshes`, the same OBJ and cache file the world
engine uses), trimmed to the plan. A scan without that mesh falls back to its walls, floors and ceilings.
A point takes its colour from the closest sweep that sees it (a depth test against the other samples) and is not
straight below the tripod; a point no sweep sees is dropped, since no training view can correct it.
"""
from __future__ import annotations

import numpy as np

from ..sources import matterport as mp
from ..sources.upstream import cache_path, cached, send
from ..vision.locate import floor_z
from ..vision.projection import face_basis, quat_matrix

FACE_PX = 256          # faces are read at this size for colour (a box filter averages the 2k face)
PER_M2 = 250           # samples per square metre of surface
MAX_POINTS = 400_000
MARGIN = 1.0           # metres of mesh kept outside the plan (beyond is the garden seen through windows)
MAX_RANGE = 8.0        # a sweep further than this does not colour a point
NADIR_COS = 0.9        # nor one standing right over it (Matterport blurs the tripod out)
DEPTH_W = 512          # equirectangular depth map per sweep for the visibility test
SLACK = 0.04           # a point this far (metres, plus 3%) behind the nearest sample in its direction still counts as seen
DEFAULT_HEIGHT = 2.6


def obj_bytes(sid: str) -> bytes:
    def load() -> bytes:
        q = 'query($id: ID!) { model(id: $id) { assets { meshes(resolutions: ["50k"]) { format status url } } } }'
        for m in mp.graph(q, id=sid)["model"]["assets"]["meshes"]:
            if m["format"] == "obj" and m.get("url"):
                return send("GET", m["url"]).content
        raise LookupError("this scan has no mesh")
    return cached(cache_path("mesh", sid, "out_res_50k.obj"), load)


def parse_obj(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    v, f = [], []
    for line in data.split(b"\n"):
        if line[:2] == b"v ":
            v.append(line[2:].split()[:3])
        elif line[:2] == b"f ":
            f.append([c.split(b"/")[0] for c in line[2:].split()[:3]])
    return np.array(v, np.float64).reshape(-1, 3), np.array(f, np.int64).reshape(-1, 3) - 1


def sample_triangles(T: np.ndarray, n: int, rng) -> np.ndarray:
    """n points spread over triangles T (m, 3, 3) in proportion to area."""
    area = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) / 2
    k = rng.choice(len(T), n, p=area / area.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    return T[k, 0] * (1 - s)[:, None] + T[k, 1] * (s * (1 - r2))[:, None] + T[k, 2] * (s * r2)[:, None]


def _bounds(plan: dict, panos: dict) -> tuple[np.ndarray, np.ndarray]:
    xy = [p for w in plan["walls"] for p in (w["a"], w["b"])] + [p for r in plan["rooms"] for p in r["polygon"]]
    pos = np.array([p["position"] for p in panos.values()])
    lo = np.min([*xy, *pos[:, :2]], 0) - MARGIN
    hi = np.max([*xy, *pos[:, :2]], 0) + MARGIN
    return np.r_[lo, pos[:, 2].min() - 2.5], np.r_[hi, pos[:, 2].max() + 2.0]


def mesh_triangles(sid: str, plan: dict, panos: dict) -> np.ndarray:
    V, F = parse_obj(obj_bytes(sid))
    T = V[F]
    lo, hi = _bounds(plan, panos)
    c = T.mean(1)
    return T[np.all((c > lo) & (c < hi), axis=1)]


def plan_triangles(plan: dict) -> np.ndarray:
    """Walls as upright rectangles, room outlines as floor and ceiling fans. For scans with no mesh."""
    hs = [r["height"] for r in plan["rooms"] if r.get("height")]
    h = float(np.median(hs)) if hs else DEFAULT_HEIGHT
    z = {f["id"]: floor_z(plan, f["id"]) for f in plan["floors"]}
    tris = []
    for w in plan["walls"]:
        if w["type"] != "wall":
            continue
        z0 = z.get(w["floor"], 0.0)
        a0, b0 = [*w["a"], z0], [*w["b"], z0]
        a1, b1 = [*w["a"], z0 + h], [*w["b"], z0 + h]
        tris += [[a0, b0, b1], [a0, b1, a1]]
    for r in plan["rooms"]:
        ring = r["polygon"]
        if len(ring) < 3:
            continue
        z0 = z.get(r["floor"], 0.0)
        top = z0 + (r.get("height") or h)
        for zz in (z0, top):
            tris += [[[*ring[0], zz], [*ring[i], zz], [*ring[i + 1], zz]] for i in range(1, len(ring) - 1)]
    return np.array(tris, float).reshape(-1, 3, 3)


def _lonlat_index(v: np.ndarray, d: np.ndarray, w: int) -> np.ndarray:
    h = w // 2
    lon = np.arctan2(v[:, 1], v[:, 0])
    lat = np.arcsin(np.clip(v[:, 2] / np.maximum(d, 1e-9), -1, 1))
    col = np.clip(((lon + np.pi) / (2 * np.pi) * w).astype(np.int64), 0, w - 1)
    row = np.clip(((np.pi / 2 - lat) / np.pi * h).astype(np.int64), 0, h - 1)
    return row * w + col


def visible(pts: np.ndarray, centre: np.ndarray, w: int = DEPTH_W) -> np.ndarray:
    """Which of the points a camera at `centre` sees, judged against the points themselves as the occluders."""
    v = pts - centre
    d = np.linalg.norm(v, axis=1)
    idx = _lonlat_index(v, d, w)
    depth = np.full(w * (w // 2), np.inf)
    np.minimum.at(depth, idx, d)
    g = depth.reshape(w // 2, w)
    m = g.copy()  # 3x3 minimum, to close the gaps between samples close to the camera
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            m = np.minimum(m, np.roll(np.roll(g, dr, 0), dc, 1))
    return d <= m.reshape(-1)[idx] * 1.03 + SLACK


def colour(d_cam: np.ndarray, faces: list[np.ndarray]) -> np.ndarray:
    """RGB where camera-frame directions hit the six faces (each FACE_PX square)."""
    n = faces[0].shape[0]
    bases = [face_basis(k) for k in range(6)]
    k = np.argmax(np.stack([d_cam @ b[0] for b in bases], 1), 1)
    out = np.zeros((len(d_cam), 3), np.uint8)
    for f, (fwd, right, down) in enumerate(bases):
        m = k == f
        if not m.any():
            continue
        dz = d_cam[m] @ fwd
        u = np.clip(((d_cam[m] @ right / dz + 1) / 2 * n).astype(int), 0, n - 1)
        v = np.clip(((d_cam[m] @ down / dz + 1) / 2 * n).astype(int), 0, n - 1)
        out[m] = faces[f][v, u]
    return out


def points(sid: str, plan: dict, panos: dict, faces: dict, seed: int = 0) -> tuple[np.ndarray, np.ndarray, str]:
    """(xyz, rgb, source) where source is "mesh" or "plan". `faces[(pano, k)]` is a FACE_PX RGB array."""
    rng = np.random.default_rng(seed)
    try:
        T, source = mesh_triangles(sid, plan, panos), "mesh"
    except LookupError:
        T, source = plan_triangles(plan), "plan"
    area = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1).sum() / 2
    pts = sample_triangles(T, int(min(MAX_POINTS, area * PER_M2)), rng)
    best = np.full(len(pts), np.inf)
    rgb = np.zeros((len(pts), 3), np.uint8)
    for pid, p in panos.items():
        if not all((pid, k) in faces for k in range(6)):
            continue
        c = np.asarray(p["position"], float)
        v = pts - c
        d = np.linalg.norm(v, axis=1)
        ok = (d < MAX_RANGE) & (d < best) & (v[:, 2] / np.maximum(d, 1e-9) > -NADIR_COS)
        ok[ok] &= visible(pts, c)[ok]
        if not ok.any():
            continue
        R = quat_matrix(p["rotation"])
        rgb[ok] = colour((v[ok] / d[ok, None]) @ R, [faces[(pid, k)] for k in range(6)])  # R.T @ v, row-wise
        best[ok] = d[ok]
    seen = np.isfinite(best)
    return pts[seen], rgb[seen], source
