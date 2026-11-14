"""Panorama readers: ask the vision model structured questions about panoramas and return located answers.

Each call sends several cube faces at once and gets JSON back (labels, boxes, confidence classes). Boxes
are turned into Contract 3 anchors by `locate`. Numbers never come from the model: it chooses and labels;
positions come from the projection and the ScanPlan.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from shapely.geometry import Point, Polygon

from ..sources import matterport as mp
from . import locate as loc
from . import projection as pj
from .model import BOX, CONCURRENCY, CONFIDENCE, ask, jpeg

FACE_PX = 1000  # faces are sent at this size, so model boxes are in [0, 1000] pixels of each face
ROOM_PX = 768

HOME_LABELS = ["Balcony", "Basement", "Bathroom", "Bedroom", "Closet", "Dining Room", "Entrance", "Exercise Room",
               "Family Room", "Game Room", "Garage", "Hallway", "Kitchen", "Laundry", "Living Room", "Loft", "Office",
               "Pantry", "Patio", "Staircase", "Utility Room", "Other"]
COMMERCIAL_LABELS = ["open office", "private office", "conference room", "reception", "kitchen or break room",
                     "restroom", "corridor", "storage", "server or electrical room", "lobby", "gym", "pool", "laundry",
                     "mail room", "leasing office", "retail floor", "warehouse floor", "loading area", "stairwell",
                     "elevator lobby", "phone booth", "lounge or clubroom", "business center", "media room",
                     "playground", "outdoor area", "other"]
# Matterport labels that name the same kind of space; used only for the lenient agreement count.
SAME = [{"Living Room", "Family Room"}, {"Laundry", "Utility Room"}, {"Entrance", "Hallway"}]

OBJECT_LABELS = ["smoke alarm", "sprinkler head", "exit sign", "fire extinguisher", "electrical panel", "water heater",
                 "gas stove", "grab bar", "step or threshold", "stairs", "ramp", "kitchen hood", "sink", "toilet",
                 "bathtub", "shower", "washer", "dryer", "outlet near the floor", "large furniture"]

CUBE_NOTE = ("The images are faces of one 360-degree cube panorama taken from a single point, each a square "
             "{px} by {px} pixels. {faces}")
FACE_DESC = {0: "face 0 looks straight up at the ceiling", 1: "face 1 looks horizontally",
             2: "face 2 looks horizontally, turned 90 degrees right of face 1", 3: "face 3 looks horizontally, opposite face 1",
             4: "face 4 looks horizontally, 90 degrees left of face 1", 5: "face 5 looks straight down at the floor"}


def _faces(sid: str, pano: str, faces, px: int, view: str = "furnished") -> list[bytes]:
    return [jpeg(mp.pano_face(sid, pano, f, "2k", view), px) for f in faces]


def _describe(faces) -> str:
    return "; ".join(f"image {i + 1} is {FACE_DESC[f]}" for i, f in enumerate(faces)) + "."


def room_panos(plan: dict, room: dict) -> list[dict]:
    """Panoramas standing in a room, the one nearest the room's centre first. Matterport leaves `room` empty on
    many panoramas in small commercial rooms (72 of 81 in the private offices of one coworking floor), so a panorama
    with no room that stands inside the room's outline on the same floor counts too."""
    poly = room.get("polygon") or []
    outline = Polygon(poly) if len(poly) >= 3 else None
    ps = [p for p in plan["panos"] if p.get("rotation") and (
        p.get("room") == room["id"] or (not p.get("room") and outline is not None and p.get("floor") == room.get("floor")
                                        and outline.contains(Point(p["position"][:2]))))]
    if poly:
        c = np.mean(np.array(poly, float), axis=0)
        ps.sort(key=lambda p: float(np.hypot(p["position"][0] - c[0], p["position"][1] - c[1])))
    return ps


def _rooms_to_read(plan: dict) -> list[dict]:
    return [r for r in plan["rooms"] if r.get("label") != "Void" and room_panos(plan, r)]


def _spread(ps: list[dict], n: int) -> list[dict]:
    """The first panorama (the central one) and then those farthest from the ones already chosen."""
    chosen = ps[:1]
    while len(chosen) < min(n, len(ps)):
        chosen.append(max((p for p in ps if p not in chosen), key=lambda p: min(
            math.dist(p["position"][:2], c["position"][:2]) for c in chosen)))
    return chosen


def _parallel(fn, items):
    with ThreadPoolExecutor(CONCURRENCY) as ex:
        return list(ex.map(fn, items))


# ---- room labels ------------------------------------------------------------------------------

def label_rooms(plan: dict, rooms: list[str] | None = None, *, labels: list[str] | None = None,
                context: str | None = None, hints: dict[str, str] | None = None,
                examples: list[dict] | None = None, views: int = 1, many: int = 4,
                large_m2: float = 150) -> list[dict]:
    """A room type for every room that has a panorama, from the panorama nearest its centre. A room of at least
    `large_m2` with at least `many` panoramas (an open floor, a courtyard) is read from `views` of them in one
    call, the central one and then those farthest apart, so one corridor view does not decide a large room.
    Below that size, extra views made answers worse (mid-size coworking rooms turned into corridors), so
    smaller rooms keep the single central view.

    Homes (scans with Matterport labels) use Matterport's label set, and the model is not shown
    Matterport's label, so `agrees` is an honest check of one against the other. Other scans use a
    commercial label set. `labels` overrides the set. `context` is a sentence about the building (say, the
    property type in its CoStar record); `hints` maps a room id to measured facts about that room (area,
    doors, windows, position); `examples` are rooms a person labelled, [{sid, pano, face, label}], sent
    after the room's faces as references. All three are evidence the model weighs, never labels it copies."""
    home = bool(plan["has"].get("room_labels"))
    labels = labels or (HOME_LABELS if home else COMMERCIAL_LABELS)
    todo = [r for r in _rooms_to_read(plan) if rooms is None or r["id"] in rooms]
    faces = [1, 2, 3, 4]
    examples = examples or []
    ref_imgs = [jpeg(mp.pano_face(e["sid"], e["pano"], e["face"], "2k"), 512) for e in examples]
    ref_note = "".join(f" Image {5 + i} is a reference: a room elsewhere in this property that a person labelled "
                       f"'{e['label']}'." for i, e in enumerate(examples))
    def schema(n_img: int) -> dict:
        return {"type": "object", "additionalProperties": False, "required": ["label", "confidence", "evidence_image", "reason"],
                "properties": {"label": {"type": "string", "enum": labels}, "confidence": CONFIDENCE,
                               "evidence_image": {"type": "integer", "enum": list(range(1, n_img + 1))},
                               "reason": {"type": "string", "description": "One short sentence naming what you saw."}}}

    def one(room):
        ps = room_panos(plan, room)
        big = len(ps) >= many and (room.get("area") or 0) >= large_m2
        pick = _spread(ps, views) if views > 1 and big else ps[:1]
        hint = (f" Measured facts about this room from the floor plan: {hints[room['id']]}. Use them as evidence "
                "alongside the images; what you see decides." if hints and hints.get(room["id"]) else "")
        where = " The camera stands inside one room of a " + ("home" if home else "commercial building") + \
            (f" ({context})" if context else "")
        if len(pick) == 1:
            prompt = (CUBE_NOTE.format(px=ROOM_PX, faces=_describe(faces)) + ref_note + where +
                      ". What type of room is the camera standing in? Judge the room the camera is in, not rooms seen "
                      "through doorways. Pick the image that shows it best." + hint)
            imgs = _faces(plan["sid"], pick[0]["id"], faces, ROOM_PX)
        else:
            n = len(pick)
            prompt = (f"The images come from {n} camera positions inside the same large room, four horizontal views each, "
                      f"looking in four directions 90 degrees apart: images 1-4 from the first position" +
                      "".join(f", {4 * i + 1}-{4 * i + 4} from position {i + 1}" for i in range(1, n)) + "." +
                      "".join(f" Image {4 * n + 1 + i} is a reference: a room elsewhere in this property that a person "
                              f"labelled '{e['label']}'." for i, e in enumerate(examples)) + where +
                      ". What is the main use of this room as a whole? A large room can hold corridors, desks and seating "
                      "at once: name what most of its floor serves. Pick the image that shows it best." + hint)
            imgs = [img for p in pick for img in _faces(plan["sid"], p["id"], faces, 512)]
        a = ask(imgs + ref_imgs, prompt, schema(len(imgs)), key=f"label_room/{plan['sid']}/{pick[0]['id']}")
        k = a["evidence_image"] - 1
        pano = pick[k // 4]
        out = {"room": room["id"], "label": a["label"], "confidence": a["confidence"], "reason": a["reason"],
               "evidence": {"sid": plan["sid"], "pano": pano["id"], "face": faces[k % 4]}, "views": len(pick),
               "source": {"layer": "model", "method": "vision", "confidence": a["confidence"],
                          "note": f"Vision model on {len(pick)} panorama{'s' if len(pick) > 1 else ''} of the room, faces 1-4"}}
        if home and labels is HOME_LABELS:
            mm = room.get("label")
            out["matterport_label"] = mm
            out["agrees"] = mm == a["label"]
            out["agrees_lenient"] = out["agrees"] or any({mm, a["label"]} <= s for s in SAME)
        return out

    return _parallel(one, todo)


def _peek_view(plan: dict, room: dict, max_m: float = 8.0) -> tuple[dict, int, float, float] | None:
    """The best outside panorama to see into a room no panorama stands in: one that looks squarely at one of the
    room's doorways from 1 to `max_m` metres away. Without a wall graph, the nearest panorama to the room's
    centre. Returns (pano, face, u, v) with (u, v) in ROOM_PX pixels of the face, or None."""
    walls = {w["id"]: w for w in plan.get("walls") or []}
    targets = []
    for o in plan.get("openings") or []:
        if o["type"] != "window" and room["id"] in (o.get("rooms") or []) and o.get("center"):
            w = walls.get(o.get("wall"))
            n = None
            if w:
                dx, dy = w["b"][0] - w["a"][0], w["b"][1] - w["a"][1]
                n = np.array([-dy, dx]) / (math.hypot(dx, dy) or 1)
            targets.append((np.array(o["center"], float), n))
    if not targets and room.get("center"):
        targets.append((np.array(room["center"], float), None))
    best = None
    for p in plan["panos"]:
        if not p.get("rotation") or p.get("floor") != room.get("floor"):
            continue
        xy = np.array(p["position"][:2], float)
        for c, n in targets:
            v = c - xy
            d = float(np.linalg.norm(v))
            if not 1.0 <= d <= max_m:
                continue
            square = abs(float(v @ n)) / d if n is not None else 1.0
            score = d / max(square, 0.2)
            if best is None or score < best[0]:
                best = (score, p, c)
    if not best:
        return None
    _, p, c = best
    face, u, v = pj.point_to_face_pixel([c[0], c[1], p["position"][2]], p["position"], ROOM_PX, p["rotation"])
    return (p, face, u, v) if 1 <= face <= 4 else None


def peek_rooms(plan: dict, rooms: list[str], *, labels: list[str] | None = None, context: str | None = None,
               hints: dict[str, str] | None = None) -> list[dict]:
    """Label rooms that no panorama stands in, through a doorway, from the panorama outside that looks most
    squarely at it. The doorway is ringed in red on the one face sent. A room seen from outside is never called
    with high confidence: high becomes medium. Same shape as `label_rooms`, plus `peek: True`."""
    import io

    from PIL import Image, ImageDraw

    labels = labels or COMMERCIAL_LABELS
    schema = {"type": "object", "additionalProperties": False, "required": ["label", "confidence", "visible", "reason"],
              "properties": {"label": {"type": "string", "enum": labels}, "confidence": CONFIDENCE,
                             "visible": {"type": "boolean", "description": "Can you see into the ringed room at all?"},
                             "reason": {"type": "string", "description": "One short sentence naming what you saw."}}}
    by_id = {r["id"]: r for r in plan["rooms"]}

    def one(rid):
        view = _peek_view(plan, by_id[rid])
        if not view:
            return None
        pano, face, u, v = view
        im = Image.open(io.BytesIO(jpeg(mp.pano_face(plan["sid"], pano["id"], face, "2k"), ROOM_PX))).convert("RGB")
        ImageDraw.Draw(im).ellipse([u - 45, v - 45, u + 45, v + 45], outline=(255, 0, 0), width=5)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
        prompt = ("The image is one horizontal face of a 360-degree panorama, taken from outside the room in question. "
                  "The red ring marks the doorway into that room. What type of room lies through the ringed doorway? "
                  "Judge only that room, from what is visible through the doorway (furniture, fixtures, finishes, size). "
                  "If the door is closed or you cannot see in, say visible false and use low confidence. "
                  "The building is a " + ("home" if labels is HOME_LABELS else "commercial building") +
                  (f" ({context})" if context else "") + "." +
                  (f" Measured facts about that room from the floor plan: {hints[rid]}." if hints and hints.get(rid) else ""))
        a = ask([buf.getvalue()], prompt, schema, key=f"peek_room/{plan['sid']}/{rid}")
        conf = "medium" if a["confidence"] == "high" else a["confidence"]
        if not a["visible"]:
            conf = "low"
        return {"room": rid, "label": a["label"], "confidence": conf, "reason": a["reason"], "peek": True,
                "evidence": {"sid": plan["sid"], "pano": pano["id"], "face": face},
                "source": {"layer": "model", "method": "vision", "confidence": conf,
                           "note": f"Vision model through a doorway, from panorama {pano['id']} face {face}"}}

    return [x for x in _parallel(one, rooms) if x]


FLOOR_FINISHES = ["carpet", "hardwood or wood-look", "tile or stone", "polished or sealed concrete", "vinyl or linoleum",
                  "rubber or gym flooring", "outdoor paving or deck", "artificial turf or grass", "cannot tell"]


def floor_finishes(plan: dict, rooms: list[str] | None = None, batch: int = 8, views: int = 1, many: int = 4,
                   large_m2: float = 150) -> dict[str, dict]:
    """Floor finish per room, from the straight-down face of its central panorama. Several views per call
    (`batch`), so a whole suite costs a call or two. A room of at least `large_m2` with at least `many`
    panoramas is looked at from up to `views` spots and gets `shares` (finish -> fraction of those spots).
    Returns room id -> {finish, shares, confidence, evidence: {sid, pano, face}}."""
    todo = [r for r in _rooms_to_read(plan) if rooms is None or r["id"] in rooms]
    items = []
    for r in todo:
        ps = room_panos(plan, r)
        big = views > 1 and len(ps) >= many and (r.get("area") or 0) >= large_m2
        items += [(r, p) for p in (_spread(ps, views) if big else ps[:1])]
    schema = {"type": "object", "additionalProperties": False, "required": ["floors"], "properties": {"floors": {
        "type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "required": ["image", "finish", "confidence"],
                                   "properties": {"image": {"type": "integer"}, "finish": {"type": "string", "enum": FLOOR_FINISHES},
                                                  "confidence": CONFIDENCE}}}}}

    def one(chunk):
        prompt = (f"Each of the {len(chunk)} images looks straight down at the floor from a 360-degree camera on a "
                  "tripod at a different spot in one building (the tripod's shadow or base may show in the centre). "
                  "For every image, name the floor finish. Rugs on top of a floor do not count; judge the floor around "
                  "them. Answer once per image, by image number starting at 1.")
        a = ask([jpeg(mp.pano_face(plan["sid"], p["id"], 5, "2k"), 512) for _, p in chunk],
                prompt, schema, key=f"floor_finish/{plan['sid']}/{chunk[0][1]['id']}")
        got = {f["image"]: f for f in a["floors"]}
        return [(r, p, got[i + 1]) for i, (r, p) in enumerate(chunk) if i + 1 in got]

    seen: dict[str, list] = {}
    for part in _parallel(one, [items[i:i + batch] for i in range(0, len(items), batch)]):
        for r, p, g in part:
            seen.setdefault(r["id"], []).append((p, g))
    rank = {"high": 0, "medium": 1, "low": 2}
    out: dict[str, dict] = {}
    for rid, xs in seen.items():
        n: dict[str, int] = {}
        for _, g in xs:
            n[g["finish"]] = n.get(g["finish"], 0) + 1
        top = max(n, key=n.get)
        out[rid] = {"finish": top, "shares": {k: v / len(xs) for k, v in n.items()},
                    "confidence": max((g["confidence"] for _, g in xs), key=rank.get),
                    "evidence": {"sid": plan["sid"], "pano": next(p["id"] for p, g in xs if g["finish"] == top), "face": 5}}
    return out


# ---- objects ----------------------------------------------------------------------------------

def _finding(plan, pano, det, face, idx, title, detail) -> dict:
    b = det["box"]
    box = [b["x0"], b["y0"], b["x1"], b["y1"]]
    where = loc.locate(plan, pano, face, box, FACE_PX)
    place = (f"position where the ray meets the room {where['surface']} ({where['confidence']} confidence)"
             if where["point_anchor"] else "direction only: the ray met no known room surface")
    finding = {
        "id": idx, "title": title, "status": "unknown", "detail": detail,
        "anchor": where["point_anchor"] or where["anchor"],
        "source": {"layer": "model", "method": "vision", "confidence": det["confidence"],
                   "note": f"Vision model on panorama {pano['id']} face {face}; {place}"},
        "media": [{"kind": "pano", "ref": f"{plan['sid']}/{pano['id']}/{face}", "box": [round(v / FACE_PX, 4) for v in box]}],
    }
    ray = (pano["position"], pj.direction(where["anchor"]["yaw_deg"], where["anchor"]["pitch_deg"]))
    return {"label": det["label"], "room": pano.get("room"), "pano_anchor": where["anchor"], "ray": ray,
            "distance_m": where["distance_m"],
            "point": where["point_anchor"]["point"] if where["point_anchor"] else None,
            "surface": where["surface"], "finding": finding}


def find_objects(plan: dict, labels: list[str] | None = None, panos: list[str] | None = None,
                 max_panos: int = 12, merge_m: float = 0.6) -> list[dict]:
    """Locate named things. By default reads the central panorama of each room (at most `max_panos`), all six
    faces at once, so the ceiling face finds smoke alarms and sprinklers. The same label seen from two
    panoramas within `merge_m` metres is reported once, with both views as media."""
    labels = labels or OBJECT_LABELS
    if panos:
        chosen = [p for p in plan["panos"] if p["id"] in panos and p.get("rotation")]
    else:
        chosen = [room_panos(plan, r)[0] for r in _rooms_to_read(plan)]
    chosen = chosen[:max_panos]
    faces = [0, 1, 2, 3, 4, 5]
    schema = {"type": "object", "additionalProperties": False, "required": ["detections"], "properties": {"detections": {
        "type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "required": ["label", "image", "box", "confidence", "note"],
                                   "properties": {"label": {"type": "string", "enum": labels},
                                                  "image": {"type": "integer", "enum": [1, 2, 3, 4, 5, 6]},
                                                  "box": BOX, "confidence": CONFIDENCE,
                                                  "note": {"type": "string", "description": "A few words: what it is and where."}}}}}}
    prompt = (CUBE_NOTE.format(px=FACE_PX, faces=_describe(faces)) +
              " Find every instance of these things: " + ", ".join(labels) + ". "
              "Give a tight box in pixel coordinates of the image it appears in (x0, y0 top left, x1, y1 bottom right). "
              "An object cut by the edge of an image may appear in two images: box it in the image that shows most of it. "
              "Report only what you can see; return an empty list when none are visible. "
              "'outlet near the floor' means an electrical outlet within about knee height. "
              "'large furniture' means sofas, beds, wardrobes, tables and the like.")

    def one(pano):
        a = ask(_faces(plan["sid"], pano["id"], faces, FACE_PX), prompt, schema,
                key=f"find_objects/{plan['sid']}/{pano['id']}")
        return pano, a["detections"]

    found: list[dict] = []
    for pano, dets in _parallel(one, chosen):
        for det in dets:
            face = faces[det["image"] - 1]
            found.append(_finding(plan, pano, det, face, f"{det['label'].replace(' ', '_')}_{len(found) + 1}",
                                  det["label"], det["note"]))
    return _merge(found, merge_m)


def rays_meet(o1, d1, o2, d2, max_gap: float = 0.25) -> tuple[float, float] | None:
    """Ranges along two rays to their closest approach, if the rays pass within `max_gap` metres in front
    of both cameras. Used to recognise one object seen from two panoramas."""
    o1, d1, o2, d2 = (np.asarray(x, float) for x in (o1, d1, o2, d2))
    w = o1 - o2
    b = float(d1 @ d2)
    den = 1 - b * b
    if den < 1e-6:  # parallel
        return None
    t1 = (b * float(d2 @ w) - float(d1 @ w)) / den
    t2 = (float(d2 @ w) - b * float(d1 @ w)) / den
    if t1 <= 0 or t2 <= 0 or np.linalg.norm((o1 + t1 * d1) - (o2 + t2 * d2)) > max_gap:
        return None
    return t1, t2


def _same(k: dict, f: dict, merge_m: float) -> bool:
    if k["label"] != f["label"] or k["pano_anchor"]["pano"] == f["pano_anchor"]["pano"]:
        return False
    if k["point"] and f["point"] and math.dist(k["point"], f["point"]) <= merge_m:
        return True
    # The base ray may hit the wall behind a standing object; the centre rays from two panoramas still meet
    # at the object, in front of (not beyond) where each ray meets the room.
    t = rays_meet(k["ray"][0], k["ray"][1], f["ray"][0], f["ray"][1])
    return bool(t) and all(d is None or ti <= d + 0.5 for ti, d in zip(t, (k["distance_m"], f["distance_m"])))


def _merge(found: list[dict], merge_m: float) -> list[dict]:
    rank = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda f: rank[f["finding"]["source"]["confidence"]])
    kept: list[dict] = []
    for f in found:
        twin = next((k for k in kept if _same(k, f, merge_m)), None)
        if twin:
            twin["finding"]["media"] += f["finding"]["media"]
        else:
            kept.append(f)
    for k in kept:
        k.pop("ray", None)
    return kept


# ---- contents ---------------------------------------------------------------------------------

COST_CLASSES = ["under $100", "$100 to $500", "$500 to $2,000", "$2,000 to $10,000", "over $10,000"]
SIZE_CLASSES = ["hand-held", "one person carries", "two people carry", "needs a mover or is built in"]


def contents(plan: dict, room: str) -> dict:
    """The belongings in a room, each with a size class and a replacement-cost class, from the furnished
    panorama. When the scan has a defurnished view, its matching faces are sent too: anything still there
    is a fixture (part of the building), not a belonging. The defurnished view is digitally edited, so
    the split is a model judgement, labelled as such."""
    r = next(x for x in plan["rooms"] if x["id"] == room)
    pano = room_panos(plan, r)[0]
    faces = [1, 2, 3, 4, 5]
    imgs = _faces(plan["sid"], pano["id"], faces, FACE_PX)
    defurn = bool(plan["has"].get("defurnished") and plan["ids"].get("defurnished_view"))
    note = CUBE_NOTE.format(px=FACE_PX, faces=_describe(faces))
    if defurn:
        imgs += _faces(plan["sid"], pano["id"], [1, 2, 3, 4], 512, "defurnished")
        note += (" Images 6 to 9 show the same views as images 1 to 4 with the furniture digitally removed. "
                 "Anything still present in them is a fixture of the building.")
    schema = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
        "type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "required": ["name", "category", "count", "size_class", "cost_class", "fixture", "image", "box", "confidence"],
                                   "properties": {
                                       "name": {"type": "string"},
                                       "category": {"type": "string", "enum": ["furniture", "appliance", "electronics", "lighting", "decor and art", "textiles", "kitchenware", "sports and leisure", "office equipment", "other"]},
                                       "count": {"type": "integer"},
                                       "size_class": {"type": "string", "enum": SIZE_CLASSES},
                                       "cost_class": {"type": "string", "enum": COST_CLASSES, "description": "Typical replacement cost of one, new, mid-market."},
                                       "fixture": {"type": "boolean"},
                                       "image": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                                       "box": BOX, "confidence": CONFIDENCE}}}}}
    prompt = (note + " List the contents of the room the camera stands in, as an insurer's inventory: furniture, "
              "appliances, electronics, lighting, decor and other belongings. Group identical small items with a count. "
              "Mark built-in things (cabinets, counters, fitted appliances, ceiling fans) as fixtures. "
              "Box each item in one of images 1 to 5.")
    a = ask(imgs, prompt, schema, key=f"contents/{plan['sid']}/{pano['id']}")
    items = []
    for i, it in enumerate(a["items"]):
        face = faces[it["image"] - 1]
        f = _finding(plan, pano, {"label": it["name"], "box": it["box"], "confidence": it["confidence"]}, face,
                     f"item_{i + 1}", it["name"], f"{it['category']}, {it['size_class']}, {it['cost_class']}")
        items.append({k: it[k] for k in ("name", "category", "count", "size_class", "cost_class", "fixture", "confidence")}
                     | {"anchor": f["finding"]["anchor"], "media": f["finding"]["media"]})
    return {"room": room, "pano": pano["id"], "defurnished_used": defurn, "items": items,
            "source": {"layer": "model", "method": "vision", "confidence": "low",
                       "note": "Vision model inventory; cost and size are classes chosen by the model, not measurements"}}
