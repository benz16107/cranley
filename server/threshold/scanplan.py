"""ScanPlan: the one normalized shape every engine, tool and view reads. Contract: docs/contracts/scanplan.md.

`normalize(raw_model)` turns one Matterport Model API response (the query in QUERY) into a ScanPlan dict.
Everything is metres, in the scan's own frame (x, y on the floor, z up).
"""
from __future__ import annotations

import math

SCHEMA = "scanplan/1"

QUERY = """query($id: ID!) { model(id: $id) { id name description visibility created
  address { address locality administrativeArea postalCode }
  geocoordinates { latitude longitude altitude source rotation { x y z w } translation { x y z } }
  generatedDescription { summary } propertyClassifications { classification type }
  floors { id label sequence
    vertices { id position { x y } }
    edges { id type thickness centerLineBias vertices { id }
            openings { id type width height lowerElevation relativeCenter } } }
  rooms { id label floor { id } classifications { label confidence }
    dimensions(units: metric) { areaFloor width depth height }
    boundary { edges { id } } holes { edges { id } } }
  panoLocations { id label position { x y z } rotation { x y z w } anchor { id neighbors room { id } floor { id } } }
  view(type: "matterport.model.defurnished") { id }
  assets { floorplans(provider: "matterport") { format flags width height resolution origin { x y } floor { id } } }
} }"""


def _yaw_deg(q: dict | None) -> float | None:
    """Rotation about z, in degrees, from a quaternion. None when there is no quaternion."""
    if not q:
        return None
    x, y, z, w = (q.get(k, 0.0) for k in "xyzw")
    return math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def _loop(edge_ids: list[str], walls: dict[str, dict]) -> list[list[float]]:
    """Order a room's boundary edges into one polygon. Returns [] when the edges do not chain."""
    segs = [(walls[e]["a_id"], walls[e]["b_id"]) for e in edge_ids if e in walls]
    if len(segs) < 3:
        return []
    pts = {walls[e]["a_id"]: walls[e]["a"] for e in edge_ids if e in walls}
    pts.update({walls[e]["b_id"]: walls[e]["b"] for e in edge_ids if e in walls})
    a, b = segs.pop(0)
    chain = [a, b]
    while segs:
        tail = chain[-1]
        nxt = next((i for i, (p, q) in enumerate(segs) if tail in (p, q)), None)
        if nxt is None:
            return []
        p, q = segs.pop(nxt)
        chain.append(q if p == tail else p)
    if chain[0] == chain[-1]:
        chain.pop()
    return [pts[v] for v in chain]


def _area(poly: list[list[float]]) -> float:
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2 if poly else 0.0


def normalize(model: dict, index_row: dict | None = None) -> dict:
    row = index_row or {}
    geo = model.get("geocoordinates") or {}
    walls: dict[str, dict] = {}
    openings: list[dict] = []
    floors = []
    for f in model.get("floors") or []:
        floors.append({"id": f["id"], "label": f.get("label"), "sequence": f.get("sequence")})
        verts = {v["id"]: [v["position"]["x"], v["position"]["y"]] for v in f.get("vertices") or []}
        for e in f.get("edges") or []:
            ids = [v["id"] for v in e.get("vertices") or []]
            if len(ids) != 2 or ids[0] not in verts or ids[1] not in verts:
                continue
            a, b = verts[ids[0]], verts[ids[1]]
            walls[e["id"]] = {"id": e["id"], "floor": f["id"], "a": a, "b": b, "a_id": ids[0], "b_id": ids[1],
                              "type": e.get("type"), "thickness": e.get("thickness"),
                              "length": math.dist(a, b), "rooms": [], "openings": []}
            for o in e.get("openings") or []:
                t = o.get("relativeCenter", 0.5)
                openings.append({"id": o["id"], "wall": e["id"], "floor": f["id"], "type": o.get("type"),
                                 "width": o.get("width"), "height": o.get("height"), "sill": o.get("lowerElevation"),
                                 "center": [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], "rooms": []})
                walls[e["id"]]["openings"].append(o["id"])
    rooms = []
    for r in model.get("rooms") or []:
        edge_ids = [e["id"] for e in (r.get("boundary") or {}).get("edges") or []]
        for e in edge_ids:
            if e in walls:
                walls[e]["rooms"].append(r["id"])
        cls = (r.get("classifications") or [{}])[0]
        dims = r.get("dimensions") or {}
        poly = _loop(edge_ids, walls)
        label = cls.get("label") or r.get("label") or None
        rooms.append({"id": r["id"], "floor": (r.get("floor") or {}).get("id"),
                      "label": None if label in ("Other", "") else label,  # "Other" is Matterport's "no idea"
                      "label_confidence": cls.get("confidence"), "label_source": "matterport" if label else None,
                      "polygon": poly, "area": dims.get("areaFloor") or (_area(poly) or None),
                      "height": dims.get("height"), "width": dims.get("width"), "depth": dims.get("depth"),
                      "walls": edge_ids,
                      "holes": [[e["id"] for e in h.get("edges") or []] for h in r.get("holes") or []]})
    for o in openings:
        o["rooms"] = walls[o["wall"]]["rooms"]  # one room: opens to outside or to unscanned space
    panos = [{"id": p["id"], "label": p.get("label"),
              "position": [p["position"]["x"], p["position"]["y"], p["position"]["z"]],
              "rotation": [(p.get("rotation") or {}).get(k) for k in "xyzw"] if p.get("rotation") else None,
              "floor": ((p.get("anchor") or {}).get("floor") or {}).get("id"),
              "room": ((p.get("anchor") or {}).get("room") or {}).get("id"),
              "neighbors": (p.get("anchor") or {}).get("neighbors") or []}
             for p in model.get("panoLocations") or []]
    addr = model.get("address") or {}
    return {
        "schema": SCHEMA, "sid": model["id"], "name": model.get("name"), "notes": model.get("description"),
        "address": addr.get("address") or row.get("address") or None, "city": addr.get("locality") or row.get("city") or None,
        "segment": row.get("segment"), "created": model.get("created"),
        "summary": (model.get("generatedDescription") or {}).get("summary"),
        "geo": {"lat": geo.get("latitude"), "lon": geo.get("longitude"), "altitude": geo.get("altitude"),
                "yaw_deg": _yaw_deg(geo.get("rotation")), "translation": geo.get("translation"),
                "source": geo.get("source")} if geo else None,
        "ids": {"costar_property": row.get("costar_property_id") or None, "homes_listing": row.get("homes_listing_id") or None,
                "defurnished_view": (model.get("view") or {}).get("id")},
        "has": {"splat": row.get("splat") == "yes", "defurnished": bool((model.get("view") or {}).get("id")),
                "room_labels": any(r["label"] and r["label"] != "Void" for r in rooms),
                "openings": bool(openings)},
        "floors": floors,
        "walls": [{k: v for k, v in w.items() if k not in ("a_id", "b_id")} for w in walls.values()],
        "openings": openings, "rooms": rooms, "panos": panos,
        "floorplans": [{k: fp.get(k) for k in ("format", "flags", "width", "height", "resolution", "origin")}
                       | {"floor": (fp.get("floor") or {}).get("id")}
                       for fp in (model.get("assets") or {}).get("floorplans") or []],
    }
