"""A scan's sweeps as COLMAP training views: six 90 degree pinhole faces per sweep, posed from the Model API.

Pose of a face. `vision.projection` measured the face layout: face k's (forward, right, down) image axes in the
panorama's camera frame are `face_basis(k)`, and the sweep's `rotation` turns camera-frame directions into the scan
frame. COLMAP wants world-to-camera with camera x right, y down, z forward, so its rotation's rows are those three
axes in the scan frame, and a pixel (u, v) of an n-pixel face looks along forward + (2u/n - 1) right + (2v/n - 1)
down: fx = fy = cx = cy = n / 2.

Held-out sweeps. Brush sorts images by name and evaluates on every `period`-th one (index % period == 0). Names
carry a running number, and the faces of every held-out sweep are placed on exactly those indices, so the PSNR
Brush reports is on sweeps it never trained on. Training faces left over are dropped, down faces first (the floor
under the tripod, which Matterport blurs).
"""
from __future__ import annotations

import io
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from ..sources import matterport as mp
from ..vision.projection import face_basis, quat_matrix
from . import ROOT, seed, virtual

FACES = range(6)
MIN_VALID = 0.2  # a virtual view with less of its pixels valid is left out


def face_pose(position, rotation, face: int) -> tuple[np.ndarray, np.ndarray]:
    """(R, t) world-to-camera in COLMAP's convention for one cube face of a sweep."""
    R_pano = quat_matrix(rotation)
    fwd, right, down = (R_pano @ a for a in face_basis(face))
    R = np.stack([right, down, fwd])
    return R, -R @ np.asarray(position, float)


def rot_to_qvec(R: np.ndarray) -> np.ndarray:
    """Rotation matrix to COLMAP's (w, x, y, z), w >= 0."""
    m = R
    t = np.trace(m)
    if t > 0:
        s = 2 * np.sqrt(t + 1)
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    else:
        i = int(np.argmax(np.diag(m)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = 2 * np.sqrt(1 + m[i, i] - m[j, j] - m[k, k])
        q = np.zeros(4)
        q[0] = (m[k, j] - m[j, k]) / s
        q[1 + i] = 0.25 * s
        q[1 + j] = (m[j, i] + m[i, j]) / s
        q[1 + k] = (m[k, i] + m[i, k]) / s
    q = np.asarray(q, float)
    q /= np.linalg.norm(q)
    return q if q[0] >= 0 else -q


def order(panos: list[str], every: int, extra: list[tuple[str, int]] = ()) -> tuple[list[tuple[str, int]], int, set[str]]:
    """Image order (pano, face) and the eval period that puts held-out sweeps' faces on index % period == 0.
    Holds out every `every`-th sweep; `every` 0 holds out none (period 0). `extra` items only ever train."""
    held = held_out(panos, every)
    ev = [(p, f) for p in panos if p in held for f in FACES]
    tr = [(p, f) for p in panos if p not in held for f in FACES] + list(extra)
    if not ev:
        return tr, 0, held
    period = len(tr) // len(ev) + 1
    spare = len(tr) - len(ev) * (period - 1)
    drop = set(sorted(tr, key=lambda pf: (pf[1] != 5, pf))[:spare])  # down faces go first
    tr = [x for x in tr if x not in drop]
    out = []
    for k, e in enumerate(ev):
        out += [e, *tr[k * (period - 1):(k + 1) * (period - 1)]]
    return out, period, held


def held_out(panos: list[str], every: int) -> set[str]:
    return set(panos[every // 2::every]) if every else set()


def _line(i: int, R: np.ndarray, t: np.ndarray, cam: int, name: str) -> str:
    q = rot_to_qvec(R)
    return f"{i + 1} {' '.join(f'{v:.9f}' for v in q)} {' '.join(f'{v:.6f}' for v in t)} {cam} {name}\n\n"


def build(sid: str, res: int = 1024, every: int = 8, view: str = "furnished", workers: int = 4,
          virtual_views: bool = True, virtual_res: int = 512) -> dict:
    """Write images/, masks/ (virtual views only), sparse/0/{cameras,images,points3D}.txt and dataset.json under
    splat/<sid>/dataset/. Returns the summary."""
    plan = mp.plan(sid)
    panos = sorted(p["id"] for p in plan["panos"] if p.get("rotation"))
    by_id = {p["id"]: p for p in plan["panos"]}
    out = dataset_dir(sid)
    img_dir, mask_dir, sparse = out / "images", out / "masks", out / "sparse" / "0"
    for d in (img_dir, mask_dir):
        shutil.rmtree(d, ignore_errors=True)
    img_dir.mkdir(parents=True)
    sparse.mkdir(parents=True, exist_ok=True)

    def face(pf):  # cached on disk by sources.matterport; the upstream rate limit is process-wide
        p, f = pf
        return pf, Image.open(io.BytesIO(mp.pano_face(sid, p, f, "2k", view))).convert("RGB")

    small: dict[tuple[str, int], np.ndarray] = {}
    mid: dict[tuple[str, int], np.ndarray] = {}
    with ThreadPoolExecutor(workers) as ex:
        for pf, im in ex.map(face, [(p, f) for p in panos for f in FACES]):
            small[pf] = np.asarray(im.resize((seed.FACE_PX, seed.FACE_PX), Image.BOX))
            if virtual_views:
                mid[pf] = np.asarray(im.resize((virtual_res, virtual_res), Image.BOX))

    held = held_out(panos, every)
    cams, T, src = [], None, None
    if virtual_views:
        try:
            T = virtual.subdivide(seed.mesh_triangles(sid, plan, {p: by_id[p] for p in panos}))
        except LookupError:
            T = None  # no mesh, no depth: real views only
        if T is not None:
            train_ids = {p: by_id[p] for p in panos if p not in held}
            src = virtual.Sources(T, train_ids, {k: v for k, v in mid.items() if k[0] in train_ids})
            cams = virtual.cameras(src, train_ids, np.random.default_rng(0))
    vcam = {f"{p}-v": (c, R) for p, c, R in cams}
    views = {}  # rendered before ordering: a view with almost nothing valid is dropped (Brush fails to load one)
    for k, (c, Rv) in vcam.items():
        for f in (1, 2, 3, 4):
            img, m = virtual.render(T, src, c, Rv, f, virtual_res, exclude=k[:-2])
            if m.mean() >= MIN_VALID:
                views[(k, f)] = (img, m)
    seq, period, held = order(panos, every, list(views))

    lines, masked = [], []
    for i, (p, f) in enumerate(seq):
        name = f"{i:05d}_{p}_{f}"
        if (p, f) in views:
            img, m = views[(p, f)]
            mask_dir.mkdir(exist_ok=True)
            Image.fromarray(img).save(img_dir / f"{name}.jpg", quality=94)
            Image.fromarray((m * 255).astype(np.uint8)).save(mask_dir / f"{name}.png")
            masked.append(float(m.mean()))
            lines.append(_line(i, *virtual._pose(*vcam[p], f), 2, f"{name}.jpg"))
        else:
            face((p, f))[1].resize((res, res), Image.LANCZOS).save(img_dir / f"{name}.jpg", quality=94)
            lines.append(_line(i, *face_pose(by_id[p]["position"], by_id[p]["rotation"], f), 1, f"{name}.jpg"))
    h = virtual_res / 2
    (sparse / "cameras.txt").write_text(f"1 PINHOLE {res} {res} {res / 2} {res / 2} {res / 2} {res / 2}\n"
                                        f"2 PINHOLE {virtual_res} {virtual_res} {h} {h} {h} {h}\n")
    (sparse / "images.txt").write_text("".join(lines))

    pts, cols, source = seed.points(sid, plan, {p: by_id[p] for p in panos}, small)
    with open(sparse / "points3D.txt", "w") as fh:
        for i, (x, c) in enumerate(zip(pts, cols)):
            fh.write(f"{i + 1} {x[0]:.4f} {x[1]:.4f} {x[2]:.4f} {c[0]} {c[1]} {c[2]} 0\n")
    summary = {"sid": sid, "res": res, "view": view, "images": len(seq), "sweeps": len(panos),
               "virtual_views": len(masked), "virtual_valid": round(float(np.mean(masked)), 3) if masked else None,
               "eval_period": period, "held_out": sorted(held), "seed_points": len(pts), "seed_source": source}
    (out / "dataset.json").write_text(json.dumps(summary, indent=1))
    return summary


def dataset_dir(sid: str) -> Path:
    """Brush reads every file under this folder (a lone .ply there becomes its starting point), so outputs live beside it."""
    return ROOT / sid / "dataset"
