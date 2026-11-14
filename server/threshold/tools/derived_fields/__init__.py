"""Derived fields: the record fields a property lacks that the scan and the aerial photo can supply.

Each proposed field has a value, the method behind it, a confidence and its evidence, and says what the record holds
for the same field (nothing, the same, or something else). Shaped as a list a researcher can accept into the record:
one finding and one check per field; numeric fields also appear as metrics (`area.<room type>` is a series).
"""
from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from .. import (
    Check,
    Finding,
    Metric,
    NotApplicable,
    ScanScope,
    Source,
    ToolError,
    ToolResult,
    Verdict,
    field,
    tool,
)
from ..record_vs_reality import claims as cl
from ..record_vs_reality import gather
from ..record_vs_reality import measure as ms
from ..record_vs_reality.compare import TALL_FT

AMENITY_ROOMS = ("Laundry", "Pantry", "Office", "Exercise Room", "Garage", "Patio", "Balcony", "Loft", "Bonus Room",
                 "Game Room", "Den", "Workshop", "Utility Room")
PITCH_M = 2.0  # a pitched roof's ridge sits about this far above the top storey's ceiling
LOWER_BOUND = {"parking_stalls_seen", "dock_doors_seen"}  # counts from above miss things
EXACT = {"bedrooms", "bathrooms", "floors_scanned", "stories_estimate", "garage_stalls", "walk_in_closets"}
AMENITY_OBJECTS = ("fireplace", "kitchen island", "washer", "dryer", "bathtub", "sprinkler head")


class Inputs(BaseModel):
    scan: str = field(source="selection.scan", description="Scan id")
    aerial: bool = field(True, description="Read the aerial facts (roof, height, footprint, pool); cached lookups")
    vision: bool = field(False, pref="truth.deep", description="Also read panoramas and count stalls from above "
                                                               "(uses the shared vision model)")


def _src(layer, method, conf, note=None) -> dict:
    return {"layer": layer, "method": method, "confidence": conf, "note": note}


def propose(plan: dict, rec: dict | None, ev: dict) -> list[dict]:
    """[{field, label, value, unit, method, source, record, anchor, media}] for one scan."""
    out: list[dict] = []
    rc = (rec or {}).get("claims") or {}
    sid = plan["sid"]

    def add(fid, label, value, unit, src, record_key=None, anchor=None, media=(), note=None):
        if value in (None, [], ""):
            return
        out.append({"field": fid, "label": label, "value": value, "unit": unit, "source": src,
                    "record": (rc.get(record_key) or {}).get("value") if record_key else None,
                    "record_path": (rc.get(record_key) or {}).get("path") if record_key else None,
                    "anchor": anchor, "media": list(media), "note": note})

    geo_hi = _src("matterport", "geometry", "high", "Matterport room areas and the wall graph")
    fa = ms.floor_area(plan)
    if fa["available"]:
        add("measured_interior_area", "Measured interior area", round(fa["ft2"]), "ft²", geo_hi,
            "living_area" if "living_area" in rc else "unit_area" if "unit_area_min" in rc else None,
            note=f"{len(fa['counted'])} walled rooms; garages, patios, balconies, basements and voids left out")
        by: dict[str, float] = defaultdict(float)
        for r in fa["counted"]:
            by[r["label"]] += r["m2"]
        for x in fa["excluded"]:
            if x["label"] in ("Garage", "Patio", "Balcony"):
                by[x["label"]] += x["m2"]
        for lab, m2 in sorted(by.items(), key=lambda kv: -kv[1]):
            add(f"area.{lab}", f"Area, {lab.lower()}", round(m2 * ms.M2_FT2), "ft²", geo_hi)
    h = ms.heights(plan)
    if h["available"]:
        src = _src("matterport", "geometry", "high" if h["of_rooms"] >= 3 else "medium",
                   f"{h['of_rooms']} of {h['rooms_total']} rooms have a measured height")
        add("ceiling_height_typical", "Typical ceiling height", round(h["median_m"] * ms.M_FT, 1), "ft", src,
            "ceiling_height_main" if "ceiling_height_main" in rc else None)
        add("ceiling_height_max", "Tallest ceiling", round(h["max_m"] * ms.M_FT, 1), "ft", src,
            "ceiling_height" if (rc.get("ceiling_height") or {}).get("value", 99) <= TALL_FT else None,
            anchor={"sid": sid, "room": h["max_room"]})
    wb = ms.windows_by_room(plan)
    if wb["available"]:
        t = wb["total"]
        src = _src("matterport", "geometry", "high" if t["windows"] else "low",
                   "Openings in the wall graph" + ("" if t["windows"] else "; this scan marks no windows, which "
                                                   "Matterport leaves optional"))
        add("doors", "Doors and openings", t["doors"], "", src)
        if t["windows"]:
            add("windows", "Windows", t["windows"], "", src)
            add("glazed_area", "Glazed area", round(t["glazed_area"] * ms.M2_FT2), "ft²", src)
            add("glazing_ratio", "Glass to floor area", round(100 * (t["glazing_ratio"] or 0)), "%", src)
    b, ba = ms.bedrooms(plan), ms.bathrooms(plan, ev.get("fixtures"))
    lab_src = _src("matterport", "lookup", "medium", "Matterport room labels (by furniture)")
    if b["available"]:
        add("bedrooms", "Bedrooms", b["count"], "", lab_src, "beds" if "beds" in rc else "unit_beds" if "unit_beds" in rc else None,
            anchor={"sid": sid, "room": b["rooms"][0]} if b["rooms"] else None)
    if ba["available"]:
        add("bathrooms", "Bathrooms", ba["count"], "", lab_src, "baths" if "baths" in rc else "unit_baths" if "unit_baths" in rc else None,
            note=f"{ba['full']} full, {ba['half']} half")
    c = ms.closets(plan)
    if c["available"] and c["closets"]:
        add("walk_in_closets", "Walk-in closets", len(c["walk_in"]), "", _src("matterport", "geometry", "high",
            f"Closets of at least {ms.WALK_IN_M2:g} m² with a side of {ms.WALK_IN_SIDE_M:g} m"))
    f = ms.floors(plan)
    if f["available"]:
        add("floors_scanned", "Floors scanned", f["count"], "", _src("matterport", "lookup", "high"),
            "stories" if cl.kind_of(rec) == "home" and "stories" in rc else None)
    amen = sorted({r["label"] for r in plan["rooms"] if r.get("label") in AMENITY_ROOMS})
    if fa["available"]:
        amen += ["Walk-in closet"] if c.get("walk_in") else []
    objs = ev.get("objects") or []
    seen = sorted({o["label"] for o in objs if o["label"] in AMENITY_OBJECTS})
    add("amenities", "Amenities seen", amen + [s.capitalize() for s in seen], None,
        _src("model" if seen else "matterport", "vision" if seen else "lookup", "medium",
             "Room labels" + (" and objects seen in the panoramas" if seen else "")),
        media=[m for o in objs if o["label"] in AMENITY_OBJECTS for m in o["finding"]["media"][:1]][:6])
    g = ms.garage_stalls(plan)
    if g["available"]:
        add("garage_stalls", "Garage stalls", g["stalls"], "", _src("matterport", "geometry", "medium",
            f"Garage floor area over {ms.CAR_STALL_M2:g} m² a car"), anchor={"sid": sid, "room": g["rooms"][0]})
    # the aerial photo
    site = ev.get("site")
    if site:
        facts = {x["id"]: x for x in site["facts"]}
        geo = {"geo": [site["lon"], site["lat"]]}
        media = ev.get("ortho_media") or []
        which = "the structure at the record's point" if site.get("structure") == "at the point" else "the parcel's main structure"

        def fact(fid, label, key, unit=None, conv=lambda v: v, record_key=None):
            x = facts.get(key)
            if x and x["value"] is not None:
                s = dict(x["source"])
                s["note"] = (s.get("note") or "") + f"; {which}"
                add(fid, label, conv(x["value"]), unit, s, record_key, anchor=geo, media=media)

        fact("building_height", "Building height (roof above ground)", "roof_height", "ft", lambda v: round(v * ms.M_FT),
             "height" if "height" in rc else None)
        fact("footprint_area", "Building footprint", "footprint_area", "ft²", lambda v: round(v * ms.M2_FT2))
        fact("roof_material", "Roof material", "roof_material")
        fact("roof_shape", "Roof shape", "roof_shape")
        fact("roof_condition", "Roof condition score", "roof_condition")
        fact("solar", "Solar panels", "solar")
        fact("pool", "Pool", "pool", None, bool)
        fact("pool_area", "Pool area", "pool_area", "ft²", lambda v: round(v * ms.M2_FT2))
        fact("parcel_area", "Parcel area", "parcel_area", "ft²", lambda v: round(v * ms.M2_FT2))
        fact("paved_share", "Paved share of the parcel", "paved_percent", "%")
        if facts.get("roof_height") and cl.kind_of(rec) != "industrial":
            storey = 3.0 if cl.kind_of(rec) in ("home", "apartment") else 4.0
            pitched = (facts.get("roof_shape") or {}).get("value") not in (None, "flat")
            n = max(1, round((facts["roof_height"]["value"] - (PITCH_M if pitched else 0)) / storey))
            add("stories_estimate", "Stories (from roof height)", n, "", _src("vexcel", "geometry", "low",
                f"Roof height{f' less {PITCH_M:g} m for the pitched roof' if pitched else ''} over {storey:g} m a storey"),
                "stories" if "stories" in rc else None, anchor=geo, media=media)
    if ev.get("parking"):
        add("parking_stalls_seen", "Parking stalls seen from above", ev["parking"]["count"], "",
            _src("vexcel", "vision", "low", "Painted stalls on the parcel in the orthophoto; a lower bound"),
            "parking_spaces" if "parking_spaces" in rc else None, anchor={"geo": [site["lon"], site["lat"]]} if site else None,
            media=ev.get("parking_media") or [])
    if ev.get("docks"):
        add("dock_doors_seen", "Dock doors seen from above", ev["docks"]["count"], "",
            _src("vexcel", "vision", "low", "Most seen in one aerial or oblique view; a lower bound"),
            "dock_doors" if "dock_doors" in rc else None, media=ev.get("docks_media") or [])
    return out


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def _agree(p: dict) -> str:
    r = p["record"]
    if r is None:
        return "new"
    a, b = _num(p["value"]), _num(r)
    if p["field"] in LOWER_BOUND and a is not None and b is not None:
        return "differs" if a > b + max(2, 0.15 * b) else "same"
    if p["field"] in EXACT and a is not None and b is not None:
        return "same" if a == b else "differs"
    if a is None or b is None:
        return "same" if str(p["value"]).lower() == str(r).lower() else "differs"
    return "same" if abs(a - b) <= max(0.5, 0.1 * abs(b)) else "differs"


@tool(id="derived_fields", title="Derived fields", icon="list-plus",
      summary="Proposes the record fields this property lacks, measured from the scan and the aerial photo.",
      model_description="For one scan, list the fields its CoStar or listing record lacks that the data can supply: "
                        "area by room type, ceiling heights, door and window counts, glazed area, amenities, parking, "
                        "roof material and condition, building height, footprint, pool. Each with value, method, "
                        "confidence, evidence, and whether the record already has it.",
      personas=["costar_researcher", "insurance_underwriter"],
      requires=[{"layer": "matterport.rooms"}, {"layer": "costar.property", "need": "optional"},
                {"layer": "vexcel.ortho", "need": "optional"}],
      blocks=["VerdictHeader", "MetricRow", "MiniChart", "CheckList", "EvidenceStrip", "StepLog"],
      annotations={"cost": "slow"}, examples=["What could we add to this record?", "What does the scan know that CoStar doesn't?"])
def run(ctx, inputs: Inputs) -> ToolResult:
    plan = ctx.plan(inputs.scan)
    rec = gather.record(inputs.scan)
    scan = cl.scan_scope(plan, rec)
    claims = cl.from_record(plan, rec)
    ev = gather.gather(plan, rec, scan, claims, aerial_on=inputs.aerial, panos_on=inputs.vision) if (inputs.aerial or inputs.vision) else {}
    props = propose(plan, rec, ev)
    if not props:
        raise NotApplicable(f"Scan {inputs.scan} has no rooms and no location, so nothing can be derived.")
    ctx.step(f"Derived {len(props)} fields from the plan" + (" and the aerial photo" if ev.get("site") else ""))
    sid = inputs.scan
    checks, findings, metrics = [], [], []
    for p in props:
        state = _agree(p)
        fid = f"derived_fields:{sid}:{p['field']}"
        src = Source(**p["source"])
        shown = ", ".join(p["value"]) if isinstance(p["value"], list) else (
            ("yes" if p["value"] else "no") if isinstance(p["value"], bool) else f"{p['value']:,}" if isinstance(p["value"], (int, float)) else p["value"])
        rec_txt = {"new": "The record has no value for this.",
               "same": f"The record agrees ({p['record']})." if p["field"] not in LOWER_BOUND else
               f"The record says {p['record']}; a count from above is a lower bound, so it does not dispute that.",
                   "differs": f"The record says {p['record']} ({p['record_path']})."}[state]
        findings.append(Finding(id=fid, title=f"{'Proposed' if state == 'new' else 'Measured'}: {p['label']}",
                                status="warn" if state == "differs" else "pass",
                                detail=f"{shown}{' ' + p['unit'] if p['unit'] else ''}. {p['note'] + '. ' if p['note'] else ''}"
                                       f"{rec_txt}", anchor=p["anchor"], source=src, media=p["media"]))
        checks.append(Check(id=p["field"], rule=p["label"], measured=_num(p["value"]), threshold=_num(p["record"]),
                            unit=p["unit"] or "", status="warn" if state == "differs" else "pass",
                            standard=p["record_path"], findings=[fid], kind="claim"))
        if _num(p["value"]) is not None and not isinstance(p["value"], bool):
            metrics.append(Metric(id=p["field"], label=p["label"], value=_num(p["value"]), unit=p["unit"] or "", source=src))
    new = sum(1 for p in props if _agree(p) == "new")
    differs = [p["label"].lower() for p in props if _agree(p) == "differs"]
    text = f"{new} fields the record lacks, {len(props) - new} it already has." + (
        f" The record disagrees on {', '.join(differs[:3])}." if differs else "")
    head = [m for m in metrics if "." not in m.id]
    return ToolResult(scope=ScanScope(sid=sid), verdict=Verdict(status="warn" if differs else "pass", text=text),
                      metrics=head[:4] + [m for m in metrics if "." in m.id] + head[4:], checks=checks, findings=findings)
