"""ScanPlan: the one normalized shape every engine, tool and view reads. Contract: Contract 1 in docs/ARCHITECTURE.md.

`normalize(raw_model)` turns one Matterport Model API response (the query in QUERY) into a ScanPlan dict.
Everything is metres, in the scan's own frame (x, y on the floor, z up).

Fields added to the contract (none renamed, none changed in meaning):
  plan.quality                       what is usable: walls, polygons, openings, labels, georef, plus counts and notes
  floors[].elevation(_source)        metres above the lowest floor, from the median height of the panoramas on it
  rooms[].hole_polygons              rings of the holes (columns, shafts) inside the outline
  rooms[].extra_polygons             further disjoint outlines when one room has several parts
  rooms[].center(_source)            a point inside the room: the outline's, else the mean of its panoramas
  rooms[].area_source                "matterport" | "polygon" | None
"""
from __future__ import annotations

import math
from statistics import median

from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

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

MIN_WALL = 0.05      # m; shorter edges are vertex noise, not walls
MIN_FACE = 1e-4      # m²; smaller faces are slivers from rounding
MIN_PART = 0.05      # m²; a second disjoint outline smaller than this is dropped
AREA_TOLERANCE = 0.25  # an outline whose area differs from Matterport's by more than this is flagged


def _yaw_deg(q: dict | None) -> float | None:
    """Rotation about z, in degrees, from a quaternion. None when there is no quaternion."""
    if not q:
        return None
    x, y, z, w = (q.get(k, 0.0) for k in "xyzw")
    return math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))


def _faces(edge_ids: list[str], walls: dict[str, dict]) -> list[Polygon]:
    """Closed faces enclosed by these edges, largest first. Dangling edges, edges shared with a neighbour that
    meet at a T, and edges listed twice do not matter: this is polygonize, not a walk along the edges."""
    lines = [LineString([walls[e]["a"], walls[e]["b"]]) for e in dict.fromkeys(edge_ids)
             if e in walls and walls[e]["length"] > 1e-6]
    if not lines:
        return []
    return sorted((f for f in polygonize(unary_union(lines)) if f.area > MIN_FACE), key=lambda f: -f.area)


def _ring(poly: Polygon) -> list[list[float]]:
    return [[x, y] for x, y in orient(poly, 1.0).exterior.coords[:-1]]


def _rings(ring) -> list[list[float]]:
    return [[x, y] for x, y in ring.coords[:-1]]


def _room_shape(edge_ids: list[str], hole_ids: list[list[str]], walls: dict[str, dict]) -> dict:
    faces = _faces(edge_ids, walls)
    if not faces:
        return {"polygon": [], "extra_polygons": [], "hole_polygons": [], "area": None, "center": None}
    main = orient(faces[0], 1.0)
    holes = [_rings(i) for i in main.interiors]
    holes += [_ring(h) for ids in hole_ids for h in _faces(ids, walls) if main.contains(h.representative_point())]
    solid = Polygon(main.exterior, [h for h in holes if len(h) >= 3])
    return {"polygon": _rings(main.exterior), "hole_polygons": holes,
            "extra_polygons": [_ring(f) for f in faces[1:] if f.area >= MIN_PART],
            "area": solid.area, "center": list(main.representative_point().coords[0])}


def _elevations(floors: list[dict], panos: list[dict]) -> None:
    """Floor elevation relative to the lowest floor that has panoramas. Matterport gives none, but every
    panorama sits at a fixed camera height above its floor, so the median pano z on a floor tracks the floor."""
    z = {f["id"]: median(p["position"][2] for p in panos if p["floor"] == f["id"])
         for f in floors if any(p["floor"] == f["id"] for p in panos)}
    base = min(z.values()) if z else None
    for f in floors:
        has = f["id"] in z
        f["elevation"] = round(z[f["id"]] - base, 3) if has else None
        f["elevation_source"] = "panos" if has else None


def normalize(model: dict, index_row: dict | None = None) -> dict:
    row = index_row or {}
    geo = model.get("geocoordinates") or {}
    walls: dict[str, dict] = {}
    openings: list[dict] = []
    floors = []
    dropped = 0
    for f in sorted(model.get("floors") or [], key=lambda f: (f.get("sequence") is None, f.get("sequence"))):
        floors.append({"id": f["id"], "label": f.get("label"), "sequence": f.get("sequence")})
        verts = {v["id"]: [v["position"]["x"], v["position"]["y"]] for v in f.get("vertices") or []}
        for e in f.get("edges") or []:
            ids = [v["id"] for v in e.get("vertices") or []]
            if len(ids) != 2 or ids[0] not in verts or ids[1] not in verts:
                dropped += 1
                continue
            a, b = verts[ids[0]], verts[ids[1]]
            walls[e["id"]] = {"id": e["id"], "floor": f["id"], "a": a, "b": b, "a_id": ids[0], "b_id": ids[1],
                              "type": e.get("type"), "thickness": e.get("thickness"),
                              "length": math.dist(a, b), "rooms": [], "openings": []}
            for o in e.get("openings") or []:
                t = o.get("relativeCenter")
                t = 0.5 if t is None else t
                openings.append({"id": o["id"], "wall": e["id"], "floor": f["id"], "type": o.get("type"),
                                 "width": o.get("width"), "height": o.get("height"), "sill": o.get("lowerElevation"),
                                 "center": [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], "rooms": []})
                walls[e["id"]]["openings"].append(o["id"])

    panos = [{"id": p["id"], "label": p.get("label"),
              "position": [p["position"]["x"], p["position"]["y"], p["position"]["z"]],
              "rotation": [(p.get("rotation") or {}).get(k) for k in "xyzw"] if p.get("rotation") else None,
              "floor": ((p.get("anchor") or {}).get("floor") or {}).get("id"),
              "room": ((p.get("anchor") or {}).get("room") or {}).get("id"),
              "neighbors": (p.get("anchor") or {}).get("neighbors") or []}
             for p in model.get("panoLocations") or []]
    _elevations(floors, panos)

    rooms = []
    for r in model.get("rooms") or []:
        edge_ids = [e["id"] for e in (r.get("boundary") or {}).get("edges") or []]
        hole_ids = [[e["id"] for e in h.get("edges") or []] for h in r.get("holes") or []]
        for e in dict.fromkeys(edge_ids):
            if e in walls:
                walls[e]["rooms"].append(r["id"])
        cls = (r.get("classifications") or [{}])[0]
        dims = r.get("dimensions") or {}
        shape = _room_shape(edge_ids, hole_ids, walls)
        label = cls.get("label") or r.get("label") or None
        label = None if label in ("Other", "") else label  # "Other" is Matterport's "no idea"; "Void" is kept
        floor = (r.get("floor") or {}).get("id") or next((walls[e]["floor"] for e in edge_ids if e in walls), None)
        center, center_source = shape["center"], "polygon" if shape["center"] else None
        if center is None:
            mine = [p["position"] for p in panos if p["room"] == r["id"]]
            if mine:
                center, center_source = [sum(p[0] for p in mine) / len(mine), sum(p[1] for p in mine) / len(mine)], "panos"
        area = dims.get("areaFloor")
        rooms.append({"id": r["id"], "floor": floor, "label": label,
                      "label_confidence": cls.get("confidence"),
                      "label_source": "matterport" if label else None,
                      "polygon": shape["polygon"], "extra_polygons": shape["extra_polygons"],
                      "hole_polygons": shape["hole_polygons"],
                      "area": area or shape["area"] or None,
                      "area_source": "matterport" if area else ("polygon" if shape["area"] else None),
                      "height": dims.get("height"), "width": dims.get("width"), "depth": dims.get("depth"),
                      "center": center, "center_source": center_source,
                      "walls": edge_ids, "holes": hole_ids,
                      "_outline_area": shape["area"]})
    for o in openings:
        o["rooms"] = list(walls[o["wall"]]["rooms"])  # one room: opens to outside or to unscanned space

    addr = model.get("address") or {}
    plan = {
        "schema": SCHEMA, "sid": model["id"], "name": model.get("name"), "notes": model.get("description"),
        "address": addr.get("address") or row.get("address") or None, "city": addr.get("locality") or row.get("city") or None,
        "segment": row.get("segment") or None, "created": model.get("created"),
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
    plan["quality"] = _quality(plan, dropped)
    for r in plan["rooms"]:
        del r["_outline_area"]
    return plan


def _quality(plan: dict, dropped: int) -> dict:
    """What a tool can rely on in this scan. Booleans first, the numbers behind them in `counts`."""
    walls = [w for w in plan["walls"] if w["type"] == "wall" and w["length"] >= MIN_WALL]
    rooms = [r for r in plan["rooms"] if r["label"] != "Void"]
    bounded = [r for r in rooms if r["walls"]]  # the rest have no boundary at all: outdoor or unscanned areas
    with_poly = [r for r in bounded if r["polygon"]]
    labelled = [r for r in rooms if r["label"]]
    off = [r for r in with_poly if r["area_source"] == "matterport" and r["area"] and r["area"] >= 1
           and abs(r["_outline_area"] - r["area"]) > AREA_TOLERANCE * r["area"]]
    geo = plan["geo"] or {}
    counts = {"walls": len(walls), "rooms": len(rooms), "rooms_void": len(plan["rooms"]) - len(rooms),
              "rooms_unbounded": len(rooms) - len(bounded), "rooms_with_polygon": len(with_poly), "rooms_labelled": len(labelled), "openings": len(plan["openings"]),
              "floors": len(plan["floors"]), "panos": len(plan["panos"]), "polygon_area_mismatch": len(off),
              "edges_dropped": dropped}
    q = {"walls": len(walls) >= 3,
         "polygons": bool(bounded) and len(with_poly) >= 0.5 * len(bounded),
         "openings": bool(plan["openings"]) and len(walls) >= 3,
         "labels": bool(rooms) and len(labelled) >= 0.5 * len(rooms),
         "georef": None not in (geo.get("lat"), geo.get("lon"), geo.get("yaw_deg"))}
    notes = []
    if not q["walls"]:
        notes.append("no wall graph: room outlines, openings and the dollhouse are unavailable; rooms have areas only")
    else:
        if len(with_poly) < len(bounded):
            notes.append(f"{len(bounded) - len(with_poly)} of {len(bounded)} rooms with a boundary did not form an outline")
        if len(bounded) < len(rooms):
            notes.append(f"{len(rooms) - len(bounded)} rooms have no boundary (outdoor or unscanned areas)")
    if off:
        notes.append(f"{len(off)} room outlines differ from Matterport's floor area by more than {AREA_TOLERANCE:.0%}")
    if q["walls"] and not plan["openings"]:
        notes.append("walls but no doors or windows recorded")
    if rooms and not q["labels"]:
        notes.append("rooms are not labelled")
    if not q["georef"]:
        notes.append("no usable geolocation or compass rotation")
    if dropped:
        notes.append(f"{dropped} wall edges referenced a missing vertex and were dropped")
    return {**q, "counts": counts, "notes": notes}
