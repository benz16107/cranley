"""What a scan measures that a record also states, as plain numbers with the rooms behind them.

Pure functions over a ScanPlan (Contract 1); no network. Every function returns `available: False` with a reason
when the scan cannot answer, so a caller can say "cannot verify" in a sentence.
"""
from __future__ import annotations

import statistics

from ...geometry import room_graph, takeoff

M2_FT2 = 10.7639
M_FT = 3.28084

# Rooms a listed living area leaves out, and why. Matterport's own label set (see vision.reader.HOME_LABELS).
NOT_LIVING = {
    "Garage": "a garage is not living area",
    "Patio": "a patio is outdoor space",
    "Balcony": "a balcony is outdoor space",
    "Basement": "listings usually leave below-grade space out of living area",
}
HALF_BATH_M2 = 3.0     # a bathroom group smaller than this is taken as a half bath (toilet and basin)
BEDROOM_MIN_M2 = 4.0   # smaller "Bedroom" rooms are labelling noise
CAR_STALL_M2 = 17.0    # one garage stall with room to open doors, for counting stalls from a garage's area
WALK_IN_M2 = 2.2       # a closet you can step into: at least this floor area
WALK_IN_SIDE_M = 1.1   # and at least this narrow side


def label(r: dict) -> str:
    return r.get("label") or "unlabelled room"


def walls_ok(plan: dict) -> bool:
    q = plan.get("quality")
    return bool(q["walls"]) if q else bool(plan.get("walls"))


def labels_ok(plan: dict) -> bool:
    q = plan.get("quality")
    return bool(q["labels"]) if q else any(r.get("label") for r in plan["rooms"])


def floor_area(plan: dict, relabel: dict[str, str] | None = None) -> dict:
    """Interior floor area of the rooms a listing counts as living area, and every room left out with the reason.
    `relabel` names unlabelled rooms from the panoramas (an open roof deck has parapet walls and reads as a room).

    Needs the wall graph: without it nothing says which rooms are indoor and bounded."""
    if not walls_ok(plan):
        raw = sum(r.get("area") or 0 for r in plan["rooms"] if r.get("label") != "Void")
        return {"available": False, "raw_m2": raw,
                "reason": "This scan has no wall graph, so it cannot tell bounded indoor rooms from open or outdoor "
                          f"captures; Matterport's room areas add up to {raw:.0f} m² but that sum is not a floor area."}
    counted, excluded = [], []
    for r in plan["rooms"]:
        a = r.get("area") or 0
        lab = r.get("label") or (relabel or {}).get(r["id"])
        why = ("an empty space inside the outline (stairwell void or shaft)" if lab == "Void" else
               NOT_LIVING.get(lab) or
               ("it has no walls around it, so it is an outdoor or unscanned area" if not r.get("walls") else None) or
               ("it has no area" if a <= 0 else None))
        row = {"room": r["id"], "label": lab or "unlabelled room", "floor": r["floor"], "m2": round(a, 2)}
        if lab and not r.get("label"):
            why = why and why + " (named from its panorama)"
        (excluded.append({**row, "why": why}) if why else counted.append(row))
    m2 = sum(x["m2"] for x in counted)
    floors = sorted({x["floor"] for x in counted})
    return {"available": True, "m2": m2, "ft2": m2 * M2_FT2, "counted": counted,
            "excluded": [x for x in excluded if x["m2"] >= 0.5], "floors": floors}


def _union(ids: list[str], links: list[tuple[str, str]]) -> list[list[str]]:
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in links:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for i in ids:
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _links(plan: dict) -> list[tuple[str, str]]:
    g = room_graph(plan)
    return [tuple(link["rooms"]) for link in g.get("links") or []] if g["available"] else []


def bedrooms(plan: dict) -> dict:
    if not labels_ok(plan):
        return {"available": False, "reason": "Matterport did not label this scan's rooms."}
    rooms = [r for r in plan["rooms"] if r.get("label") == "Bedroom" and (r.get("area") or 0) >= BEDROOM_MIN_M2]
    maybe = [r for r in plan["rooms"] if r.get("label") in ("Office", "Den", "Bonus Room", "Loft", "Family Room", "Game Room")]
    return {"available": True, "count": len(rooms), "rooms": [r["id"] for r in rooms],
            "maybe": [{"room": r["id"], "label": r["label"], "m2": round(r.get("area") or 0, 1)} for r in maybe]}


def bathrooms(plan: dict, fixtures: dict[str, set[str]] | None = None) -> dict:
    """Bathrooms, with rooms joined by a doorway merged into one (a vanity room and a toilet room are one bath).
    A bath is full when a tub or shower was seen in it (`fixtures`: room id -> labels seen, for rooms whose
    panorama was read), half when it was read and none was seen, and otherwise judged by its size."""
    if not labels_ok(plan):
        return {"available": False, "reason": "Matterport did not label this scan's rooms."}
    baths = {r["id"]: r for r in plan["rooms"] if r.get("label") == "Bathroom" and (r.get("area") or 0) > 0.5}
    groups = _union(list(baths), _links(plan))
    out = []
    for g in groups:
        m2 = sum(baths[i].get("area") or 0 for i in g)
        read = [i for i in g if fixtures is not None and i in fixtures]
        wet = any({"bathtub", "shower"} & fixtures[i] for i in read)
        out.append({"rooms": g, "m2": round(m2, 2), "half": (not wet) if read else m2 < HALF_BATH_M2,
                    "by": "panorama" if read else "size"})
    full = sum(1 for g in out if not g["half"])
    half = len(out) - full
    return {"available": True, "full": full, "half": half, "count": full + 0.5 * half, "groups": out,
            "merged": sum(len(g["rooms"]) - 1 for g in out), "seen": sum(1 for g in out if g["by"] == "panorama")}


def floors(plan: dict) -> dict:
    """Floors that hold at least one real room (not a void, at least 3 m²)."""
    used = {r["floor"] for r in plan["rooms"] if r.get("label") != "Void" and (r.get("area") or 0) >= 3}
    names = [f["label"] for f in plan["floors"] if f["id"] in used]
    return {"available": bool(used), "count": len(used), "names": names,
            "reason": None if used else "The scan has no rooms."}


def heights(plan: dict) -> dict:
    hs = [(r["id"], r["height"]) for r in plan["rooms"] if r.get("height") and r.get("label") != "Void"]
    if not hs:
        return {"available": False, "reason": "Matterport recorded no ceiling height for any room in this scan."}
    vals = [h for _, h in hs]
    top = max(hs, key=lambda x: x[1])
    return {"available": True, "median_m": statistics.median(vals), "max_m": top[1], "max_room": top[0],
            "min_m": min(vals), "rooms": dict(hs), "of_rooms": len(hs),
            "rooms_total": sum(1 for r in plan["rooms"] if r.get("label") != "Void")}


def closets(plan: dict) -> dict:
    """Closet rooms, each marked walk-in when you can step into it."""
    if not labels_ok(plan):
        return {"available": False, "reason": "Matterport did not label this scan's rooms."}
    out = []
    for r in plan["rooms"]:
        if r.get("label") != "Closet":
            continue
        side = min(r.get("width") or 0, r.get("depth") or 0)
        out.append({"room": r["id"], "m2": round(r.get("area") or 0, 2), "side_m": round(side, 2),
                    "walk_in": (r.get("area") or 0) >= WALK_IN_M2 and (side >= WALK_IN_SIDE_M or not side)})
    return {"available": True, "closets": out, "walk_in": [c for c in out if c["walk_in"]]}


def rooms_labelled(plan: dict, *names: str) -> list[dict]:
    return [r for r in plan["rooms"] if r.get("label") in names]


def garage_stalls(plan: dict) -> dict:
    g = rooms_labelled(plan, "Garage")
    if not g:
        return {"available": False, "reason": "No garage was scanned."}
    m2 = sum(r.get("area") or 0 for r in g)
    return {"available": True, "stalls": max(1, int(m2 // CAR_STALL_M2)), "m2": m2, "rooms": [r["id"] for r in g]}


def windows_by_room(plan: dict) -> dict:
    """Window count and glazed area per room, from the geometry engine's takeoff."""
    t = takeoff(plan)
    if not t["available"] or not plan.get("openings"):
        return {"available": False, "reason": "This scan has no doors or windows in its wall graph."}
    return {"available": True, "rooms": {x["room"]: {"windows": x["windows"], "glazed_m2": x["glazed_area"],
                                                    "doors": x["doors"], "height": x["height"],
                                                    "height_estimated": x["height_estimated"]} for x in t["rooms"]},
            "total": t["total"]}
