"""Where a drone splat sits in the world: a rotation about up and a shift that lay its top surface on Vexcel's
surface model.

Measured 2026-11-14 on the cached splats: a splat is metric, z up, already close to east/north, and centred within
a few metres of the scan's geo anchor. Roofs and trees are in both the splat and the surface model, so the two
height maps are correlated over a small range of turns, and the best shift is read off the correlation peak.
"""
from __future__ import annotations

import json

import numpy as np

from ..sources import hackathon
from ..sources.upstream import cache_path, check, write_atomic
from . import terrain

PREFIX_BYTES = 48 << 20   # the file's Gaussians are in no spatial order, so a prefix is a fair sample
SIZE_M, CELLS = 160.0, 320
CLIP_M = 12.0             # heights above ground are capped here: a tall tree should not outvote a roof
MAX_SHIFT_M = 25.0
MIN_SCORE = 0.3           # below this the peak is not trusted and the splat stays where the file puts it
VERSION = 1


def read_prefix(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Positions (n, 3) and opacities (n,) of the whole Gaussians in the first bytes of an INRIA splat PLY."""
    end = data.index(b"end_header\n") + 11
    props = [ln.split()[-1] for ln in data[:end].decode().splitlines() if ln.startswith("property float")]
    n = (len(data) - end) // (4 * len(props))
    a = np.frombuffer(data, "<f4", n * len(props), end).reshape(n, len(props))
    xyz = a[:, [props.index("x"), props.index("y"), props.index("z")]]
    op = 1 / (1 + np.exp(-a[:, props.index("opacity")])) if "opacity" in props else np.ones(n, np.float32)
    return xyz, op


def height_map(xy: np.ndarray, z: np.ndarray, bounds: tuple[float, float, float, float], shape: tuple[int, int]) -> np.ndarray:
    """Highest z per cell, row 0 north; NaN where no point fell."""
    west, south, east, north = bounds
    h, w = shape
    c = np.floor((xy[:, 0] - west) / (east - west) * w).astype(int)
    r = np.floor((north - xy[:, 1]) / (north - south) * h).astype(int)
    ok = (c >= 0) & (c < w) & (r >= 0) & (r < h)
    out = np.full(shape, np.nan, np.float32)
    order = np.argsort(z[ok])
    out[r[ok][order], c[ok][order]] = z[ok][order]  # written low to high, so the highest stays
    return out


def relief(hm: np.ndarray, ground: float) -> np.ndarray:
    """Height above ground, capped, zero where unknown, mean removed: what the correlation compares."""
    a = np.clip(np.nan_to_num(hm - ground, nan=0.0), 0, CLIP_M)
    return a - a.mean()


def best_shift(a: np.ndarray, b: np.ndarray, max_cells: int) -> tuple[int, int, float]:
    """(rows, cols, score): move b down by rows and right by cols to lie on a. Score is the normalised peak."""
    corr = np.fft.irfft2(np.fft.rfft2(a) * np.conj(np.fft.rfft2(b)), a.shape)
    h, w = a.shape
    dr, dc = np.meshgrid(np.fft.fftfreq(h, 1 / h), np.fft.fftfreq(w, 1 / w), indexing="ij")
    corr[(np.abs(dr) > max_cells) | (np.abs(dc) > max_cells)] = -np.inf
    i = np.unravel_index(np.argmax(corr), corr.shape)
    norm = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return int(dr[i]), int(dc[i]), float(corr[i] / norm)


def align(xyz: np.ndarray, dsm: dict, turns=np.arange(-12, 12.01, 1.0)) -> dict:
    """rot_deg and t (east, north, up) with  enu = Rz(rot_deg) p + t, up measured from the ground at the anchor."""
    bounds, shape = dsm["bounds_enu"], dsm["heights"].shape
    cell = (bounds[2] - bounds[0]) / shape[1]
    target = relief(dsm["heights"], dsm["ground_m"])
    near = np.hypot(xyz[:, 0], xyz[:, 1]) < SIZE_M
    xyz = xyz[near]
    ground = float(np.percentile(xyz[np.hypot(xyz[:, 0], xyz[:, 1]) < 35, 2], 8))

    def trial(deg: float) -> tuple[float, int, int]:
        c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
        xy = np.stack([xyz[:, 0] * c - xyz[:, 1] * s, xyz[:, 0] * s + xyz[:, 1] * c], 1)
        dr, dc, score = best_shift(target, relief(height_map(xy, xyz[:, 2], bounds, shape), ground), int(MAX_SHIFT_M / cell))
        return score, dr, dc

    coarse = max((trial(d) + (d,) for d in turns), key=lambda t: t[0])
    score, dr, dc, deg = max((trial(d) + (d,) for d in coarse[3] + np.arange(-0.75, 0.76, 0.25)), key=lambda t: t[0])
    return {"rot_deg": round(float(deg), 2), "t": [round(dc * cell, 2), round(-dr * cell, 2), round(-ground, 2)],
            "score": round(score, 3), "verified": bool(score >= MIN_SCORE), "method": "surface_model_correlation"}


def fit(sid: str, lat: float, lon: float) -> dict:
    """The cached fit for a scan's splat, computed when the splat is on disk. {state: ready | pending, ...}."""
    check(sid, "sid")
    f = cache_path("world", "splat_fit", f"{sid}.json")
    if f.exists():
        hit = json.loads(f.read_text())
        if hit.get("version") == VERSION:
            return hit
    ply = cache_path("splat", f"{sid}.ply")
    if not ply.exists():
        hackathon._ensure_splat(sid)  # starts the download the viewer needs anyway
        return {"state": "pending"}
    with open(ply, "rb") as fh:
        xyz, op = read_prefix(fh.read(PREFIX_BYTES))
    out = {"state": "ready", "version": VERSION,
           **align(xyz[op > 0.3], terrain.grid(lat, lon, SIZE_M, CELLS))}
    write_atomic(f, json.dumps(out).encode())
    return out
