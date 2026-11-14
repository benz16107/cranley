"""Room graph: rooms are nodes; doorways, wall-less openings and invisible walls are links."""
from __future__ import annotations

from ._plan import (
    geo_source,
    polygon_source,
    polygons,
    room_label,
    rooms_beside,
    rooms_by_id,
    unavailable,
    walls_by_id,
)

PASSABLE = ("doorway", "opening", "divider")  # a divider is Matterport's open boundary between two rooms (no wall)


def room_graph(plan: dict) -> dict:
    """Nodes, links, entrances and connected components, per the whole plan (links never cross floors).

    A doorway whose wall sits on no room boundary, or on one, is placed by probing the room polygons either
    side of it; such links carry `inferred: True`. An opening with one room after that is an entrance: it leads
    outside or to unscanned space. Stairs are not in the scan data, so floors are not linked."""
    if not plan.get("walls"):
        return unavailable("This scan has rooms but no wall graph, so doors and connections are unknown.",
                           nodes=_nodes(plan))
    rooms, walls = rooms_by_id(plan), walls_by_id(plan)
    links, entrances, unplaced = [], [], []
    for o in plan.get("openings") or []:
        if o["type"] not in PASSABLE:
            continue
        listed = [r for r in o.get("rooms") or [] if r in rooms]
        found = listed if len(listed) >= 2 else listed + [r for r in rooms_beside(plan, o, walls.get(o["wall"]))
                                                         if r not in listed]
        kind = "opening" if o["type"] == "divider" else o["type"]
        base = {"opening": o["id"], "kind": kind, "floor": o["floor"], "width": o.get("width"),
                "height": o.get("height"), "sill": o.get("sill"), "center": o["center"], "wall": o["wall"]}
        if len(found) >= 2:
            links.append({"id": o["id"], **base, "rooms": found[:2], "inferred": len(listed) < 2})
        elif len(found) == 1 and o["type"] != "divider":  # a divider with one room scanned is no way out
            entrances.append({"id": o["id"], **base, "room": found[0], "inferred": len(listed) == 0})
        else:
            unplaced.append(base)
    for w in plan["walls"]:
        if w.get("type") == "invisible" and len(w.get("rooms") or []) >= 2:
            ra, rb = w["rooms"][:2]
            links.append({"id": w["id"], "opening": None, "kind": "invisible", "floor": w["floor"],
                          "width": w["length"], "height": None, "sill": None, "wall": w["id"],
                          "center": [(w["a"][0] + w["b"][0]) / 2, (w["a"][1] + w["b"][1]) / 2],
                          "rooms": [ra, rb], "inferred": False})
    nodes = _nodes(plan)
    return {"available": True, "nodes": nodes, "links": links, "entrances": entrances, "unplaced": unplaced,
            "components": _components([n["room"] for n in nodes], links),
            "source": geo_source("Matterport wall graph. Door widths are the opening in the wall, not clear width.")}


def neighbours(graph: dict) -> dict[str, list[tuple[str, dict]]]:
    adj: dict[str, list[tuple[str, dict]]] = {n["room"]: [] for n in graph["nodes"]}
    for link in graph["links"]:
        a, b = link["rooms"]
        adj.setdefault(a, []).append((b, link))
        adj.setdefault(b, []).append((a, link))
    return adj


def _nodes(plan: dict) -> list[dict]:
    out = []
    polys = polygons(plan)
    for r in plan.get("rooms") or []:
        poly = polys[r["id"]]
        out.append({"room": r["id"], "floor": r["floor"], "label": room_label(r), "void": r.get("label") == "Void",
                    "has_polygon": poly is not None, "polygon_source": polygon_source(plan, r["id"]), "area": poly.area if poly is not None else r.get("area"),
                    "centroid": [poly.centroid.x, poly.centroid.y] if poly is not None else None})
    return out


def _components(room_ids: list[str], links: list[dict]) -> list[list[str]]:
    parent = {r: r for r in room_ids}

    def find(x: str) -> str:
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for link in links:
        parent[find(link["rooms"][0])] = find(link["rooms"][1])
    groups: dict[str, list[str]] = {}
    for r in parent:
        groups.setdefault(find(r), []).append(r)
    return sorted(groups.values(), key=len, reverse=True)
