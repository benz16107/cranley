"""Checks the cube-face layout in projection.py against real panoramas. Run: `python -m threshold.vision.verify SID...`.

1. Edge continuity: pixels just across each shared cube edge must match. This fixes how the up and down
   faces are turned relative to the side faces.
2. Doorways: every doorway of the panorama's room, projected through the panorama's rotation, must land
   on a door. This fixes the heading of face 1 relative to the rotation quaternion. Annotated images go
   to `$THRESHOLD_DATA_DIR/shots/perception/`.
"""
from __future__ import annotations

import io
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

from ..config import DATA
from ..sources import matterport as mp
from . import projection as pj
from .locate import floor_z

SHOTS = DATA / "shots" / "perception"


def faces(sid: str, pano: str, size: int = 512, view: str = "furnished") -> list[np.ndarray]:
    return [np.asarray(Image.open(io.BytesIO(mp.pano_face(sid, pano, f, "2k", view))).convert("RGB").resize((size, size)), float)
            for f in range(6)]


def sample(imgs: list[np.ndarray], d_cam: np.ndarray, layout) -> np.ndarray:
    size = imgs[0].shape[0]
    f, u, v = pj.cam_to_face_pixel(d_cam, size, layout)
    return imgs[f][min(size - 1, max(0, int(v))), min(size - 1, max(0, int(u)))]


def edge_error(imgs: list[np.ndarray], layout, gap: float = 2.0) -> float:
    """Mean colour difference across the 8 edges between side faces and the up/down faces."""
    size = imgs[0].shape[0]
    diffs = []
    for k in range(1, 5):
        for u in np.linspace(8, size - 8, 40):
            for v_in, v_out in ((gap, -gap), (size - gap, size + gap)):
                inside = imgs[k][int(min(size - 1, v_in)), int(u)]
                d_out = pj.face_pixel_to_cam(k, u, v_out, size, layout)
                diffs.append(np.abs(inside - sample(imgs, d_out, layout)).mean())
    return float(np.mean(diffs))


def calibrate_caps(imgs) -> list[tuple[float, float, float]]:
    """Every (up_top, down_top) choice ranked by edge error, for the current side-face heading."""
    f1 = pj.FACE1_YAW_DEG
    res = [(edge_error(imgs, (f1, ut, dt)), ut, dt) for ut in (0, 90, 180, 270) for dt in (0, 90, 180, 270)]
    return sorted(res)


# ---- doorways ---------------------------------------------------------------------------------

def opening_corners(plan: dict, op: dict) -> list[np.ndarray]:
    """The four 3D corners of an opening (bottom-left, bottom-right, top-right, top-left along its wall)."""
    wall = next(w for w in plan["walls"] if w["id"] == op["wall"])
    a, b = np.array(wall["a"], float), np.array(wall["b"], float)
    t = (b - a) / (np.linalg.norm(b - a) or 1)
    c = np.array(op["center"], float)
    z0 = floor_z(plan, op["floor"]) + (op.get("sill") or 0.0)
    z1 = z0 + (op.get("height") or 2.0)
    p0, p1 = c - t * op["width"] / 2, c + t * op["width"] / 2
    return [np.array([*p0, z0]), np.array([*p1, z0]), np.array([*p1, z1]), np.array([*p0, z1])]


def annotate_doorways(plan: dict, pano: dict, layout=None, size: int = 1024, path=None) -> tuple[Image.Image, int]:
    """Side faces 1-4 side by side with every doorway outline in the panorama's room drawn on."""
    imgs = [Image.open(io.BytesIO(mp.pano_face(plan["sid"], pano["id"], f, "2k"))).convert("RGB").resize((size, size))
            for f in range(1, 5)]
    strip = Image.new("RGB", (size * 4, size))
    for i, im in enumerate(imgs):
        strip.paste(im, (i * size, 0))
    draw = ImageDraw.Draw(strip)
    cam = np.array(pano["position"], float)
    ops = [o for o in plan["openings"] if o["type"] == "doorway" and pano.get("room") in o["rooms"]]
    drawn = 0
    for op in ops:
        pts = []
        for p in opening_corners(plan, op):
            f, u, v = pj.point_to_face_pixel(p, cam, size, pano["rotation"], layout)
            pts.append((f, u, v))
        # draw each corner on its face, and edges when both ends are on the same side face
        for (f0, u0, v0), (f1, u1, v1) in zip(pts, pts[1:] + pts[:1]):
            if f0 == f1 and 1 <= f0 <= 4:
                x = (f0 - 1) * size
                draw.line([(x + u0, v0), (x + u1, v1)], fill=(255, 40, 40), width=5)
        for f, u, v in pts:
            if 1 <= f <= 4:
                x = (f - 1) * size
                draw.ellipse([x + u - 9, v - 9, x + u + 9, v + 9], outline=(255, 230, 0), width=4)
        drawn += 1
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        strip.resize((size * 2, size // 2)).save(path, quality=85)
    return strip, drawn


def main(sids: list[str]) -> None:
    from ..config import DATA as D
    for sid in sids:
        plan = json.loads((D / "fixtures" / "scanplan" / f"{sid}.json").read_text())
        pano = next(p for p in plan["panos"] if p.get("room") and p.get("rotation") and any(
            o["type"] == "doorway" and p["room"] in o["rooms"] for o in plan["openings"]))
        imgs = faces(sid, pano["id"])
        print(sid, pano["id"], "cap layouts (error, up_top, down_top):", [tuple(round(x, 1) for x in r) for r in calibrate_caps(imgs)[:3]])
        _, n = annotate_doorways(plan, pano, path=SHOTS / f"doorways_{sid}.jpg")
        print("  wrote", n, "doorways to", SHOTS / f"doorways_{sid}.jpg")
        if "--sweep" in sys.argv:  # every face-1 heading, to see the three that miss
            for f1 in (0, 90, 180, 270):
                annotate_doorways(plan, pano, (f1, pj.UP_TOP_YAW_DEG, pj.DOWN_TOP_YAW_DEG),
                                  path=SHOTS / "calibrate" / f"{sid}_{pano['id']}_f1_{f1}.jpg")


if __name__ == "__main__":
    sids = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not sids:
        sys.exit("usage: python -m threshold.vision.verify SID [SID ...] [--sweep]  (fixture scan ids)")
    main(sids)
