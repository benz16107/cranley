"""Panorama readers: ask the vision model structured questions about panoramas and return located answers.

Each call sends several cube faces at once and gets JSON back (labels, boxes, confidence classes). Boxes
are turned into Contract 3 anchors by `locate`. Numbers never come from the model: it chooses and labels;
positions come from the projection and the ScanPlan.
"""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from ..sources import matterport as mp
from . import locate as loc
from .model import BOX, CONCURRENCY, CONFIDENCE, ask, jpeg

FACE_PX = 1000  # faces are sent at this size, so model boxes are in [0, 1000] pixels of each face
ROOM_PX = 768

HOME_LABELS = ["Balcony", "Basement", "Bathroom", "Bedroom", "Closet", "Dining Room", "Entrance", "Exercise Room",
               "Family Room", "Game Room", "Garage", "Hallway", "Kitchen", "Laundry", "Living Room", "Loft", "Office",
               "Pantry", "Patio", "Staircase", "Utility Room", "Other"]
COMMERCIAL_LABELS = ["open office", "private office", "conference room", "reception", "kitchen or break room",
                     "restroom", "corridor", "storage", "server or electrical room", "lobby", "gym", "pool", "laundry",
                     "mail room", "leasing office", "retail floor", "warehouse floor", "loading area", "stairwell",
                     "elevator lobby", "other"]
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
    """Panoramas standing in a room, the one nearest the room's centre first."""
    ps = [p for p in plan["panos"] if p.get("room") == room["id"] and p.get("rotation")]
    poly = room.get("polygon") or []
    if poly:
        c = np.mean(np.array(poly, float), axis=0)
        ps.sort(key=lambda p: float(np.hypot(p["position"][0] - c[0], p["position"][1] - c[1])))
    return ps


def _rooms_to_read(plan: dict) -> list[dict]:
    return [r for r in plan["rooms"] if r.get("label") != "Void" and room_panos(plan, r)]


def _parallel(fn, items):
    with ThreadPoolExecutor(CONCURRENCY) as ex:
        return list(ex.map(fn, items))


# ---- room labels ------------------------------------------------------------------------------

def label_rooms(plan: dict, rooms: list[str] | None = None) -> list[dict]:
    """A room type for every room that has a panorama, from the panorama nearest its centre.

    Homes (scans with Matterport labels) use Matterport's label set, and the model is not shown
    Matterport's label, so `agrees` is an honest check of one against the other. Other scans use a
    commercial label set."""
    home = bool(plan["has"].get("room_labels"))
    labels = HOME_LABELS if home else COMMERCIAL_LABELS
    todo = [r for r in _rooms_to_read(plan) if rooms is None or r["id"] in rooms]
    faces = [1, 2, 3, 4]
    schema = {"type": "object", "additionalProperties": False, "required": ["label", "confidence", "evidence_image", "reason"],
              "properties": {"label": {"type": "string", "enum": labels}, "confidence": CONFIDENCE,
                             "evidence_image": {"type": "integer", "enum": [1, 2, 3, 4]},
                             "reason": {"type": "string", "description": "One short sentence naming what you saw."}}}

    def one(room):
        pano = room_panos(plan, room)[0]
        prompt = (CUBE_NOTE.format(px=ROOM_PX, faces=_describe(faces)) +
                  " The camera stands inside one room of a " + ("home" if home else "commercial building") +
                  ". What type of room is the camera standing in? Judge the room the camera is in, not rooms seen "
                  "through doorways. Pick the image that shows it best.")
        a = ask(_faces(plan["sid"], pano["id"], faces, ROOM_PX), prompt, schema, key=f"label_room/{plan['sid']}/{pano['id']}")
        out = {"room": room["id"], "label": a["label"], "confidence": a["confidence"], "reason": a["reason"],
               "evidence": {"sid": plan["sid"], "pano": pano["id"], "face": faces[a["evidence_image"] - 1]},
               "source": {"layer": "model", "method": "vision", "confidence": a["confidence"],
                          "note": f"Vision model on panorama {pano['id']} faces 1-4"}}
        if home:
            mm = room.get("label")
            out["matterport_label"] = mm
            out["agrees"] = mm == a["label"]
            out["agrees_lenient"] = out["agrees"] or any({mm, a["label"]} <= s for s in SAME)
        return out

    return _parallel(one, todo)


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
    return {"label": det["label"], "room": pano.get("room"), "pano_anchor": where["anchor"],
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


def _merge(found: list[dict], merge_m: float) -> list[dict]:
    rank = {"high": 0, "medium": 1, "low": 2}
    found.sort(key=lambda f: rank[f["finding"]["source"]["confidence"]])
    kept: list[dict] = []
    for f in found:
        twin = next((k for k in kept if k["label"] == f["label"] and k["point"] and f["point"]
                     and k["finding"]["media"][0]["ref"].split("/")[1] != f["finding"]["media"][0]["ref"].split("/")[1]
                     and math.dist(k["point"], f["point"]) <= merge_m), None)
        if twin:
            twin["finding"]["media"] += f["finding"]["media"]
        else:
            kept.append(f)
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
