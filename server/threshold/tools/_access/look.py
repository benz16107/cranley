"""What the panoramas say, through threshold.vision. Every answer is a label or a class, never a number; the
model's answers are cached on disk by the vision engine, so a re-run costs nothing."""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageDraw

from ...sources import matterport as mp
from ...vision import projection as pj
from ...vision.model import CONFIDENCE, ask, jpeg
from ...vision.reader import find_objects, room_panos

FACE_PX = 1000
DOORWAY_SEEN = ["doorway a person can walk through", "opening too narrow for a person", "no opening, wall or furniture",
                "cannot tell from this view"]
DOOR_KIND = ["hinged door", "sliding or pocket door", "double door", "open archway or passage", "garage door",
             "no door leaf", "cannot tell"]
BATHING = ["bathtub with shower", "bathtub only", "shower with a curb or step-in lip", "curbless walk-in shower",
           "no tub or shower visible", "cannot tell"]
BARS = ["at the toilet", "at the tub or shower", "at both", "none visible", "cannot tell"]


def _err(e: Exception) -> str:
    return f"the panorama reader failed ({type(e).__name__}); nothing was read from the panoramas"


def objects(plan: dict, panos: list[str]) -> tuple[list[dict], str | None]:
    """find_objects on these panoramas with the reader's default labels (so its cached answers are reused)."""
    if not panos:
        return [], None
    try:
        return find_objects(plan, None, panos=panos, max_panos=len(panos)), None
    except Exception as e:  # the model endpoint is shared and may be down: say so, do not crash the tool
        return [], _err(e)


def central_pano(plan: dict, room: dict) -> dict | None:
    ps = room_panos(plan, room)
    return ps[0] if ps else None


def _corners(plan: dict, op: dict) -> list[np.ndarray]:
    wall = next(w for w in plan["walls"] if w["id"] == op["wall"])
    a, b = np.array(wall["a"], float), np.array(wall["b"], float)
    t = (b - a) / (np.linalg.norm(b - a) or 1)
    c = np.array(op["center"], float)
    half = max(op.get("width") or 0, 0.1) / 2
    z0 = op["sill"] if op.get("sill") is not None else 0.0   # sills are absolute scan z
    z1 = z0 + (op.get("height") or 2.0)
    return [np.array([*(c - t * half), z0]), np.array([*(c + t * half), z0]), np.array([*(c + t * half), z1]),
            np.array([*(c - t * half), z1])]


def _view(plan: dict, op: dict) -> tuple[dict, int, list[tuple[float, float]]] | None:
    """The panorama that sees the doorway best: in one of its rooms, 1 to 6 m away, nearest first."""
    c = np.array(op["center"], float)
    cands = [p for p in plan.get("panos") or [] if p.get("rotation") and p.get("floor") == op["floor"]]
    cands = [p for p in cands if 0.8 <= math.dist(p["position"][:2], c) <= 6.0]
    cands.sort(key=lambda p: (p.get("room") not in (op.get("rooms") or []), math.dist(p["position"][:2], c)))
    corners = _corners(plan, op)
    for p in cands[:4]:
        mid = (corners[0] + corners[2]) / 2
        face, _, _ = pj.point_to_face_pixel(mid, p["position"], FACE_PX, p["rotation"])
        if not 1 <= face <= 4:
            continue
        pts = [(u, v) for f, u, v in (pj.point_to_face_pixel(q, p["position"], FACE_PX, p["rotation"])
                                      for q in corners) if f == face]
        if pts:
            return p, face, pts
    return None


def doorway(plan: dict, op: dict) -> dict:
    """Ask the panorama what is at a doorway whose recorded width is implausible. Returns {seen, door, confidence,
    media, pano} or {error}. The red box on the image is where the wall graph puts the opening."""
    v = _view(plan, op)
    if v is None:
        return {"error": "no panorama looks at this doorway from 1 to 6 m away"}
    pano, face, pts = v
    try:
        img = Image.open(io.BytesIO(jpeg(mp.pano_face(plan["sid"], pano["id"], face, "2k"), FACE_PX))).convert("RGB")
    except Exception as e:
        return {"error": _err(e)}
    us, vs = [u for u, _ in pts], [v for _, v in pts]
    box = [max(0, min(us) - 25), max(0, min(vs) - 25), min(FACE_PX, max(us) + 25), min(FACE_PX, max(vs) + 25)]
    ImageDraw.Draw(img).rectangle(box, outline=(255, 0, 0), width=5)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    schema = {"type": "object", "additionalProperties": False, "required": ["seen", "door", "confidence", "reason"],
              "properties": {"seen": {"type": "string", "enum": DOORWAY_SEEN},
                             "door": {"type": "string", "enum": DOOR_KIND}, "confidence": CONFIDENCE,
                             "reason": {"type": "string", "description": "One short sentence naming what you saw."}}}
    prompt = ("This is one face of a 360-degree panorama inside a home, 1000 by 1000 pixels. The red rectangle marks "
              "where the floor plan records a doorway. Look inside and right around the red rectangle. What is there, "
              "and what kind of door, if any? Do not estimate any size.")
    try:
        a = ask([buf.getvalue()], prompt, schema, key=f"access_doorway/{plan['sid']}/{op['id']}")
    except Exception as e:
        return {"error": _err(e)}
    return {**a, "pano": pano["id"], "face": face,
            "media": [{"kind": "pano", "ref": f"{plan['sid']}/{pano['id']}/{face}",
                       "box": [round(x / FACE_PX, 4) for x in box]}]}


def bath_fixtures(plan: dict, room: dict) -> dict:
    """The bathing fixture type and visible grab bars in a bathroom, from its central panorama."""
    pano = central_pano(plan, room)
    if pano is None:
        return {"error": "no panorama in this bathroom"}
    faces = [1, 2, 3, 4, 5]
    try:
        imgs = [jpeg(mp.pano_face(plan["sid"], pano["id"], f, "2k"), 768) for f in faces]
    except Exception as e:
        return {"error": _err(e)}
    schema = {"type": "object", "additionalProperties": False,
              "required": ["bathing", "grab_bars", "toilet", "confidence", "image", "reason"],
              "properties": {"bathing": {"type": "string", "enum": BATHING},
                             "grab_bars": {"type": "string", "enum": BARS},
                             "toilet": {"type": "boolean", "description": "A toilet is visible in this room"},
                             "confidence": CONFIDENCE, "image": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                             "reason": {"type": "string", "description": "One short sentence naming what you saw."}}}
    prompt = ("These are five faces of one 360-degree cube panorama taken inside a bathroom: images 1 to 4 look "
              "horizontally, each turned 90 degrees right of the one before, and image 5 looks straight down. "
              "What bathing fixture is in this bathroom (a shower with any curb or lip to step over is not curbless)? "
              "Are grab bars installed, and where? Is a toilet visible? Name the image that shows the bathing fixture "
              "best. Towel bars are not grab bars.")
    try:
        a = ask(imgs, prompt, schema, key=f"access_bath/{plan['sid']}/{pano['id']}")
    except Exception as e:
        return {"error": _err(e)}
    return {**a, "pano": pano["id"], "media": [{"kind": "pano", "ref": f"{plan['sid']}/{pano['id']}/{faces[a['image'] - 1]}"}]}
