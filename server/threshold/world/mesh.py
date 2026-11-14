"""Matterport's own scanned mesh (the 50,000 triangle one behind its dollhouse view), coloured from the panoramas.

The Model API lists that mesh as an OBJ with no texture coordinates (MatterPak, which has a textured one, is
unavailable on these scans). So the colour is baked here from data the API does give: every triangle gets its own
cell in one atlas, and each texel takes the pixel of the panorama that sees that spot best: in front of the
surface, close, and with nothing of the mesh in between.

Outputs, in `$THRESHOLD_DATA_DIR/cache/mesh/<sid>/`: `mesh.bin` (positions, normals, texture coordinates; written
in a second or two) and `atlas.jpg` (minutes the first time: up to six requests per panorama).
"""
from __future__ import annotations

import io
import json
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from ..sources import matterport as mp
from ..sources.upstream import cache_path, cached, check, one_flight, send, write_atomic
from ..vision.projection import face_basis, quat_matrix

ATLAS = 4096
CLASSES = (4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024)  # a cell side, in texels
PAD = 3                 # a cell is its triangle's legs plus this: half a texel at each end and a gap between its two triangles
MAX_DENSITY = 140.0     # texels per metre when the atlas has room
VOXEL = 0.08            # metres; the occupancy grid that decides whether a panorama sees a triangle
MAX_RANGE = 10.0        # a panorama further than this does not colour a triangle
MIN_COS = 0.2           # nor one that sees it at a flatter angle than this
NADIR_COS = 0.9         # nor, by choice, one standing right over it: Matterport blurs the tripod out of each panorama
BAKE_VERSION = 3
CANDIDATES = 6
MARGIN = 1.0            # metres of mesh kept outside the plan's walls (the rest is the garden seen through windows)
NEUTRAL = (204, 200, 192)
MAGIC = b"THM2"

_state: dict[str, dict] = {}


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


def trim(V: np.ndarray, F: np.ndarray, plan: dict) -> np.ndarray:
    """Triangles within MARGIN of the plan's walls and rooms, and no higher than its tallest ceiling."""
    pts = [p for w in plan["walls"] for p in (w["a"], w["b"])] + [p for r in plan["rooms"] for p in r["polygon"]] \
        + [p["position"][:2] for p in plan["panos"]]
    if not pts:
        return F
    lo, hi = np.min(pts, 0) - MARGIN, np.max(pts, 0) + MARGIN
    top = max((fl.get("elevation") or 0) for fl in plan["floors"]) + max([r.get("height") or 0 for r in plan["rooms"]] + [2.7]) + 0.6
    c = V[F].mean(1)
    keep = (c[:, 0] > lo[0]) & (c[:, 0] < hi[0]) & (c[:, 1] > lo[1]) & (c[:, 1] < hi[1]) & (c[:, 2] < top) & (c[:, 2] > -1.0)
    return F[keep]


def without_specks(F: np.ndarray, share: float = 0.01, least: int = 150) -> np.ndarray:
    """The triangles of every connected piece that is not a speck. A scan leaves scraps of tree and roof floating
    beside the building; a piece with under 1% of the triangles (and under 150) is one of those."""
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

def layout(V: np.ndarray, F: np.ndarray, atlas: int = ATLAS) -> dict:
    """A cell for every triangle: a rectangle as wide and as tall as the two edges at its first corner, shared with
    one other triangle of the same size. Returns kw, kh (indexes into CLASSES), x, y (the cell's corner in texels),
    slot (0 the lower-left half of the cell, 1 the upper-right), uv (m, 3, 2) in 0..1 with v up, and the density
    reached (texels per metre; lowered until everything fits)."""
    T = V[F]
    la, lb = np.linalg.norm(T[:, 1] - T[:, 0], axis=1), np.linalg.norm(T[:, 2] - T[:, 0], axis=1)
    sizes = np.array(CLASSES)
    density = MAX_DENSITY
    while True:
        kw = np.minimum(np.searchsorted(sizes, la * density), len(sizes) - 1)
        kh = np.minimum(np.searchsorted(sizes, lb * density), len(sizes) - 1)
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
    return {"kw": kw, "kh": kh, "x": x, "y": y, "slot": slot, "uv": uv.astype(np.float32), "density": density}


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


def assign(V: np.ndarray, F: np.ndarray, cams: np.ndarray) -> np.ndarray:
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
    grid, lo = occupancy(surface_points(V, F, VOXEL * 0.6))
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


def paint(atlas: np.ndarray, V: np.ndarray, F: np.ndarray, lay: dict, faces: np.ndarray, cam: np.ndarray,
          rot: np.ndarray, cubes: list[np.ndarray]) -> None:
    """Colour the cells of `faces` from one panorama. `cubes` are the same panorama at falling sizes; a texel takes
    the size whose pixels are about as large as its own, so a near wall is sharp and a far one does not shimmer."""
    sizes = [c.shape[1] for c in cubes][::-1]  # smallest first
    key = lay["kw"][faces].astype(np.int64) * 1000 + lay["kh"][faces] * 10 + lay["slot"][faces]
    for k in np.unique(key):
        ids = faces[key == k]
        px, py, u1, u2 = cell_texels(int(k // 1000), int(k // 10 % 100))[int(k % 10)]
        T = V[F[ids]]
        P = (T[:, None, 0] + u1[None, :, None] * (T[:, None, 1] - T[:, None, 0])
             + u2[None, :, None] * (T[:, None, 2] - T[:, None, 0])).reshape(-1, 3)
        d = (P - cam) @ rot  # scan frame to the panorama's own frame: R transposed, written for row vectors
        want = 3 * lay["density"] * np.linalg.norm(d, axis=1)  # face size at which a photo pixel matches a texel
        level = np.clip(np.searchsorted(sizes, want), 0, len(cubes) - 1)
        col = np.zeros((len(P), 3), np.uint8)
        for i, cube in enumerate(cubes[::-1]):
            m = level == i
            if m.any():
                col[m] = cube_lookup(cube, d[m])
        atlas[(lay["y"][ids][:, None] + py[None, :]).ravel(), (lay["x"][ids][:, None] + px[None, :]).ravel()] = col


def pano_cubes(sid: str, pano: str) -> list[np.ndarray]:
    """One panorama as cubes 1024, 512 and 256 texels across."""
    faces = []
    for f in range(6):
        im = Image.open(io.BytesIO(mp.pano_face(sid, pano, f, "2k")))
        im.draft("RGB", (1024, 1024))
        faces.append(im.convert("RGB").resize((1024, 1024), Image.BILINEAR))
    return [np.stack([np.asarray(im.reduce(r) if r > 1 else im) for im in faces]) for r in (1, 2, 4)]


def prepared(sid: str) -> tuple[np.ndarray, np.ndarray, dict, dict]:
    plan = mp.plan(sid)
    V, F = parse_obj(obj_bytes(sid))
    F = without_specks(trim(V, F, plan))
    cams = np.array([p["position"] for p in plan["panos"]], np.float32).reshape(-1, 3)
    if len(cams):
        F = facing_in(V, F, cams)
    F = face_frames(V, F)
    return V, F, layout(V, F), plan


def floor_of(V: np.ndarray, F: np.ndarray, plan: dict) -> np.ndarray:
    """Index into plan.floors for each triangle: the highest floor that starts below its middle."""
    z = V[F].mean(1)[:, 2]
    out = np.zeros(len(F), np.int8)
    for i, fl in enumerate(plan["floors"]):
        out[z >= (fl.get("elevation") or 0) - 0.4] = i
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
        return cached(cache_path("mesh", sid, "mesh3.bin"), make)


def bake(sid: str, progress=lambda done, total: None) -> dict:
    V, F, lay, plan = prepared(sid)
    panos = plan["panos"]
    cams = np.array([p["position"] for p in panos], np.float32).reshape(-1, 3)
    owner = assign(V, F, cams) if len(panos) else np.full(len(F), -1, np.int32)
    atlas = np.empty((ATLAS, ATLAS, 3), np.uint8)
    atlas[:] = NEUTRAL
    used = [i for i in range(len(panos)) if (owner == i).any()]
    with ThreadPoolExecutor(4) as pool:  # the upstream gate spaces the requests; this only overlaps their waiting
        for done, (i, cubes) in enumerate(zip(used, pool.map(lambda i: _cubes_or_none(sid, panos[i]["id"]), used))):
            if cubes is not None:
                rot = quat_matrix(panos[i]["rotation"]) if panos[i].get("rotation") else np.eye(3)
                paint(atlas, V, F, lay, np.nonzero(owner == i)[0], cams[i], rot.astype(np.float32), cubes)
            progress(done + 1, len(used))
    buf = io.BytesIO()
    Image.fromarray(atlas).save(buf, "JPEG", quality=86)
    write_atomic(cache_path("mesh", sid, "atlas.jpg"), buf.getvalue())
    meta = {"version": BAKE_VERSION, "triangles": int(len(F)), "coloured": round(float((owner >= 0).mean()), 3), "panoramas": len(used),
            "texels_per_m": round(float(lay["density"]), 1), "atlas_px": ATLAS}
    write_atomic(cache_path("mesh", sid, "meta.json"), json.dumps(meta).encode())
    return meta


def _cubes_or_none(sid: str, pano: str):
    try:
        return pano_cubes(sid, pano)
    except Exception:  # noqa: BLE001 - one panorama that will not load leaves its triangles neutral
        return None


def status(sid: str, start: bool = True) -> dict:
    """{state: ready | baking | failed | idle, progress 0..1, ...meta}. Starts the bake when asked to and needed."""
    check(sid, "sid")
    meta = cache_path("mesh", sid, "meta.json")
    if meta.exists() and cache_path("mesh", sid, "atlas.jpg").exists() and json.loads(meta.read_text()).get("version") == BAKE_VERSION:
        return {"state": "ready", "progress": 1.0, **json.loads(meta.read_text())}
    with one_flight(f"mesh-state:{sid}"):
        st = _state.get(sid)
        if st is None or (st["state"] == "failed" and start):
            if not start:
                return {"state": "idle", "progress": 0.0}
            st = _state[sid] = {"state": "baking", "progress": 0.0}

            def run() -> None:
                try:
                    bake(sid, lambda d, t: st.update(progress=round(d / max(t, 1), 3)))
                    st["state"] = "ready"
                except Exception as e:  # noqa: BLE001 - reported to the caller, who may ask again
                    st.update(state="failed", note=f"{type(e).__name__}: {e}"[:200])
            threading.Thread(target=run, daemon=True, name=f"bake-{sid}").start()
        return dict(st)
