"""RoomPlan export (iPhone LiDAR) to ScanPlan (Contract 1).

The iPhone app sends `JSONEncoder().encode(capturedRoom)` or a `CapturedStructure` (several rooms, several
storeys). The format was checked against Apple's own decoder in the iOS 26 simulator on 2026-11-14:

  surface  {identifier, parentIdentifier, category: {"wall": {}} | {"door": {"isOpen": true}} | {"window": {}} |
            {"opening": {}} | {"floor": {}}, confidence: {"high": {}}, dimensions: [w, h, 0],
            transform: 16 floats column-major, polygonCorners, completedEdges, curve, story}
  object   {identifier, parentIdentifier, category: {"bathtub": {}}, confidence, dimensions: [w, h, d],
            transform, attributes, story}
  section  {label: "bedroom" | "bathroom" | "kitchen" | "livingRoom" | "diningRoom" | "unidentified",
            center: [x, y, z], story}
  room     {version, identifier, story, walls, doors, windows, openings, objects, floors, sections,
            referenceOriginTransform}
  structure {version, rooms: [room], walls, doors, windows, openings, objects, ...}  (surfaces merged, top level)

RoomPlan's world is ARKit's: metres, y up. ScanPlan is x, y on the floor, z up: (X, Y, Z) -> (X, -Z, Y), shifted so
the lowest floor is z = 0. A surface's local x axis runs along it (dimensions[0] is its width), y is up.

Rooms come from the walls: every closed face the walls enclose on a storey is a room (the same polygonize the
Matterport normalizer uses), labelled by RoomPlan's sections, else by the objects in it. Fields beyond Contract 1:
`objects` (furniture and fixtures with real sizes), `openings[].is_open`, `label_source: "roomplan"`.
"""
from __future__ import annotations

import math
from statistics import median

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

from ..scanplan import SCHEMA, _exterior, _quality

SNAP_M = 0.15          # wall ends this close are one corner
EXTEND_M = 0.08        # each wall is lengthened this much so a wall that stops short of another still meets it
MIN_ROOM_M2 = 0.6      # smaller enclosed faces are gaps between walls, not rooms
ATTACH_M = 0.35        # a door or window this close to a wall (in plan) sits in it
PROBE_M = 0.3          # how far either side of a door to look for the room it opens into
WALL_THICKNESS_M = 0.12  # shortcut: RoomPlan does not measure wall thickness; a typical interior stud wall
SURFACES = ("walls", "doors", "windows", "openings")
OPENING_TYPE = {"door": "doorway", "window": "window", "opening": "opening"}
SECTION_LABEL = {"bedroom": "Bedroom", "bathroom": "Bathroom", "kitchen": "Kitchen", "livingRoom": "Living Room",
                 "diningRoom": "Dining Room"}
OBJECT_LABEL = {"storage": "Storage", "refrigerator": "Refrigerator", "stove": "Stove", "bed": "Bed", "sink": "Sink",
                "washerDryer": "Washer or dryer", "toilet": "Toilet", "bathtub": "Bathtub", "oven": "Oven",
                "dishwasher": "Dishwasher", "table": "Table", "sofa": "Sofa", "chair": "Chair",
                "fireplace": "Fireplace", "television": "Television", "stairs": "Stairs"}
# a room with one of these objects (first match wins) gets this label when RoomPlan gave no section for it
ROOM_BY_OBJECT = [("toilet", "Bathroom"), ("bathtub", "Bathroom"), ("bed", "Bedroom"), ("stove", "Kitchen"),
                  ("oven", "Kitchen"), ("refrigerator", "Kitchen"), ("dishwasher", "Kitchen"),
                  ("washerDryer", "Laundry"), ("sofa", "Living Room"), ("television", "Living Room"),
                  ("fireplace", "Living Room"), ("table", "Dining Room")]


class ExportError(ValueError):
    """The upload is not a RoomPlan export this converter can read."""


def _tag(v) -> str | None:
    """{"door": {"isOpen": true}} -> "door"; a plain string passes through."""
    if isinstance(v, dict) and v:
        return next(iter(v))
    return v if isinstance(v, str) else None


def _matrix(t) -> list[float]:
    """A column-major 4x4 as 16 numbers, flat or nested."""
    if isinstance(t, list) and len(t) == 4 and all(isinstance(c, list) for c in t):
        t = [v for c in t for v in c]
    if not isinstance(t, list) or len(t) != 16:
        raise ExportError("a transform is not 16 numbers")
    return [float(v) for v in t]


def _pose(t: list) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Position and local x axis, in ScanPlan axes (before the z shift), from a column-major 4x4."""
    t = _matrix(t)
    to_plan = lambda X, Y, Z: (X, -Z, Y)  # noqa: E731
    return to_plan(t[12], t[13], t[14]), to_plan(t[0], t[1], t[2])


def _surfaces(export: dict) -> dict[str, list[dict]]:
    if "rooms" in export:  # CapturedStructure: surfaces are merged at the top; floors and sections stay per room
        out = {k: list(export.get(k) or []) for k in (*SURFACES, "objects")}
        out["floors"] = [s for r in export["rooms"] for s in r.get("floors") or []]
        out["sections"] = [s for r in export["rooms"] for s in r.get("sections") or []]
        if not out["walls"]:
            for k in (*SURFACES, "objects"):
                out[k] = [s for r in export["rooms"] for s in r.get(k) or []]
        return out
    return {k: list(export.get(k) or []) for k in (*SURFACES, "objects", "floors", "sections")}


def _faces(segs: list[tuple]) -> list[Polygon]:
    lines = []
    for a, b in segs:
        d = math.dist(a, b)
        if d < 1e-6:
            continue
        ux, uy = (b[0] - a[0]) / d, (b[1] - a[1]) / d
        lines.append(LineString([(a[0] - ux * EXTEND_M, a[1] - uy * EXTEND_M), (b[0] + ux * EXTEND_M, b[1] + uy * EXTEND_M)]))
    if not lines:
        return []
    faces = [orient(f, 1.0) for f in polygonize(unary_union(lines)) if f.area >= MIN_ROOM_M2]
    return sorted(faces, key=lambda f: -f.area)


def _snap(points: list[list[float]]) -> None:
    """Move wall ends within SNAP_M of each other onto their mean, in place."""
    groups: list[list[list[float]]] = []
    for p in points:
        g = next((g for g in groups if math.dist(g[0], p) <= SNAP_M), None)
        (g.append(p) if g else groups.append([p]))
    for g in groups:
        mx, my = sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g)
        for p in g:
            p[0], p[1] = mx, my


def _rect(poly: Polygon) -> tuple[float, float]:
    """Width and depth of the smallest rectangle around the outline, longer side first."""
    c = list(poly.minimum_rotated_rectangle.exterior.coords)
    a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
    return max(a, b), min(a, b)


def _seg_dist(p, a, b) -> tuple[float, float]:
    """Distance from p to segment ab, and the position along it (0..1)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy)), t


MAX_WALLS = 1500  # a whole house is under 200; converting is quadratic in walls


def convert(export: dict, sid: str, *args, **kwargs) -> dict:
    """One RoomPlan export to a ScanPlan (see _convert). Any malformed field is an ExportError, never a crash."""
    from shapely.errors import ShapelyError
    try:
        return _convert(export, sid, *args, **kwargs)
    except ExportError:
        raise
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, ShapelyError) as e:
        raise ExportError(f"the export is malformed ({type(e).__name__}); send RoomPlan's own JSON unchanged") from e


def _convert(export: dict, sid: str, name: str | None = None, *, kind: str | None = None, address: str | None = None,
            city: str | None = None, geo: dict | None = None, created: str | None = None, notes: str | None = None) -> dict:
    """One RoomPlan export to a ScanPlan. `geo` is the phone's reading at the scan: {lat, lon, altitude,
    heading_deg (compass, of camera_forward), camera_forward: [x, y] and camera_position: [x, y] in RoomPlan's
    world X and Z, or omitted to mean the scan's start}. Raises ExportError when there is nothing to convert."""
    if not isinstance(export, dict):
        raise ExportError("the export is not a JSON object")
    s = _surfaces(export)
    if not s["walls"]:
        raise ExportError("the export has no walls: scan at least one room to the end")
    if len(s["walls"]) > MAX_WALLS:
        raise ExportError(f"the export has more than {MAX_WALLS} walls")

    def read(item: dict) -> dict:
        (x, y, z), (ax, ay, _az) = _pose(item.get("transform"))
        dims = item.get("dimensions") or [0, 0, 0]
        n = math.hypot(ax, ay) or 1.0
        return {"id": str(item.get("identifier")), "parent": item.get("parentIdentifier"), "story": int(item.get("story") or 0),
                "pos": [x, y, z], "axis": (ax / n, ay / n), "w": float(dims[0]), "h": float(dims[1]),
                "d": float(dims[2]) if len(dims) > 2 else 0.0, "cat": _tag(item.get("category")),
                "is_open": (item.get("category") or {}).get("door", {}).get("isOpen") if isinstance(item.get("category"), dict) else None,
                "confidence": _tag(item.get("confidence"))}

    walls_raw = [read(w) for w in s["walls"]]
    stories = sorted({w["story"] for w in walls_raw})
    base_by_story = {st: min(w["pos"][2] - w["h"] / 2 for w in walls_raw if w["story"] == st) for st in stories}
    base = min(base_by_story.values())
    fid = lambda st: f"f{st}"  # noqa: E731
    floors = [{"id": fid(st), "label": f"Floor {i + 1}" if len(stories) > 1 else "Floor 1", "sequence": i,
               "elevation": round(base_by_story[st] - base, 3), "elevation_source": "roomplan"}
              for i, st in enumerate(stories)]

    walls = []
    for i, w in enumerate(walls_raw):
        (x, y, _), (ux, uy) = w["pos"], w["axis"]
        h = w["w"] / 2
        walls.append({"id": f"w{i}", "floor": fid(w["story"]), "a": [x - ux * h, y - uy * h], "b": [x + ux * h, y + uy * h],
                      "type": "wall", "thickness": WALL_THICKNESS_M, "length": 0.0, "rooms": [], "openings": [],
                      "height": round(w["h"], 3), "source": "roomplan", "_uuid": w["id"]})
    for st in stories:
        _snap([p for w in walls if w["floor"] == fid(st) for p in (w["a"], w["b"])])
    for w in walls:
        w["length"] = math.dist(w["a"], w["b"])
    walls = [w for w in walls if w["length"] >= 0.05]

    # rooms: the faces the walls enclose
    rooms, polys = [], {}
    for st in stories:
        on = [w for w in walls if w["floor"] == fid(st)]
        faces = _faces([(w["a"], w["b"]) for w in on])
        if not faces:  # walls that never close (a partial scan): fall back to RoomPlan's floor outlines
            faces = _floor_faces(s["floors"], st)
        heights = [w["height"] for w in on]
        for f in faces:
            rid = f"r{len(rooms)}"
            edge = f.exterior.buffer(0.1)
            bound = [w["id"] for w in on if LineString([w["a"], w["b"]]).intersection(edge).length > 0.3]
            for w in on:
                if w["id"] in bound:
                    w["rooms"].append(rid)
            rh = [w["height"] for w in on if w["id"] in bound] or heights
            wd, dp = _rect(f)
            polys[rid] = f
            rooms.append({"id": rid, "floor": fid(st), "label": None, "label_confidence": None, "label_source": None,
                          "polygon": [[x, y] for x, y in f.exterior.coords[:-1]], "extra_polygons": [], "hole_polygons": [],
                          "area": round(f.area, 3), "area_source": "polygon", "height": round(median(rh), 3) if rh else None,
                          "width": round(wd, 3), "depth": round(dp, 3),
                          "center": list(f.representative_point().coords[0]), "center_source": "polygon",
                          "walls": bound, "holes": [], "polygon_source": "roomplan", "_outline_area": f.area})

    def room_at(pt, floor) -> str | None:
        p = Point(pt)
        return next((r["id"] for r in rooms if r["floor"] == floor and polys[r["id"]].contains(p)), None)

    # doors, windows, openings: in the wall RoomPlan names as parent, else the nearest wall in line with them
    by_uuid = {w["_uuid"]: w for w in walls}
    openings = []
    for kind_key in ("doors", "windows", "openings"):
        for item in s[kind_key]:
            o = read(item)
            floor = fid(o["story"])
            c = o["pos"][:2]
            wall = by_uuid.get(o["parent"])
            if wall is None:
                near = [(d, w) for w in walls if w["floor"] == floor
                        for d, _ in [_seg_dist(c, w["a"], w["b"])] if d <= ATTACH_M]
                wall = min(near, key=lambda dw: dw[0])[1] if near else None
            if wall is not None:  # sit the opening on the wall's centre line
                _, t = _seg_dist(c, wall["a"], wall["b"])
                c = [wall["a"][0] + (wall["b"][0] - wall["a"][0]) * t, wall["a"][1] + (wall["b"][1] - wall["a"][1]) * t]
            nx, ny = (-o["axis"][1], o["axis"][0])
            sides = [room_at((c[0] + sg * nx * PROBE_M, c[1] + sg * ny * PROBE_M), floor) for sg in (1, -1)]
            oid = f"o{len(openings)}"
            openings.append({"id": oid, "wall": wall["id"] if wall else None, "floor": floor,
                             "type": OPENING_TYPE.get(o["cat"], "opening"), "width": round(o["w"], 3), "height": round(o["h"], 3),
                             "sill": round(o["pos"][2] - o["h"] / 2 - base, 3), "center": c,
                             "rooms": list(dict.fromkeys(r for r in sides if r)), "is_open": o["is_open"],
                             "confidence": o["confidence"], "source": "roomplan"})
            if wall is not None:
                wall["openings"].append(oid)

    # objects: furniture and fixtures with their measured sizes
    objects = []
    for i, item in enumerate(s["objects"]):
        o = read(item)
        floor = fid(o["story"])
        objects.append({"id": f"x{i}", "floor": floor, "room": room_at(o["pos"][:2], floor), "category": o["cat"],
                        "label": OBJECT_LABEL.get(o["cat"], o["cat"]),
                        "center": [o["pos"][0], o["pos"][1], round(o["pos"][2] - base, 3)],
                        "size": [round(o["w"], 3), round(o["d"], 3), round(o["h"], 3)],  # width, depth, height
                        "yaw_deg": round(math.degrees(math.atan2(o["axis"][1], o["axis"][0])), 1),
                        "confidence": o["confidence"], "source": "roomplan"})

    # labels: RoomPlan's sections first, then what is in the room
    for sec in s["sections"]:
        label = SECTION_LABEL.get(_tag(sec.get("label")) or "")
        X, _, Z = (sec.get("center") or [0, 0, 0])[:3]
        cx, cy = X, -Z
        rid = room_at((cx, cy), fid(int(sec.get("story") or 0)))
        r = next((r for r in rooms if r["id"] == rid), None)
        if label and r and not r["label"]:
            r.update(label=label, label_confidence=0.8, label_source="roomplan")
    multi = len(stories) > 1
    for r in rooms:
        cats = {o["category"] for o in objects if o["room"] == r["id"]}
        if r["label"]:
            continue
        if multi and "stairs" in cats:
            r.update(label="Staircase", label_confidence=0.6, label_source="roomplan")
            continue
        label = next((lab for cat, lab in ROOM_BY_OBJECT if cat in cats), None)
        if label:
            r.update(label=label, label_confidence=0.6, label_source="roomplan")

    for r in rooms:  # a narrow unlabelled room between two or more doors is a hallway
        doors = sum(r["id"] in o["rooms"] and o["type"] != "window" for o in openings)
        if not r["label"] and r["depth"] < 1.6 and doors >= 2:
            r.update(label="Hallway", label_confidence=0.5, label_source="roomplan")

    plan = {
        "schema": SCHEMA, "sid": sid, "name": name or "My scan", "notes": notes, "address": address, "city": city,
        "segment": kind, "created": created, "summary": None, "geo": _geo(geo),
        "ids": {"costar_property": None, "homes_listing": None, "defurnished_view": None},
        "has": {"splat": False, "defurnished": False, "openings": bool(openings),
                "room_labels": any(r["label"] for r in rooms), "objects": bool(objects)},
        "floors": floors, "walls": [{k: v for k, v in w.items() if k != "_uuid"} for w in walls],
        "openings": openings, "rooms": rooms, "panos": [], "floorplans": [], "objects": objects,
        "source": {"kind": "roomplan", "version": export.get("version"), "rooms": len(export.get("rooms") or []) or 1},
    }
    _exterior(plan, kind)
    plan["stairs"] = []
    q = _quality(plan, 0)
    for r in rooms:
        del r["_outline_area"]
    q.update(walls_source="roomplan" if q["walls"] else None, walls_confidence="high" if q["walls"] else None)
    q["counts"]["objects"] = len(objects)
    q["notes"].append("scanned with iPhone LiDAR (Apple RoomPlan): walls, doors, windows and objects are measured; "
                      f"wall thickness is not measured ({WALL_THICKNESS_M} m assumed); no panoramas, so tools that "
                      "read photos cannot run")
    if plan["geo"]:
        q["notes"].append("location and compass are the phone's own readings, not checked against an aerial footprint")
    plan["quality"] = q
    return plan


def _floor_faces(floors: list[dict], story: int) -> list[Polygon]:
    """Outlines from RoomPlan's floor surfaces: corners are in the surface's own frame, so carry them through its
    transform and keep the two horizontal axes."""
    out = []
    for f in floors:
        if int(f.get("story") or 0) != story or len(f.get("polygonCorners") or []) < 3:
            continue
        t = _matrix(f.get("transform"))
        pts = []
        for x, y, z in (c[:3] for c in f["polygonCorners"]):
            X = t[0] * x + t[4] * y + t[8] * z + t[12]
            Z = t[2] * x + t[6] * y + t[10] * z + t[14]
            pts.append((X, -Z))
        poly = Polygon(pts).buffer(0)
        if poly.area >= MIN_ROOM_M2:
            out.append(orient(poly, 1.0) if poly.geom_type == "Polygon" else orient(max(poly.geoms, key=lambda g: g.area), 1.0))
    return out


def _geo(g: dict | None) -> dict | None:
    """The phone's GPS and compass as Contract 1 geo: ENU = Rz(yaw) p + t (threshold.geometry.georef)."""
    if not g or g.get("lat") is None or g.get("lon") is None:
        return None
    yaw = None
    t = {"x": 0.0, "y": 0.0}
    if g.get("heading_deg") is not None:
        fx, fz = g.get("camera_forward") or (0.0, -1.0)  # RoomPlan world X, Z; the scan starts facing -Z
        scan_angle = math.degrees(math.atan2(-fz, fx))
        yaw = ((90.0 - float(g["heading_deg"])) - scan_angle + 180.0) % 360.0 - 180.0
        cx, cz = g.get("camera_position") or (0.0, 0.0)
        c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        px, py = cx, -cz
        t = {"x": -(px * c - py * s_), "y": -(px * s_ + py * c)}  # the phone stood at the GPS point
    return {"lat": g["lat"], "lon": g["lon"], "altitude": g.get("altitude"), "yaw_deg": yaw, "translation": t,
            "source": "phone", "accuracy_m": g.get("accuracy_m"), "heading_accuracy_deg": g.get("heading_accuracy_deg")}
