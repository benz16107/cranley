"""Train with Brush (github.com/ArthurBrussee/brush, Apache-2.0, run as an external binary on wgpu/Vulkan), score the
held-out sweeps, and publish `interior.spz`, `interior.ply` and `interior.json` under splat/<sid>/.

Brush renders the held-out faces itself (`--eval-save-to-disk`); PSNR is computed here against the same faces the
dataset wrote, so it is on sweeps the model never saw.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

from ..sources import matterport as mp
from . import ROOT, carve, dataset, seed, spz, virtual

BRUSH = os.environ.get("BRUSH_BIN", str(Path.home() / ".local/share/brush-dl/brush-app-x86_64-unknown-linux-gnu/brush_app"))
BRUSH_VERSION = "0.3.0"
SHOTS = ROOT.parent / "shots" / "splat"
REFINE = 2000  # steps after the outer shell is cut
GROWTH_STOP = 0.7  # of the steps; splats stop multiplying after this, so the last phase only refines
IDENTITY = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _brush(d: Path, out: Path, meta: dict, start: int, end: int, sh_degree: int, max_splats: int, eval_every: int,
           growth_stop: int) -> None:
    cmd = [BRUSH, str(d), "--start-iter", str(start), "--total-steps", str(end), "--max-resolution", str(meta["res"]),
           "--sh-degree", str(sh_degree), "--max-splats", str(max_splats), "--growth-stop-iter", str(growth_stop),
           "--export-every", str(end), "--export-path", str(out), "--export-name", f"phase_{end}.ply"]
    if meta["eval_period"]:
        cmd += ["--eval-split-every", str(meta["eval_period"]), "--eval-every", str(eval_every), "--eval-save-to-disk"]
    with open(out / "brush.log", "a") as log:
        subprocess.run(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True)


def run(sid: str, steps: int = 10000, sh_degree: int = 2, max_splats: int = 1_500_000, phases: int = 1,
        refine: int = REFINE) -> dict:
    """Train in `phases` Brush runs; after each, carve the free-space splats and the ones outside the building, and
    start the next from what is left. Then `refine` more steps without growth, so surfaces that leaned on the cut
    outer shell turn opaque, and one last carve. A one-step run scores what ships on the held-out sweeps."""
    root, d = ROOT / sid, dataset.dataset_dir(sid)
    meta = json.loads((d / "dataset.json").read_text())
    plan = mp.plan(sid)
    panos = {p["id"]: p for p in plan["panos"] if p.get("rotation")}
    sweeps = [p for k, p in panos.items() if k not in set(meta["held_out"])]  # never the held-out sweeps
    try:
        T = virtual.subdivide(seed.mesh_triangles(sid, plan, panos))
    except LookupError:
        T = None  # no mesh: no free-space carve, only the building crop
    out = root / f"run_{steps}"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    init = d / "init.ply"
    init.unlink(missing_ok=True)
    t0, carved = time.time(), []
    ends = [round(steps * (i + 1) / phases) for i in range(phases)]
    runs = [(s, e, e - s, round(steps * GROWTH_STOP)) for s, e in zip([0, *ends], ends)]
    if refine:
        runs.append((steps, steps + refine, refine, 0))
    for start, end, every, growth in runs:
        _brush(d, out, meta, start, end, sh_degree, max_splats, every, growth)
        cols = spz.read_ply(out / f"phase_{end}.ply")
        xyz = np.stack([cols["x"], cols["y"], cols["z"]], 1)
        drop = carve.outside(xyz, plan)
        if T is not None:
            drop |= carve.free_space(xyz, T, sweeps)
        carved.append({"step": end, "splats": len(drop), "removed": int(drop.sum())})
        spz.write_ply(init, {k: v[~drop] for k, v in cols.items()})
    last = runs[-1][1]
    shutil.move(init, out / "carved.ply")
    if meta["eval_period"]:  # score exactly what ships: start from the carved splats, one step, eval and export
        spz.write_ply(init, spz.read_ply(out / "carved.ply"))
        _brush(d, out, meta, last, last + 1, sh_degree, max_splats, 1, 0)
        init.unlink()
        shutil.move(out / f"phase_{last + 1}.ply", out / "final.ply")
    else:
        shutil.move(out / "carved.ply", out / "final.ply")
    return publish(sid, out, last, sh_degree, max_splats, round(time.time() - t0), phases, carved)


def publish(sid: str, out: Path, steps: int, sh_degree: int, max_splats: int, seconds: int, phases: int,
            carved: list) -> dict:
    """Score a finished run folder (final.ply and eval_*/), and write interior.spz, .ply and .json beside the dataset."""
    root, d = ROOT / sid, dataset.dataset_dir(sid)
    meta = json.loads((d / "dataset.json").read_text())
    scores = {int(p.name.split("_")[1]): psnr_dir(p, d / "images") for p in sorted(out.glob("eval_*"))}
    last = scores.get(max(scores)) if scores else None
    sbs = side_by_side(sid, out / f"eval_{max(scores)}", d / "images") if scores else []

    n = spz.ply_to_spz(out / "final.ply", root / "interior.spz")
    shutil.copyfile(out / "final.ply", root / "interior.ply")
    cols = spz.read_ply(root / "interior.ply")
    xyz = np.stack([cols["x"], cols["y"], cols["z"]], 1)
    side = {
        "schema": "interior-splat/1", "sid": sid,
        "frame": "scanplan", "units": "m", "up": "+z",
        "transform": [v for row in IDENTITY for v in row],  # what the viewer reads (web/src/world/InteriorSplat.ts)
        "to_scanplan": IDENTITY,
        "convention": "Splat positions are ScanPlan scan-frame metres (x, y on the floor, z up); transform (16 numbers, "
                      "row by row) and to_scanplan (the same as a 4x4) take splat coordinates to the scan frame. No axis flip in the .spz or the .ply. "
                      "Place in the world with the plan's geo (ENU = Rz(yaw) p + translation).",
        "files": {"spz": {"url": f"/api/scan/{sid}/interior-splat", "bytes": (root / "interior.spz").stat().st_size},
                  "ply": {"url": f"/api/scan/{sid}/interior-splat?format=ply", "bytes": (root / "interior.ply").stat().st_size}},
        "splats": n, "sh_degree": sh_degree,
        "bounds": {"min": np.percentile(xyz.astype(float), 1, 0).round(3).tolist(),
                   "max": np.percentile(xyz.astype(float), 99, 0).round(3).tolist()},
        "trainer": {"name": "brush", "version": BRUSH_VERSION, "licence": "Apache-2.0", "steps": steps,
                    "resolution": meta["res"], "max_splats": max_splats, "seconds": seconds,
                    "phases": phases, "carved": carved},
        "data": {"sweeps": meta["sweeps"], "images": meta["images"], "view": meta["view"],
                 "seed": {"source": meta["seed_source"], "points": meta["seed_points"]}},
        "eval": {"held_out_sweeps": meta["held_out"], "psnr_by_step": {str(k): v["mean"] for k, v in scores.items()},
                 "psnr": last["mean"] if last else None,
                 "psnr_indoor": indoor_psnr(sid, last["per_view"]) if last else None, "per_view": last["per_view"] if last else {},
                 "side_by_side": [str(p) for p in sbs], "reliability": "medium",
                 "note": "PSNR on cube faces of sweeps left out of training; renders sit at the sweep's own position, "
                         "so views far from any sweep are not measured."},
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (root / "interior.json").write_text(json.dumps(side, indent=1))
    return side


def indoor_psnr(sid: str, per_view: dict) -> float | None:
    """Mean PSNR over held-out sweeps standing inside the building: outdoor sweeps look at what the crop leaves
    to the drone splat, so they score low by design."""
    plan = mp.plan(sid)
    pos = {p["id"]: p["position"] for p in plan["panos"]}
    ids = sorted({k.split("_")[1] for k in per_view})
    inside = {i for i, out in zip(ids, carve.outside(np.array([pos[i] for i in ids], float), plan)) if not out}
    vals = [v for k, v in per_view.items() if k.split("_")[1] in inside]
    return round(float(np.mean(vals)), 2) if vals else None


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float(10 * np.log10(255 ** 2 / max(mse, 1e-10)))


def _pair(render: Path, images: Path) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(Image.open(render).convert("RGB"))
    b = np.asarray(Image.open(images / f"{render.stem}.jpg").convert("RGB").resize(a.shape[1::-1]))
    return a, b


def psnr_dir(evals: Path, images: Path) -> dict:
    per = {p.stem: round(psnr(*_pair(p, images)), 2) for p in sorted(evals.glob("*.png"))}
    return {"mean": round(float(np.mean(list(per.values()))), 2), "per_view": per}


def side_by_side(sid: str, evals: Path, images: Path) -> list[Path]:
    """One image per held-out sweep: its four horizon faces rendered (top) over the real panorama faces (bottom)."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    by_pano: dict[str, dict[int, Path]] = {}
    for p in evals.glob("*.png"):
        _, pano, face = p.stem.split("_")
        by_pano.setdefault(pano, {})[int(face)] = p
    out = []
    for pano, faces in sorted(by_pano.items()):
        if not all(k in faces for k in (1, 2, 3, 4)):
            continue
        pairs = [_pair(faces[k], images) for k in (1, 2, 3, 4)]
        grid = np.vstack([np.hstack([a for a, _ in pairs]), np.hstack([b for _, b in pairs])])
        f = SHOTS / f"{sid}_{pano}_render_vs_pano.jpg"
        Image.fromarray(grid).resize((grid.shape[1] // 2, grid.shape[0] // 2), Image.LANCZOS).save(f, quality=88)
        out.append(f)
    return out
