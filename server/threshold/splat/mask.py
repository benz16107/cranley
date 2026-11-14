"""Which pixels of a cube face look outdoors: their ray meets none of the scan's mesh within the plan (windows,
open doors to the garden). Those pixels get alpha 0 in the training images, so Brush leaves them transparent and
the drone exterior shows through the interior splat's windows.

Coverage is a plain rasterization of the trimmed mesh's triangles at a coarse size, grown by a pixel; depth is not
needed. Triangles crossing the camera plane (within NEAR of the camera) are skipped.
"""
from __future__ import annotations

import numpy as np

COARSE = 128
NEAR = 0.05


def coverage(T: np.ndarray, R: np.ndarray, t: np.ndarray, n: int = COARSE) -> np.ndarray:
    """(n, n) bool: pixels of a 90 degree pinhole face (world-to-camera R, t, COLMAP axes) covered by triangles T."""
    P = T @ R.T + t                                    # (m, 3, 3) camera coordinates
    P = P[np.all(P[:, :, 2] > NEAR, axis=1)]
    uv = P[:, :, :2] / P[:, :, 2:3] * (n / 2) + n / 2  # pixel units, centres at +0.5
    lo = np.clip(np.floor(uv.min(1) - 0.5), 0, n).astype(np.int64)
    hi = np.clip(np.ceil(uv.max(1) + 0.5), 0, n).astype(np.int64)
    keep = np.all(hi > lo, axis=1)
    uv, lo, hi = uv[keep], lo[keep], hi[keep]
    w, h = hi[:, 0] - lo[:, 0], hi[:, 1] - lo[:, 1]
    cnt = w * h
    out = np.zeros((n, n), bool)
    big = cnt > 4096  # a triangle filling much of the face: fill its box row by row would be slow, test the grid
    for k in np.nonzero(big)[0]:
        ys, xs = np.mgrid[lo[k, 1]:hi[k, 1], lo[k, 0]:hi[k, 0]]
        out[ys, xs] |= _inside(uv[k][None], xs.ravel() + 0.5, ys.ravel() + 0.5, np.zeros(xs.size, int)).reshape(xs.shape)
    s = ~big
    uv, lo, w, cnt = uv[s], lo[s], w[s], cnt[s]
    tri = np.repeat(np.arange(len(cnt)), cnt)
    j = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    xs = lo[tri, 0] + j % w[tri]
    ys = lo[tri, 1] + j // w[tri]
    ok = _inside(uv, xs + 0.5, ys + 0.5, tri)
    out[ys[ok], xs[ok]] = True
    grown = out.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(out, dy, 0), dx, 1)
    return grown


def _inside(uv: np.ndarray, x: np.ndarray, y: np.ndarray, tri: np.ndarray, pad: float = 0.5) -> np.ndarray:
    """Point (x, y) within triangle uv[tri], with a half-pixel allowance so thin slivers still cover their pixels."""
    a, b, c = uv[tri, 0], uv[tri, 1], uv[tri, 2]

    def edge(p, q):
        e = q - p
        d = (x - p[:, 0]) * e[:, 1] - (y - p[:, 1]) * e[:, 0]
        return d / np.maximum(np.hypot(e[:, 0], e[:, 1]), 1e-9)
    e1, e2, e3 = edge(a, b), edge(b, c), edge(c, a)
    return ((e1 >= -pad) & (e2 >= -pad) & (e3 >= -pad)) | ((e1 <= pad) & (e2 <= pad) & (e3 <= pad))
