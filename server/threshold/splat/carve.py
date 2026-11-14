"""Remove splats floating in space the scanned mesh shows to be empty.

Panorama training has no parallax inside a sweep: every face of it shares one centre, so a blur painted close to
the camera fits that sweep as well as the wall behind it, and looks wrong from anywhere else. Matterport's mesh
says where the surfaces are. A splat whose centre lies clearly in front of the mesh as seen from a training sweep
(nearer than the surface in that direction, by more than CLEAR m plus 4%) sits in air that sweep looked through,
and goes. Directions with no mesh (windows, the trimmed garden) carve nothing.
"""
from __future__ import annotations

import numpy as np

from . import seed

CLEAR = 0.12
DEPTH_W = 1024
MESH_SAMPLES = 1_500_000


def depth_points(sid: str, plan: dict, panos: dict, rng=None) -> np.ndarray:
    T = seed.mesh_triangles(sid, plan, panos)
    return seed.sample_triangles(T, MESH_SAMPLES, rng or np.random.default_rng(1))


def free_space(xyz: np.ndarray, surface: np.ndarray, centres: list, w: int = DEPTH_W) -> np.ndarray:
    """True for points nearer than the surface from some centre (by CLEAR + 4%), within seed.MAX_RANGE of it."""
    out = np.zeros(len(xyz), bool)
    h = w // 2
    for c in centres:
        c = np.asarray(c, float)
        v = surface - c
        d = np.linalg.norm(v, axis=1)
        depth = np.full(w * h, np.inf)
        np.minimum.at(depth, seed._lonlat_index(v, d, w), d)
        g = depth.reshape(h, w)
        m = g.copy()  # 3x3 minimum closes gaps between samples near the camera and keeps edges conservative
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                m = np.minimum(m, np.roll(np.roll(g, dr, 0), dc, 1))
        u = xyz - c
        du = np.linalg.norm(u, axis=1)
        near = du < seed.MAX_RANGE
        surf = m.reshape(-1)[seed._lonlat_index(u[near], du[near], w)]
        out[near] |= du[near] < surf * 0.96 - CLEAR
    return out
