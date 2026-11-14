"""Remove splats floating in space the scanned mesh shows to be empty.

Panorama training has no parallax inside a sweep: every face of it shares one centre, so a blur painted close to
the camera fits that sweep as well as the wall behind it, and looks wrong from anywhere else. Matterport's mesh
says where the surfaces are. A splat whose centre lies clearly in front of the mesh as seen from a training sweep
(nearer than the surface in that direction, by more than CLEAR m plus 4%) sits in air that sweep looked through,
and goes. Directions with no mesh (windows, the trimmed garden) carve nothing.

Depth is a z-buffer of the mesh's triangles per cube face (`virtual.depth`). Point samples are not enough: on a
large house they sit 4 to 5 cm apart, near surfaces turn see-through between them, and the carve then ate the
kitchen island and the ceiling (<scan-id>, 2026-11-14).
"""
from __future__ import annotations

import numpy as np

from . import dataset, seed, virtual

CLEAR = 0.12
PX = 256


def free_space(xyz: np.ndarray, T: np.ndarray, sweeps: list[dict], px: int = PX) -> np.ndarray:
    """True for splat centres nearer than the mesh (by CLEAR + 4%) from some sweep, within seed.MAX_RANGE of it.
    T is the subdivided mesh (virtual.subdivide); sweeps are ScanPlan panos with position and rotation."""
    out = np.zeros(len(xyz), bool)
    for s in sweeps:
        near = np.linalg.norm(xyz - np.asarray(s["position"]), axis=1) < seed.MAX_RANGE
        for f in range(6):
            R, t = dataset.face_pose(s["position"], s["rotation"], f)
            pc = xyz[near] @ R.T + t
            z = pc[:, 2]
            ok = z > 0.05
            a = np.where(ok, pc[:, 0] / np.where(ok, z, 1), 9)
            b = np.where(ok, pc[:, 1] / np.where(ok, z, 1), 9)
            ok &= (np.abs(a) <= 1) & (np.abs(b) <= 1)
            if not ok.any():
                continue
            D = virtual.depth(T, R, t, px)
            u = np.clip(((a[ok] + 1) / 2 * px).astype(int), 0, px - 1)
            v = np.clip(((b[ok] + 1) / 2 * px).astype(int), 0, px - 1)
            idx = np.nonzero(near)[0][ok]
            surf = D[v, u]
            out[idx] |= np.isfinite(surf) & (z[ok] < surf * 0.96 - CLEAR)  # no mesh in that direction: keep
    return out
