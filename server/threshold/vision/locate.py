"""Turn a detection (a box on a cube face) into Contract 3 anchors.

Every detection gets a direction anchor `{sid, pano, yaw_deg, pitch_deg}`, exact up to the box. Where the
room's shell is known, it also gets a 3D point: the ray through the bottom centre of the box (where an
object meets the floor, the wall it hangs on, or the ceiling it is fixed to) is intersected with the
room's walls, floor and ceiling. A free-standing object in the middle of a room is not on the shell, so
its point is where its base meets the floor only if the base is visible.
"""
from __future__ import annotations

import statistics

import numpy as np

from . import projection as pj

DEFAULT_HEIGHT_M = 2.5


def floor_z(plan: dict, floor: str | None) -> float:
    """Floor elevation in the scan frame. Panoramas sit at camera height above their floor and the lowest
    floor is at z = 0 in every fixture we checked, so a floor is its panoramas' median z minus the lowest
    floor's median z (assumes one camera height per scan)."""
    zs: dict[str, list[float]] = {}
    for p in plan["panos"]:
        zs.setdefault(p["floor"], []).append(p["position"][2])
    if not zs:
        return 0.0
    seq = {f["id"]: f["sequence"] for f in plan["floors"]}
    base = statistics.median(zs[min(zs, key=lambda f: seq.get(f, 0))])
    return statistics.median(zs.get(floor, [base])) - base


def _segments(plan: dict, room: dict) -> list[tuple[np.ndarray, np.ndarray]]:
    walls = {w["id"]: w for w in plan["walls"]}
    segs = [(np.array(walls[w]["a"], float), np.array(walls[w]["b"], float)) for w in room.get("walls") or [] if w in walls]
    if not segs and len(room.get("polygon") or []) >= 3:
        poly = [np.array(p, float) for p in room["polygon"]]
        segs = list(zip(poly, poly[1:] + poly[:1]))
    return segs


def intersect_room(plan: dict, pano: dict, d_scan: np.ndarray) -> tuple[np.ndarray, str, str] | None:
    """Nearest hit of the ray from the panorama along `d_scan` with its room: (point, surface, confidence).
    surface is "wall", "floor" or "ceiling"."""
    room = next((r for r in plan["rooms"] if r["id"] == pano.get("room")), None)
    o = np.array(pano["position"], float)
    d = np.asarray(d_scan, float) / np.linalg.norm(d_scan)
    z0 = floor_z(plan, pano.get("floor"))
    h = (room or {}).get("height") or None
    z1 = z0 + (h or DEFAULT_HEIGHT_M)
    hits: list[tuple[float, str]] = []
    if d[2] < -1e-6:
        hits.append(((z0 - o[2]) / d[2], "floor"))
    if d[2] > 1e-6:
        hits.append(((z1 - o[2]) / d[2], "ceiling"))
    segs = _segments(plan, room) if room else []
    for a, b in segs:
        # solve o.xy + t d.xy = a + s (b - a)
        e = b - a
        m = np.array([[d[0], -e[0]], [d[1], -e[1]]])
        if abs(np.linalg.det(m)) < 1e-9:
            continue
        t, s = np.linalg.solve(m, a - o[:2])
        if t > 1e-6 and -1e-3 <= s <= 1 + 1e-3 and z0 - 0.05 <= o[2] + t * d[2] <= z1 + 0.05:
            hits.append((t, "wall"))
    hits = [x for x in hits if x[0] > 1e-6]
    if not hits:
        return None
    t, surface = min(hits)
    shell_known = bool(segs) and h is not None
    if surface == "wall" and not segs:
        return None
    if surface == "ceiling" and h is None:
        return None  # ceiling height assumed, so the point would be invented
    return o + t * d, surface, "medium" if shell_known else "low"


def locate(plan: dict, pano: dict, face: int, box: list[float], size: int) -> dict:
    """box = [x0, y0, x1, y1] in pixels of a face `size` pixels across. Returns
    {anchor (pano direction), point_anchor | None, surface, confidence, distance_m}."""
    x0, y0, x1, y1 = box
    rot = pano.get("rotation")
    centre = pj.face_pixel_to_scan(face, (x0 + x1) / 2, (y0 + y1) / 2, size, rot)
    yaw, pitch = pj.yaw_pitch(centre)
    out = {"anchor": {"sid": plan["sid"], "pano": pano["id"], "yaw_deg": round(yaw, 2), "pitch_deg": round(pitch, 2)},
           "point_anchor": None, "surface": None, "confidence": None, "distance_m": None}
    # Faces 0 and 5 look straight up or down: there the box centre is the contact point.
    base = centre if face in (0, 5) else pj.face_pixel_to_scan(face, (x0 + x1) / 2, y1, size, rot)
    hit = intersect_room(plan, pano, base)
    if hit:
        p, surface, conf = hit
        out.update(point_anchor={"sid": plan["sid"], "point": [round(float(c), 3) for c in p]}, surface=surface,
                   confidence=conf, distance_m=round(float(np.linalg.norm(p - np.array(pano["position"]))), 2))
    return out
