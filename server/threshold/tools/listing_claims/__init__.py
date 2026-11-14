"""Listing claims: the renter's check. Every claim in a listing's text and record, checked against the scan, plus what
the listing leaves out that the scan shows (a bedroom with no window, a bathroom reached only through a bedroom,
bedrooms with no closet, a low ceiling).

Paste a listing's text, or leave it empty to use the scan's own listing (its remarks and feature sentences).
"""
from __future__ import annotations

import datetime as dt
import re
import statistics

from pydantic import BaseModel

from ... import geometry
from ...geometry.graph import neighbours
from .. import (
    Action,
    Assumption,
    Check,
    Finding,
    RoomAnchor,
    Source,
    ToolError,
    ToolResult,
    field,
    tool,
)
from ..daylight import per_room
from ..record_vs_reality import audit, gather, result
from ..record_vs_reality import claims as cl
from ..record_vs_reality import compare as cmp
from ..record_vs_reality import measure as ms

HIGH_CEILING_M = 2.74   # 9 ft: what "high ceilings" has to beat
LOW_CEILING_M = 2.29    # 7.5 ft: lower than this in a living space is worth saying
CODE_CEILING_M = 2.13   # 7 ft: the usual minimum for a habitable room (IRC R305)
LIVING = {"Bedroom", "Living Room", "Family Room", "Dining Room", "Kitchen", "Office", "Den", "Loft", "Bonus Room"}
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "single": 1}
CARDINAL = {"north": 0, "east": 90, "south": 180, "west": 270}
GEOM = Source(layer="matterport", method="geometry", confidence="high", note="Wall graph and room labels")
FAMILY = {"beds": "beds", "unit_beds": "beds", "title_beds": "beds", "baths": "baths", "unit_baths": "baths",
          "title_baths": "baths", "area": "area", "living_area": "area", "unit_area": "area", "title_area": "area"}
TEXT_ONLY = {"high_ceilings", "ceiling_ft", "natural_light", "facing"}


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    text: str | None = field(None, ask="Paste the listing text, or leave it empty to use this scan's own listing.",
                             description="Listing text to check; empty uses the scan's own listing", max_length=20000)
    deep: bool = field(False, pref="truth.deep", description="Also read the aerial photo and the panoramas")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+|•", text) if s.strip()]


def parse(text: str) -> list[dict]:
    """Claims stated in free listing text, each with the sentence it came from."""
    out: dict[str, dict] = {}

    def put(key, label, value, unit, sentence):
        if key not in out:
            out[key] = {"key": key, "label": label, "value": value, "unit": unit, "origin": "listing text",
                        "path": f"listing text: \"{sentence[:160]}\"", "scope": "scan"}

    for s in _sentences(text):
        if m := re.search(r"\b(\d+)\s*(?:-\s*)?(?:bed(?:room)?s?|bd|br)\b", s, re.IGNORECASE):
            put("beds", "Bedrooms", int(m.group(1)), None, s)
        elif re.search(r"\bstudio\b", s, re.IGNORECASE):
            put("beds", "Bedrooms", 0, None, s)
        if m := re.search(r"\b(\d+(?:\.\d)?)\s*(?:-\s*)?(?:bath(?:room)?s?|ba)\b", s, re.IGNORECASE):
            put("baths", "Bathrooms", float(m.group(1)), None, s)
        if m := re.search(r"\b(\d{1,3}(?:,\d{3})+|\d{3,6})\s*(?:\+\s*)?(?:sq\.?\s*ft\.?|square\s*feet|sf|sqft)\b", s, re.IGNORECASE):
            put("area", "Area", int(m.group(1).replace(",", "")), "ft2", s)
        if m := re.search(r"\b(\d|one|two|three|four|single)[- ]stor(?:y|ies)\b", s, re.IGNORECASE):
            put("stories", "Stories", WORDS.get(m.group(1).lower()) or int(m.group(1)), None, s)
        if m := re.search(r"\b(\d{1,2})\s*(?:'|’|ft\.?|foot|feet)\s*(?:-\s*)?(?:high\s+)?ceilings?", s, re.IGNORECASE):
            put("ceiling_ft", "Ceiling height", int(m.group(1)), "ft", s)
        elif re.search(r"\b(?:high|tall|soaring|vaulted|lofty|cathedral)\s+ceilings?", s, re.IGNORECASE):
            put("high_ceilings", "High ceilings", True, None, s)
        if re.search(r"natural light|sun-?drenched|sun-?lit|light-?filled|\bbright\b|abundant light|lots of light|"
                     r"flooded with light", s, re.IGNORECASE):
            put("natural_light", "Plenty of natural light", True, None, s)
        if m := re.search(r"\b(north|south|east|west)(?:ern)?[- ](?:facing|exposure)", s, re.IGNORECASE):
            put("facing", "Facing", m.group(1).lower(), None, s)
        if m := re.search(r"\b(\d+)\s*(?:-\s*)?(?:car garage|parking spaces?|parking spots?|covered (?:parking )?spaces?)",
                          s, re.IGNORECASE):
            put("parking_spaces", "Parking spaces", int(m.group(1)), None, s)
        for key, (lab, yes, no) in cl.FEATURES.items():
            if yes.search(s) and not (no and no.search(s)):
                put(key, lab, True, None, s)
    return list(out.values())


# ---- the claims only free text makes --------------------------------------------------------------------------

def _ceiling(plan: dict, c: dict) -> dict:
    h = ms.heights(plan)
    if not h["available"]:
        return cmp._c(c, cmp.UNVERIFIABLE, "high", h["reason"])
    labels = {r["id"]: r.get("label") for r in plan["rooms"]}
    living = [v for rid, v in h["rooms"].items() if labels.get(rid) in LIVING]
    m = statistics.median(living or list(h["rooms"].values()))
    ft = m * ms.M_FT
    conf = "high" if len(living) >= 2 else "medium"
    head = f"The living rooms' median ceiling is {ft:.1f} ft ({m:.2f} m)."
    if c["key"] == "high_ceilings":
        return cmp._c(c, cmp.CONFIRMED if m >= HIGH_CEILING_M else cmp.CONTRADICTED, conf,
                      head + " 'High' should beat 9 ft.", measured=round(ft, 1), unit="ft")
    return cmp._c(c, cmp.CONFIRMED if abs(ft - c["value"]) <= 0.75 else cmp.CONTRADICTED, conf, head,
                  measured=round(ft, 1), unit="ft")


def _light(plan: dict, c: dict, day: dt.date) -> dict:
    d = per_room(plan, day)
    if not d["available"]:
        return cmp._c(c, cmp.UNVERIFIABLE, "high", d["reason"])
    t = d["total"]
    ratio = t["glazing_ratio"] or 0
    head = (f"Glass is {ratio:.0%} of the floor area ({t['glazed_area']:.1f} m² of window over {t['floor_area']:.0f} m²); "
            "building codes ask for 8% in living rooms. ")
    pct = {"measured": round(100 * ratio), "unit": "%"}
    if ratio >= 0.10:
        return cmp._c(c, cmp.CONFIRMED, "medium", head, **pct)
    if ratio < 0.05:
        return cmp._c(c, cmp.CONTRADICTED, "medium", head + "This is a dim place unless windows went unmarked.", **pct)
    return cmp._c(c, cmp.CONFIRMED, "low", head + "That is ordinary, not especially bright.", **pct)


def _facing(plan: dict, c: dict) -> dict:
    f = geometry.facing(plan)
    if not f["available"]:
        return cmp._c(c, cmp.UNVERIFIABLE, "high", f["reason"])
    wins = [o for o in f["openings"] if o["type"] == "window" and o.get("width")]
    if not wins:
        return cmp._c(c, cmp.UNVERIFIABLE, "high", "This scan records no outside window.")
    want = CARDINAL[c["value"]]
    glass = sum((o["width"] or 0) * (o["height"] or 0) for o in wins)
    toward = sum((o["width"] or 0) * (o["height"] or 0) for o in wins
                 if abs((o["azimuth_deg"] - want + 180) % 360 - 180) <= 45)
    share = toward / glass if glass else 0
    sure = f.get("verified") and (plan.get("quality") or {}).get("georef")
    iff = "" if sure else "If the scan's compass rotation is right, "
    return cmp._c(c, cmp.CONFIRMED if share >= 0.3 else cmp.CONTRADICTED, "medium" if sure else "low",
                  f"{iff}{share:.0%} of the window glass faces {c['value']} (within 45 degrees).",
                  measured=round(100 * share), unit="%", method="simulation")


# ---- what the listing does not say ----------------------------------------------------------------------------

def unsaid(plan: dict) -> list[dict]:
    """Facts a renter would want that listings leave out, each {key, title, status, detail, room, confidence}."""
    out = []
    labels = {r["id"]: r.get("label") for r in plan["rooms"]}
    beds = [r for r in plan["rooms"] if r.get("label") == "Bedroom" and (r.get("area") or 0) >= ms.BEDROOM_MIN_M2]
    wb = ms.windows_by_room(plan)
    if wb["available"] and wb["total"]["windows"]:
        for r in beds:
            if not wb["rooms"].get(r["id"], {}).get("windows"):
                out.append({"key": f"windowless:{r['id']}", "title": "A bedroom has no window", "status": "warn",
                            "room": r["id"], "confidence": "medium",
                            "detail": f"This bedroom ({r.get('area') or 0:.1f} m²) has no window in the wall graph, which "
                                      "marks windows elsewhere in the scan. A bedroom usually needs a window to count "
                                      "as one (an egress opening)."})
    g = geometry.room_graph(plan)
    if g["available"] and beds:
        adj = neighbours(g)
        baths = [r for r in plan["rooms"] if r.get("label") == "Bathroom" and adj.get(r["id"])]
        via_bed = [b for b in baths
                   if {labels.get(n) for n, _ in adj[b["id"]] if labels.get(n) not in ("Bathroom", "Closet")} == {"Bedroom"}]
        if via_bed and len(via_bed) == len(baths) and len(beds) > 1:
            out.append({"key": f"through_bedroom:{via_bed[0]['id']}", "title": "A bathroom is reached only through a bedroom",
                        "status": "warn", "room": via_bed[0]["id"], "confidence": "medium",
                        "detail": "Every bathroom opens only off a bedroom, so anyone in the other bedrooms walks "
                                  "through someone's room to reach one."})
        bare = [r for r in beds if "Closet" not in {labels.get(n) for n, _ in adj.get(r["id"], [])}]
        if bare and ms.labels_ok(plan):
            n = len(bare)
            out.append({"key": f"no_closet:{bare[0]['id']}", "title": f"{n} bedroom{'s have' if n != 1 else ' has'} no closet",
                        "status": "warn", "room": bare[0]["id"], "confidence": "low",
                        "detail": f"No closet room opens off {n} of the {len(beds)} bedrooms. A shallow reach-in closet "
                                  "may be drawn as part of its bedroom, so check the panoramas."})
    h = ms.heights(plan)
    if h["available"]:
        for rid, v in h["rooms"].items():
            if labels.get(rid) in LIVING and v < LOW_CEILING_M:
                out.append({"key": f"low_ceiling:{rid}", "title": f"Low ceiling in the {labels[rid].lower()}",
                            "status": "fail" if v < CODE_CEILING_M else "warn", "room": rid, "confidence": "high",
                            "detail": f"The ceiling is {v * ms.M_FT:.1f} ft ({v:.2f} m)"
                                      + (", under the usual 7 ft minimum for a living space." if v < CODE_CEILING_M
                                         else ", under 7.5 ft.")})
    return out


@tool(id="listing_claims", title="Listing claims", icon="clipboard-check",
      summary="Checks what a listing says against the scan, and lists what it leaves out.",
      model_description="For one scan and a listing (pasted text, or the scan's own listing when text is empty): "
                        "extracts each claim (bedrooms, bathrooms, area, stories, ceilings, light, facing, parking, "
                        "fireplace, island, walk-in closet, hardwood, laundry, garage, pool), checks it against the "
                        "scan and aerial photo, and adds what the listing does not say: bedrooms with no window, "
                        "bathrooms reached only through a bedroom, bedrooms with no closet, low ceilings.",
      personas=["renter_listing"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "matterport.openings", "need": "optional"},
                {"layer": "costar.listing", "need": "optional", "fallback": "pasted listing text"}],
      blocks=["VerdictHeader", "MetricRow", "CheckList", "EvidenceStrip", "FloorPlanMini", "AssumptionChips", "StepLog",
              "ActionBar"],
      overlays=["rule", "pins"], examples=["Is this listing honest?", "What does the listing not tell me?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    rec = gather.record(inputs.scan)
    text = inputs.text or ((rec or {}).get("residential_listing") or {}).get("remarks") or ""
    said = parse(text) if text else []
    ctx.step(f"Read {len(said)} claims from the {'pasted' if inputs.text else 'listing'} text" if text
             else "No listing text; using the record only")
    base = None if inputs.text else rec  # a pasted listing replaces the record's claims; the scan title's stay
    on_record = {(FAMILY.get(c["key"], c["key"]), str(c["value"])) for c in cl.from_record(plan, base)}
    mapped = [{**c, "key": {"area": "title_area", "beds": "title_beds", "baths": "title_baths"}.get(c["key"], c["key"]),
               "scope": "scan" if c["key"] in ("area", "beds", "baths") else "home"}
              for c in said if c["key"] not in TEXT_ONLY and (FAMILY.get(c["key"], c["key"]), str(c["value"])) not in on_record]
    a = audit(plan, base, deep=inputs.deep, extra_claims=mapped, step=ctx.step)
    comps = a["comparisons"]
    for c in comps:  # free-text claims keep their plain labels
        if c["claim"]["origin"] == "listing text":
            c["label"] = c["label"].replace(" in the scan title", "")
    for c in said:
        if c["key"] in ("high_ceilings", "ceiling_ft"):
            comps.append(_ceiling(plan, c))
        elif c["key"] == "natural_light":
            comps.append(_light(plan, c, dt.date.today()))
        elif c["key"] == "facing":
            comps.append(_facing(plan, c))
    if not comps:
        raise ToolError("Nothing to check: paste the listing text, or pick a scan that has a listing.")
    ctx.step(f"Checked {len(comps)} claims")
    extra = unsaid(plan)
    n_extra = sum(1 for x in extra if x["status"] != "pass")
    ctx.step(f"Found {n_extra} thing{'s' if n_extra != 1 else ''} the listing does not say")
    scan = a["scan"] if base is not None or not rec else cl.scan_scope(plan, rec)
    res = result.build("listing_claims", inputs.scan, comps, scan, a["area_ft2"], [
        Assumption(id="truth.area_low", label="Interior area may be this share of a listed area",
                   value=cmp.DEFAULTS["area_low"], editable=True),
        Assumption(id="high_ceiling", label="'High ceilings' means over this", value=HIGH_CEILING_M, unit="m")],
        [Action(id="daylight", label="See daylight room by room", tool="daylight", inputs={"scan": inputs.scan})])
    for x in extra:
        fid = f"listing_claims:{inputs.scan}:{x['key']}"
        res.findings.append(Finding(id=fid, title=f"Not in the listing: {x['title'][0].lower()}{x['title'][1:]}",
                                    status=x["status"], detail=x["detail"], anchor=RoomAnchor(sid=inputs.scan, room=x["room"]),
                                    source=GEOM.model_copy(update={"confidence": x["confidence"]})))
        res.checks.append(Check(id=x["key"], rule=x["title"], measured=None, threshold=None, unit="", status=x["status"],
                                findings=[fid]))
    if n_extra:
        res.verdict.text += f" The listing does not mention {n_extra} thing{'s' if n_extra != 1 else ''} the scan shows."
        if res.verdict.status in ("pass", "unknown"):
            res.verdict.status = "warn"
    return res
