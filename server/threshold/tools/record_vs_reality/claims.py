"""Claims: what a record, a listing or the scan's own title says that the data can check.

Each claim is `{key, label, value, unit, path, origin, scope}`. `scope` is what part of a building the claim is about
(`home`, `unit`, `suite`, `floor`, `building`), so a unit's area is never set beside a building's.
"""
from __future__ import annotations

import re

AMENITY_WORDS = ("lobby", "pool", "fitness", "gym", "clubhouse", "club room", "clubroom", "lounge", "courtyard",
                 "business center", "leasing", "game room", "laundry facilities", "amenity", "rooftop", "roof deck",
                 "mail", "dog", "theater", "theatre", "spa", "sky", "conference room", "co-working", "coworking")

KIND_BY_TYPE = {11: "apartment", 5: "office", 2: "industrial", 7: "industrial"}

# Record claim key -> (label, scope it describes). Scope "unit-or-home" is resolved with the scan.
RECORD_KEYS = {
    "living_area": ("Living area", "home"), "beds": ("Bedrooms", "home"), "baths": ("Bathrooms", "home"),
    "stories": ("Stories", "building"), "parking_spaces": ("Parking spaces", "building"),
    "unit_beds": ("Bedrooms", "unit"), "unit_baths": ("Bathrooms", "unit"),
    "unit_area_min": ("Unit area", "unit"), "unit_area_max": ("Unit area", "unit"),
    "gross_area": ("Gross building area", "building"), "rentable_area": ("Rentable building area", "building"),
    "typical_floor_area": ("Typical floor area", "floor"), "height": ("Building height", "building"),
    "parking_ratio": ("Parking ratio", "building"), "has_sprinklers": ("Sprinklers", "building"),
    "ceiling_height": ("Ceiling height", "building"), "ceiling_height_main": ("Main ceiling height", "home"),
    "dock_doors": ("Loading dock doors", "building"), "drive_in_bays": ("Drive-in doors", "building"),
    "year_built": ("Year built", "building"), "construction_material": ("Construction", "building"),
    "year_renovated": ("Year renovated", "building"),
}

ZERO_IS_UNKNOWN = {"stories", "living_area", "gross_area", "rentable_area", "typical_floor_area", "height",
                   "ceiling_height", "ceiling_height_main", "unit_area_min", "unit_area_max"}

# Feature sentences in residential-listing-features that a scan or an aerial photo can check.
FEATURES = {
    "fireplace": ("Fireplace", re.compile(r"fireplace", re.IGNORECASE), re.compile(r"\bno fireplace", re.IGNORECASE)),
    "kitchen_island": ("Kitchen island", re.compile(r"\bisland\b", re.IGNORECASE), None),
    "walk_in_closet": ("Walk-in closet", re.compile(r"walk-?in closet", re.IGNORECASE), None),
    "wood_floors": ("Hardwood floors", re.compile(r"hardwood|wood floor|wood flooring", re.IGNORECASE), None),
    "laundry_in_unit": ("Laundry in the home", re.compile(r"laundry room|laundry in unit|in-unit laundry|"
                                                          r"inside laundry|laundry closet|washer|dryer|utility room", re.IGNORECASE),
                        re.compile(r"community|common|shared|on site|on-site|in building|no laundry|hookups? only", re.IGNORECASE)),
    "garage": ("Garage", re.compile(r"garage", re.IGNORECASE), re.compile(r"\bno garage", re.IGNORECASE)),
    "pool": ("Private pool", re.compile(r"\bpool\b", re.IGNORECASE), re.compile(r"community|shared|no pool|pool table", re.IGNORECASE)),
}


def kind_of(record: dict | None) -> str:
    if not record:
        return "unknown"
    if record.get("residential_listing"):
        return "home"
    return KIND_BY_TYPE.get((record.get("property") or {}).get("propertyType"), "commercial")


def parse_title(name: str | None) -> dict:
    """Beds, baths and area named in a scan title such as "2BR, 1.5BA - 755SF" or "Suite 6A-10,000SF"."""
    n = name or ""
    out: dict = {}
    if m := re.search(r"(\d+)\s*(?:BR|BD|Bed(?:room)?s?)\b", n, re.IGNORECASE):
        out["beds"] = int(m.group(1))
    elif re.search(r"\bstudio\b", n, re.IGNORECASE):
        out["beds"] = 0
    if m := re.search(r"(\d+(?:\.\d)?)\s*(?:BA|Bath(?:room)?s?)\b", n, re.IGNORECASE):
        out["baths"] = float(m.group(1))
    if m := re.search(r"(\d{1,3}(?:,\d{3})+|\d{3,6})\s*(?:SF|Sq\.?\s*Ft\.?|SQFT|square feet)\b", n, re.IGNORECASE):
        out["area"] = int(m.group(1).replace(",", ""))
    return out


def scan_scope(plan: dict, record: dict | None) -> dict:
    """What part of a building the scan covers: home, unit, suite, floor, amenity, building or unknown, and why."""
    name = plan.get("name") or ""
    low = name.lower()
    t = parse_title(name)
    kind = kind_of(record)
    rs = (record or {}).get("scope")
    if kind == "home":
        condo = (record.get("residential_listing") or {}).get("isInCondoBuilding")
        return {"scope": "home", "kind": kind, "why": "a residential listing" + (" of a condo unit" if condo else " of a home")}
    if rs in ("unit", "floor_plan"):
        return {"scope": "unit", "kind": kind, "why": f"the record attaches this scan to an apartment {rs.replace('_', ' ')}"}
    if "beds" in t:
        return {"scope": "unit", "kind": kind, "why": f"the scan title \"{name}\" names a unit"}
    if re.search(r"\bsuite\b|\bste\.?\s|\bunit\b", low):
        return {"scope": "suite", "kind": kind, "why": f"the scan title \"{name}\" names a suite"}
    if any(w in low for w in AMENITY_WORDS):
        return {"scope": "amenity", "kind": kind, "why": f"the scan title \"{name}\" names a shared amenity space"}
    if re.search(r"\b(floor|level|flr)\b", low):
        return {"scope": "floor", "kind": kind, "why": f"the scan title \"{name}\" names a floor"}
    if rs == "building":
        return {"scope": "building", "kind": kind, "why": "the record attaches this scan to the whole property"}
    return {"scope": "unknown", "kind": kind, "why": "neither the record nor the scan title says which part was scanned"}


def _feature_lines(features: dict | None) -> list[tuple[str, str]]:
    """(section, line) pairs of the 'Inside This Home' part of a listing."""
    out = []
    for s in (features or {}).get("sections") or []:
        if (s.get("category") or "").lower().startswith("community"):
            continue
        for line in s.get("lines") or []:
            out.append((s.get("subcategory") or "", line))
    return out


def feature_claims(features: dict | None, path: str = "residential-listing-features.sections[].lines") -> list[dict]:
    """One claim per checkable feature sentence, valued True, with the sentence it came from."""
    out = []
    lines = _feature_lines(features)
    for key, (lab, yes, no) in FEATURES.items():
        hit = next((ln for sec, ln in lines if yes.search(ln) and not (no and no.search(ln))
                    and (key != "kitchen_island" or "kitchen" in sec.lower() or "island" in ln.lower())), None)
        if hit:
            out.append({"key": key, "label": lab, "value": True, "unit": None, "path": f"{path}: \"{hit}\"",
                        "origin": "listing", "scope": "home", "quote": hit})
    return out


def from_record(plan: dict, record: dict | None) -> list[dict]:
    """Every checkable claim: the record's `claims`, the listing's feature sentences, and the scan title."""
    out: list[dict] = []
    rc = (record or {}).get("claims") or {}
    kind = kind_of(record)
    rl = (record or {}).get("residential_listing") or {}
    in_building = bool(rl.get("isInCondoBuilding") or ((rl.get("property") or {}).get("address") or {}).get("unitNumber"))
    for key, c in rc.items():
        if key not in RECORD_KEYS or (c["value"] == 0 and key in ZERO_IS_UNKNOWN):
            continue  # the kit records "not known" as 0 for these (concepts/data-quality-and-confidence.md)
        lab, scope = RECORD_KEYS[key]
        if kind == "home" and key in ("parking_spaces", "year_built"):
            scope = "home"
        if kind == "home" and key == "stories":
            scope = "building" if in_building else "home"  # a condo listing's stories are the building's
        origin = "listing" if c["path"].startswith("residential-") else "costar"
        out.append({"key": key, "label": lab, "value": c["value"], "unit": c.get("unit"), "path": c["path"],
                    "origin": origin, "scope": scope})
    # one unit area claim, not min and max, when the floor plan has a single size
    mins = next((c for c in out if c["key"] == "unit_area_min"), None)
    maxs = next((c for c in out if c["key"] == "unit_area_max"), None)
    if mins and maxs:
        out.remove(maxs)
        mins.update(key="unit_area", value=mins["value"] if mins["value"] == maxs["value"] else [mins["value"], maxs["value"]],
                    path=mins["path"] + (" = maxSquareFeet" if mins["value"] == maxs["value"] else " .. maxSquareFeet"))
    if record and record.get("residential_features"):
        out += feature_claims(record["residential_features"])
    t = parse_title(plan.get("name"))
    for key, lab in (("beds", "Bedrooms"), ("baths", "Bathrooms"), ("area", "Area")):
        if key in t:
            out.append({"key": f"title_{key}", "label": f"{lab} in the scan title", "value": t[key],
                        "unit": "ft2" if key == "area" else None, "path": f"scan title \"{plan.get('name')}\"",
                        "origin": "scan title", "scope": "scan"})
    return out
