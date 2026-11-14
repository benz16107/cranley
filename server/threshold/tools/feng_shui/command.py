"""The command position: where a bed or desk sees the room's door without sitting in line with it, with a solid
wall behind. Found by sliding the piece along every opening-free wall run in the room. Pure geometry."""
from __future__ import annotations

import math

from shapely.geometry import LineString, Point, Polygon

from ...geometry import free_wall_runs
from ...geometry._plan import polygons, rooms_by_id
from ...geometry.georef import azimuth_of
from .bagua import inward
from .kua import compass8

BEDS = {"twin": (0.97, 1.91), "full": (1.37, 1.91), "queen": (1.52, 2.03), "king": (1.93, 2.03)}
DESK = (1.2, 0.6)          # a common desk top
CHAIR_M = 0.8              # room for the chair between the desk and the wall behind the sitter
STEP_M = 0.1
WALL_GAP_M = 0.06          # from the wall's centre line to the back of the piece
VIEW_MAX_DEG = 75          # the door is within this angle of straight ahead: seen without turning round
SWING_EXTRA_M = 0.2        # keep this much clear past a door's swing
SOFT_WALLS = ("Bathroom", "Toilet", "Laundry", "Kitchen")   # a headboard against these is a common note
SKIP_DOORS = ("Closet",)


def doors_of(plan: dict, room_id: str, links: list[dict]) -> list[dict]:
    """Doorways and openings of a room with the room on the far side; the entry door (to a hall or living
    space, the widest) first. Closet doors are left out."""
    rooms = rooms_by_id(plan)
    out = []
    for link in links:
        if room_id not in (link.get("rooms") or [link.get("room")]) or link["kind"] == "invisible":
            continue
        other = next((r for r in link.get("rooms") or [] if r != room_id), None)
        lab = (rooms.get(other) or {}).get("label")
        if lab in SKIP_DOORS:
            continue
        out.append(link | {"to": other, "to_label": lab})
    return sorted(out, key=lambda d: (d["to_label"] in ("Bathroom", "Toilet"), -(d.get("width") or 0)))


def _rect(a, u, n, s, off, w, d) -> Polygon:
    p = (a[0] + u[0] * s + n[0] * off, a[1] + u[1] * s + n[1] * off)
    return Polygon([p, (p[0] + u[0] * w, p[1] + u[1] * w), (p[0] + u[0] * w + n[0] * d, p[1] + u[1] * w + n[1] * d),
                    (p[0] + n[0] * d, p[1] + n[1] * d)])


def _angle(a, b) -> float:
    dot = (a[0] * b[0] + a[1] * b[1]) / ((math.hypot(*a) * math.hypot(*b)) or 1)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def place(plan: dict, room_id: str, piece: str, size: tuple[float, float], links: list[dict], walls: dict,
          good_dirs: set[str] | None = None) -> dict:
    """Best spot for a bed (head to the wall) or a desk (sitter's back to the wall) in one room.
    {available, ok, center, yaw_deg, size, head_az, face_az, rules: {view, not_in_line, solid_wall}, ...}."""
    poly = polygons(plan).get(room_id)
    if poly is None:
        return {"available": False, "reason": "This room has no outline in the scan."}
    doors = doors_of(plan, room_id, links)
    if not doors:
        return {"available": False, "reason": "The scan shows no door into this room."}
    runs = free_wall_runs(plan, room_id)
    if not runs["available"]:
        return {"available": False, "reason": runs["reason"]}
    w, d = size
    depth = d + (CHAIR_M if piece == "desk" else 0.0)
    inside = poly.buffer(-0.04)
    door_info = []
    for dr in doors:
        m = inward(plan, {"wall": dr["wall"], "center": dr["center"]}, room_id, walls)
        c, dw = dr["center"], dr.get("width") or 0.8
        wall = walls.get(dr["wall"])
        ux, uy = ((wall["b"][0] - wall["a"][0]), (wall["b"][1] - wall["a"][1])) if wall else (-m[1], m[0])
        ul = math.hypot(ux, uy) or 1
        ux, uy = ux / ul, uy / ul
        swing = _rect((c[0] - ux * dw / 2, c[1] - uy * dw / 2), (ux, uy), m, 0, 0, dw, dw + SWING_EXTRA_M)
        corridor = _rect((c[0] - ux * dw / 2, c[1] - uy * dw / 2), (ux, uy), m, 0, 0, dw, 30.0)
        door_info.append({"door": dr, "in": m, "swing": swing, "corridor": corridor})
    main = door_info[0]
    best, best_key = None, None
    for run in runs["runs"]:
        a, b = run["a"], run["b"]
        length = run["length"]
        if length + 2 * WALL_GAP_M < w - 0.05:
            continue
        u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        n = (-u[1], u[0])
        if not poly.contains(Point(mid[0] + 0.3 * n[0], mid[1] + 0.3 * n[1])):
            n = (-n[0], -n[1])
        steps = max(0, int((length - w) / STEP_M))
        for k in range(steps + 1):
            s = k * STEP_M if steps else (length - w) / 2
            foot = _rect(a, u, n, s, WALL_GAP_M, w, depth)
            if not foot.within(inside) or any(foot.intersects(di["swing"]) for di in door_info):
                continue
            sit = 0.3 if piece == "bed" else 0.45   # the pillow, or the sitter's eyes, out from the wall
            eye = (a[0] + u[0] * (s + w / 2) + n[0] * (WALL_GAP_M + sit), a[1] + u[1] * (s + w / 2) + n[1] * (WALL_GAP_M + sit))
            dc = main["door"]["center"]
            to_door = (dc[0] - eye[0], dc[1] - eye[1])
            angle = _angle(n, to_door)
            seen = angle <= VIEW_MAX_DEG and LineString([eye, (dc[0] + main["in"][0] * 0.1, dc[1] + main["in"][1] * 0.1)]).within(poly.buffer(0.02))
            in_line = [di["door"]["id"] for di in door_info if foot.intersects(di["corridor"])]
            behind = (a[0] + u[0] * (s + w / 2) - n[0] * 0.3, a[1] + u[1] * (s + w / 2) - n[1] * 0.3)
            back_room = next((r for r in plan.get("rooms") or [] if r["id"] != room_id and polygons(plan).get(r["id"]) is not None
                              and r["floor"] == rooms_by_id(plan)[room_id]["floor"] and polygons(plan)[r["id"]].contains(Point(behind))), None)
            soft = (back_room or {}).get("label") in SOFT_WALLS
            head_az = azimuth_of(plan, -n[0], -n[1])
            face_az = azimuth_of(plan, n[0], n[1])
            kua_ok = bool(good_dirs) and (compass8(head_az if piece == "bed" else face_az) in good_dirs) \
                if head_az is not None else False
            dist = math.hypot(*to_door)
            key = (seen and not in_line, seen, not in_line, not soft, kua_ok, -abs(angle - 35) / 90 + dist / 10)
            if best_key is None or key > best_key:
                c = foot.centroid
                off = WALL_GAP_M + (CHAIR_M + d / 2 if piece == "desk" else d / 2)
                center = (a[0] + u[0] * (s + w / 2) + n[0] * off, a[1] + u[1] * (s + w / 2) + n[1] * off)
                best_key = key
                best = {"available": True, "ok": seen and not in_line and not soft, "center": center,
                        "footprint_center": (c.x, c.y), "yaw_deg": math.degrees(math.atan2(u[1], u[0])),
                        "size": (w, d), "head_az": head_az, "face_az": face_az, "door": main["door"]["id"],
                        "door_distance_m": dist, "door_angle_deg": angle, "kua_ok": kua_ok,
                        "rules": {"view": seen, "not_in_line": not in_line, "solid_wall": True, "no_soft_wall": not soft},
                        "in_line_with": in_line, "back_room": (back_room or {}).get("label")}
    if best is None:
        return {"available": False, "reason": f"No wall in this room is clear and long enough for the {piece}."}
    return best
