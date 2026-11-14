"""The label overlay: room labels that a vision pass or a person set, kept beside the plan cache so every tool
sees them (`apply` runs inside the default plan loader).

    $THRESHOLD_DATA_DIR/cache/labels/<sid>.json
    {sid, rooms: {room id: entry}, finishes: {room id: {finish, confidence, evidence}}, corrections: [...]}
    entry = {label, confidence, label_source: "vision"|"user", reason, evidence: {sid, pano, face}, at, ...}

A user entry always wins. A vision entry fills rooms that Matterport left unlabelled or called Other, and
never replaces a Matterport label.
"""
from __future__ import annotations

import copy
import json
import threading
import time

from ...config import CACHE
from ...sources.upstream import check

DIR = CACHE / "labels"
CONFIDENCE = {"high": 0.9, "medium": 0.7, "low": 0.4}
_lock = threading.Lock()


def load(sid: str) -> dict:
    f = DIR / f"{check(sid)}.json"
    if f.exists():
        return json.loads(f.read_text())
    return {"sid": sid, "rooms": {}, "finishes": {}, "corrections": []}


def save(doc: dict) -> None:
    f = DIR / f"{check(doc['sid'])}.json"
    with _lock:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".part")
        tmp.write_text(json.dumps(doc, indent=1))
        tmp.replace(f)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def overrides(room: dict, entry: dict) -> bool:
    if entry["label_source"] == "user":
        return True
    return room.get("label") in (None, "Other") or room.get("label_source") in ("vision", None)


def apply(plan: dict) -> dict:
    """The plan with the overlay's labels on its rooms; the same dict when there is no overlay."""
    try:
        doc = load(plan["sid"])
    except LookupError:
        return plan
    if not doc["rooms"]:
        return plan
    plan = copy.deepcopy(plan)
    for r in plan["rooms"]:
        e = doc["rooms"].get(r["id"])
        if e and e.get("label") and overrides(r, e):
            r.update(label=e["label"], label_source=e["label_source"],
                     label_confidence=1.0 if e["label_source"] == "user" else CONFIDENCE.get(e.get("confidence"), 0.5))
    return plan
