"""Set each claim beside what the data measures and give it a verdict: confirmed, contradicted or cannot verify.

`compare(plan, scope, claims, evidence, params)` is pure: the aerial facts, aerial detections and panorama
detections arrive in `evidence` (gathered by `gather.py`), so tests pass hand-made ones. Every comparison has
the same shape for every property type, so one panel shows homes, units, offices and warehouses alike:

    {key, label, claim: {value, unit, path, origin}, measured: {value, unit}, verdict, confidence, reason,
     layer, method, rooms: {counted, excluded}, anchor, media, ratio}
"""
from __future__ import annotations

from . import measure as ms

CONFIRMED, CONTRADICTED, UNVERIFIABLE, CONTEXT = "confirmed", "contradicted", "cannot verify", "context"

DEFAULTS = {
    "area_low": 0.85,       # measured interior area may be this share of a listed (gross) area and still confirm it
    "area_high": 1.05,      # and at most this share above it
    "storey_min_m": 2.6,    # a storey is at least this tall, roof height over stories
    "storey_max_m": 6.0,    # and at most this (taller means a missing storey or a tall single-storey shed)
    "height_tol": 0.15,     # building height within 15% of the aerial roof height
    "ceiling_tol_ft": 1.0,  # ceiling height within a foot
    "count_tol": 0.15,      # parking stalls and dock doors within 15% (and at least 2)
}
TALL_FT = 13.0  # above this a Matterport room height cannot be trusted to reach the ceiling
AREA_SCOPES = {"home": ("home",), "unit": ("unit",), "floor": ("floor", "building"), "building": ("building",)}


def _c(claim: dict, verdict: str, confidence: str, reason: str, *, measured=None, unit=None, layer="matterport",
       method="geometry", **extra) -> dict:
    return {"key": claim["key"], "label": claim["label"],
            "claim": {k: claim.get(k) for k in ("value", "unit", "path", "origin")},
            "measured": {"value": measured, "unit": unit if unit is not None else claim.get("unit")},
            "verdict": verdict, "confidence": confidence, "reason": reason, "layer": layer, "method": method,
            "rooms": extra.pop("rooms", None), "anchor": extra.pop("anchor", None), "media": extra.pop("media", []),
            "ratio": extra.pop("ratio", None), **extra}


def _fmt(v, unit=None) -> str:
    if isinstance(v, list):
        return " to ".join(_fmt(x, unit) for x in v)
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float) and not v.is_integer():
        s = f"{v:,.1f}"
    elif isinstance(v, (int, float)):
        s = f"{int(v):,}"
    else:
        s = str(v)
    return s + ({"ft2": " ft²", "ft": " ft", "m2": " m²", "m": " m"}.get(unit) or (" " + unit.replace("ft2", "ft²") if unit else ""))


def _scope_ok(claim: dict, scan: dict) -> bool:
    if claim["scope"] == "scan":
        return True
    return scan["scope"] in AREA_SCOPES.get(claim["scope"], (claim["scope"],))


def _wrong_scope(claim: dict, scan: dict) -> dict:
    return _c(claim, UNVERIFIABLE, "high",
              f"The record's figure is for the {claim['scope']}, and this scan covers {_scope_word(scan)} "
              f"({scan['why']}), so the two are not comparable.", method="lookup")


def _scope_word(scan: dict) -> str:
    return {"home": "the home", "unit": "one unit", "suite": "one suite", "floor": "one floor",
            "amenity": "one shared amenity space", "building": "the whole building",
            "unknown": "an unknown part of the building"}[scan["scope"]]


# ---- area -------------------------------------------------------------------------------------------------------

def area(plan: dict, claim: dict, scan: dict, p: dict, ev: dict | None = None) -> dict:
    if not _scope_ok(claim, scan):
        return _wrong_scope(claim, scan)
    fa = ms.floor_area(plan, (ev or {}).get("relabel"))
    if not fa["available"]:
        return _c(claim, UNVERIFIABLE, "high", fa["reason"])
    listed = claim["value"]
    lo_v, hi_v = (listed if isinstance(listed, list) else [listed, listed])
    ft2 = fa["ft2"]
    ratio = ft2 / ((lo_v + hi_v) / 2)
    excl = fa["excluded"]
    rooms = {"counted": fa["counted"], "excluded": excl}
    head = (f"Measured interior floor area is {ft2:,.0f} ft² ({fa['m2']:.1f} m²) over {len(fa['counted'])} rooms on "
            f"{len(fa['floors'])} floor{'s' if len(fa['floors']) != 1 else ''}, {ratio:.0%} of the listed {_fmt(listed, 'ft2')}. ")
    basis = ("Listed areas are usually measured to the outside of exterior walls, so interior area runs about 5 to 10% "
             "lower. ")
    left = "; ".join(f"{x['label']} {x['m2']:.0f} m² ({x['why']})" for x in excl if x["label"] != "Void")
    left_m2 = sum(x["m2"] for x in excl if x["label"] != "Void")
    if p["area_low"] * lo_v <= ft2 <= p["area_high"] * hi_v:
        return _c(claim, CONFIRMED, "high" if ms.labels_ok(plan) else "medium",
                  head + basis + (f"Not counted: {left}." if left else ""), measured=round(ft2), unit="ft2",
                  rooms=rooms, ratio=ratio)
    why = []
    if ft2 < p["area_low"] * lo_v:
        if left:
            with_left = ft2 + left_m2 * ms.M2_FT2
            why.append(f"Not counted: {left}; with them the total would be {with_left:,.0f} ft² "
                       f"({with_left / ((lo_v + hi_v) / 2):.0%}).")
        why.append("Rooms the scan skipped (a garage, an attic room, a locked closet, a second floor) are the usual "
                   "cause when a scan measures less.")
    else:
        stairs = sum(r["m2"] for r in fa["counted"] if r["label"] == "Staircase")
        big = [r for r in fa["counted"] if r["label"] == "unlabelled room" and r["m2"] >= 15]
        if len(fa["floors"]) > 1 and stairs:
            why.append(f"Stair rooms on {len(fa['floors'])} levels add {stairs * ms.M2_FT2:,.0f} ft², and a listing "
                       "counts each flight once.")
        if big:
            why.append("Unlabelled rooms of " + ", ".join(f"{r['m2']:.0f} m²" for r in big) + " are counted; one may be "
                       "a garage or storage room Matterport did not name.")
        why.append("Otherwise the scan measures more than the record: a garage conversion, an enclosed patio, an "
                   "addition or a guest suite counted in the scan, an out-of-date record, or a scan that runs into a "
                   "neighbouring space.")
    conf = "medium" if ms.labels_ok(plan) else "low"
    if ratio < 0.6:
        why.append("The scan covers well under the stated area, which points to a partial scan more than a wrong figure.")
        conf = "low"
    return _c(claim, CONTRADICTED, conf, head + basis + " ".join(why), measured=round(ft2), unit="ft2", rooms=rooms,
              ratio=ratio)


# ---- rooms ------------------------------------------------------------------------------------------------------

def beds(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    if not _scope_ok(claim, scan):
        return _wrong_scope(claim, scan)
    b = ms.bedrooms(plan)
    labels = ev.get("labels")  # vision labels for scans Matterport did not label
    if not b["available"] and labels:
        n = sum(1 for x in labels if x["label"] in ("Bedroom",))
        b = {"available": True, "count": n, "rooms": [x["room"] for x in labels if x["label"] == "Bedroom"], "maybe": [],
             "vision": True}
    if not b["available"]:
        return _c(claim, UNVERIFIABLE, "high", b["reason"] + " Run the deep check to label rooms from the panoramas.")
    n, want = b["count"], claim["value"]
    layer, method = ("model", "vision") if b.get("vision") else ("matterport", "lookup")
    pins = b["rooms"]
    if n == want:
        return _c(claim, CONFIRMED, "high" if not b.get("vision") else "medium",
                  f"{n} room{'s are' if n != 1 else ' is'} labelled Bedroom.", measured=n, layer=layer, method=method,
                  pins=pins)
    maybe = ", ".join(f"{m['label']} ({m['m2']} m²)" for m in b["maybe"])
    if n < want:
        reason = (f"{n} room{'s are' if n != 1 else ' is'} labelled Bedroom, {want - n} fewer than the record. "
                  "Matterport labels a room by its furniture, so a bedroom furnished as an office or left empty reads "
                  "as something else" + (f"; candidates here: {maybe}." if maybe else ".") +
                  " A bedroom on an unscanned floor also explains it.")
    else:
        reason = (f"{n} rooms are labelled Bedroom, {n - want} more than the record: a bed in a den, loft or "
                  "converted garage counts here, or the record is out of date.")
    return _c(claim, CONTRADICTED, "medium" if not maybe or n > want else "low", reason, measured=n, layer=layer,
              method=method, pins=pins)


def baths(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    if not _scope_ok(claim, scan):
        return _wrong_scope(claim, scan)
    b = ms.bathrooms(plan, ev.get("fixtures"))
    if not b["available"]:
        return _c(claim, UNVERIFIABLE, "high", b["reason"] + " Run the deep check to label rooms from the panoramas.")
    want = float(claim["value"])
    full, half = b["full"], b["half"]
    pins = [r for g in b["groups"] for r in g["rooms"]]
    how = (f"by the panoramas (a tub or shower makes it full) for {b['seen']} and by size for the rest"
           if b["seen"] else f"by size (under {ms.HALF_BATH_M2:g} m² counts as half)")
    desc = (f"{full} full and {half} half bathroom{'s' if half != 1 else ''} {how}"
            + (f"; {b['merged']} pair of rooms joined by a doorway counted as one" if b["merged"] else "") + ".")
    if half and want == float(full + half):
        return _c(claim, CONFIRMED, "low", desc + " The room count matches if the smaller bathroom is a full one.",
                  measured=full + 0.5 * half, method="lookup", pins=pins)
    if want == full + 0.5 * half:
        return _c(claim, CONFIRMED, "high" if b["seen"] == len(b["groups"]) else "medium", desc,
                  measured=full + 0.5 * half, layer="matterport", method="lookup", pins=pins)
    if want != int(want) and full + half == int(want) + 1:
        return _c(claim, CONFIRMED, "low", desc + " The room count matches; which ones are half baths is a size guess.",
                  measured=full + 0.5 * half, method="lookup", pins=pins)
    reason = desc + (" Fewer than the record: a bathroom on an unscanned floor, or an en-suite merged into its bedroom."
                     if full + 0.5 * half < want else " More than the record: a powder room the record leaves out, "
                     "or one bathroom split into two scan rooms with no doorway between them.")
    return _c(claim, CONTRADICTED, "medium", reason, measured=full + 0.5 * half, method="lookup", pins=pins)


def stories_home(plan: dict, claim: dict, scan: dict, p: dict) -> dict:
    f = ms.floors(plan)
    if not f["available"]:
        return _c(claim, UNVERIFIABLE, "high", f["reason"])
    n, want = f["count"], claim["value"]
    names = ", ".join(f["names"])
    if n == want:
        return _c(claim, CONFIRMED, "high", f"The scan has {n} floor{'s' if n != 1 else ''} with rooms ({names}).",
                  measured=n, method="lookup")
    if n < want:
        return _c(claim, CONTRADICTED, "low", f"The scan has {n} floor{'s' if n != 1 else ''} with rooms ({names}), "
                  f"{want - n} fewer than the record. Scans often skip a floor, so this more likely means an incomplete "
                  "scan than a wrong record.", measured=n, method="lookup")
    return _c(claim, CONTRADICTED, "medium", f"The scan has {n} floors with rooms ({names}), more than the record's "
              f"{want}: a basement, attic room or mezzanine counted as a floor here, or the record leaves one out.",
              measured=n, method="lookup")


def ceiling(plan: dict, claim: dict, scan: dict, p: dict) -> dict:
    h = ms.heights(plan)
    if not h["available"]:
        return _c(claim, UNVERIFIABLE, "high", h["reason"])
    shed = scan["kind"] == "industrial"
    m = h["max_m"] if shed else h["median_m"]
    ft = m * ms.M_FT
    want = float(claim["value"])
    which = "tallest room" if shed else "median room"
    head = (f"The {which} height is {ft:.1f} ft ({m:.2f} m), from {h['of_rooms']} of {h['rooms_total']} rooms with a "
            "height. ")
    note = ("Matterport measures floor to the visible ceiling; under a dropped ceiling that is lower than the clear "
            "height a record gives. ")
    anchor = {"sid": plan["sid"], "room": h["max_room"]} if shed else None
    if abs(ft - want) <= p["ceiling_tol_ft"]:
        return _c(claim, CONFIRMED, "high", head, measured=round(ft, 1), unit="ft", anchor=anchor)
    if want > TALL_FT and ft < want:
        # Matterport's room height stops where the camera's depth reaches (seen across the field audit's warehouses),
        # so a scan cannot measure a warehouse's clear height.
        return _c(claim, UNVERIFIABLE, "medium", head + f"Matterport's room heights stop near the camera's reach, so a "
                  f"scan cannot measure a ceiling above about {TALL_FT:g} ft such as a warehouse's clear height.",
                  measured=round(ft, 1), unit="ft", anchor=anchor)
    return _c(claim, CONTRADICTED, "medium" if h["of_rooms"] >= 3 else "low", head + note,
              measured=round(ft, 1), unit="ft", anchor=anchor)


# ---- features from the listing's sentences ------------------------------------------------------------------------

FEATURE_OBJECTS = {"fireplace": ["fireplace"], "kitchen_island": ["kitchen island"], "wood_floors": ["wood floor"],
                   "laundry_in_unit": ["washer", "dryer"], "garage": [], "walk_in_closet": [], "pool": []}
FEATURE_ROOMS = {"fireplace": ("Living Room", "Family Room", "Dining Room", "Bedroom"), "kitchen_island": ("Kitchen",),
                 "wood_floors": ("Living Room", "Bedroom", "Dining Room", "Hallway", "Family Room"),
                 "laundry_in_unit": ("Laundry", "Utility Room", "Kitchen", "Hallway", "Closet", "Garage")}


def feature(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    key = claim["key"]
    if key == "walk_in_closet":
        c = ms.closets(plan)
        if not c["available"]:
            return _c(claim, UNVERIFIABLE, "high", c["reason"])
        if c["walk_in"]:
            best = max(c["walk_in"], key=lambda x: x["m2"])
            return _c(claim, CONFIRMED, "high", f"{len(c['walk_in'])} closet{'s are' if len(c['walk_in']) != 1 else ' is'} "
                      f"large enough to walk into; the largest is {best['m2']:.1f} m².", measured=True, unit=None,
                      anchor={"sid": plan["sid"], "room": best["room"]}, pins=[x["room"] for x in c["walk_in"]])
        if c["closets"]:
            return _c(claim, CONTRADICTED, "medium", f"The scan has {len(c['closets'])} closet{'s' if len(c['closets']) != 1 else ''} and none is larger than "
                      f"{ms.WALK_IN_M2:g} m² with a side of {ms.WALK_IN_SIDE_M:g} m.", measured=False,
                      pins=[x["room"] for x in c["closets"]])
        return _c(claim, UNVERIFIABLE, "medium", "No closet is a room of its own in this scan; a closet may be part "
                  "of its bedroom's outline.")
    if key == "garage":
        g = ms.garage_stalls(plan)
        if g["available"]:
            return _c(claim, CONFIRMED, "high", f"A room labelled Garage was scanned ({g['m2']:.0f} m²).", measured=True,
                      anchor={"sid": plan["sid"], "room": g["rooms"][0]}, method="lookup")
        return _c(claim, UNVERIFIABLE, "medium", "No garage was scanned; scans often stop at the garage door.",
                  method="lookup")
    if key == "pool":
        return pool(plan, claim, scan, p, ev)
    if key == "laundry_in_unit":
        rooms = ms.rooms_labelled(plan, "Laundry", "Utility Room")
        if rooms:
            return _c(claim, CONFIRMED, "high", f"A room labelled {rooms[0]['label']} was scanned.", measured=True,
                      anchor={"sid": plan["sid"], "room": rooms[0]["id"]}, method="lookup")
    return _vision_feature(plan, claim, ev)


def _vision_feature(plan: dict, claim: dict, ev: dict) -> dict:
    objs = ev.get("objects")
    want = FEATURE_OBJECTS.get(claim["key"]) or []
    if objs is None:
        return _c(claim, UNVERIFIABLE, "high", "Seeing this needs the panoramas; run the deep check.", method="vision",
                  layer="model")
    hits = [o for o in objs if o["label"] in want]
    read = ev.get("objects_rooms") or []
    labels = {r["id"]: r.get("label") for r in plan["rooms"]}
    if hits:
        best = hits[0]["finding"]
        conf = best["source"]["confidence"]
        return _c(claim, CONFIRMED, conf, f"Seen in the panorama of the {labels.get(hits[0]['room']) or 'scan'}: "
                  f"{best['detail']}.", measured=True, layer="model", method="vision", anchor=best["anchor"],
                  media=best["media"], pins=[])
    looked = sorted({labels.get(r) or "unlabelled room" for r in read})
    should = FEATURE_ROOMS.get(claim["key"], ())
    if any(lab in should for lab in looked):
        return _c(claim, CONTRADICTED, "low", f"Not seen in the panoramas read ({', '.join(looked)}). It may be in a "
                  "room that was not read, or out of view.", measured=False, layer="model", method="vision")
    return _c(claim, UNVERIFIABLE, "medium", f"The panoramas read ({', '.join(looked) or 'none'}) do not cover the "
              "rooms where this would be.", layer="model", method="vision")


# ---- the aerial photo -----------------------------------------------------------------------------------------------

def _fact(site: dict | None, fid: str):
    return next((f for f in (site or {}).get("facts") or [] if f["id"] == fid), None)


def _others(site: dict) -> int:
    """Structures on the parcel when the facts may describe a different one than the record's (1 when they are the
    structure at the record's point, or the only one)."""
    n = (_fact(site, "structures") or {}).get("value") or 1
    return 1 if site.get("structure") == "at the point" else n


def _no_aerial(claim: dict, why: str = "Run the deep check to read the aerial photo.") -> dict:
    return _c(claim, UNVERIFIABLE, "high", why, layer="vexcel", method="lookup")


def _geo(ev: dict):
    s = ev.get("site") or {}
    return {"geo": [s["lon"], s["lat"]]} if s.get("lat") is not None else None


def pool(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    site = ev.get("site")
    if not site:
        return _no_aerial(claim)
    f = _fact(site, "pool")
    if f is None:
        return _no_aerial(claim, "The aerial survey has no pool reading for this parcel.")
    seen = bool(f["value"])
    a = _fact(site, "pool_area")
    detail = f" ({a['value']:.0f} m² of water)" if seen and a else ""
    ok = seen == bool(claim["value"])
    return _c(claim, CONFIRMED if ok else CONTRADICTED, "medium",
              f"The aerial survey {'finds' if seen else 'finds no'} pool on the parcel{detail}.", measured=seen, unit=None,
              layer="vexcel", method="lookup", anchor=_geo(ev), media=ev.get("ortho_media") or [])


def stories_aerial(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    site = ev.get("site")
    if not site:
        return _no_aerial(claim)
    h = _fact(site, "roof_height")
    if not h:
        return _no_aerial(claim, "The aerial survey has no roof height for this building.")
    want = int(claim["value"])
    per = h["value"] / want
    n_struct = _others(site)
    head = (f"The roof is {h['value']:.1f} m above ground in the aerial surface model, {per:.1f} m a storey over "
            f"{want} stor{'ies' if want != 1 else 'y'}. ")
    if p["storey_min_m"] <= per <= p["storey_max_m"] or (want == 1 and scan["kind"] == "industrial"):
        return _c(claim, CONFIRMED, "medium", head + "That is a normal storey height.", measured=round(h["value"], 1),
                  unit="m", layer="vexcel", method="lookup", anchor=_geo(ev), media=ev.get("ortho_media") or [])
    implied = max(1, round(h["value"] / 3.5))
    multi = f" The parcel has {n_struct} structures and the reading is for the main one." if n_struct > 1 else ""
    return _c(claim, CONTRADICTED, "medium" if n_struct == 1 else "low",
              head + f"That is {'too low' if per < p['storey_min_m'] else 'too tall'} for one storey; the height "
              f"suggests about {implied}.{multi}", measured=round(h["value"], 1), unit="m", layer="vexcel",
              method="lookup", anchor=_geo(ev), media=ev.get("ortho_media") or [])


def height_aerial(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    site = ev.get("site")
    if not site:
        return _no_aerial(claim)
    h = _fact(site, "roof_height")
    if not h:
        return _no_aerial(claim, "The aerial survey has no roof height for this building.")
    ft = h["value"] * ms.M_FT
    want = float(claim["value"])
    ok = abs(ft - want) <= max(5.0, p["height_tol"] * want)
    return _c(claim, CONFIRMED if ok else CONTRADICTED, "medium" if _others(site) == 1 else "low",
              f"The roof is {ft:.0f} ft ({h['value']:.1f} m) above ground in the aerial surface model."
              + ("" if ok else " That is the top of the roof with any parapet or rooftop plant; a record may give "
                 "the eave or clear height."),
              measured=round(ft), unit="ft", layer="vexcel", method="lookup", anchor=_geo(ev),
              media=ev.get("ortho_media") or [])


def floor_vs_footprint(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    """Typical floor or gross area against the building footprint seen from above (outside walls, like GBA)."""
    site = ev.get("site")
    if not site:
        return _no_aerial(claim)
    fp = _fact(site, "footprint_area")
    if not fp:
        return _no_aerial(claim, "The aerial survey has no footprint for this building.")
    fp_ft2 = fp["value"] * ms.M2_FT2
    stories = ev.get("stories") or 1
    expect = fp_ft2 * (stories if claim["key"] in ("gross_area", "rentable_area") else 1)
    ratio = float(claim["value"]) / expect
    n_struct = _others(site)
    what = (f"the footprint times {stories} stor{'ies' if stories != 1 else 'y'}" if expect != fp_ft2 else "the footprint")
    head = (f"The main building's footprint from above is {fp_ft2:,.0f} ft² ({fp['value']:.0f} m²); the record's "
            f"{_fmt(claim['value'], 'ft2')} is {ratio:.0%} of {what}. ")
    if 0.8 <= ratio <= 1.2:
        return _c(claim, CONFIRMED, "medium", head, measured=round(expect), unit="ft2", layer="vexcel", method="lookup",
                  anchor=_geo(ev), media=ev.get("ortho_media") or [], ratio=ratio)
    if ratio < 0.5:
        return _c(claim, UNVERIFIABLE, "medium", head + "Vexcel draws buildings that touch, and attached parking decks, as "
                  "one footprint, so a record this far under it more likely covers one of joined buildings.",
                  measured=round(expect), unit="ft2", layer="vexcel", method="lookup", anchor=_geo(ev),
                  media=ev.get("ortho_media") or [], ratio=ratio)
    if ratio > 2.5:
        return _c(claim, UNVERIFIABLE, "high", head + "The record is several times the building seen from above, so it "
                  "covers several buildings (an apartment community or a campus) and one footprint cannot check it.",
                  measured=round(expect), unit="ft2", layer="vexcel", method="lookup", anchor=_geo(ev),
                  media=ev.get("ortho_media") or [], ratio=ratio)
    if ratio > 1.2 and n_struct > 1:
        return _c(claim, UNVERIFIABLE, "medium", head + f"The parcel has {n_struct} structures and the record may cover "
                  "all of them, while the footprint is the main one only.", measured=round(expect), unit="ft2",
                  layer="vexcel", method="lookup", anchor=_geo(ev), media=ev.get("ortho_media") or [], ratio=ratio)
    return _c(claim, CONTRADICTED, "medium" if ratio > 1 else "low",
              head + ("The record is larger than the building seen from above." if ratio > 1 else
                      "The record is smaller than the building seen from above: a partial record, a building that grew, "
                      "or a neighbour joined to it in Vexcel's footprint."),
              measured=round(expect), unit="ft2", layer="vexcel", method="lookup", anchor=_geo(ev),
              media=ev.get("ortho_media") or [], ratio=ratio)


def _count(claim: dict, n: int, what: str, ev: dict, media_key: str, note: str, p: dict) -> dict:
    """Counts from above miss things (covered stalls, doors on a side no view faces), so they are lower bounds:
    a count at or above the record confirms it, a count well above contradicts it, a lower one proves nothing."""
    want = float(claim["value"])
    tol = max(2, p["count_tol"] * want)
    common = dict(measured=n, unit=None, layer="vexcel", method="vision", anchor=_geo(ev), media=ev.get(media_key) or [])
    head = f"{n} {what} counted from above. "
    if n > want + tol:
        return _c(claim, CONTRADICTED, "low", head + "More than the record, and counts from above only miss things.",
                  **common)
    if n >= want - tol:
        return _c(claim, CONFIRMED, "low", head + note, **common)
    return _c(claim, UNVERIFIABLE, "low", head + note + " A lower count than the record is not evidence against it.",
              **common)


def parking(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    if scan["kind"] == "home":
        return parking_home(plan, claim, p, ev)
    det = ev.get("parking")
    if not det:
        return _no_aerial(claim, "Counting stalls needs the aerial detection; run the deep check.")
    n = det["count"]
    if claim["key"] == "parking_ratio":
        area = ev.get("gross_area")
        if not area:
            return _no_aerial(claim, "A ratio needs the building's area, which the record does not give.")
        r = n / (area / 1000)
        want = float(claim["value"])
        tol = max(0.3, p["count_tol"] * want)
        verdict = CONTRADICTED if r > want + tol else CONFIRMED if r >= want - tol else UNVERIFIABLE
        return _c(claim, verdict, "low", f"{n} stalls counted from above on the parcel, {r:.2f} per 1,000 ft² of the "
                  f"record's {area:,.0f} ft². Garage and covered stalls are not visible, so the count is a lower bound.",
                  measured=round(r, 2), layer="vexcel", method="vision", anchor=_geo(ev),
                  media=ev.get("parking_media") or [])
    return _count(claim, n, "painted stalls", ev, "parking_media",
                  "Stalls inside a parking garage or under a carport roof cannot be seen from above, and the stall "
                  "reader misses faded paint.", p)


def parking_home(plan: dict, claim: dict, p: dict, ev: dict) -> dict:
    g = ms.garage_stalls(plan)
    want = int(claim["value"])
    site = ev.get("site")
    cars = (_fact(site, "vehicles") or {}).get("value") if site else None
    stalls = g["stalls"] if g["available"] else 0
    head = (f"The scanned garage ({g['m2']:.0f} m²) holds about {stalls} car{'s' if stalls != 1 else ''}. " if g["available"]
            else "No garage was scanned. ")
    if g["available"] and stalls == want:
        return _c(claim, CONFIRMED, "medium", head, measured=stalls, anchor={"sid": plan["sid"], "room": g["rooms"][0]})
    if cars is None:
        return _c(claim, UNVERIFIABLE, "medium", head + ("The aerial survey counted no vehicles here, so a driveway's "
                  "spaces cannot be judged." if site else "A driveway's spaces need the aerial photo; run the deep check."),
                  measured=stalls or None)
    total = stalls + cars
    if total >= want:
        return _c(claim, CONFIRMED, "low", head + f"{cars} vehicle{'s were' if cars != 1 else ' was'} parked on the parcel "
                  "on the capture day, so the rest fit outside.", measured=total, layer="vexcel", method="lookup",
                  anchor=_geo(ev), media=ev.get("ortho_media") or [])
    return _c(claim, UNVERIFIABLE, "low", head + f"Only {cars} vehicle{'s were' if cars != 1 else ' was'} parked on the "
              "parcel on the capture day; an empty driveway proves nothing.", measured=total, layer="vexcel",
              method="lookup", anchor=_geo(ev), media=ev.get("ortho_media") or [])


def docks(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    det = ev.get("docks")
    if not det:
        return _no_aerial(claim, "Counting dock doors needs the aerial and oblique detection; run the deep check.")
    return _count(claim, det["count"], "dock doors", ev, "docks_media",
                  "The count is the most seen in any one aerial or oblique view; doors on a side no view faces are "
                  "missed.", p)


def sprinklers(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    objs = ev.get("objects")
    if objs is None:
        return _c(claim, UNVERIFIABLE, "high", "Seeing sprinkler heads needs the ceiling panoramas; run the deep check.",
                  layer="model", method="vision")
    hits = [o for o in objs if o["label"] == "sprinkler head"]
    n_rooms = len(ev.get("objects_rooms") or [])
    if hits:
        f = hits[0]["finding"]
        verdict = CONFIRMED if claim["value"] else CONTRADICTED
        return _c(claim, verdict, f["source"]["confidence"], f"{len(hits)} sprinkler head{'s' if len(hits) != 1 else ''} "
                  f"seen on the ceilings of {n_rooms} rooms read.", measured=True, layer="model", method="vision",
                  anchor=f["anchor"], media=[m for h in hits[:4] for m in h["finding"]["media"]][:6])
    if claim["value"]:
        return _c(claim, CONTRADICTED if n_rooms >= 4 else UNVERIFIABLE, "low",
                  f"No sprinkler head seen on the ceilings of {n_rooms} rooms read. Concealed heads under cover plates "
                  "are hard to see, so this is weak evidence.", measured=False, layer="model", method="vision")
    return _c(claim, CONFIRMED, "low", f"No sprinkler head seen on the ceilings of {n_rooms} rooms read.",
              measured=False, layer="model", method="vision")


def context(plan: dict, claim: dict, scan: dict, p: dict, ev: dict) -> dict:
    return _c(claim, CONTEXT, "high", "Context from the record; a scan cannot date a building or see its frame.",
              method="lookup", layer="costar")


# ---- dispatch -------------------------------------------------------------------------------------------------------

def compare_one(plan: dict, claim: dict, scan: dict, ev: dict, p: dict) -> dict | None:
    k = claim["key"]
    if k in ("living_area", "unit_area", "title_area"):
        return area(plan, claim, scan, p, ev)
    if k in ("gross_area", "rentable_area", "typical_floor_area"):
        if scan["scope"] in ("building",) and k != "typical_floor_area" or scan["scope"] == "floor" and k == "typical_floor_area":
            out = area(plan, claim, scan, p, ev)
            if out["verdict"] != UNVERIFIABLE or not ev.get("site"):
                return out
        return floor_vs_footprint(plan, claim, scan, p, ev)
    if k in ("beds", "unit_beds", "title_beds"):
        return beds(plan, claim, scan, p, ev)
    if k in ("baths", "unit_baths", "title_baths"):
        return baths(plan, claim, scan, p, ev)
    if k == "stories":
        return stories_home(plan, claim, scan, p) if scan["kind"] == "home" else stories_aerial(plan, claim, scan, p, ev)
    if k == "height":
        return height_aerial(plan, claim, scan, p, ev)
    if k in ("ceiling_height", "ceiling_height_main"):
        return ceiling(plan, claim, scan, p)
    if k in ("parking_spaces", "parking_ratio"):
        return parking(plan, claim, scan, p, ev)
    if k == "dock_doors":
        return docks(plan, claim, scan, p, ev)
    if k == "has_sprinklers":
        return sprinklers(plan, claim, scan, p, ev)
    if k in ("year_built", "year_renovated", "construction_material", "drive_in_bays"):
        return context(plan, claim, scan, p, ev)
    if k in FEATURE_OBJECTS:
        return feature(plan, claim, scan, p, ev)
    return None


def compare(plan: dict, scan: dict, claims: list[dict], ev: dict | None = None, params: dict | None = None) -> list[dict]:
    p = {**DEFAULTS, **(params or {})}
    ev = ev or {}
    out = [c for c in (compare_one(plan, cl, scan, ev, p) for cl in claims) if c]
    # the pool is checkable even when a home's listing never mentions one: an unlisted pool is a finding
    if scan["kind"] == "home" and ev.get("site") and not any(c["key"] == "pool" for c in out):
        f = _fact(ev["site"], "pool")
        if f and f["value"]:
            out.append(pool(plan, {"key": "pool", "label": "Private pool", "value": False, "unit": None,
                                   "path": "residential-listing-features.sections[].lines (no pool sentence)",
                                   "origin": "listing", "scope": "home"}, scan, p, ev))
    return out
