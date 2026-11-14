"""What the plan and the record already say about each room and the building; shared by the office tools.

Everything here is measured or looked up, never asked of the model.
"""
from __future__ import annotations

import functools

from shapely.geometry import Polygon

from ...sources import costar
from ...sources import index as scan_index

M2_TO_FT2 = 10.7639
PROPERTY_TYPES = {1: "hotel", 2: "industrial", 5: "office", 6: "retail", 7: "flex (office and warehouse)",
                  8: "sports and entertainment", 9: "mixed use", 10: "specialty", 11: "apartment community",
                  13: "healthcare", 15: "residential", 16: "home"}
CLASSES = {1: "A", 2: "B", 3: "C"}


def quality(plan: dict) -> dict:
    """plan.quality, or the same booleans worked out for an older plan that lacks it."""
    q = plan.get("quality")
    if q:
        return q
    rooms = [r for r in plan["rooms"] if r.get("label") != "Void"]
    return {"walls": bool(plan.get("walls")), "polygons": any(r.get("polygon") for r in rooms),
            "openings": bool(plan.get("openings")), "labels": any(r.get("label") for r in rooms), "notes": []}


def live_rooms(plan: dict) -> list[dict]:
    """Rooms that are floor: not Matterport's Void."""
    return [r for r in plan["rooms"] if r.get("label") != "Void"]


def room_facts(plan: dict) -> dict[str, dict]:
    """Per room: area, width and depth, doorways, windows, openings that lead out of the scan, and how many
    panoramas stand in it. Doors and windows are None when the scan has no wall graph."""
    from ...vision.reader import room_panos
    q = quality(plan)
    out = {}
    for r in live_rooms(plan):
        ops = [o for o in plan.get("openings") or [] if r["id"] in (o.get("rooms") or [])]
        w, d = r.get("width"), r.get("depth")
        poly = r.get("polygon") or []
        if (not w or not d) and len(poly) >= 3:
            box = Polygon(poly).minimum_rotated_rectangle
            xs = list(box.exterior.coords)
            sides = sorted({round(((xs[i][0] - xs[i + 1][0]) ** 2 + (xs[i][1] - xs[i + 1][1]) ** 2) ** 0.5, 2) for i in range(2)})
            w, d = sides[0], sides[-1]
        out[r["id"]] = {
            "area": r.get("area"), "width": min(w, d) if w and d else None, "depth": max(w, d) if w and d else None,
            "height": r.get("height"),
            "doors": sum(1 for o in ops if o["type"] != "window") if q["openings"] else None,
            "windows": sum(1 for o in ops if o["type"] == "window") if q["openings"] else None,
            "outward": sum(1 for o in ops if o["type"] != "window" and len(o.get("rooms") or []) == 1) if q["openings"] else None,
            "panos": len(room_panos(plan, r)),
        }
    return out


def hint(f: dict) -> str:
    """One room's facts as a sentence for the vision model."""
    parts = []
    if f["area"]:
        parts.append(f"floor area {f['area']:.1f} m2 ({f['area'] * M2_TO_FT2:.0f} ft2)")
    if f["width"] and f["depth"]:
        parts.append(f"about {f['width']:.1f} m by {f['depth']:.1f} m")
    if f["doors"] is None:
        parts.append("doors and windows unknown (no wall graph)")
    else:
        parts.append(f"{f['doors']} doorway{'s' if f['doors'] != 1 else ''} or openings")
        parts.append(f"{f['windows']} exterior window{'s' if f['windows'] != 1 else ''}" if f["windows"] else "no windows")
    if f["panos"] > 3:
        parts.append(f"{f['panos']} camera positions inside it, so it is a large or long space")
    return "; ".join(parts)


@functools.lru_cache(maxsize=256)
def _record(sid: str) -> dict | None:
    try:
        return costar.record(sid)
    except LookupError:  # no kit, or no record for this scan
        return None


def record(sid: str) -> dict | None:
    """The CoStar record for a scan (costar.record), or None."""
    return _record(sid)


def property_type(sid: str) -> str | None:
    p = (record(sid) or {}).get("property") or {}
    return PROPERTY_TYPES.get(p.get("propertyType"))


def context(sid: str) -> str | None:
    """A sentence about the building for the vision model: type and class from the CoStar record."""
    p = (record(sid) or {}).get("property") or {}
    kind = PROPERTY_TYPES.get(p.get("propertyType"))
    if not kind:
        return None
    cls = CLASSES.get(p.get("buildingClass"))
    return f"the CoStar record lists the property as {kind}" + (f", class {cls}" if cls else "")


def property_id(sid: str) -> int | None:
    return costar.property_id_of(sid)


def siblings(sid: str) -> list[str]:
    """Other scans of the same CoStar property."""
    pid = property_id(sid)
    return [s for s in costar.scans_of_property(pid) if s != sid] if pid else []


def scan_kind(sid: str) -> str:
    """The index's guess from the scan title: house, apartment_unit, amenity, office, warehouse, retail, other."""
    return (scan_index.rows().get(sid) or {}).get("kind") or "other"


def scan_name(sid: str) -> str:
    return (scan_index.rows().get(sid) or {}).get("name") or sid


# Matterport's home labels in the commercial vocabulary the office tools count with.
COMMERCIAL_OF = {"Office": "private office", "Kitchen": "kitchen or break room", "Bathroom": "restroom",
                 "Hallway": "corridor", "Entrance": "reception", "Closet": "storage", "Pantry": "storage",
                 "Utility Room": "server or electrical room", "Laundry": "laundry", "Exercise Room": "gym",
                 "Staircase": "stairwell", "Living Room": "lounge or clubroom", "Family Room": "lounge or clubroom",
                 "Game Room": "lounge or clubroom", "Patio": "outdoor area", "Balcony": "outdoor area"}


def commercial(label: str | None) -> str | None:
    return COMMERCIAL_OF.get(label, label) if label else None
