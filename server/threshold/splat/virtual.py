"""Extra training views with parallax, made from the mesh and the training sweeps.

A sweep's six faces share one centre, so nothing tells Brush how far away a colour is, and it paints haze near the
camera that looks wrong from anywhere else. Here a virtual camera stands OFFSET metres from a sweep, in free space,
turned 45 degrees so its face edges fall elsewhere. Each of its horizon faces is rendered by ray-casting Matterport's
mesh for depth (a perspective-correct z-buffer of the subdivided triangles), and each pixel takes its colour from
the nearest training sweep that sees that same point (its own depth agrees). Pixels nobody saw, and pixels on depth
edges (where the 50k-triangle mesh is least exact), are masked out, so Brush ignores them.

Only training sweeps are used, never held-out ones, as sources or as centres.
"""
from __future__ import annotations

import math

import numpy as np

from ..vision.projection import face_basis, quat_matrix

NEAR = 0.05
MAX_EDGE = 0.3        # metres; triangles are split until no edge is longer, so dropping ones at the camera is harmless
OFFSET = 0.5          # metres from the sweep to its virtual camera
CLEARANCE = 0.5       # free space needed beyond the virtual camera in the direction it moved
SRC_PX = 256          # source depth faces for the visibility test
AGREE = 0.05          # metres (+3%) between the point and the source's own surface for the source to count as seeing it
EDGE_RATIO = 1.08     # a pixel whose neighbours' depth differs by more than this ratio is a depth edge: masked
SOURCES = 4           # nearest training sweeps tried, nearest first
BLUR_PX = 64          # faces are compared at this size
DISAGREE = 45         # mean absolute RGB difference above which two sweeps disagree about a point
CHUNK = 4_000_000     # candidate pixels per batch


def subdivide(T: np.ndarray, max_edge: float = MAX_EDGE) -> np.ndarray:
    for _ in range(8):
        e = np.linalg.norm(T - np.roll(T, -1, 1), axis=2).max(1)
        big = e > max_edge
        if not big.any():
            break
        a, b, c = T[big, 0], T[big, 1], T[big, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        T = np.concatenate([T[~big], np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1),
                            np.stack([ca, bc, c], 1), np.stack([ab, bc, ca], 1)])
    return T


def depth(T: np.ndarray, R: np.ndarray, t: np.ndarray, n: int) -> np.ndarray:
    """(n, n) camera z of the nearest triangle per pixel of a 90 degree pinhole face (COLMAP axes); inf where none."""
    P = T @ R.T + t
    P = P[np.all(P[:, :, 2] > NEAR, axis=1)]
    uv = P[:, :, :2] / P[:, :, 2:3] * (n / 2) + n / 2
    iz = 1 / P[:, :, 2]
    lo = np.clip(np.floor(uv.min(1) - 0.5), 0, n).astype(np.int64)
    hi = np.clip(np.ceil(uv.max(1) + 0.5), 0, n).astype(np.int64)
    w, h = hi[:, 0] - lo[:, 0], hi[:, 1] - lo[:, 1]
    keep = (w > 0) & (h > 0)
    uv, iz, lo, w, h = uv[keep], iz[keep], lo[keep], w[keep], h[keep]
    cnt = w * h
    out = np.full(n * n, np.inf)
    a, b, c = uv[:, 0], uv[:, 1], uv[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    ok_tri = np.abs(area) > 1e-9
    bounds = np.searchsorted(np.cumsum(cnt), np.arange(CHUNK, cnt.sum() + CHUNK, CHUNK))
    start = 0
    for stop in [*bounds.tolist(), len(cnt)]:
        stop = max(stop, start + 1)
        idx = np.arange(start, min(stop, len(cnt)))
        start = stop
        idx = idx[ok_tri[idx]]
        if not len(idx):
            continue
        k = cnt[idx]
        tri = np.repeat(idx, k)
        j = np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)
        xs = lo[tri, 0] + j % w[tri]
        ys = lo[tri, 1] + j // w[tri]
        px, py = xs + 0.5, ys + 0.5
        A, B, C = a[tri], b[tri], c[tri]
        w0 = ((B[:, 0] - px) * (C[:, 1] - py) - (B[:, 1] - py) * (C[:, 0] - px)) / area[tri]
        w1 = ((C[:, 0] - px) * (A[:, 1] - py) - (C[:, 1] - py) * (A[:, 0] - px)) / area[tri]
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
        z = 1 / (w0 * iz[tri, 0] + w1 * iz[tri, 1] + w2 * iz[tri, 2])
        np.minimum.at(out, (ys * n + xs)[inside], z[inside])
    return out.reshape(n, n)


def _rz(deg: float) -> np.ndarray:
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])


def _pose(centre, R_pano: np.ndarray, face: int) -> tuple[np.ndarray, np.ndarray]:
    fwd, right, down = (R_pano @ v for v in face_basis(face))
    R = np.stack([right, down, fwd])
    return R, -R @ np.asarray(centre, float)


def _edges(z: np.ndarray) -> np.ndarray:
    lo, hi = z.copy(), z.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            s = np.roll(np.roll(z, dy, 0), dx, 1)
            lo, hi = np.minimum(lo, s), np.maximum(hi, s)
    return ~(hi <= lo * EDGE_RATIO)


class Sources:
    """Training sweeps' faces and depth, for colour lookups."""

    def __init__(self, T: np.ndarray, panos: dict, faces: dict):
        self.ids = list(panos)
        self.centres = np.array([panos[p]["position"] for p in self.ids], float)
        self.R = {p: quat_matrix(panos[p]["rotation"]) for p in self.ids}
        self.faces = faces  # (pano, face) -> (m, m, 3) uint8
        self.blur = {k: _block_mean(v, BLUR_PX) for k, v in faces.items()}  # agreement is judged on these
        self.depth = {(p, f): depth(T, *_pose(panos[p]["position"], self.R[p], f), SRC_PX)
                      for p in self.ids for f in range(6)}

    def free(self, p: str, direction: np.ndarray) -> float:
        """Distance to the mesh from sweep p along a scan-frame direction (inf if none)."""
        d_cam = self.R[p].T @ direction
        f = int(np.argmax([d_cam @ face_basis(k)[0] for k in range(6)]))
        fwd, right, down = face_basis(f)
        z = d_cam @ fwd
        u = int(np.clip((d_cam @ right / z + 1) / 2 * SRC_PX, 0, SRC_PX - 1))
        v = int(np.clip((d_cam @ down / z + 1) / 2 * SRC_PX, 0, SRC_PX - 1))
        return float(self.depth[(p, f)][v, u] / z)

    def colour(self, X: np.ndarray, order: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """RGB for world points X from the first sweep in `order` that sees each, and which to keep: a point two
        sweeps see keeps its colour only if they agree (blinds, glass and misplaced edges do not)."""
        first = np.zeros((len(X), 3), np.int16)
        first_blur = np.zeros((len(X), 3), np.int16)
        hits = np.zeros(len(X), np.int8)
        agree = np.ones(len(X), bool)
        bases = [face_basis(k) for k in range(6)]
        for p in order:
            todo = hits < 2
            if not todo.any():
                break
            v = X[todo] - self.centres[self.ids.index(p)]
            d_cam = v @ self.R[p]  # R.T @ v, row-wise
            k = np.argmax(np.stack([d_cam @ b[0] for b in bases], 1), 1)
            seen = np.zeros(len(v), bool)
            col = np.zeros((len(v), 3), np.int16)
            colb = np.zeros((len(v), 3), np.int16)
            for f, (fwd, right, down) in enumerate(bases):
                m = k == f
                if not m.any():
                    continue
                z = d_cam[m] @ fwd
                a, b = d_cam[m] @ right / z, d_cam[m] @ down / z
                ds = self.depth[(p, f)]
                su = np.clip(((a + 1) / 2 * SRC_PX).astype(int), 0, SRC_PX - 1)
                sv = np.clip(((b + 1) / 2 * SRC_PX).astype(int), 0, SRC_PX - 1)
                img = self.faces[(p, f)]
                mpx = img.shape[0]
                cu = np.clip(((a + 1) / 2 * mpx).astype(int), 0, mpx - 1)
                cv = np.clip(((b + 1) / 2 * mpx).astype(int), 0, mpx - 1)
                col[m] = img[cv, cu]
                colb[m] = self.blur[(p, f)][np.minimum(cv * BLUR_PX // mpx, BLUR_PX - 1), np.minimum(cu * BLUR_PX // mpx, BLUR_PX - 1)]
                seen[m] = np.abs(z - ds[sv, su]) < AGREE + 0.03 * z
            idx = np.nonzero(todo)[0][seen]
            new = hits[idx] == 0
            first[idx[new]] = col[seen][new]
            first_blur[idx[new]] = colb[seen][new]
            second = idx[~new]
            agree[second] = np.abs(first_blur[second] - colb[seen][~new]).mean(1) < DISAGREE
            hits[idx] += 1
        return first.astype(np.uint8), (hits > 0) & agree


def _block_mean(img: np.ndarray, n: int) -> np.ndarray:
    m = img.shape[0] // n
    return img[:m * n, :m * n].reshape(n, m, n, m, 3).mean((1, 3)).astype(np.int16)


def render(T: np.ndarray, src: Sources, centre, R_pano: np.ndarray, face: int, n: int,
           exclude: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(rgb (n, n, 3), mask (n, n) bool) for one face of a virtual camera."""
    R, t = _pose(centre, R_pano, face)
    z = depth(T, R, t, n)
    valid = np.isfinite(z) & ~_edges(np.where(np.isfinite(z), z, 1e6))
    ys, xs = np.nonzero(valid)
    cam = np.stack([(xs + 0.5 - n / 2) / (n / 2) * z[ys, xs], (ys + 0.5 - n / 2) / (n / 2) * z[ys, xs], z[ys, xs]], 1)
    X = (cam - t) @ R  # R.T @ (cam - t), row-wise
    near = np.argsort(np.linalg.norm(src.centres - np.asarray(centre), axis=1))
    order = [src.ids[i] for i in near if src.ids[i] != exclude][:SOURCES]
    if exclude in src.ids:
        order = [exclude, *order]  # the sweep the camera stepped away from sees almost all of it
    rgb, done = src.colour(X, order)
    img = np.zeros((n, n, 3), np.uint8)
    mask = np.zeros((n, n), bool)
    img[ys[done], xs[done]] = rgb[done]
    mask[ys[done], xs[done]] = True
    return img, mask


def cameras(src: Sources, panos: dict, rng) -> list[tuple[str, np.ndarray, np.ndarray]]:
    """One virtual camera per training sweep: (sweep id, centre, rotation), OFFSET m away in free space."""
    out = []
    for p in src.ids:
        c = np.asarray(panos[p]["position"], float)
        for a in rng.permutation(8) * 45.0:
            d = np.array([math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0])
            if src.free(p, d) > OFFSET + CLEARANCE:
                out.append((p, c + OFFSET * d, _rz(45.0) @ src.R[p]))
                break
    return out

