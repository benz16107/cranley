"""Quantity takeoff per room and per plan: areas, perimeter, wall area net of openings, doors, windows."""
from __future__ import annotations

from ._plan import (
    default_ceiling,
    geo_source,
    openings_by_id,
    polygons,
    room_label,
    unavailable,
    walls_by_id,
)


def takeoff(plan: dict) -> dict:
    """Per room: floor area, perimeter, ceiling height, gross and net wall area (each face of a wall counts for
    the room it faces, so interior walls count twice at plan level, as paint does), door and window counts,
    glazed area. Rooms without a height use the plan's median ceiling and say so. Plan totals leave out voids
    and wall-less rooms (in scans that have walls these are yards and porches), reported separately."""
    rooms = plan.get("rooms") or []
    if not rooms:
        return unavailable("This scan has no rooms.")
    walls, opens, polys = walls_by_id(plan), openings_by_id(plan), polygons(plan)
    ceiling = default_ceiling(plan)
    out = []
    for r in rooms:
        poly = polys[r["id"]]
        h = r.get("height") or ceiling
        rw = [walls[w] for w in r.get("walls") or [] if w in walls and walls[w].get("type") != "invisible"]
        ro = [opens[o] for w in rw for o in w.get("openings") or [] if o in opens]
        gross = sum(w["length"] for w in rw) * h if h and rw else None
        cut = sum((o["width"] or 0) * min(o["height"] or 0, h) for o in ro) if h else 0.0
        win = [o for o in ro if o["type"] == "window"]
        out.append({"room": r["id"], "label": room_label(r), "floor": r["floor"], "void": r.get("label") == "Void",
                    # a room with no walls in a scan that has walls is usually a yard or porch capture
                    "unwalled": not r.get("walls") and bool(plan.get("walls")),
                    "floor_area": r.get("area") or (poly.area if poly is not None else None),
                    "outline_area": poly.area if poly is not None else None,
                    "perimeter": poly.length if poly is not None else None,
                    "height": h, "height_estimated": not r.get("height") and h is not None,
                    "wall_area_gross": gross, "wall_area_net": gross - cut if gross is not None else None,
                    "doors": sum(1 for o in ro if o["type"] != "window"), "windows": len(win),
                    "glazed_area": sum((o["width"] or 0) * (o["height"] or 0) for o in win)})
    live = [x for x in out if not x["void"] and not x["unwalled"]]
    plan_opens = plan.get("openings") or []
    windows = [o for o in plan_opens if o["type"] == "window"]
    total = {"floor_area": sum(x["floor_area"] or 0 for x in live),
             "floor_area_voids": sum(x["floor_area"] or 0 for x in out if x["void"]),
             "floor_area_unwalled": sum(x["floor_area"] or 0 for x in out if x["unwalled"]),
             "wall_area_net": sum(x["wall_area_net"] or 0 for x in live),
             "doors": sum(1 for o in plan_opens if o["type"] != "window"), "windows": len(windows),
             "glazed_area": sum((o["width"] or 0) * (o["height"] or 0) for o in windows),
             "ceiling_height_median": ceiling, "rooms": len(live)}
    total["glazing_ratio"] = total["glazed_area"] / total["floor_area"] if total["floor_area"] else None
    src = geo_source("Matterport room areas and wall graph; heights missing on some rooms use the median.")
    metrics = [{"id": k, "label": label, "value": total[k], "unit": unit, "source": src} for k, label, unit in (
        ("floor_area", "Floor area (walled rooms, no voids)", "m2"), ("wall_area_net", "Wall area net of openings", "m2"),
        ("doors", "Doors and openings", "count"), ("windows", "Windows", "count"),
        ("glazed_area", "Glazed area", "m2"), ("ceiling_height_median", "Typical ceiling height", "m"))]
    return {"available": True, "rooms": out, "total": total, "metrics": metrics, "source": src}
