"""Matterport's own scanned mesh (the 50,000 triangle one behind its dollhouse view), coloured from the panoramas.

The Model API lists that mesh as an OBJ with no texture coordinates (MatterPak, which has a textured one, is
unavailable on these scans). So the colour is baked here from data the API does give: every triangle gets its own
cell in one atlas, and each texel takes the pixel of the panorama that sees that spot best: in front of the
surface, close, and with nothing of the mesh in between. Where two panoramas meet along an edge both are sampled
and feathered across it, and every panorama is first given a gain per colour channel so that neighbours agree on
the brightness of what they both see (their exposures differ room to room).

Outputs, in `$THRESHOLD_DATA_DIR/cache/mesh/<sid>/`, each named with BAKE_VERSION so servers on different code can
share the folder: `mesh<v>.bin` (positions, normals, texture coordinates; written in a second or two) and
`atlas<v>.jpg` with `meta<v>.json` (minutes the first time: up to six requests per panorama).
"""
from __future__ import annotations

import io
import json
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import shapely
from PIL import Image
from shapely.geometry import Polygon
from shapely.ops import unary_union

from ..geometry._plan import floor_z
from ..sources import matterport as mp
from ..sources.upstream import cache_path, cached, check, one_flight, send, write_atomic
from ..vision.projection import face_basis, quat_matrix

ATLASES = (4096, 6144, 8192)  # the smallest atlas that gives the building WANT_DENSITY, else the largest
WANT_DENSITY = 75.0      # texels per metre
FEATHER = 0.35           # metres over which two panoramas are blended either side of the edge where they meet
ONE = 64                 # a weight of 1 in the fixed-point sums the atlas is accumulated in
CLASSES = (4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024)  # a cell side, in texels
PAD = 3                 # a cell is its triangle's legs plus this: half a texel at each end and a gap between its two triangles
MAX_DENSITY = 140.0     # texels per metre when the atlas has room
BIG = 512               # no cell side is longer than this: a few wall-sized triangles would otherwise take the whole
                        # atlas and drag every small one (the furniture, the fittings) down to their density
VOXEL = 0.08            # metres; the occupancy grid that decides whether a panorama sees a triangle
MAX_RANGE = 10.0        # a panorama further than this does not colour a triangle
MIN_COS = 0.2           # nor one that sees it at a flatter angle than this
NADIR_COS = 0.9         # nor, by choice, one standing right over it: Matterport blurs the tripod out of each panorama
BAKE_VERSION = 7        # 7: the mesh is trimmed and split into floors by each floor's own scan z (6 lost a ground floor under the origin)
RETRY_S = 600
CANDIDATES = 6
MARGIN = 1.0            # metres of mesh kept outside the plan's walls (the rest is the garden seen through windows)
NEUTRAL = (204, 200, 192)
MAGIC = b"THM2"

_state: dict[str, dict] = {}
_one_bake = threading.Semaphore(1)  # a bake holds up to a gigabyte; a second one waits its turn


def path(sid: str, name: str):
    """A versioned file of this scan's bake: path(sid, "atlas.jpg") is .../atlas7.jpg."""
    stem, _, ext = name.partition(".")
    return cache_path("mesh", sid, f"{stem}{BAKE_VERSION}.{ext}")


# ---- geometry ----------------------------------------------------------------------------------------------------

def obj_bytes(sid: str) -> bytes:
    def load() -> bytes:
        q = 'query($id: ID!) { model(id: $id) { assets { meshes(resolutions: ["50k"]) { format status url } } } }'
        for m in mp.graph(q, id=sid)["model"]["assets"]["meshes"]:
            if m["format"] == "obj" and m.get("url"):
                return send("GET", m["url"]).content
        raise LookupError("this scan has no mesh")
    return cached(cache_path("mesh", sid, "out_res_50k.obj"), load)


def parse_obj(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Vertices (n, 3) and triangles (m, 3, zero-based). Only `v` and three-cornered `f` lines are read."""
    v, f = [], []
    for line in data.split(b"\n"):
        if line[:2] == b"v ":
            v.append(line[2:].split()[:3])
        elif line[:2] == b"f ":
            f.append([c.split(b"/")[0] for c in line[2:].split()[:3]])
    return np.array(v, np.float32).reshape(-1, 3), np.array(f, np.int64).reshape(-1, 3).astype(np.int32) - 1


def weld(V: np.ndarray, F: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """One vertex per position (to the millimetre). Some scans' meshes come as loose triangles, each with its own
    three vertices; without this no triangle has a neighbour, so nothing is blended across an edge."""
    uniq, inverse = np.unique(np.round(V, 3), axis=0, return_inverse=True)
    return uniq.astype(np.float32), inverse.reshape(-1)[F].astype(np.int32)


def trim(V: np.ndarray, F: np.ndarray, plan: dict) -> np.ndarray:
    """Triangles within MARGIN of the plan's rooms, and no higher than its tallest ceiling. The garden a scan picks
    up from its outdoor positions goes: it is scraps, and the surroundings are drawn from better data. Rooms are
    taken by their outlines, so the yard inside an L-shaped house's corner goes too. A scan with no room outlines
    is boxed by its walls, and with no walls by its panorama positions."""
    c = V[F].mean(1)
    # each floor's own level in scan z: Matterport's origin can be on any floor (a ground floor 3 m under it was cut off)
    levels = list(floor_z(plan).values()) or [0.0]
    top = max(levels) + max([r.get("height") or 0 for r in plan["rooms"]] + [2.7]) + 0.6
    keep = (c[:, 2] < top) & (c[:, 2] > min(levels) - 1.0)
    rooms = [Polygon(r["polygon"]).buffer(0) for r in plan["rooms"] if len(r.get("polygon") or []) > 2]
    if rooms:
        return F[keep & shapely.contains_xy(unary_union(rooms).buffer(MARGIN), c[:, 0], c[:, 1])]
    pts = [p for w in plan["walls"] for p in (w["a"], w["b"])] or [p["position"][:2] for p in plan["panos"]]
    if not pts:
        return F
    lo, hi = np.min(pts, 0) - MARGIN, np.max(pts, 0) + MARGIN
    return F[keep & (c[:, 0] > lo[0]) & (c[:, 0] < hi[0]) & (c[:, 1] > lo[1]) & (c[:, 1] < hi[1])]


def without_specks(F: np.ndarray, share: float = 0.01, least: int = 150) -> np.ndarray:
    """The triangles of every connected piece that is not a speck. A scan leaves scraps of tree and roof floating
    beside the building; a piece with under 1% of the triangles (and under 150) is one of those. That only holds
    for a mesh that is mostly one piece: some scans' meshes are hundreds of separate flat patches, and those are
    left whole."""
    parent = np.arange(int(F.max()) + 1) if len(F) else np.arange(0)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, c in F.tolist():
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[rc] = ra
    root = np.array([find(i) for i in F[:, 0].tolist()])
    _, piece, count = np.unique(root, return_inverse=True, return_counts=True)
    if not len(F) or count.max() < 0.6 * len(F):
        return F
    return F[count[piece] >= min(least, share * len(F))]


def face_frames(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    """Each triangle turned so its first corner faces its longest edge (the corner that sits in the cell's corner)."""
    T = V[F]
    edge = np.linalg.norm(T - np.roll(T, -1, 1), axis=2)  # edge i runs from corner i to corner i + 1
    first = (np.argmax(edge, 1) + 2) % 3                  # the corner not on the longest edge
    idx = (first[:, None] + np.arange(3)) % 3
    return np.take_along_axis(F, idx, 1)


def vertex_normals(V: np.ndarray, F: np.ndarray) -> np.ndarray:
    T = V[F]
    fn = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])  # length is twice the area, which is the weight we want
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, F[:, k], fn)
    return vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-9)


# ---- atlas layout --------------------------------------------------------------------------------------------------

def layout_for(V: np.ndarray, F: np.ndarray) -> dict:
    """The layout in the smallest atlas that gives the building enough texels."""
    for size in ATLASES:
        lay = layout(V, F, size)
        if lay["density"] >= WANT_DENSITY:
            break
    return lay


def layout(V: np.ndarray, F: np.ndarray, atlas: int = ATLASES[0]) -> dict:
    """A cell for every triangle: a rectangle as wide and as tall as the two edges at its first corner, shared with
    one other triangle of the same size. Returns kw, kh (indexes into CLASSES), x, y (the cell's corner in texels),
    slot (0 the lower-left half of the cell, 1 the upper-right), uv (m, 3, 2) in 0..1 with v up, and the density
    reached (texels per metre; lowered until everything fits)."""
    T = V[F]
    la, lb = np.linalg.norm(T[:, 1] - T[:, 0], axis=1), np.linalg.norm(T[:, 2] - T[:, 0], axis=1)
    sizes = np.array(CLASSES)
    density = MAX_DENSITY
    while True:
        kw = np.minimum(np.searchsorted(sizes, la * density), CLASSES.index(BIG))
        kh = np.minimum(np.searchsorted(sizes, lb * density), CLASSES.index(BIG))
        x = np.zeros(len(F), np.int32); y = np.zeros(len(F), np.int32); slot = np.zeros(len(F), np.int8)
        cx = cy = row_h = 0
        for h in np.unique(kh)[::-1]:          # tallest cells first; cells of one height share rows
            for w in np.unique(kw[kh == h])[::-1]:
                ids = np.nonzero((kh == h) & (kw == w))[0]
                cw, ch = int(sizes[w]) + PAD, int(sizes[h]) + PAD
                if ch != row_h and cx:
                    cx, cy = 0, cy + row_h
                row_h = ch
                cell = np.arange(len(ids)) // 2
                n, first, per_row = int(cell[-1]) + 1, (atlas - cx) // cw, atlas // cw
                later = cell - first
                x[ids] = np.where(cell < first, cx + cell * cw, (later % per_row) * cw)
                y[ids] = np.where(cell < first, cy, cy + (1 + later // per_row) * ch)
                slot[ids] = np.arange(len(ids)) % 2
                if n <= first:
                    cx += n * cw
                else:
                    cy += -(-(n - first) // per_row) * ch
                    cx = ((n - first - 1) % per_row + 1) * cw
        if cy + row_h <= atlas:
            break
        density *= 0.9
    W, H = sizes[kw].astype(np.float32), sizes[kh].astype(np.float32)
    half, zero = np.full_like(W, 0.5), np.zeros_like(W)
    lower = np.stack([np.stack([half, half], 1), np.stack([half + W, half], 1), np.stack([half, half + H], 1)], 1)
    far = np.stack([W + PAD - 0.5, H + PAD - 0.5], 1)[:, None, :]
    upper = far - np.stack([np.stack([zero, zero], 1), np.stack([W, zero], 1), np.stack([zero, H], 1)], 1)
    px = np.where(slot[:, None, None] == 0, lower, upper) + np.stack([x, y], 1)[:, None, :]
    uv = px / atlas
    uv[..., 1] = 1 - uv[..., 1]  # texel rows count down, texture v counts up
    each = np.minimum(W / np.maximum(la, 1e-6), H / np.maximum(lb, 1e-6))  # what each triangle got, texels per metre
    return {"kw": kw, "kh": kh, "x": x, "y": y, "slot": slot, "uv": uv.astype(np.float32), "density": density, "each": each, "atlas": atlas}


def cell_texels(kw: int, kh: int) -> tuple[tuple, tuple]:
    """For a cell of this size: texel offsets (px, py) and the weights of corners 1 and 2, for each of its two halves.
    A texel belongs to the half whose triangle it is nearer to, so the gap between the two is shared."""
    W, H = CLASSES[kw], CLASSES[kh]
    py, px = np.mgrid[0:H + PAD, 0:W + PAD]
    u1, u2 = (px + 0.5 - 0.5) / W, (py + 0.5 - 0.5) / H
    v1, v2 = (W + PAD - 1 - px) / W, (H + PAD - 1 - py) / H
    lower = (u1 + u2) <= (v1 + v2)
    return ((px[lower], py[lower], u1[lower].astype(np.float32), u2[lower].astype(np.float32)),
            (px[~lower], py[~lower], v1[~lower].astype(np.float32), v2[~lower].astype(np.float32)))


# ---- which panorama sees which triangle ----------------------------------------------------------------------------

def surface_points(V: np.ndarray, F: np.ndarray, step: float) -> np.ndarray:
    """Points over every triangle no further apart than `step`."""
    T = V[F]
    longest = np.max(np.linalg.norm(T - np.roll(T, -1, 1), axis=2), 1)
    n = np.clip(np.ceil(longest / step).astype(int), 1, 96)
    out = []
    for k in np.unique(n):
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1))
        ok = i + j <= k
        w1, w2 = (i[ok] / k).astype(np.float32), (j[ok] / k).astype(np.float32)
        t = T[n == k]
        out.append((t[:, None, 0] + w1[None, :, None] * (t[:, None, 1] - t[:, None, 0])
                    + w2[None, :, None] * (t[:, None, 2] - t[:, None, 0])).reshape(-1, 3))
    return np.concatenate(out)


def occupancy(points: np.ndarray, voxel: float = VOXEL) -> tuple[np.ndarray, np.ndarray]:
    lo = points.min(0) - voxel
    shape = np.ceil((points.max(0) + voxel - lo) / voxel).astype(int) + 1
    grid = np.zeros(shape, bool)
    i = ((points - lo) / voxel).astype(int)
    grid[i[:, 0], i[:, 1], i[:, 2]] = True
    return grid, lo


def clear(grid: np.ndarray, lo: np.ndarray, a: np.ndarray, b: np.ndarray, voxel: float = VOXEL, skip: float = 0.12) -> np.ndarray:
    """True where nothing occupied lies on the segment a to b, ignoring `skip` metres at each end."""
    out = np.ones(len(a), bool)
    for s in range(0, len(a), 6000):
        p, d = a[s:s + 6000], b[s:s + 6000] - a[s:s + 6000]
        length = np.linalg.norm(d, axis=1)
        n = max(2, int(np.ceil(length.max() / (voxel * 0.5))))
        t = (np.arange(n, dtype=np.float32) + 0.5) / n
        along = t[None, :] * length[:, None]
        live = (along > skip) & (along < length[:, None] - skip)
        q = ((p[:, None, :] + d[:, None, :] * t[None, :, None] - lo) / voxel).astype(int)
        inside = np.all((q >= 0) & (q < np.array(grid.shape)), axis=2)
        q = np.clip(q, 0, np.array(grid.shape) - 1)
        out[s:s + 6000] = ~np.any(grid[q[..., 0], q[..., 1], q[..., 2]] & live & inside, axis=1)
    return out


def assign(V: np.ndarray, F: np.ndarray, cams: np.ndarray, occ: tuple[np.ndarray, np.ndarray] | None = None) -> np.ndarray:
    """Index of the panorama that colours each triangle, or -1 when none is in front of it. Best first by angle over
    distance squared (the size of a texel in the photo), and the first candidate with a clear line of sight wins."""
    T = V[F]
    centre = T.mean(1)
    normal = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-12)
    to = cams[None, :, :] - centre[:, None, :]
    dist = np.linalg.norm(to, axis=2)
    cos = np.einsum("fcd,fd->fc", to, normal) / np.maximum(dist, 1e-6)
    under = to[:, :, 2] / np.maximum(dist, 1e-6) > NADIR_COS
    score = np.where((cos > MIN_COS) & (dist < MAX_RANGE) & ~under, cos / np.maximum(dist, 0.4) ** 2, -1.0)
    order = np.argsort(-score, axis=1)[:, :CANDIDATES]
    grid, lo = occ or occupancy(surface_points(V, F, VOXEL * 0.6))
    out = np.full(len(F), -1, np.int32)
    start = centre + normal * 0.1
    rows = np.arange(len(F))
    for r in range(order.shape[1]):
        cand = order[:, r]
        todo = np.nonzero((out < 0) & (score[rows, cand] > 0))[0]
        if not len(todo):
            break
        ok = clear(grid, lo, start[todo], cams[cand[todo]])
        out[todo[ok]] = cand[todo[ok]]
    # A grey hole reads worse than a slightly wrong photo: what no camera sees clearly takes its best candidate,
    # then any camera in front of it.
    hidden = (out < 0) & (score[rows, order[:, 0]] > 0)
    out[hidden] = order[hidden, 0]
    loose = np.where((cos > 0.05) & (dist < 1.5 * MAX_RANGE), cos / np.maximum(dist, 0.4) ** 2, -1.0)
    rest = (out < 0) & (loose.max(1) > 0)
    out[rest] = np.argmax(loose[rest], 1)
    return out


def neighbours(F: np.ndarray) -> np.ndarray:
    """For each triangle and corner, the triangle across the edge opposite that corner; -1 where the edge is open
    or shared by more than two."""
    a, b = F[:, [1, 2, 0]], F[:, [2, 0, 1]]  # the edge opposite corner i runs from corner i + 1 to corner i + 2
    key = (np.minimum(a, b).astype(np.int64) * (int(F.max()) + 1) + np.maximum(a, b)).ravel()  # entry f * 3 + i
    order = np.argsort(key, kind="stable")
    same = key[order][1:] == key[order][:-1]
    first = np.nonzero(same & ~np.r_[False, same[:-1]] & ~np.r_[same[1:], False])[0]  # runs of exactly two
    out = np.full(len(key), -1, np.int32)
    i, j = order[first], order[first + 1]
    out[i], out[j] = j // 3, i // 3
    return out.reshape(-1, 3)


def seams(V: np.ndarray, F: np.ndarray, owner: np.ndarray, cams: np.ndarray, occ: tuple[np.ndarray, np.ndarray]) -> tuple:
    """Where two panoramas meet along an edge: (triangle, corner, panorama, tau) rows. The panorama colours the
    triangle across the edge opposite `corner`, sees this triangle too, and is blended into it with a weight that
    is 1 on the edge and 0 at tau of the way to the corner (FEATHER metres, never less than a fifth of the way)."""
    nbr = neighbours(F)
    f, c = np.nonzero(nbr >= 0)
    p = owner[nbr[f, c]]
    keep = (p >= 0) & (owner[f] >= 0) & (p != owner[f])
    f, c, p = f[keep], c[keep], p[keep]
    T = V[F[f]]
    centre = T.mean(1)
    cross = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    area2 = np.maximum(np.linalg.norm(cross, axis=1), 1e-12)
    normal = cross / area2[:, None]
    to = cams[p] - centre
    dist = np.maximum(np.linalg.norm(to, axis=1), 1e-6)
    ok = (np.einsum("fd,fd->f", to, normal) / dist > 0.15) & (dist < 1.5 * MAX_RANGE)
    ok[ok] = clear(*occ, (centre + normal * 0.1)[ok], cams[p[ok]])
    rows = np.arange(len(f))
    edge = np.linalg.norm(T[rows, (c + 1) % 3] - T[rows, (c + 2) % 3], axis=1)
    tau = np.clip(FEATHER * np.maximum(edge, 1e-6) / area2, 0.2, 1.0)  # area2 / edge is the height over the edge
    return f[ok], c[ok], p[ok], tau[ok].astype(np.float32)


def gains(i: np.ndarray, j: np.ndarray, a: np.ndarray, b: np.ndarray, n: int, noise: float = 0.05, slack: float = 0.15) -> np.ndarray:
    """A gain for each of n panoramas and colour channel, so that panorama i[k] and panorama j[k], which saw the
    same spot as a[k] and b[k] (0..1 per channel), agree after scaling. Every gain is pulled toward 1, or all of them
    would agree at 0 (the least squares of Brown and Lowe's panorama stitching); the pull still leaves them a little
    low, so they are rescaled to average 1 over the panoramas that took part: the building keeps its brightness and
    only the differences between panoramas go. Kept within 0.6 and 1.6."""
    g = np.ones((n, 3), np.float32)
    for ch in range(3):
        x, y = a[:, ch].astype(np.float64), b[:, ch].astype(np.float64)
        ok = (x > 0.04) & (x < 0.96) & (y > 0.04) & (y < 0.96)  # a clipped or black sample says nothing about exposure
        ii, jj, x, y = i[ok], j[ok], x[ok], y[ok]
        A, rhs = np.zeros((n, n)), np.zeros(n)
        np.add.at(A, (ii, ii), x * x / noise ** 2)
        np.add.at(A, (jj, jj), y * y / noise ** 2)
        np.add.at(A, (ii, jj), -x * y / noise ** 2)
        np.add.at(A, (jj, ii), -x * y / noise ** 2)
        prior = (np.bincount(np.r_[ii, jj], minlength=n) + 1) / slack ** 2
        A[np.arange(n), np.arange(n)] += prior
        g[:, ch] = np.linalg.solve(A, rhs + prior)
        part = np.bincount(np.r_[ii, jj], minlength=n) > 0
        if part.any():
            g[part, ch] /= g[part, ch].mean()
    return np.clip(g, 0.6, 1.6)


def facing_in(V: np.ndarray, F: np.ndarray, cams: np.ndarray) -> np.ndarray:
    """The triangles wound so that most of them face the camera nearest to them (the inside of the rooms)."""
    T = V[F]
    centre = T.mean(1)
    normal = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    near = cams[np.argmin(np.linalg.norm(cams[None] - centre[:, None], axis=2), axis=1)]
    return F if np.mean(np.einsum("fd,fd->f", near - centre, normal) > 0) >= 0.5 else F[:, ::-1].copy()


# ---- baking ------------------------------------------------------------------------------------------------------

def cube_lookup(cube: np.ndarray, d_cam: np.ndarray) -> np.ndarray:
    """Colours of a cube (6, S, S, 3; faces as Matterport orders them) along camera-frame directions (n, 3)."""
    size = cube.shape[1]
    bases = [face_basis(f) for f in range(6)]
    t = np.stack([d_cam @ fwd for fwd, _, _ in bases], 1)
    face = np.argmax(t, 1)
    out = np.zeros((len(d_cam), 3), np.uint8)
    for f, (_, right, down) in enumerate(bases):
        m = face == f
        if not m.any():
            continue
        p = d_cam[m] / t[m, f][:, None]
        u = np.clip(((p @ right + 1) * size / 2).astype(int), 0, size - 1)
        v = np.clip(((p @ down + 1) * size / 2).astype(int), 0, size - 1)
        out[m] = cube[f, v, u]
    return out


def paint(acc: np.ndarray, wsum: np.ndarray, V: np.ndarray, F: np.ndarray, lay: dict, faces: np.ndarray, cam: np.ndarray,
          rot: np.ndarray, cubes: list[np.ndarray], corner: np.ndarray | None = None, tau: np.ndarray | None = None) -> None:
    """Add one panorama's colour to the cells of `faces`, into the running sums `acc` (colour times weight) and
    `wsum` (weight), both in units of ONE. With no `corner` the weight is 1 over the whole triangle (the panorama
    owns it). With `corner` and `tau` it is a guest across the edge opposite that corner: 1 on the edge, falling to 0
    at tau of the way to the corner. `cubes` are the same panorama at falling sizes; a texel takes the size whose
    pixels are about as large as its own, so a near wall is sharp and a far one does not shimmer."""
    sizes = [c.shape[1] for c in cubes][::-1]  # smallest first
    key = (lay["kw"][faces].astype(np.int64) * 1000 + lay["kh"][faces] * 10 + lay["slot"][faces]) * 4 + (0 if corner is None else corner)
    for k in np.unique(key):
        sel = key == k
        ids = faces[sel]
        px, py, u1, u2 = cell_texels(int(k // 4 // 1000), int(k // 4 // 10 % 100))[int(k // 4 % 10)]
        if corner is None:
            w = np.full((len(ids), len(px)), ONE, np.uint16)
        else:
            along = (1 - u1 - u2, u1, u2)[int(k % 4)]  # 0 on the edge opposite the corner, 1 at the corner
            w = np.round(np.clip(1 - along[None, :] / tau[sel][:, None], 0, 1) * ONE).astype(np.uint16)
        live = w.ravel() > 0
        if not live.any():
            continue
        T = V[F[ids]]
        P = (T[:, None, 0] + u1[None, :, None] * (T[:, None, 1] - T[:, None, 0])
             + u2[None, :, None] * (T[:, None, 2] - T[:, None, 0])).reshape(-1, 3)[live]
        d = (P - cam) @ rot  # scan frame to the panorama's own frame: R transposed, written for row vectors
        want = 3 * np.repeat(lay["each"][ids], len(px))[live] * np.linalg.norm(d, axis=1)  # face size at which a photo pixel matches a texel
        level = np.clip(np.searchsorted(sizes, want), 0, len(cubes) - 1)
        col = np.zeros((len(P), 3), np.uint16)
        for i, cube in enumerate(cubes[::-1]):
            m = level == i
            if m.any():
                col[m] = cube_lookup(cube, d[m])
        ay = (lay["y"][ids][:, None] + py[None, :]).ravel()[live]
        ax = (lay["x"][ids][:, None] + px[None, :]).ravel()[live]
        ww = w.ravel()[live]
        acc[ay, ax] += col * ww[:, None]  # a texel belongs to one triangle, so no index repeats within a call
        wsum[ay, ax] += ww


def _faces(sid: str, pano: str, size: int) -> list[Image.Image]:
    out = []
    for f in range(6):
        im = Image.open(io.BytesIO(mp.pano_face(sid, pano, f, "2k")))
        im.draft("RGB", (size, size))
        out.append(im.convert("RGB").resize((size, size), Image.BILINEAR))
    return out


def pano_cubes(sid: str, pano: str, gain: np.ndarray | None = None) -> list[np.ndarray]:
    """One panorama as cubes 1024, 512 and 256 texels across, each colour channel scaled by `gain`."""
    faces = _faces(sid, pano, 1024)
    cubes = [np.stack([np.asarray(im.reduce(r) if r > 1 else im) for im in faces]) for r in (1, 2, 4)]
    return cubes if gain is None else [np.clip(c * gain, 0, 255).astype(np.uint8) for c in cubes]


def pano_small(sid: str, pano: str) -> np.ndarray:
    """One panorama as a cube 128 texels across: a blurred view, for comparing exposures."""
    return np.stack([np.asarray(im) for im in _faces(sid, pano, 128)])


def prepared(sid: str) -> tuple[np.ndarray, np.ndarray, dict, dict]:
    plan = mp.plan(sid)
    V, F = weld(*parse_obj(obj_bytes(sid)))
    F = without_specks(trim(V, F, plan))
    if not len(F):
        raise LookupError("this scan's mesh has nothing inside its rooms")
    cams = np.array([p["position"] for p in plan["panos"]], np.float32).reshape(-1, 3)
    if len(cams):
        F = facing_in(V, F, cams)
    F = face_frames(V, F)
    return V, F, layout_for(V, F), plan


def floor_of(V: np.ndarray, F: np.ndarray, plan: dict) -> np.ndarray:
    """Index into plan.floors for each triangle: the highest floor that starts below its middle."""
    z = V[F].mean(1)[:, 2]
    out = np.zeros(len(F), np.int8)
    levels = floor_z(plan)
    for i, fl in enumerate(plan["floors"]):
        out[z >= levels[fl["id"]] - 0.4] = i
    return out


def pack(V: np.ndarray, F: np.ndarray, uv: np.ndarray, floor: np.ndarray) -> bytes:
    """MAGIC, triangle count, then per corner: position (3 float32), normal (3 int8) and floor index (int8), uv (2 uint16)."""
    n = vertex_normals(V, F)[F].reshape(-1, 3)
    nb = np.zeros((len(n), 4), np.int8)
    nb[:, :3] = np.round(n * 127)
    nb[:, 3] = np.repeat(floor, 3)
    return b"".join([MAGIC, struct.pack("<I", len(F)), V[F].astype("<f4").tobytes(), nb.tobytes(),
                     np.round(np.clip(uv, 0, 1) * 65535).astype("<u2").tobytes()])


def geometry(sid: str) -> bytes:
    check(sid, "sid")

    def make() -> bytes:
        V, F, lay, plan = prepared(sid)
        return pack(V, F, lay["uv"], floor_of(V, F, plan))
    with one_flight(f"mesh:{sid}"):
        return cached(path(sid, "mesh.bin"), make)


def bake(sid: str, progress=lambda done, total: None) -> dict:
    V, F, lay, plan = prepared(sid)
    panos, size = plan["panos"], lay["atlas"]
    cams = np.array([p["position"] for p in panos], np.float32).reshape(-1, 3)
    rots = [(quat_matrix(p["rotation"]) if p.get("rotation") else np.eye(3)).astype(np.float32) for p in panos]
    owner, seam = np.full(len(F), -1, np.int32), (np.zeros(0, np.int64),) * 3 + (np.zeros(0, np.float32),)
    if len(panos):
        occ = occupancy(surface_points(V, F, VOXEL * 0.6))
        owner = assign(V, F, cams, occ)
        seam = seams(V, F, owner, cams, occ)
    sf, sc, sp, st = seam
    used = sorted(set(owner[owner >= 0].tolist()) | set(sp.tolist()))
    steps = 2 * len(used)
    with ThreadPoolExecutor(4) as pool:  # the upstream gate spaces the requests; this only overlaps their waiting
        # exposure: what each seam triangle's middle looks like in its own panorama and in its guest
        mid = V[F[sf]].mean(1)
        own, guest = np.zeros((len(sf), 3), np.float32), np.zeros((len(sf), 3), np.float32)
        for done, (i, cube) in enumerate(zip(used, pool.map(lambda i: _or_none(pano_small, sid, panos[i]["id"]), used))):
            if cube is not None:
                for rows, into in ((owner[sf] == i, own), (sp == i, guest)):
                    if rows.any():
                        into[rows] = cube_lookup(cube, (mid[rows] - cams[i]) @ rots[i]) / 255.0
            progress(done + 1, steps)
        gain = gains(owner[sf], sp, own, guest, len(panos)) if len(sf) else np.ones((len(panos), 3), np.float32)
        acc, wsum = np.zeros((size, size, 3), np.uint16), np.zeros((size, size), np.uint16)
        for done, (i, cubes) in enumerate(zip(used, pool.map(lambda i: _or_none(pano_cubes, sid, panos[i]["id"], gain[i]), used))):
            if cubes is not None:
                paint(acc, wsum, V, F, lay, np.nonzero(owner == i)[0], cams[i], rots[i], cubes)
                g = sp == i
                paint(acc, wsum, V, F, lay, sf[g], cams[i], rots[i], cubes, sc[g], st[g])
            progress(len(used) + done + 1, steps)
    atlas = np.empty((size, size, 3), np.uint8)
    atlas[:] = NEUTRAL
    lit = wsum > 0
    atlas[lit] = ((acc[lit].astype(np.uint32) + (wsum[lit][:, None] >> 1)) // wsum[lit][:, None]).astype(np.uint8)
    del acc, wsum
    buf = io.BytesIO()
    Image.fromarray(atlas).save(buf, "JPEG", quality=86)
    write_atomic(path(sid, "atlas.jpg"), buf.getvalue())
    meta = {"version": BAKE_VERSION, "triangles": int(len(F)), "coloured": round(float((owner >= 0).mean()), 3), "panoramas": len(used),
            "texels_per_m": round(float(lay["density"]), 1), "atlas_px": size, "seam_edges": int(len(sf)),
            "gain_range": [round(float(gain[used].min()), 2), round(float(gain[used].max()), 2)] if used else [1.0, 1.0]}
    write_atomic(path(sid, "meta.json"), json.dumps(meta).encode())
    return meta


def _or_none(fn, *a):
    try:
        return fn(*a)
    except Exception:  # noqa: BLE001 - one panorama that will not load leaves its triangles to their neighbours, or neutral
        return None


def status(sid: str, start: bool = True) -> dict:
    """{state: ready | baking | failed | idle, progress 0..1, ...meta}. Starts the bake when asked to and needed."""
    check(sid, "sid")
    meta = path(sid, "meta.json")
    if meta.exists() and path(sid, "atlas.jpg").exists():
        return {"state": "ready", "progress": 1.0, **json.loads(meta.read_text())}
    with one_flight(f"mesh-state:{sid}"):
        st = _state.get(sid)
        # a bake that failed is tried again only after a while: a viewer asks every few seconds
        if st is None or (st["state"] == "failed" and start and time.monotonic() - st["at"] > RETRY_S):
            if not start:
                return {"state": "idle", "progress": 0.0}
            st = _state[sid] = {"state": "baking", "progress": 0.0, "at": time.monotonic()}

            def run() -> None:
                try:
                    with _one_bake:
                        bake(sid, lambda d, t: st.update(progress=round(d / max(t, 1), 3)))
                    st["state"] = "ready"
                except Exception as e:  # noqa: BLE001 - reported to the caller, who may ask again later
                    st.update(state="failed", note=f"{type(e).__name__}: {e}"[:200], at=time.monotonic())
            threading.Thread(target=run, daemon=True, name=f"bake-{sid}").start()
        return {k: v for k, v in st.items() if k != "at"}
