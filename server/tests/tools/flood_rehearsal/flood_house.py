"""A small hand-made one-storey house for the flood tools. No sponsor data, no network.

    y=10 +-----GD (garage door)-+------WR------+
         |  G  garage, 0.15 m   |  R bedroom    |
         |  below the house     |               |
    y=5  +--------LG------------+------KR------+
         F  L living            LK  K kitchen   WK
         |                      |               |
    y=0  +-------WL-------------+-------B-------+
        x=0                    x=6            x=10

F front door (sill 0.15 m below the floor: one step), B back door, LG two steps down into the garage.
Indoor panoramas stand 1.40 m above their floor; three outdoor ones by the front door stand 1.15 m above the
house floor, so the ground there is 0.25 m below the floor.
"""
import math

ID_ROT = [0.0, 0.0, 0.0, 1.0]


def house(walls: bool = True) -> dict:
    ws, ops = {}, []

    def wall(wid, a, b, rooms):
        ws[wid] = {"id": wid, "floor": "f1", "a": list(a), "b": list(b), "type": "wall", "thickness": 0.12,
                   "length": math.dist(a, b), "rooms": list(rooms), "openings": []}

    def opening(oid, wid, kind, width, sill, height=2.03, t=0.5):
        w = ws[wid]
        c = [w["a"][0] + (w["b"][0] - w["a"][0]) * t, w["a"][1] + (w["b"][1] - w["a"][1]) * t]
        ops.append({"id": oid, "wall": wid, "floor": "f1", "type": kind, "width": width, "height": height,
                    "sill": sill, "center": c, "rooms": w["rooms"]})
        w["openings"].append(oid)

    wall("l_s", (0, 0), (6, 0), ["L"]); wall("lk", (6, 0), (6, 5), ["L", "K"]); wall("lg", (6, 5), (0, 5), ["L", "G"])
    wall("l_w", (0, 5), (0, 0), ["L"]); wall("k_s", (6, 0), (10, 0), ["K"]); wall("k_e", (10, 0), (10, 5), ["K"])
    wall("kr", (10, 5), (6, 5), ["K", "R"]); wall("g_w", (0, 5), (0, 10), ["G"]); wall("g_n", (0, 10), (6, 10), ["G"])
    wall("gr", (6, 10), (6, 5), ["G", "R"]); wall("r_n", (6, 10), (10, 10), ["R"]); wall("r_e", (10, 10), (10, 5), ["R"])
    opening("F", "l_w", "doorway", 0.91, -0.15)
    opening("WL", "l_s", "window", 1.5, 0.9, height=1.2)
    opening("LK", "lk", "doorway", 0.9, 0.0)
    opening("LK2", "lk", "doorway", 0.8, 0.0, t=0.2)
    opening("LG", "lg", "doorway", 0.81, -0.15)
    opening("B", "k_s", "doorway", 0.81, 0.0)
    opening("WK", "k_e", "window", 1.0, 1.0, height=1.0)
    opening("GD", "g_n", "doorway", 4.8, -0.17)
    opening("KR", "kr", "doorway", 0.81, 0.0)
    opening("KR2", "kr", "doorway", 0.7, 0.0, t=0.2)
    opening("WR", "r_n", "window", 1.2, 0.8, height=1.2)

    def room(rid, label, poly, wall_ids):
        return {"id": rid, "floor": "f1", "label": label, "label_confidence": 1, "label_source": "matterport",
                "polygon": [list(p) for p in poly], "area": None, "height": 2.44, "width": None, "depth": None,
                "walls": wall_ids, "holes": []}

    rooms = [room("L", "Living Room", [(0, 0), (6, 0), (6, 5), (0, 5)], ["l_s", "lk", "lg", "l_w"]),
             room("K", "Kitchen", [(6, 0), (10, 0), (10, 5), (6, 5)], ["k_s", "k_e", "kr", "lk"]),
             room("G", "Garage", [(0, 5), (6, 5), (6, 10), (0, 10)], ["lg", "g_w", "g_n", "gr"]),
             room("R", "Bedroom", [(6, 5), (10, 5), (10, 10), (6, 10)], ["kr", "gr", "r_n", "r_e"])]
    for r in rooms:
        xs, ys = zip(*r["polygon"])
        r["area"] = (max(xs) - min(xs)) * (max(ys) - min(ys))

    def pano(pid, x, y, z, room_id):
        return {"id": pid, "label": pid, "position": [x, y, z], "rotation": ID_ROT, "floor": "f1", "room": room_id,
                "neighbors": []}

    panos = [pano("l1", 2, 2, 1.4, "L"), pano("l2", 4, 3, 1.4, "L"), pano("k1", 8, 2, 1.4, "K"),
             pano("k2", 8, 3.5, 1.41, "K"), pano("r1", 8, 7.5, 1.4, "R"), pano("g1", 2, 7, 1.25, "G"),
             pano("g2", 4, 8, 1.25, "G"), pano("o1", -2, 2.5, 1.15, None), pano("o2", -3, 1.5, 1.14, None),
             pano("o3", -2.5, 3.5, 1.16, None)]
    plan = {"schema": "scanplan/1", "sid": "house", "name": "Test house", "address": None, "city": "Houston",
            "geo": {"lat": 29.78, "lon": -95.245, "altitude": 0, "yaw_deg": 0.0, "translation": {"x": 0, "y": 0, "z": 0},
                    "source": "test"},
            "ids": {"defurnished_view": None}, "has": {"splat": False, "defurnished": False, "room_labels": True,
                                                       "openings": True},
            "floors": [{"id": "f1", "label": "Floor 1", "sequence": 0, "elevation": 0.0}],
            "walls": list(ws.values()), "openings": ops, "rooms": rooms, "panos": panos, "floorplans": []}
    if not walls:
        plan["walls"], plan["openings"] = [], []
        for r in plan["rooms"]:
            r["walls"] = []
    return plan


def plans_of(*ps):
    by = {p["sid"]: p for p in ps}

    def get(sid):
        if sid not in by:
            raise LookupError(sid)
        return by[sid]
    return get
